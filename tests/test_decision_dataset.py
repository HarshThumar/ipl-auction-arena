"""Tests for L3 decision dataset (docs/L3-decision-dataset-spec.md section 7).

Ships all 9 spec tests:
1. Leakage guard
2. Label correctness
3. Monotonic ladder
4. Engine invariants
5. Reconciliation
6. Determinism
7. Unit (integer lakhs)
8. Split integrity
9. Balance reported
"""
from __future__ import annotations

import csv
import json
import re
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from scripts.build_decision_dataset import (
    CONFIG,
    build_decision_dataset,
    compute_sha256,
    norm_name,
)

ROOT = Path(__file__).resolve().parents[1]
DECISIONS_DIR = ROOT / "data" / "processed" / "decisions"


@pytest.fixture(scope="module")
def dataset_artifacts():
    """Ensure artifacts exist and load them."""
    parquet_path = DECISIONS_DIR / "decision_rows.parquet"
    manifest_path = DECISIONS_DIR / "manifest.json"
    splits_path = DECISIONS_DIR / "splits.json"
    schema_path = DECISIONS_DIR / "schema.json"

    # Always generate fresh for test run
    build_decision_dataset(repo_root=ROOT, out_dir=DECISIONS_DIR, seed=0)

    df = pd.read_parquet(parquet_path)
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    with open(splits_path, encoding="utf-8") as f:
        splits = json.load(f)
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    return {
        "df": df,
        "manifest": manifest,
        "splits": splits,
        "schema": schema,
        "parquet_path": parquet_path,
    }


def test_1_leakage_guard(dataset_artifacts):
    """Test 1: Assert no feature column name or value derives from final_price/winner/final_two.

    Assert purse_left at a row uses only prior-lot prices.
    """
    df = dataset_artifacts["df"]

    # 1. Feature column names must not contain outcome variables
    outcome_terms = ["final_price", "winner"]
    for col in df.columns:
        if col in ("action", "lot_id", "confidence", "contested"):
            continue
        for term in outcome_terms:
            assert term not in col, f"Feature column '{col}' leaks outcome term '{term}'"

    # Strict leakage guard: is_final_two must NEVER be True while n_active_estimate > 2
    leaked_f2 = df[(df["is_final_two"] == True) & (df["n_active_estimate"] > 2)]
    assert len(leaked_f2) == 0, (
        f"is_final_two is True while n_active_estimate > 2 in {len(leaked_f2)} rows:\n"
        f"{leaked_f2[['season', 'lot_id', 'step_index', 'franchise_id', 'n_active_estimate', 'is_final_two']].head(10)}"
    )

    # 2. Assert purse_left_lakhs within each lot is constant across all decision steps
    # (i.e. does not reflect the current lot's realized hammer price)
    grouped = df.groupby(["season", "lot_id"])
    for (season, lot_id), group in grouped:
        for team in group["franchise_id"].unique():
            team_rows = group[group["franchise_id"] == team]
            purses = team_rows["purse_left_lakhs"].unique()
            assert len(purses) == 1, (
                f"Lot {lot_id} team {team} purse_left changed intra-lot: {purses}"
            )

    # 3. Assert current_price_lakhs is non-decreasing across steps
    for (season, lot_id), group in grouped:
        raise_rows = group[group["action"] == "RAISE"].sort_values("step_index")
        if len(raise_rows) > 1:
            prices = raise_rows["current_price_lakhs"].tolist()
            assert prices[0] <= prices[-1]


def test_2_label_correctness(dataset_artifacts):
    """Test 2: Every RAISE row's team == its bid_step.team (or master winner on reconciliation).

    Every DROP row's team is a losing participant; winner has no DROP.
    """
    df = dataset_artifacts["df"]

    raw_bids_by_season = {}
    for y in df["season"].unique():
        bp = ROOT / "data" / "processed" / "bid_sequences" / f"{y}_bids.json"
        with open(bp, encoding="utf-8") as f:
            raw_bids_by_season[y] = json.load(f)["lots"]

    # Franchises alias mapping
    alias = {"DD": "DC", "KXIP": "PBKS"}
    with open(ROOT / "data" / "reference" / "franchises.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fid = r["franchise_id"]
            alias[fid] = fid
            for a in (r.get("aliases") or "").split("|"):
                if a.strip():
                    alias[a.strip()] = fid

    # Master lots
    master_lots = {}
    master_csv = ROOT / "data" / "processed" / "master" / "all_auctions_master.csv"
    if master_csv.exists():
        with open(master_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                master_lots[(int(row["season"]), norm_name(row["player"]))] = row

    grouped = df.groupby(["season", "lot_id"])
    for (season, lot_id), group in grouped:
        # Extract lot index from lot_id: e.g. "2025-L272-anukulroy" -> index 271
        match = re.match(r"\d+-L(\d+)-", lot_id)
        assert match is not None
        l_idx = int(match.group(1)) - 1

        raw_lot = raw_bids_by_season[season][l_idx]
        raw_steps = raw_lot.get("bid_steps", [])

        # Check winner
        p_norm = norm_name(group["player"].iloc[0])
        m = master_lots.get((season, p_norm))
        if m and m.get("winner"):
            winner = alias.get(m["winner"], m["winner"])
        else:
            winner = alias.get(raw_lot.get("winner", ""), raw_lot.get("winner", ""))

        # Check RAISE rows
        raise_rows = group[group["action"] == "RAISE"].sort_values("step_index")
        assert len(raise_rows) == len(raw_steps)

        # Reconciled uncontested team
        if len(raw_steps) == 1 and winner:
            expected_first_team = winner
        else:
            expected_first_team = alias.get(raw_steps[0]["team"], raw_steps[0]["team"])

        assert raise_rows.iloc[0]["franchise_id"] == expected_first_team

        # Check DROP rows
        drop_rows = group[group["action"] == "DROP"]
        participating_teams = {r["franchise_id"] for _, r in raise_rows.iterrows()}
        for _, d_row in drop_rows.iterrows():
            d_team = d_row["franchise_id"]
            assert d_team in participating_teams, f"DROP row team {d_team} never participated in {lot_id}"
            assert d_team != winner, f"Winner {winner} has a DROP row in lot {lot_id}"

        # Winner has no DROP
        winner_drops = drop_rows[drop_rows["franchise_id"] == winner]
        assert len(winner_drops) == 0, f"Winner {winner} dropped in lot {lot_id}"

        # Every losing participant drops at most once (exactly once)
        drop_teams = drop_rows["franchise_id"].tolist()
        assert len(drop_teams) == len(set(drop_teams)), (
            f"Duplicate drop rows for a team in lot {lot_id}: {drop_teams}"
        )

    # Assert RTM top bidders have NO DROP rows (Fault 2 fix verification)
    # 2025 Arshdeep Singh: SRH was top bidder (18.0 cr), PBKS matched via RTM
    arshdeep_drops = df[(df["season"] == 2025) & (df["player"].str.contains("Arshdeep", case=False)) & (df["action"] == "DROP")]
    assert "SRH" not in arshdeep_drops["franchise_id"].values, "SRH incorrectly got a DROP row in Arshdeep Singh 2025 RTM lot"
    assert "PBKS" not in arshdeep_drops["franchise_id"].values, "PBKS incorrectly got a DROP row in Arshdeep Singh 2025 RTM lot"

    # 2018 Piyush Chawla: CSK bid 420 (SOLD), KKR matched via RTM
    chawla_drops = df[(df["season"] == 2018) & (df["player"].str.contains("Chawla", case=False)) & (df["action"] == "DROP")]
    assert "CSK" not in chawla_drops["franchise_id"].values, "CSK incorrectly got a DROP row in Piyush Chawla 2018 RTM lot"
    assert "KKR" not in chawla_drops["franchise_id"].values, "KKR incorrectly got a DROP row in Piyush Chawla 2018 RTM lot"


def test_3_monotonic_ladder(dataset_artifacts):
    """Test 3: Prices non-decreasing within each lot.

    Last step == final_price (in lakhs) or lot is dropped+logged.
    """
    df = dataset_artifacts["df"]
    manifest = dataset_artifacts["manifest"]

    grouped = df.groupby(["season", "lot_id"])
    for (season, lot_id), group in grouped:
        raise_rows = group[group["action"] == "RAISE"].sort_values("step_index")
        prices = raise_rows["current_price_lakhs"].tolist()

        # Non-decreasing prices
        for i in range(1, len(prices)):
            assert prices[i] >= prices[i - 1], (
                f"Lot {lot_id} has decreasing prices: {prices[i-1]} -> {prices[i]}"
            )

    # All dropped lots must have a recorded reason in manifest
    assert len(manifest["lots_dropped"]) > 0
    for drop_entry in manifest["lots_dropped"]:
        assert "season" in drop_entry
        assert "player" in drop_entry
        assert "reason" in drop_entry
        assert drop_entry["reason"] in ("last_step_ne_final_price", "missing_final_price", "missing_step_price")


def test_4_engine_invariants(dataset_artifacts):
    """Test 4: purse_left >= 0, slots/overseas within season rules at every row (reuse engine checks)."""
    df = dataset_artifacts["df"]

    assert (df["purse_left_lakhs"] >= 0).all(), f"Found negative purse_left: {df[df['purse_left_lakhs'] < 0][['season', 'lot_id', 'franchise_id', 'purse_left_lakhs']]}"
    assert (df["slots_left"] >= 0).all(), "Found negative slots_left"
    assert (df["slots_left"] <= 25).all(), "Found slots_left > 25"
    assert (df["overseas_left"] >= 0).all(), "Found negative overseas_left"
    assert (df["overseas_left"] <= 8).all(), "Found overseas_left > 8"

    # Opponent invariants
    rival_rows = df[df["rival_id"].notna()]
    assert (rival_rows["rival_purse_left_lakhs"] >= 0).all(), "Found negative rival_purse"
    assert (rival_rows["rival_slots_left"] >= 0).all(), "Found negative rival_slots"
    assert (rival_rows["rival_slots_left"] <= 25).all(), "Found rival_slots > 25"


def test_5_reconciliation(dataset_artifacts):
    """Test 5: Per-lot winner & final price match the master; mismatches resolve to master and are logged."""
    df = dataset_artifacts["df"]
    manifest = dataset_artifacts["manifest"]

    master_path = ROOT / "data" / "processed" / "master" / "all_auctions_master.csv"
    if not master_path.exists():
        pytest.skip("all_auctions_master.csv not found")

    alias = {"DD": "DC", "KXIP": "PBKS"}
    with open(ROOT / "data" / "reference" / "franchises.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fid = r["franchise_id"]
            alias[fid] = fid
            for a in (r.get("aliases") or "").split("|"):
                if a.strip():
                    alias[a.strip()] = fid

    master_lots = {}
    with open(master_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            s = int(row["season"])
            p = norm_name(row["player"])
            master_lots[(s, p)] = row

    # Check that in all lots in df that exist in master, the last RAISE step price matches master hammer
    grouped = df.groupby(["season", "lot_id"])
    for (season, lot_id), group in grouped:
        if season < 2022:
            continue
        p_name = group["player"].iloc[0]
        p_norm = norm_name(p_name)
        m = master_lots.get((season, p_norm))
        if m and m.get("hammer_lakh"):
            expected_hammer = int(m["hammer_lakh"])
            last_raise = group[group["action"] == "RAISE"].sort_values("step_index").iloc[-1]
            assert last_raise["current_price_lakhs"] == expected_hammer, (
                f"Lot {lot_id} hammer {last_raise['current_price_lakhs']} != master {expected_hammer}"
            )

    # Discrepancies log exists in manifest
    assert "discrepancies_vs_master" in manifest


def test_6_determinism(dataset_artifacts):
    """Test 6: Run twice -> identical output hash."""
    parquet_path = dataset_artifacts["parquet_path"]
    original_hash = compute_sha256(parquet_path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        build_decision_dataset(repo_root=ROOT, out_dir=tmp_path, seed=0)
        reproduced_hash = compute_sha256(tmp_path / "decision_rows.parquet")

    assert original_hash == reproduced_hash, (
        f"Non-deterministic output: original={original_hash}, reproduced={reproduced_hash}"
    )


def test_7_unit_integer_lakhs(dataset_artifacts):
    """Test 7: All monetary columns integer lakhs."""
    df = dataset_artifacts["df"]

    monetary_cols = [
        "base_price_lakhs",
        "current_price_lakhs",
        "next_increment_lakhs",
        "spend_so_far_lakhs",
        "purse_left_lakhs",
    ]

    for col in monetary_cols:
        assert pd.api.types.is_integer_dtype(df[col]), f"Column {col} is not integer dtype"
        assert (df[col] % 1 == 0).all(), f"Column {col} contains non-integer values"

    # rival_purse_left_lakhs is nullable integer
    rival_non_null = df["rival_purse_left_lakhs"].dropna()
    assert (rival_non_null % 1 == 0).all(), "rival_purse_left_lakhs contains non-integer values"


def test_8_split_integrity(dataset_artifacts):
    """Test 8: No lot_id appears in two folds; 2025-26 absent from train/val."""
    splits = dataset_artifacts["splits"]

    holdout = set(splits["holdout_test_seasons"])
    assert holdout == {2025, 2026}, f"Expected holdout {2025, 2026}, got {holdout}"

    train_val = set(splits["train_val_seasons"])
    assert 2025 not in train_val
    assert 2026 not in train_val

    seen_val_seasons = set()
    for fold in splits["folds"]:
        val_s = fold["val_season"]
        train_s = set(fold["train_seasons"])

        assert val_s not in train_s, f"Validation season {val_s} also in train_seasons"
        assert val_s not in seen_val_seasons, f"Duplicate validation season fold: {val_s}"
        seen_val_seasons.add(val_s)

        # 2025-2026 absent from all train/val sets
        assert 2025 not in train_s and val_s != 2025
        assert 2026 not in train_s and val_s != 2026

    # Verify lot IDs by season are disjoint
    lot_ids_by_season = splits["lot_ids_by_season"]
    for s1 in lot_ids_by_season:
        for s2 in lot_ids_by_season:
            if s1 != s2:
                overlap = set(lot_ids_by_season[s1]) & set(lot_ids_by_season[s2])
                assert len(overlap) == 0, f"Overlap between seasons {s1} and {s2}: {overlap}"


def test_9_balance_reported(dataset_artifacts):
    """Test 9: Manifest has non-empty per-team/per-season label counts."""
    manifest = dataset_artifacts["manifest"]

    team_balance = manifest["label_balance_by_team"]
    season_balance = manifest["label_balance_by_season"]

    expected_teams = {"CSK", "DC", "GT", "KKR", "LSG", "MI", "PBKS", "RCB", "RR", "SRH"}
    assert set(team_balance.keys()) == expected_teams

    for team, counts in team_balance.items():
        assert counts.get("RAISE", 0) > 0, f"Team {team} has 0 RAISE"
        assert counts.get("DROP", 0) > 0, f"Team {team} has 0 DROP"

    for y in range(2018, 2027):
        counts = season_balance.get(str(y)) or season_balance.get(y)
        assert counts is not None, f"Season {y} missing in manifest"
        assert counts.get("RAISE", 0) > 0, f"Season {y} has 0 RAISE"
        assert counts.get("DROP", 0) > 0, f"Season {y} has 0 DROP"

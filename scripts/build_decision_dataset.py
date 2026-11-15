"""Build L3 Decision Dataset for IPL Auction Arena.

Converts reconstructed bid trails (2018-2026) into canonical decision rows
{state -> RAISE | DROP} computed strictly as-of each decision.
Reuses src/engine/ledger.py for cross-lot accounting.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from src.engine.ledger import Player, Team, Treasurer, teams_from_state
from src.engine.season_rules import Ladder, SeasonRules, load_season

# Config block at top of script
CONFIG = {
    "repo_root": Path(__file__).resolve().parents[1],
    "data_dir": Path(__file__).resolve().parents[1] / "data",
    "out_dir": Path(__file__).resolve().parents[1] / "data" / "processed" / "decisions",
    "seed": 0,
    "holdout_seasons": [2025, 2026],
    "train_val_seasons": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
    "all_seasons": list(range(2018, 2027)),
    "unit": "lakhs",
}

TARGET_ROLES = {
    "batter": 6,
    "bowler": 8,
    "all-rounder": 5,
    "wicketkeeper": 2,
}

V1_FEATURE_COLUMNS = [
    # Identifiers
    "season",
    "lot_id",
    "player",
    "set_no",
    "step_index",
    "confidence",
    "contested",
    # Label
    "action",
    # Identity
    "franchise_id",
    "era",
    # Lot / player basics
    "role",
    "is_overseas",
    "capped",
    "base_price_lakhs",
    # v2 placeholders (declared null in v1)
    "age",
    "age_isnull",
    "powerplay_sr",
    "powerplay_sr_isnull",
    "death_economy",
    "death_economy_isnull",
    "vs_spin_sr",
    "vs_spin_sr_isnull",
    "vs_pace_sr",
    "vs_pace_sr_isnull",
    "home_ground_fit",
    "home_ground_fit_isnull",
    "impact_player_era",
    "impact_player_era_isnull",
    # Auction state as-of
    "current_price_lakhs",
    "next_increment_lakhs",
    "lots_done",
    "spend_so_far_lakhs",
    "spend_pace_vs_expected",
    # Deciding team state
    "purse_left_lakhs",
    "slots_left",
    "overseas_left",
    "role_gap",
    "is_final_two",
    # Opponent state
    "rival_id",
    "rival_purse_left_lakhs",
    "rival_slots_left",
    "rival_role_gap",
    "n_active_estimate",
    # Pool scarcity
    "same_role_remaining",
    "same_role_avg_base",
]


def norm_name(s: str) -> str:
    """Normalize string for lookup: lowercase alphanumeric only."""
    import re

    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def norm_role(r: str) -> str:
    """Normalize role string to canonical 4 roles."""
    cleaned = (r or "").lower().strip()
    if cleaned in ("batter", "batsman"):
        return "batter"
    if cleaned in ("bowler",):
        return "bowler"
    if cleaned in ("all-rounder", "allrounder"):
        return "all-rounder"
    if cleaned in ("wicketkeeper", "wk-batter", "wicket keeper", "wicket-keeper"):
        return "wicketkeeper"
    return "all-rounder"


def get_era(season: int) -> str:
    """Return the rule-era bucket."""
    if season <= 2021:
        return "2018-21"
    if season <= 2024:
        return "2022-24"
    return "2025+"


def load_franchise_alias_map(repo_root: Path) -> Dict[str, str]:
    """Load franchise code alias mapping from franchises.csv."""
    path = repo_root / "data" / "reference" / "franchises.csv"
    alias_map: Dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fid = row["franchise_id"]
            alias_map[fid] = fid
            aliases = row.get("aliases") or ""
            for a in aliases.split("|"):
                if a.strip():
                    alias_map[a.strip()] = fid
    alias_map["DD"] = "DC"
    alias_map["KXIP"] = "PBKS"
    return alias_map


def load_rules(season: int, repo_root: Path) -> SeasonRules:
    """Load or synthesize SeasonRules for the given season."""
    if season >= 2022:
        return load_season(season)

    path = repo_root / "data" / "reference" / "rules_by_season.yaml"
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)["seasons"][season]

    ladder = Ladder(bands=((0, 5), (100, 10), (200, 20), (500, 25)))
    return SeasonRules(
        season=season,
        auction_type=doc.get("type", "mega" if season == 2018 else "mini"),
        purse_lakh=int(doc["purse_inr_lakh"]),
        squad_min=int(doc.get("squad_min", 18)),
        squad_max=int(doc.get("squad_max", 25)),
        overseas_max=int(doc.get("overseas_max", 8)),
        min_base_lakh=20,
        ladder=ladder,
        rtm=bool(doc.get("rtm")),
    )


def build_schema_dict() -> Dict[str, Any]:
    """Build the schema dictionary data-dictionary."""
    return {
        "columns": {
            "season": {"type": "int64", "group": "identifier", "status": "v1", "nullable": False, "as_of": "Season year"},
            "lot_id": {"type": "string", "group": "identifier", "status": "v1", "nullable": False, "as_of": "Unique lot identifier"},
            "player": {"type": "string", "group": "identifier", "status": "v1", "nullable": False, "as_of": "Player name"},
            "set_no": {"type": "int64", "group": "identifier", "status": "v1", "nullable": True, "as_of": "Official auction set number if known"},
            "step_index": {"type": "int64", "group": "identifier", "status": "v1", "nullable": False, "as_of": "Step sequence within this lot"},
            "confidence": {"type": "string", "group": "identifier", "status": "v1", "nullable": False, "as_of": "Confidence level from bid sequence"},
            "contested": {"type": "boolean", "group": "identifier", "status": "v1", "nullable": False, "as_of": "True if >1 bid step or multi-team"},
            "action": {"type": "string", "group": "label", "status": "v1", "nullable": False, "as_of": "Label: RAISE or DROP"},
            "franchise_id": {"type": "string", "group": "identity", "status": "v1", "nullable": False, "as_of": "Lineage-resolved canonical franchise code"},
            "era": {"type": "string", "group": "identity", "status": "v1", "nullable": False, "as_of": "Rule-era bucket: 2018-21, 2022-24, 2025+"},
            "role": {"type": "string", "group": "lot_player", "status": "v1", "nullable": False, "as_of": "Canonical role: batter, bowler, all-rounder, wicketkeeper"},
            "is_overseas": {"type": "boolean", "group": "lot_player", "status": "v1", "nullable": False, "as_of": "True if overseas player"},
            "capped": {"type": "boolean", "group": "lot_player", "status": "v1", "nullable": False, "as_of": "True if capped international"},
            "base_price_lakhs": {"type": "int64", "group": "lot_player", "status": "v1", "nullable": False, "as_of": "Base price in integer lakhs"},
            "age": {"type": "float64", "group": "lot_player", "status": "v2", "nullable": True, "as_of": "Age at auction (v2 placeholder)"},
            "age_isnull": {"type": "boolean", "group": "lot_player", "status": "v2", "nullable": False, "as_of": "Missingness indicator for age"},
            "powerplay_sr": {"type": "float64", "group": "lot_player", "status": "v2", "nullable": True, "as_of": "Powerplay SR (v2 placeholder)"},
            "powerplay_sr_isnull": {"type": "boolean", "group": "lot_player", "status": "v2", "nullable": False, "as_of": "Missingness indicator for powerplay_sr"},
            "death_economy": {"type": "float64", "group": "lot_player", "status": "v2", "nullable": True, "as_of": "Death-over economy (v2 placeholder)"},
            "death_economy_isnull": {"type": "boolean", "group": "lot_player", "status": "v2", "nullable": False, "as_of": "Missingness indicator for death_economy"},
            "vs_spin_sr": {"type": "float64", "group": "lot_player", "status": "v2", "nullable": True, "as_of": "SR vs spin (v2 placeholder)"},
            "vs_spin_sr_isnull": {"type": "boolean", "group": "lot_player", "status": "v2", "nullable": False, "as_of": "Missingness indicator for vs_spin_sr"},
            "vs_pace_sr": {"type": "float64", "group": "lot_player", "status": "v2", "nullable": True, "as_of": "SR vs pace (v2 placeholder)"},
            "vs_pace_sr_isnull": {"type": "boolean", "group": "lot_player", "status": "v2", "nullable": False, "as_of": "Missingness indicator for vs_pace_sr"},
            "home_ground_fit": {"type": "float64", "group": "lot_player", "status": "v2", "nullable": True, "as_of": "Home ground fit (v2 placeholder)"},
            "home_ground_fit_isnull": {"type": "boolean", "group": "lot_player", "status": "v2", "nullable": False, "as_of": "Missingness indicator for home_ground_fit"},
            "impact_player_era": {"type": "float64", "group": "lot_player", "status": "v2", "nullable": True, "as_of": "Impact player era flag (v2 placeholder)"},
            "impact_player_era_isnull": {"type": "boolean", "group": "lot_player", "status": "v2", "nullable": False, "as_of": "Missingness indicator for impact_player_era"},
            "current_price_lakhs": {"type": "int64", "group": "auction_state", "status": "v1", "nullable": False, "as_of": "Price being decided in integer lakhs"},
            "next_increment_lakhs": {"type": "int64", "group": "auction_state", "status": "v1", "nullable": False, "as_of": "Bid ladder increment from current price"},
            "lots_done": {"type": "int64", "group": "auction_state", "status": "v1", "nullable": False, "as_of": "Count of auction lots completed before this lot"},
            "spend_so_far_lakhs": {"type": "int64", "group": "auction_state", "status": "v1", "nullable": False, "as_of": "Total spend across all teams prior to this lot"},
            "spend_pace_vs_expected": {"type": "float64", "group": "auction_state", "status": "v1", "nullable": False, "as_of": "Actual spend pace vs expected linear pace"},
            "purse_left_lakhs": {"type": "int64", "group": "team_state", "status": "v1", "nullable": False, "as_of": "Deciding team purse remaining before this lot"},
            "slots_left": {"type": "int64", "group": "team_state", "status": "v1", "nullable": False, "as_of": "Deciding team squad slots left before this lot"},
            "overseas_left": {"type": "int64", "group": "team_state", "status": "v1", "nullable": False, "as_of": "Deciding team overseas slots left before this lot"},
            "role_gap": {"type": "int64", "group": "team_state", "status": "v1", "nullable": False, "as_of": "Deciding team gap/need for this player's role"},
            "is_final_two": {"type": "boolean", "group": "team_state", "status": "v1", "nullable": False, "as_of": "Whether lot is in heads-up / final-two state as-of this step (<= 2 active teams so far)"},
            "rival_id": {"type": "string", "group": "opponent_state", "status": "v1", "nullable": True, "as_of": "Team currently holding top bid (null at open)"},
            "rival_purse_left_lakhs": {"type": "int64", "group": "opponent_state", "status": "v1", "nullable": True, "as_of": "Rival purse remaining before this lot"},
            "rival_slots_left": {"type": "int64", "group": "opponent_state", "status": "v1", "nullable": True, "as_of": "Rival squad slots left before this lot"},
            "rival_role_gap": {"type": "int64", "group": "opponent_state", "status": "v1", "nullable": True, "as_of": "Rival gap for this player's role"},
            "n_active_estimate": {"type": "int64", "group": "opponent_state", "status": "v1", "nullable": True, "as_of": "Distinct bidders active in this lot so far"},
            "same_role_remaining": {"type": "int64", "group": "pool_scarcity", "status": "v1", "nullable": False, "as_of": "Upcoming pool count of same role in this auction"},
            "same_role_avg_base": {"type": "float64", "group": "pool_scarcity", "status": "v1", "nullable": False, "as_of": "Average base price of upcoming same-role pool"},
        }
    }


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_decision_dataset(
    repo_root: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    seed: int = 0,
) -> Tuple[pd.DataFrame, Dict[str, Any], Dict[str, Any]]:
    """Build the complete canonical decision dataset.

    Returns:
        (df_rows, manifest, splits)
    """
    repo = repo_root or CONFIG["repo_root"]
    dest_dir = out_dir or CONFIG["out_dir"]
    dest_dir.mkdir(parents=True, exist_ok=True)

    alias_map = load_franchise_alias_map(repo)

    # Load master as truth
    master_lots: Dict[Tuple[int, str], Dict[str, str]] = {}
    master_csv = repo / "data" / "processed" / "master" / "all_auctions_master.csv"
    if master_csv.exists():
        with open(master_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                master_lots[(int(row["season"]), norm_name(row["player"]))] = row

    # Load staged 2018-2021
    staged_lots: Dict[Tuple[int, str], Dict[str, str]] = {}
    staged_csv = repo / "data" / "processed" / "2018_2021_staging" / "staged_2018_2021_joined.csv"
    if staged_csv.exists():
        with open(staged_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                staged_lots[(int(row["season"]), norm_name(row["player_name"]))] = row

    # Load lot_order set numbers
    lot_order_sets: Dict[Tuple[int, str], int] = {}
    lot_order_csv = repo / "data" / "processed" / "auction_order" / "lot_order.csv"
    if lot_order_csv.exists():
        with open(lot_order_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sn = row.get("set_no") or ""
                if sn.strip():
                    try:
                        lot_order_sets[(int(row["season"]), norm_name(row["player"]))] = int(sn.strip())
                    except ValueError:
                        pass

    # Load capped status
    capped_lookup: Dict[Tuple[int, str], bool] = {}
    capped_csv = repo / "data" / "processed" / "players" / "capped_by_season.csv"
    if capped_csv.exists():
        with open(capped_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                capped_lookup[(int(row["season"]), norm_name(row["player"]))] = (row.get("capped") == "capped")

    all_decision_rows: List[Dict[str, Any]] = []
    lots_dropped_log: List[Dict[str, Any]] = []
    discrepancies_log: List[Dict[str, Any]] = []

    label_by_team: Dict[str, Counter] = defaultdict(Counter)
    label_by_season: Dict[int, Counter] = defaultdict(Counter)
    contested_lots_cnt = 0
    uncontested_lots_cnt = 0
    contested_rows_cnt = 0
    uncontested_rows_cnt = 0

    input_hashes: Dict[str, str] = {}
    for y in CONFIG["all_seasons"]:
        bf = repo / "data" / "processed" / "bid_sequences" / f"{y}_bids.json"
        if bf.exists():
            input_hashes[f"{y}_bids.json"] = compute_sha256(bf)
    if master_csv.exists():
        input_hashes["all_auctions_master.csv"] = compute_sha256(master_csv)

    for y in CONFIG["all_seasons"]:
        rules = load_rules(y, repo)
        tr = Treasurer(rules)

        state_path = repo / "data" / "processed" / "pre_auction_state" / f"{y}.json"
        with open(state_path, encoding="utf-8") as f:
            state_doc = json.load(f)
        teams = teams_from_state(state_doc["teams"], rules)

        squad_roles: Dict[str, Counter] = defaultdict(Counter)

        bids_path = repo / "data" / "processed" / "bid_sequences" / f"{y}_bids.json"
        with open(bids_path, encoding="utf-8") as f:
            bids_doc = json.load(f)

        lots = bids_doc.get("lots", [])
        is_crore = (y >= 2022)
        total_lots = len(lots)
        total_purse_lakhs = sum(t.purse_lakh for t in teams.values())
        spend_so_far_lakhs = 0
        lots_done = 0

        # Pre-parse metadata for scarcity calculations (as-of upcoming lots)
        meta_lots = []
        for l in lots:
            p_name = l["player"]
            p_norm = norm_name(p_name)
            m = master_lots.get((y, p_norm))
            st = staged_lots.get((y, p_norm))

            if m and m.get("role"):
                r_name = norm_role(m["role"])
            elif l.get("role"):
                r_name = norm_role(l["role"])
            elif st and st.get("role"):
                r_name = norm_role(st["role"])
            else:
                r_name = "all-rounder"

            if m and m.get("base_lakh"):
                bp_lakh = int(m["base_lakh"])
            elif l.get("base_price") is not None:
                bp_lakh = round(float(l["base_price"]) * 100) if is_crore else int(round(float(l["base_price"])))
            else:
                bp_lakh = 20

            meta_lots.append({"role": r_name, "base_lakh": bp_lakh})

        for l_idx, l in enumerate(lots):
            p_name = l["player"]
            p_norm = norm_name(p_name)
            m = master_lots.get((y, p_norm))
            st = staged_lots.get((y, p_norm))

            role = meta_lots[l_idx]["role"]
            base_lakh = meta_lots[l_idx]["base_lakh"]

            # is_overseas
            if m and m.get("nationality"):
                is_ovs = (m["nationality"] == "Overseas")
            elif "is_overseas" in l:
                is_ovs = bool(l["is_overseas"])
            elif st and "is_overseas" in st:
                is_ovs = (st["is_overseas"] == "True")
            else:
                is_ovs = False

            # capped
            if m and m.get("capped"):
                capped = (m["capped"] == "capped")
            elif (y, p_norm) in capped_lookup:
                capped = capped_lookup[(y, p_norm)]
            else:
                capped = True

            set_no = lot_order_sets.get((y, p_norm), None)

            # Winner & final price resolution (master wins on any conflict)
            if m:
                winner = alias_map.get(m.get("winner", ""), m.get("winner", ""))
                final_price_lakh = int(m["hammer_lakh"]) if m.get("hammer_lakh") else None
                # Check bids file against master
                if l.get("winner"):
                    l_win = alias_map.get(l["winner"], l["winner"])
                    if l_win and winner and l_win != winner:
                        discrepancies_log.append({
                            "season": y, "player": p_name, "field": "winner",
                            "bids_val": l_win, "master_val": winner, "resolution": "master_wins"
                        })
                if l.get("final_price") is not None:
                    raw_fp = round(float(l["final_price"]) * 100) if is_crore else int(round(float(l["final_price"])))
                    if final_price_lakh is not None and raw_fp != final_price_lakh:
                        discrepancies_log.append({
                            "season": y, "player": p_name, "field": "final_price",
                            "bids_val": raw_fp, "master_val": final_price_lakh, "resolution": "master_wins"
                        })
            else:
                winner = alias_map.get(l.get("winner", ""), l.get("winner", ""))
                if l.get("final_price") is not None:
                    final_price_lakh = round(float(l["final_price"]) * 100) if is_crore else int(round(float(l["final_price"])))
                elif st and st.get("hammer_price_lakh"):
                    final_price_lakh = int(st["hammer_price_lakh"])
                else:
                    final_price_lakh = None

            steps = l.get("bid_steps", [])

            # Check ladder integrity: monotonic and last step == final_price
            is_dropped = False
            if steps:
                if final_price_lakh is None:
                    is_dropped = True
                    lots_dropped_log.append({
                        "season": y, "player": p_name, "reason": "missing_final_price"
                    })
                else:
                    last_step_raw = steps[-1].get("price")
                    if last_step_raw is None:
                        is_dropped = True
                        lots_dropped_log.append({
                            "season": y, "player": p_name, "reason": "missing_step_price"
                        })
                    else:
                        last_step_lakh = round(float(last_step_raw) * 100) if is_crore else int(round(float(last_step_raw)))
                        if last_step_lakh != final_price_lakh:
                            is_dropped = True
                            lots_dropped_log.append({
                                "season": y, "player": p_name, "reason": "last_step_ne_final_price",
                                "last_step_lakh": last_step_lakh, "final_price_lakh": final_price_lakh
                            })

            # Upcoming pool scarcity (known as-of the lot start)
            upcoming = [meta_lots[j] for j in range(l_idx + 1, total_lots) if meta_lots[j]["role"] == role]
            same_role_remaining = len(upcoming)
            same_role_avg_base = round(sum(u["base_lakh"] for u in upcoming) / len(upcoming), 2) if upcoming else 0.0

            # Spend pace vs expected linear pace
            expected_frac = (lots_done / total_lots) if total_lots > 0 else 0.0
            actual_frac = (spend_so_far_lakhs / total_purse_lakhs) if total_purse_lakhs > 0 else 0.0
            spend_pace = round(actual_frac / expected_frac, 4) if expected_frac > 0 else 1.0

            lot_id = f"{y}-L{l_idx+1:03d}-{p_norm[:20]}"
            confidence = l.get("confidence", "outcome_only" if not steps else "authentic_telemetry")

            if steps and not is_dropped:
                norm_steps: List[Dict[str, Any]] = []
                for s in steps:
                    t_code = alias_map.get(s["team"], s["team"])
                    p_raw = s["price"]
                    p_lakh = round(float(p_raw) * 100) if is_crore else int(round(float(p_raw)))
                    norm_steps.append({"team": t_code, "price_lakh": p_lakh})

                # Reconcile uncontested single-step lot team with master winner
                if len(norm_steps) == 1 and winner and norm_steps[0]["team"] != winner:
                    discrepancies_log.append({
                        "season": y, "player": p_name, "field": "uncontested_team",
                        "bids_val": norm_steps[0]["team"], "master_val": winner, "resolution": "master_wins"
                    })
                    norm_steps[0]["team"] = winner

                contested = (len(norm_steps) > 1 or len(set(s["team"] for s in norm_steps)) > 1)
                if contested:
                    contested_lots_cnt += 1
                else:
                    uncontested_lots_cnt += 1

                participating_teams = {s["team"] for s in norm_steps}

                def calc_role_gap(team_code: str, r_role: str) -> int:
                    have_cnt = squad_roles[team_code][r_role]
                    tgt = TARGET_ROLES.get(r_role, 5)
                    return max(0, tgt - have_cnt)

                # 1. RAISE rows: every bid step is a raise
                for step_idx, step in enumerate(norm_steps):
                    t_code = step["team"]
                    cur_p = step["price_lakh"]
                    next_inc = rules.ladder.step_at(cur_p)

                    if step_idx == 0:
                        rival_id = None
                        rival_purse = None
                        rival_slots = None
                        rival_gap = None
                    else:
                        rival_id = norm_steps[step_idx - 1]["team"]
                        rival_team = teams[rival_id]
                        rival_purse = rival_team.purse_lakh
                        rival_slots = tr.slots_left(rival_team)
                        rival_gap = calc_role_gap(rival_id, role)

                    n_active = len(set(s["team"] for s in norm_steps[:step_idx + 1]))
                    # Heads-up / final-two state as-of this step
                    is_f2 = bool(n_active <= 2 and step_idx >= 1)

                    t_team = teams[t_code]
                    row: Dict[str, Any] = {
                        "season": y,
                        "lot_id": lot_id,
                        "player": p_name,
                        "set_no": set_no,
                        "step_index": step_idx,
                        "confidence": confidence,
                        "contested": contested,
                        "action": "RAISE",
                        "franchise_id": t_code,
                        "era": get_era(y),
                        "role": role,
                        "is_overseas": is_ovs,
                        "capped": capped,
                        "base_price_lakhs": base_lakh,
                        "age": None,
                        "age_isnull": True,
                        "powerplay_sr": None,
                        "powerplay_sr_isnull": True,
                        "death_economy": None,
                        "death_economy_isnull": True,
                        "vs_spin_sr": None,
                        "vs_spin_sr_isnull": True,
                        "vs_pace_sr": None,
                        "vs_pace_sr_isnull": True,
                        "home_ground_fit": None,
                        "home_ground_fit_isnull": True,
                        "impact_player_era": None,
                        "impact_player_era_isnull": True,
                        "current_price_lakhs": cur_p,
                        "next_increment_lakhs": next_inc,
                        "lots_done": lots_done,
                        "spend_so_far_lakhs": spend_so_far_lakhs,
                        "spend_pace_vs_expected": spend_pace,
                        "purse_left_lakhs": t_team.purse_lakh,
                        "slots_left": tr.slots_left(t_team),
                        "overseas_left": tr.overseas_slots_left(t_team),
                        "role_gap": calc_role_gap(t_code, role),
                        "is_final_two": is_f2,
                        "rival_id": rival_id,
                        "rival_purse_left_lakhs": rival_purse,
                        "rival_slots_left": rival_slots,
                        "rival_role_gap": rival_gap,
                        "n_active_estimate": n_active,
                        "same_role_remaining": same_role_remaining,
                        "same_role_avg_base": same_role_avg_base,
                    }
                    all_decision_rows.append(row)
                    label_by_team[t_code]["RAISE"] += 1
                    label_by_season[y]["RAISE"] += 1
                    if contested:
                        contested_rows_cnt += 1
                    else:
                        uncontested_rows_cnt += 1

                # 2. DROP rows: every losing participant drops exactly once
                # On RTM lots, the top open bidder did not drop (they were matched by RTM, ending the lot).
                # Only genuinely-topped teams drop.
                top_open_bidder = None

                # Case 1: An explicit RTM step exists in steps (e.g. 2018 where RTM matching step is recorded)
                rtm_teams = {alias_map.get(s["team"], s["team"]) for s in steps if s.get("status") == "RTM"}
                sold_teams = {alias_map.get(s["team"], s["team"]) for s in steps if s.get("status") == "SOLD"}
                if rtm_teams:
                    # Both the RTM-matching team and the topped open bidder (marked SOLD) are non-dropping teams
                    excluded_from_drop = {winner} | rtm_teams | sold_teams
                # Case 2: winner is not the last bidder in norm_steps (e.g. 2025 RTM lots like Arshdeep Singh)
                elif winner and len(norm_steps) >= 1 and norm_steps[-1]["team"] != winner:
                    top_open_bidder = norm_steps[-1]["team"]
                    excluded_from_drop = {winner, top_open_bidder}
                else:
                    excluded_from_drop = {winner}

                losing_participants = participating_teams - excluded_from_drop
                for losing_t in sorted(losing_participants):
                    last_idx = max(j for j, s in enumerate(norm_steps) if s["team"] == losing_t)
                    topped_idx = last_idx + 1
                    if topped_idx < len(norm_steps):
                        topped_step = norm_steps[topped_idx]
                        cur_p = topped_step["price_lakh"]
                        rival_id = topped_step["team"]
                    else:
                        cur_p = final_price_lakh
                        rival_id = winner

                    next_inc = rules.ladder.step_at(cur_p)
                    rival_team = teams[rival_id]
                    rival_purse = rival_team.purse_lakh
                    rival_slots = tr.slots_left(rival_team)
                    rival_gap = calc_role_gap(rival_id, role)

                    n_active = len(set(s["team"] for s in norm_steps[:topped_idx + 1]))
                    is_f2 = bool(n_active <= 2 and topped_idx >= 1)
                    t_team = teams[losing_t]

                    row = {
                        "season": y,
                        "lot_id": lot_id,
                        "player": p_name,
                        "set_no": set_no,
                        "step_index": topped_idx,
                        "confidence": confidence,
                        "contested": contested,
                        "action": "DROP",
                        "franchise_id": losing_t,
                        "era": get_era(y),
                        "role": role,
                        "is_overseas": is_ovs,
                        "capped": capped,
                        "base_price_lakhs": base_lakh,
                        "age": None,
                        "age_isnull": True,
                        "powerplay_sr": None,
                        "powerplay_sr_isnull": True,
                        "death_economy": None,
                        "death_economy_isnull": True,
                        "vs_spin_sr": None,
                        "vs_spin_sr_isnull": True,
                        "vs_pace_sr": None,
                        "vs_pace_sr_isnull": True,
                        "home_ground_fit": None,
                        "home_ground_fit_isnull": True,
                        "impact_player_era": None,
                        "impact_player_era_isnull": True,
                        "current_price_lakhs": cur_p,
                        "next_increment_lakhs": next_inc,
                        "lots_done": lots_done,
                        "spend_so_far_lakhs": spend_so_far_lakhs,
                        "spend_pace_vs_expected": spend_pace,
                        "purse_left_lakhs": t_team.purse_lakh,
                        "slots_left": tr.slots_left(t_team),
                        "overseas_left": tr.overseas_slots_left(t_team),
                        "role_gap": calc_role_gap(losing_t, role),
                        "is_final_two": is_f2,
                        "rival_id": rival_id,
                        "rival_purse_left_lakhs": rival_purse,
                        "rival_slots_left": rival_slots,
                        "rival_role_gap": rival_gap,
                        "n_active_estimate": n_active,
                        "same_role_remaining": same_role_remaining,
                        "same_role_avg_base": same_role_avg_base,
                    }
                    all_decision_rows.append(row)
                    label_by_team[losing_t]["DROP"] += 1
                    label_by_season[y]["DROP"] += 1
                    if contested:
                        contested_rows_cnt += 1
                    else:
                        uncontested_rows_cnt += 1

            # Engine ledger advancement: charge ONLY if THIS lot was sold
            is_sold = bool(l.get("sold", False))
            if is_sold and winner and winner in teams and final_price_lakh is not None:
                p_obj = Player(
                    key=p_name,
                    name=p_name,
                    overseas=is_ovs,
                    capped=capped,
                    base_lakh=base_lakh,
                    role=role,
                )
                tr.apply_purchase(teams[winner], p_obj, final_price_lakh)
                squad_roles[winner][role] += 1
                spend_so_far_lakhs += final_price_lakh

            lots_done += 1

    # Convert to DataFrame with strict sorting for determinism
    df = pd.DataFrame(all_decision_rows)
    sort_cols = ["season", "lot_id", "step_index", "action", "franchise_id"]
    df.sort_values(by=sort_cols, inplace=True, ascending=[True, True, True, False, True])
    df.reset_index(drop=True, inplace=True)

    # Write outputs
    parquet_path = dest_dir / "decision_rows.parquet"
    sample_csv_path = dest_dir / "decision_rows_sample.csv"
    schema_path = dest_dir / "schema.json"
    manifest_path = dest_dir / "manifest.json"
    splits_path = dest_dir / "splits.json"

    # Save parquet deterministically
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, parquet_path, compression="snappy")

    # Save first 500 rows sample
    df.head(500).to_csv(sample_csv_path, index=False)

    # Save schema.json
    schema_dict = build_schema_dict()
    schema_path.write_text(json.dumps(schema_dict, indent=2), encoding="utf-8")

    # Leave-one-season-out splits (2018-2024 train/val, 2025-2026 held out)
    train_val_seasons = CONFIG["train_val_seasons"]
    holdout_seasons = CONFIG["holdout_seasons"]

    # Folds
    folds = []
    lot_ids_by_season = {
        s: sorted(list(set(df[df["season"] == s]["lot_id"])))
        for s in CONFIG["all_seasons"]
    }

    for val_s in train_val_seasons:
        t_seasons = [s for s in train_val_seasons if s != val_s]
        fold_info = {
            "fold": f"val_{val_s}",
            "val_season": val_s,
            "train_seasons": t_seasons,
            "val_lot_count": len(lot_ids_by_season[val_s]),
            "train_lot_count": sum(len(lot_ids_by_season[s]) for s in t_seasons),
        }
        folds.append(fold_info)

    splits_data = {
        "holdout_test_seasons": holdout_seasons,
        "train_val_seasons": train_val_seasons,
        "folds": folds,
        "lot_ids_by_season": lot_ids_by_season,
    }
    splits_path.write_text(json.dumps(splits_data, indent=2), encoding="utf-8")

    # Save manifest.json
    parquet_hash = compute_sha256(parquet_path)
    output_hashes = {
        "decision_rows.parquet": parquet_hash,
        "decision_rows_sample.csv": compute_sha256(sample_csv_path),
        "schema.json": compute_sha256(schema_path),
        "splits.json": compute_sha256(splits_path),
    }

    tot_raise = sum(1 for r in all_decision_rows if r["action"] == "RAISE")
    tot_drop = sum(1 for r in all_decision_rows if r["action"] == "DROP")

    manifest_data = {
        "row_counts_total": len(df),
        "label_balance_total": {"RAISE": tot_raise, "DROP": tot_drop},
        "label_balance_by_team": {k: dict(v) for k, v in sorted(label_by_team.items())},
        "label_balance_by_season": {k: dict(v) for k, v in sorted(label_by_season.items())},
        "contested_vs_uncontested": {
            "contested_lots": contested_lots_cnt,
            "uncontested_lots": uncontested_lots_cnt,
            "contested_rows": contested_rows_cnt,
            "uncontested_rows": uncontested_rows_cnt,
        },
        "lots_dropped": lots_dropped_log,
        "discrepancies_vs_master": discrepancies_log,
        "features": list(df.columns),
        "config": {
            "holdout_seasons": holdout_seasons,
            "train_val_seasons": train_val_seasons,
            "seed": seed,
            "unit": CONFIG["unit"],
            "provenance": "withheld",
        },
        "input_hashes": input_hashes,
        "output_hashes": output_hashes,
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    return df, manifest_data, splits_data


def main():
    parser = argparse.ArgumentParser(description="Build L3 decision dataset from bid sequences.")
    parser.add_argument("--out", type=str, default=str(CONFIG["out_dir"]), help="Output directory")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for determinism")
    args = parser.parse_args()

    out_p = Path(args.out)
    df, manifest, _ = build_decision_dataset(out_dir=out_p, seed=args.seed)

    print(f"Generated {len(df)} decision rows to {out_p}")
    print(f"Label balance: RAISE={manifest['label_balance_total']['RAISE']}, DROP={manifest['label_balance_total']['DROP']}")
    print(f"Contested lots: {manifest['contested_vs_uncontested']['contested_lots']}, Uncontested lots: {manifest['contested_vs_uncontested']['uncontested_lots']}")
    print(f"Lots dropped: {len(manifest['lots_dropped'])}")


if __name__ == "__main__":
    main()

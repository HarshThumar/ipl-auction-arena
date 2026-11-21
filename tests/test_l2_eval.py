"""L2 evaluation harness tests. Synthetic data only: these test the code, they fit nothing real.

Closes in code: D1 guard (contamination.py), D2 as-of splits, D7 metric set, D8 minis-only,
and the rule #1 gate.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.eval import contamination as cg
from src.eval import decision_baselines as db
from src.eval import gate, lot_baselines as lb, metrics as mt

TEAMS = ["CSK", "DC", "GT", "KKR", "LSG", "MI", "PBKS", "RCB", "RR", "SRH"]


# ---------- metrics ----------

def test_log_loss_and_brier_known_values():
    y = np.array([1, 0])
    assert mt.log_loss(y, np.array([0.5, 0.5])) == pytest.approx(np.log(2))
    assert mt.brier(y, np.array([1.0, 0.0])) == 0.0


def test_auc_spearman_coverage_top3():
    assert mt.auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert mt.auc([1, 1], [0.1, 0.2]) is None
    assert mt.spearman(np.array([1, 2, 3]), np.array([10, 20, 30])) == pytest.approx(1.0)
    assert mt.coverage([1, 1], [2, 2], [1.5, 3]) == 0.5
    assert mt.top3_hit([["A", "B", "C", "D"], ["A", "B", "C", "D"]], ["C", "D"]) == 0.5


def test_bootstrap_resamples_whole_groups():
    groups = np.array(["a", "a", "b", "b"])
    vals = np.array([1.0, 1.0, 3.0, 3.0])
    ci = mt.bootstrap_ci(groups, lambda i: vals[i].mean(), n=200)
    assert 1.0 <= ci[0] <= ci[1] <= 3.0
    # a group's two rows always come together, so a mean of exactly 1.5 or 2.5 is impossible
    seen = set()
    rng_stat = lambda i: seen.add(round(vals[i].mean(), 3)) or 0.0  # noqa: E731
    mt.bootstrap_ci(groups, rng_stat, n=200)
    assert seen <= {1.0, 2.0, 3.0}


# ---------- D1 contamination guard ----------

def test_release_after_auction_is_flagged():
    assert cg.status("qwen2.5:7b", 2023) == "possibly_contaminated"
    assert cg.status("qwen2.5:7b", 2024) == "possibly_contaminated"
    with pytest.raises(cg.ContaminationError):
        cg.require_clean("qwen2.5:7b", 2024)


def test_held_out_seasons_are_clean_for_qwen25():
    for s in (2025, 2026, 2027):
        assert cg.status("qwen2.5:7b", s) == "clean"
        cg.require_clean("qwen2.5:7b", s)


def test_gemini_and_unknown_models_refused():
    with pytest.raises(cg.ContaminationError):
        cg.status("gemini-2.5-flash", 2026)
    with pytest.raises(cg.ContaminationError):
        cg.status("some-new-model", 2026)


# ---------- rule #1 gate ----------

LEVELS_MD = """| Level | Name | Done when | Closes | Target date |
|---|---|---|---|---|
| **L0** | a | b | X1, X2 (Y9 move to L1) | d |
| **L1** | a | b | A2–A4 | d |
| **L2** | a | b | D6 | d |
| **L1** | depth table row | ignored |
"""


def _register(rows):
    head = "| # | Failure | Sev | Detect | Fix | Src | Status |\n|---|---|---|---|---|---|---|\n"
    return head + "".join(f"| {r} | f | {s} | d | m | s | {st} |\n" for r, s, st in rows)


def test_gate_blocks_on_earlier_level_high_rows(tmp_path):
    lv, rg = tmp_path / "levels.md", tmp_path / "reg.md"
    lv.write_text(LEVELS_MD.replace("X1, X2", "D2, G1"), encoding="utf-8")
    rg.write_text(_register([("D2", "H", "In progress — CI"), ("G1", "M", "Open"),
                             ("A2", "H", "Closed"), ("A3", "H", "Closed"), ("A4", "H", "Closed"),
                             ("D6", "H", "Open")]), encoding="utf-8")
    r = gate.check(2, lv, rg)
    assert not r["ok"] and r["blocking"] == ["D2 (In progress)"]
    assert r["own_level_open"] == ["D6 (Open)"]
    assert set(gate.owners(lv)) == {"D2", "G1", "A2", "A3", "A4", "D6"}


def test_gate_passes_when_closed(tmp_path):
    lv, rg = tmp_path / "levels.md", tmp_path / "reg.md"
    lv.write_text(LEVELS_MD.replace("X1, X2", "D2"), encoding="utf-8")
    rg.write_text(_register([("D2", "H", "**Closed** (test)"), ("A2", "H", "Closed"),
                             ("A3", "H", "Deferred (L8)"), ("A4", "L", "Open")]), encoding="utf-8")
    assert gate.check(2, lv, rg)["ok"]


# ---------- decision baselines (D2 as-of, leakage) ----------

def _synthetic_decisions(n_lots=60, seasons=(2020, 2021, 2022, 2023), seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for lot in range(n_lots):
            base = int(rng.choice([20, 50, 100, 200]))
            purse = int(rng.integers(500, 5000))
            for step in range(int(rng.integers(1, 6))):
                price = base + 20 * step
                p_drop = 0.05 if step == 0 else min(0.9, price / purse * 5)
                drop = step > 0 and rng.random() < p_drop
                rows.append(dict(
                    season=s, lot_id=f"{s}-{lot}", player=f"p{lot}", contested=step > 0,
                    confidence="partial", action="DROP" if drop else "RAISE",
                    franchise_id=TEAMS[int(rng.integers(0, 10))], era="2018-21", role="batter",
                    rival_id=None if step == 0 else TEAMS[int(rng.integers(0, 10))],
                    is_overseas=bool(rng.random() < 0.3), capped=True, base_price_lakhs=base,
                    set_no=float(lot // 10), step_index=step, current_price_lakhs=price,
                    next_increment_lakhs=20, lots_done=lot, spend_so_far_lakhs=lot * 50,
                    spend_pace_vs_expected=1.0, purse_left_lakhs=purse, slots_left=5,
                    overseas_left=2, role_gap=1, is_final_two=step >= 2,
                    rival_purse_left_lakhs=None if step == 0 else float(rng.integers(500, 5000)),
                    rival_slots_left=None if step == 0 else 4.0,
                    rival_role_gap=None if step == 0 else 1.0, n_active_estimate=min(step + 1, 3),
                    same_role_remaining=10, same_role_avg_base=60.0,
                ))
    return pd.DataFrame(rows)


def test_features_exclude_forbidden_and_outcomes():
    assert not set(db.FEATURES) & db.FORBIDDEN
    assert "contested" not in db.FEATURES and "confidence" not in db.FEATURES
    df = _synthetic_decisions(n_lots=5)
    with pytest.raises(AssertionError):
        db.make_X(df, db.FEATURES + ["contested"])


def test_forward_split_never_trains_on_target_or_future():
    df = _synthetic_decisions(n_lots=5)
    tr, va = db.forward_split(df, 2022)
    assert tr["season"].max() < 2022 and set(va["season"]) == {2022}
    assert not set(tr["lot_id"]) & set(va["lot_id"])


def test_lgbm_learns_signal_and_is_deterministic():
    df = _synthetic_decisions()
    tr, va = db.forward_split(df, 2023)
    y = db.label(va)
    p1 = db.LGBM().fit(tr).predict(va)
    p2 = db.LGBM().fit(tr).predict(va)
    assert np.array_equal(p1, p2)
    assert mt.log_loss(y, p1) < mt.log_loss(y, db.Prior().fit(tr).predict(va))


def test_unseen_category_and_no_identity_variant():
    df = _synthetic_decisions(n_lots=20)
    tr, va = db.forward_split(df, 2023)
    va = va.copy()
    va.loc[va.index[0], "franchise_id"] = "NEWTEAM"
    m = db.LGBM().fit(tr)
    assert np.isfinite(m.predict(va)).all()
    assert not set(db.IDENTITY) & set(db.LGBM(with_identity=False).features)
    assert db.TeamPrior().fit(tr).predict(va)[0] == pytest.approx(db.label(tr).mean())


# ---------- lot baselines (as-of) ----------

def _synthetic_master(tmp_path):
    rows = [
        # season, player, id, base, status, winner, hammer
        (2022, "A", "id_a", 50, "sold", "CSK", 300),
        (2022, "B", "id_b", 20, "unsold", None, None),
        (2022, "C", "id_c", 100, "sold", "MI", 150),
        (2023, "A", "id_a", 100, "sold", "RR", 500),
        (2023, "B", "id_b", 20, "sold", "DC", 20),
        (2023, "D", "id_d", 200, "sold", "GT", 900),
        (2024, "A", "id_a", 200, "sold", "KKR", 9999),  # future: must never feed 2023
    ]
    df = pd.DataFrame(rows, columns=["season", "player", "cricsheet_id", "base_lakh", "status",
                                     "winner", "hammer_lakh"])
    df["withdrawn"] = False
    p = tmp_path / "master.csv"
    df.to_csv(p, index=False)
    return lb.load_master(p)


def test_last_price_uses_only_earlier_seasons(tmp_path):
    m = _synthetic_master(tmp_path)
    purses = {t: 1000 for t in TEAMS} | {"SRH": 5000}
    p = lb.predict("last_price", m, 2023, purses).set_index("player")
    assert p.loc["A", "point"] == 300  # 2022 price, not 2024's 9999
    assert p.loc["D", "point"] == 200  # no history -> base
    assert p.loc["A", "ranking"][0] == "CSK"  # last buyer first
    assert p.loc["D", "ranking"][0] == "SRH"  # then richest purse


def test_base_price_baseline_and_interval_calibration(tmp_path):
    m = _synthetic_master(tmp_path)
    purses = {t: 1000 + i for i, t in enumerate(TEAMS)}
    p = lb.predict("base_price", m, 2023, purses)
    assert (p["point"] == m[m.season == 2023]["base_lakh"].to_numpy()).all()
    assert (p["lo"] <= p["point"] * 6).all() and (p["hi"] >= p["lo"]).all()
    assert p["ranking"].iloc[0][0] == "SRH"
    assert ((0 < p["p_sold"]) & (p["p_sold"] < 1)).all()


def test_l2_scores_minis_only():
    import scripts.run_l2_baselines as run

    assert run.SCORE_SEASONS == [2023, 2024]  # minis only (D8); 2026 is held back for L5 (D5)
    assert 2026 not in run.SCORE_SEASONS and 2025 not in run.SCORE_SEASONS


def test_real_purse_file_shape():
    purses = lb.load_purses(2024)
    assert set(purses) == set(TEAMS) and all(isinstance(v, int) for v in purses.values())
    json.dumps(purses)


# ---------- AuctionIQ adapter ----------

def test_auctioniq_name_matching():
    from scripts.score_auctioniq import match_names

    ours = pd.DataFrame({"player": ["Phil Salt", "Mujeeb ur Rahman", "Steven Smith", "Nobody Known"],
                         "base_lakh": [150, 200, 200, 20]})
    theirs = pd.DataFrame({"name": ["Philip Salt", "Mujeeb Rahman", "Steve Smith", "Jos Buttler"],
                           "base_lakh": [150, 200, 200, 200]})
    mp = match_names(ours, theirs)
    assert mp == {0: 0, 1: 1, 2: 2}  # surname within same base price; no forced match for the 4th


def test_auctioniq_section_without_scores(tmp_path, monkeypatch):
    import scripts.run_l2_baselines as run

    monkeypatch.setattr(run, "AUCTIONIQ", tmp_path / "missing.json")
    assert "Not scored yet" in "\n".join(run.auctioniq_section())

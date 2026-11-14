"""Player performance features: checked against official IPL figures, blanks, and the as-of rule.

Official figures (IPL 2023 season, read before the Dec 2023 auction = season 2024 row,
window prev_ipl_), from the IPL 2023 season statistics as reported by ESPNcricinfo:
  Virat Kohli   14 matches, 639 runs, strike rate 139.82
  Shubman Gill  17 matches, 890 runs, strike rate 157.80
  Mohammed Siraj 19 wickets
  Ravindra Jadeja 20 wickets
"""
import math
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
F = ROOT / "data" / "processed" / "player_features" / "features_by_season.csv.gz"
pytestmark = pytest.mark.skipif(not F.exists(), reason="features not built")


@pytest.fixture(scope="module")
def feats():
    return pd.read_csv(F, dtype={"cricsheet_id": str})


def row(feats, season, name):
    r = feats[(feats["season"] == season) & (feats["player"] == name)]
    assert len(r) == 1, f"{name} {season}: {len(r)} rows"
    return r.iloc[0]


@pytest.mark.parametrize("name,matches,runs,sr", [("V Kohli", 14, 639, 139.82), ("Shubman Gill", 17, 890, 157.80)])
def test_official_batting_ipl_2023(feats, name, matches, runs, sr):
    r = row(feats, 2024, name)
    assert (r["prev_ipl_matches"], r["prev_ipl_runs"]) == (matches, runs)
    assert r["prev_ipl_bat_sr"] == pytest.approx(sr, abs=0.01)


@pytest.mark.parametrize("name,wkts", [("Mohammed Siraj", 19), ("RA Jadeja", 20)])
def test_official_bowling_ipl_2023(feats, name, wkts):
    assert row(feats, 2024, name)["prev_ipl_bowl_wkts"] == wkts


def test_rates_blank_when_no_denominator(feats):
    no_bowl = feats[feats["t20_bowl_balls"] == 0]
    assert len(no_bowl) and no_bowl["t20_bowl_econ"].isna().all()
    no_wkt = feats[(feats["t20_bowl_balls"] > 0) & (feats["t20_bowl_wkts"] == 0)]
    assert no_wkt["t20_bowl_sr"].isna().all() and no_wkt["t20_bowl_avg"].isna().all()
    no_out = feats[feats["t20_outs"] == 0]
    assert no_out["t20_bat_avg"].isna().all()


def test_as_of_dates_and_window_nesting(feats):
    assert set(feats["season"]) == set(range(2018, 2028))
    for w in ("ipl_", "last3y_", "last12m_"):
        assert (feats[f"{w}matches"] <= feats["t20_matches"]).all(), w
    assert (feats["last12m_matches"] <= feats["last3y_matches"]).all()
    assert (feats["prev_ipl_matches"] <= feats["ipl_matches"]).all()


def test_counts_only_grow_between_seasons(feats):
    """t20_ counts are cumulative: a player can't have fewer matches before a later auction."""
    p = feats.pivot_table(index="cricsheet_id", columns="season", values="t20_matches")
    diffs = p.diff(axis=1).iloc[:, 1:]
    assert (diffs.fillna(0) >= 0).all().all()


def test_rate_matches_counts(feats):
    r = row(feats, 2024, "V Kohli")
    assert r["t20_bat_sr"] == pytest.approx(round(100 * r["t20_runs"] / r["t20_balls_faced"], 2))
    if r["t20_bowl_balls"]:
        assert r["t20_bowl_econ"] == pytest.approx(round(6 * r["t20_bowl_runs"] / r["t20_bowl_balls"], 2))
    assert not math.isnan(r["t20_bat_avg"])

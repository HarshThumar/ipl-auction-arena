"""Retention-day ingest: backtest on 2022-2026 and fault injection for 17 Nov 2026."""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_pre_auction_state as bps  # noqa: E402

MOCK = ROOT / "tests" / "fixtures" / "mock_2027_retained.csv"
# published totals for the mini auctions (2021 purse uses the CSK 19.90 cr figure, see the csv note) (purse in lakh, slots, overseas slots)
PUBLISHED_TOTALS = {2019: (14525, 70, 20), 2020: (20765, 73, 29), 2021: (19660, 61, 22),
                    2023: (20650, 87, 30), 2024: (26295, 77, 30), 2026: (23755, 77, 31),
                    2027: (29795, 66, 25)}


def fails(issues):
    return [m for level, m in issues if level == "FAIL"]


@pytest.mark.parametrize("season", bps.BACKTEST_SEASONS)
def test_backtest_has_no_hard_failures(season):
    state, issues = bps.run(season, write=False, quiet=True)
    assert fails(issues) == []
    assert state["status"] == "FINAL"


@pytest.mark.parametrize("season", sorted(PUBLISHED_TOTALS))
def test_backtest_matches_published_totals(season):
    state, _ = bps.run(season, write=False, quiet=True)
    t = state["totals"]
    assert (t["purse_left_lakh"], t["slots_left"], t["overseas_slots_left"]) == PUBLISHED_TOTALS[season]


def _mock():
    return bps.load_retained(2027, MOCK)


def _build(retained, official=None):
    return bps.build(2027, retained, official or {}, bps.load_rules(2027))


def test_dry_run_2027_mock_is_provisional_without_official_figures():
    state, issues = _build(_mock())
    assert fails(issues) == []
    assert state["status"] == "PROVISIONAL"
    assert any("PROVISIONAL" in m for _, m in issues)
    assert len(state["teams"]) == 10


def test_dry_run_2027_mock_is_final_with_consistent_official_figures():
    retained = _mock()
    draft, _ = _build(retained)
    official = {t: {"purse_left_lakh": s["purse_left_derived_lakh"], "slots_left": s["slots_left"],
                    "overseas_slots_left": s["overseas_slots_left"], "source": "test"}
                for t, s in draft["teams"].items()}
    state, issues = _build(retained, official)
    assert fails(issues) == [] and state["status"] == "FINAL"
    assert not [m for _, m in issues if "purse derived" in m]


def test_missing_player_caught_by_official_slot_count():
    retained = _mock()
    draft, _ = _build(retained)
    official = {t: {"purse_left_lakh": None, "slots_left": s["slots_left"],
                    "overseas_slots_left": s["overseas_slots_left"]} for t, s in draft["teams"].items()}
    retained = copy.deepcopy(retained)
    retained["KKR"].pop()
    _, issues = _build(retained, official)
    assert any(m.startswith("KKR: slots left") for m in fails(issues))


def test_player_on_two_teams_fails():
    retained = copy.deepcopy(_mock())
    retained["MI"].append(dict(retained["CSK"][0]))
    assert any("retained by both" in m for m in fails(_build(retained)[1]))


def test_unit_typo_salary_fails():
    retained = copy.deepcopy(_mock())
    retained["LSG"][0]["salary_lakh"] = 8   # "7.75 lakh" for 7.75 crore
    assert any("below the 20 lakh minimum" in m for m in fails(_build(retained)[1]))


def test_2027_is_final():
    state, issues = bps.run(2027, write=False, quiet=True)
    assert [m for l, m in issues if l == "FAIL"] == []
    assert state["status"] == "FINAL"


def test_missing_team_fails():
    retained = copy.deepcopy(_mock())
    del retained["SRH"]
    assert any("no retained list" in m for m in fails(_build(retained)[1]))


def test_bad_nationality_fails():
    retained = copy.deepcopy(_mock())
    retained["RR"][0]["nationality"] = None
    assert any("nationality" in m for m in fails(_build(retained)[1]))


def test_unknown_team_in_csv_exits(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("team,player,nationality,salary_lakh\nXYZ,A Player,India,100\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        bps.load_retained(2027, p)

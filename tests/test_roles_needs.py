"""Role labels and team needs: golden players, leakage and consistency.

GOLDEN is a draft list of well-known players whose labels are not in doubt. Harsh to confirm
each row against ESPNcricinfo; a failure here means a rule broke, not that the player changed.
"""
import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ROLES = ROOT / "data" / "processed" / "roles" / "player_roles.csv"
NEEDS = ROOT / "data" / "processed" / "team_needs" / "needs_long.csv"

pytestmark = pytest.mark.skipif(not ROLES.exists() or not NEEDS.exists(),
                                reason="role/needs outputs not built")

# (player, season, team): {field: expected}
GOLDEN = {
    ("Rohit Sharma", 2026, "MI"): {"main_role": "batter", "bat_subtype": "opener"},
    ("Virat Kohli", 2026, "RCB"): {"main_role": "batter", "bat_subtype": "opener"},
    ("Shubman Gill", 2026, "GT"): {"main_role": "batter", "bat_subtype": "opener"},
    ("Ruturaj Gaikwad", 2026, "CSK"): {"main_role": "batter", "bat_subtype": "opener"},
    ("Rinku Singh", 2026, "KKR"): {"main_role": "batter", "bat_subtype": "finisher"},
    ("Tim David", 2026, "RCB"): {"main_role": "batter", "bat_subtype": "finisher"},
    ("MS Dhoni", 2026, "CSK"): {"main_role": "wicketkeeper", "bat_subtype": "finisher"},
    ("Jos Buttler", 2026, "GT"): {"main_role": "wicketkeeper", "bat_subtype": "opener"},
    ("KL Rahul", 2026, "DC"): {"main_role": "wicketkeeper"},
    ("Heinrich Klaasen", 2026, "SRH"): {"main_role": "wicketkeeper"},
    ("Rishabh Pant", 2026, "LSG"): {"main_role": "wicketkeeper", "left_hand_bat": "1"},
    ("Hardik Pandya", 2026, "MI"): {"main_role": "allrounder_genuine", "bowl_type": "pace_right"},
    ("Axar Patel", 2026, "DC"): {"main_role": "allrounder_genuine", "bowl_type": "left_orthodox"},
    ("Ravindra Jadeja", 2026, "RR"): {"main_role": "allrounder_genuine", "bowl_type": "left_orthodox"},
    ("Sunil Narine", 2026, "KKR"): {"bowl_type": "off_spin"},
    ("Rashid Khan", 2026, "GT"): {"bowl_type": "leg_spin", "bat_subtype": "tail"},
    ("Andre Russell", 2025, "KKR"): {"main_role": "allrounder_batting", "bat_subtype": "finisher"},
    ("Jasprit Bumrah", 2026, "MI"): {"main_role": "bowler", "bowl_type": "pace_right", "bat_subtype": "tail"},
    ("Arshdeep Singh", 2026, "PBKS"): {"main_role": "bowler", "bowl_type": "pace_left"},
    ("Trent Boult", 2026, "MI"): {"main_role": "bowler", "bowl_type": "pace_left", "bowl_phase": "powerplay"},
    ("Mitchell Starc", 2026, "DC"): {"main_role": "bowler", "bowl_type": "pace_left"},
    ("Harshal Patel", 2026, "SRH"): {"bowl_type": "pace_right", "bowl_phase": "death"},
    ("T Natarajan", 2024, "SRH"): {"bowl_type": "pace_left", "bowl_phase": "death"},
    ("Kuldeep Yadav", 2026, "DC"): {"main_role": "bowler", "bowl_type": "left_wrist"},
    ("Yuzvendra Chahal", 2026, "PBKS"): {"main_role": "bowler", "bowl_type": "leg_spin", "bowl_phase": "middle"},
    ("Ravi Bishnoi", 2026, "RR"): {"main_role": "bowler", "bowl_type": "leg_spin"},
    ("Ravichandran Ashwin", 2025, "CSK"): {"bowl_type": "off_spin"},
}


@pytest.fixture(scope="module")
def roles():
    return list(csv.DictReader(open(ROLES, encoding="utf-8")))


@pytest.mark.parametrize("key", list(GOLDEN), ids=lambda k: f"{k[0]}-{k[1]}")
def test_golden(roles, key):
    name, season, team = key
    hits = [r for r in roles if r["player"] == name and int(r["season"]) == season and r["team"] == team]
    assert hits, f"{key} missing from player_roles.csv"
    for f, want in GOLDEN[key].items():
        assert hits[0][f] == want, f"{name} {season}: {f} = {hits[0][f]!r}, expected {want!r}"


def test_one_row_per_player_team_season(roles):
    keys = [(r["season"], r["team"], r["player"]) for r in roles]
    assert len(keys) == len(set(keys))


def test_label_consistency(roles):
    for r in roles:
        if r["main_role"] in ("bowler", "allrounder_bowling"):
            assert r["bat_subtype"] == "tail", r["player"]
        if r["bowl_type"]:
            assert r["bowl_group"] == ("pace" if r["bowl_type"].startswith("pace") else "spin")


def test_same_player_same_bowl_type_every_season(roles):
    seen = {}
    for r in roles:
        if r["cricsheet_id"] and r["bowl_type"]:
            assert seen.setdefault(r["cricsheet_id"], r["bowl_type"]) == r["bowl_type"], r["player"]


def test_needs_use_no_purchases(roles):
    """have = counts over retained rows only: recompute one cell and compare."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_team_needs import CELLS
    needs = list(csv.DictReader(open(NEEDS, encoding="utf-8")))
    for n in needs:
        if n["cell"] not in ("pace", "opener", "wicketkeeper"):
            continue
        pre = [r for r in roles if r["season"] == n["season"] and r["team"] == n["team"] and r["source"] == "retained"]
        assert int(n["have"]) == sum(CELLS[n["cell"]](r) for r in pre)


def test_first_season_has_no_baseline():
    needs = list(csv.DictReader(open(NEEDS, encoding="utf-8")))
    first = min(int(n["season"]) for n in needs)
    assert all(n["typical"] == "" and n["need"] == "" for n in needs if int(n["season"]) == first)


def test_borderline_matches_spec(roles):
    """docs/role-rules.md section 10, recomputed from the stored measurements."""
    for r in roles:
        if not r["main_data"]:
            assert r["borderline"] == "0", r["player"]
            continue
        o = int(r["n_balls_bowled"]) / 6 / int(r["n_matches"])   # unrounded; the column is rounded
        m = float(r["median_bat_pos"]) if r["median_bat_pos"] else None
        top = m is not None and m <= 6 and int(r["n_innings"]) >= 0.5 * int(r["n_matches"])
        want = (2.0 <= o < 3.0) or (0.5 <= o < 1.0) or (m is not None and 5.5 <= m <= 6.5) or \
               (o >= 2.5 and not top and m is not None and 7.5 <= m <= 8.5)
        assert r["borderline"] == str(int(want)), r["player"]

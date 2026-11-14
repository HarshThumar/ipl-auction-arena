"""Age, capped status and auction order: known facts as tests."""
import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BIO = ROOT / "data" / "processed" / "players" / "player_bio.csv"
CAPS = ROOT / "data" / "processed" / "players" / "capped_by_season.csv"
ORDER = ROOT / "data" / "processed" / "auction_order" / "lot_order.csv"
pytestmark = pytest.mark.skipif(not (BIO.exists() and CAPS.exists() and ORDER.exists()), reason="not built")


@pytest.fixture(scope="module")
def caps():
    return {(int(r["season"]), r["player"]): r for r in csv.DictReader(open(CAPS, encoding="utf-8"))}


def test_dhoni_birth_date_and_5_year_rule(caps):
    # MS Dhoni, born 7 Jul 1981; last international Jul 2019. CSK retained him as an UNCAPPED
    # player for 2025 under the restored 5-year rule (widely reported, Oct 2024).
    assert caps[(2024, "MS Dhoni")]["capped"] == "capped"
    assert caps[(2025, "MS Dhoni")]["capped"] == "uncapped"
    assert caps[(2025, "MS Dhoni")]["capped_basis"] == "indian_5yr_rule"
    assert float(caps[(2025, "MS Dhoni")]["age_at_auction"]) == pytest.approx(43.38, abs=0.01)


def test_capped_stars(caps):
    for name in ("Jasprit Bumrah", "Virat Kohli", "Pat Cummins"):
        rows = [r for (y, n), r in caps.items() if n == name and y == 2026]
        assert rows and rows[0]["capped"] == "capped", name


def test_uncapped_teenager(caps):
    r = caps[(2025, "Vaibhav Sooryavanshi")]
    assert r["capped"] == "uncapped"
    assert 13 <= float(r["age_at_auction"]) < 14   # born 27 Mar 2011, auction 24 Nov 2024


def test_capped_matches_auction_lists_where_both_exist():
    import json
    caps = {(int(r["season"]), r["cricsheet_id"]): r["capped"] for r in csv.DictReader(open(CAPS, encoding="utf-8"))}
    master = json.loads((ROOT / "data" / "processed" / "master" / "all_auctions_master.json").read_text(encoding="utf-8"))
    pairs = [(caps[(r["season"], r["cricsheet_id"])], r["capped"]) for r in master
             if r.get("cricsheet_id") and r.get("capped") in ("capped", "uncapped") and (r["season"], r["cricsheet_id"]) in caps]
    agree = sum(a == b for a, b in pairs)
    assert len(pairs) > 500 and agree / len(pairs) >= 0.99, f"{agree}/{len(pairs)}"


def test_2024_order_moves_forward_through_sets():
    rows = [r for r in csv.DictReader(open(ORDER, encoding="utf-8")) if r["season"] == "2024" and r["seq"] and r["set_no"]]
    sets = [int(r["set_no"]) for r in sorted(rows, key=lambda r: int(r["seq"]))]
    assert len(sets) > 30 and sets == sorted(sets)


def test_2025_starts_with_marquee_set_1():
    first = [r["player"] for r in csv.DictReader(open(ORDER, encoding="utf-8")) if r["season"] == "2025"][:6]
    assert set(first) == {"Rishabh Pant", "Shreyas Iyer", "Mitchell Starc", "Jos Buttler", "Arshdeep Singh", "Kagiso Rabada"}

"""Unit and property tests for Auctioneer and RulesEngine."""

import pytest
from hypothesis import given, strategies as st

from src.engine.rules import PlayerLot, RulesEngine, TeamState
from src.engine.auctioneer import Auctioneer, EventType


def test_rules_increment_steps():
    rules = RulesEngine()
    # Below 100 lakh: step is 5
    assert rules.get_next_increment(50) == 5
    assert rules.get_next_valid_bid(50) == 55

    # 100 to 200 lakh: step is 10
    assert rules.get_next_increment(100) == 10
    assert rules.get_next_valid_bid(100) == 110

    # 200 to 500 lakh: step is 20
    assert rules.get_next_increment(200) == 20
    assert rules.get_next_valid_bid(200) == 220

    # Above 500 lakh: step is 25
    assert rules.get_next_increment(500) == 25
    assert rules.get_next_valid_bid(500) == 525
    assert rules.get_next_valid_bid(1200) == 1225


def test_max_legal_bid_calculation():
    team = TeamState(
        team_code="CSK",
        purse_remaining_lakh=5000,
        retained_count=10,
        retained_overseas=3,
    )
    # squad size is 10. Needs 8 more to reach min_squad (18).
    # Reserve needed for 7 players at min_base 30 lakh = 210 lakh.
    # Max legal bid = 5000 - 210 = 4790 lakh.
    assert team.compute_max_legal_bid(min_squad=18, min_base_price_lakh=30) == 4790

    # When squad is already >= 17, needs <= 1 player, so entire purse is legal
    team.retained_count = 17
    assert team.compute_max_legal_bid(min_squad=18, min_base_price_lakh=30) == 5000


def test_single_lot_sold():
    teams = {
        "CSK": TeamState(team_code="CSK", purse_remaining_lakh=5000),
        "MI": TeamState(team_code="MI", purse_remaining_lakh=5000),
    }
    auctioneer = Auctioneer(season=2025, teams=teams, seed=123)

    lot = PlayerLot(
        lot_id="LOT_01",
        player_name="Star Player",
        role="allrounder",
        is_overseas=False,
        base_price_lakh=200,
    )

    # Policy: CSK bids up to 300, MI bids up to 260
    def policy(team_code: str, cur_lot: PlayerLot, price_lakh: int, leader: str) -> bool:
        if team_code == "CSK" and price_lakh <= 300:
            return True
        if team_code == "MI" and price_lakh <= 260:
            return True
        return False

    winner, hammer, paid = auctioneer.conduct_lot(lot, policy)

    assert winner == "CSK"
    assert hammer > 200
    assert paid == hammer
    assert teams["CSK"].purse_remaining_lakh == 5000 - paid
    assert len(teams["CSK"].squad) == 1


def test_overseas_mini_cap_applied():
    teams = {
        "RCB": TeamState(team_code="RCB", purse_remaining_lakh=5000),
        "KKR": TeamState(team_code="KKR", purse_remaining_lakh=5000),
    }
    # 2026 is a mini auction
    auctioneer = Auctioneer(season=2026, teams=teams, seed=42)

    lot = PlayerLot(
        lot_id="LOT_02",
        player_name="Overseas Star",
        role="allrounder",
        is_overseas=True,
        base_price_lakh=200,
    )

    # Both willing to bid up to 2500 lakh (25 cr)
    def policy(team_code: str, cur_lot: PlayerLot, price_lakh: int, leader: str) -> bool:
        return price_lakh <= 2000

    winner, hammer, paid = auctioneer.conduct_lot(lot, policy)

    assert winner is not None
    assert hammer > 1800
    # Overseas mini cap: hammer > 1800 => paid = 1800
    assert paid == 1800
    assert teams[winner].purse_remaining_lakh == 5000 - 1800


@given(
    purse=st.integers(min_value=1000, max_value=12000),
    retained=st.integers(min_value=0, max_value=17),
)
def test_hypothesis_max_legal_bid_invariants(purse: int, retained: int):
    team = TeamState(
        team_code="TEST",
        purse_remaining_lakh=purse,
        retained_count=retained,
    )
    max_bid = team.compute_max_legal_bid(min_squad=18, min_base_price_lakh=30)
    assert max_bid >= 0
    assert max_bid <= purse
    # Remainder after max_bid must be enough for needed - 1 slots
    needed = team.min_slots_needed(18)
    if needed > 1:
        assert (purse - max_bid) >= (needed - 1) * 30

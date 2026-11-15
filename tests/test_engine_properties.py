"""Property tests for the auction engine (failure register H3, A1, A15).

Random pools, seasons 2022-2026, mixed bidders (random with garbage answers, valuation, pass).
After the run the event log is replayed lot by lot and every rule is checked.

Note on the squad minimum: "squad >= 18 at the end" is NOT a property here. A random or passing
bidder can leave the squad short, and the minimum is the franchise's obligation, not something the
room can force. The room only guarantees that a bid never strands a team (max legal bid, A1). The
18-player check belongs to the real-auction replay (tests for replay.py), where outcomes are given.
"""
from __future__ import annotations

from hypothesis import HealthCheck, given, settings, strategies as st

from src.engine import events as E
from src.engine import load_season, run_auction
from src.engine.events import rebuild_teams
from src.engine.ledger import Treasurer
from src.engine.synth import load_teams, make_bidders, make_pool

SETTINGS = dict(derandomize=True, deadline=None, database=None,
                suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])

seasons = st.sampled_from([2022, 2023, 2024, 2025, 2026])
kinds = st.sampled_from(["mixed", "random", "valuation", "pass"])


def play(season: int, seed: int, n: int, kind: str):
    rules = load_season(season)
    teams = load_teams(rules)
    pool = make_pool(rules, n, seed, sorted(teams))
    res = run_auction(rules, pool, teams, make_bidders(kind, sorted(teams), seed), seed=seed)
    return rules, res


def check_log(rules, res) -> None:
    """Replay the log, keeping a copy of every team, and check each rule at the moment it applies."""
    tr = Treasurer(rules)
    teams = {k: v.copy() for k, v in res.start.items()}
    base = {}                    # lot_id -> (base price, player overseas, player key)
    sold_lots, sold_keys = set(), set()
    lot_ids = [e.lot_id for e in res.log.of_type(E.LOT_ANNOUNCED)]
    assert len(lot_ids) == len(set(lot_ids)), "lot ids are not unique"

    def check_price(lot_id: str, team: str, price: int, what: str) -> None:
        b, overseas, key = base[lot_id]
        t = teams[team]
        assert rules.ladder.on_path(b, price), f"{what} {price} off the grid from base {b}"
        assert price <= tr.max_legal_bid(t), f"{what} {price} above max legal bid {tr.max_legal_bid(t)} of {team}"
        assert tr.slots_left(t) > 0, f"{what} by {team} with a full squad"
        if overseas:
            assert tr.overseas_slots_left(t) > 0, f"{what} by {team} with no overseas slot"

    for e in res.log.events:
        if e.type == E.LOT_ANNOUNCED:
            base[e.lot_id] = (e.data["base"], e.data["overseas"], e.data["key"])
        elif e.type in (E.BID, E.RTM_RAISE):
            check_price(e.lot_id, e.team, e.price, e.type)
        elif e.type == E.SOLD:
            assert e.lot_id not in sold_lots, "two SOLD events for one lot"
            assert e.data["key"] not in sold_keys, "a player sold twice"
            sold_lots.add(e.lot_id)
            sold_keys.add(e.data["key"])
            check_price(e.lot_id, e.team, e.price, "hammer")
            t = teams[e.team]
            t.purse_lakh -= e.price
            t.squad += 1
            t.overseas += int(e.data["overseas"])
            t.bought.append(e.data["key"])
            card = e.data.get("rtm_card")
            if card:
                from src.engine.season_rules import RtmCards
                t.rtm = RtmCards(**{**t.rtm.__dict__, card: getattr(t.rtm, card) - 1})
            # after every lot: the three hard limits and the RTM cards
            for x in teams.values():
                assert x.purse_lakh >= 0, f"{x.code} purse {x.purse_lakh} < 0"
                assert x.squad <= rules.squad_max, f"{x.code} squad {x.squad}"
                assert x.overseas <= rules.overseas_max, f"{x.code} overseas {x.overseas}"
                assert min(x.rtm.capped, x.rtm.uncapped, x.rtm.any) >= 0, f"{x.code} RTM cards negative"
            assert e.data["purse_after"] == t.purse_lakh, "purse_after in SOLD does not match the replay"

    # the live end state equals the state rebuilt from the log alone (H3)
    rebuilt = rebuild_teams(res.log.events, res.start)
    assert rebuilt == res.room.teams
    assert teams == res.room.teams
    assert res.violations() == []          # purse, squad max, overseas max (not the 18 minimum)


@settings(max_examples=60, **SETTINGS)
@given(season=seasons, seed=st.integers(0, 10_000), n=st.integers(20, 90), kind=kinds)
def test_rules_hold_for_random_auctions(season, seed, n, kind):
    rules, res = play(season, seed, n, kind)
    check_log(rules, res)


@settings(max_examples=40, **SETTINGS)
@given(season=seasons, seed=st.integers(0, 10_000), n=st.integers(20, 70), kind=kinds)
def test_same_seed_same_log(season, seed, n, kind):
    _, a = play(season, seed, n, kind)
    _, b = play(season, seed, n, kind)
    assert a.log.digest() == b.log.digest()
    assert list(a.log.lines()) == list(b.log.lines())


@settings(max_examples=15, **SETTINGS)
@given(season=seasons, seed=st.integers(0, 10_000))
def test_different_seed_usually_differs(season, seed):
    _, a = play(season, seed, 40, "valuation")
    _, b = play(season, seed + 1, 40, "valuation")
    # not a hard law, but two seeds giving identical logs would mean the seed is ignored
    assert a.log.digest() != b.log.digest()


@settings(max_examples=40, **SETTINGS)
@given(season=st.just(2025), seed=st.integers(0, 10_000), n=st.integers(30, 100))
def test_rtm_season_cards_never_negative(season, seed, n):
    rules, res = play(season, seed, n, "mixed")
    check_log(rules, res)
    for t in res.room.teams.values():
        assert min(t.rtm.capped, t.rtm.uncapped, t.rtm.any) >= 0

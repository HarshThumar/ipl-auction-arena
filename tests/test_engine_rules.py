"""Focused, deterministic tests of the auction-room rules (hand-built players, teams and scripted bidders).

Rules and their sources: data/reference/engine_rules.yaml, docs/L1-plan.md section 3. Money in integer lakhs.
"""
from __future__ import annotations

import dataclasses

import pytest

from src.engine import events as E
from src.engine.auction import run_auction
from src.engine.ledger import Player, Team, Treasurer
from src.engine.lot import Room
from src.engine.season_rules import RtmCards, load_season


# ------------------------------------------------------------------ helpers
class Scripted:
    """Answers per decision point. A value is a dict, a list (one item per call, last repeats),
    or a callable(view). Unlisted points get the safe default. Records every view it was asked."""

    DEFAULT = {"enter": {"action": "stay_out"}, "huddle": {"action": "drop"}, "final_two": {"action": "stay"},
               "rtm_use": {"action": "decline"}, "rtm_raise": {"action": "no_raise"},
               "rtm_match": {"action": "decline"}, "tie_break": {"amount_lakh": 0}, "nominate": {"players": []}}

    def __init__(self, **answers):
        self.answers = answers
        self.views = []

    def calls(self, point):
        return [v for v in self.views if v["point"] == point]

    def decide(self, view):
        self.views.append(view)
        pt = view["point"]
        a = self.answers.get(pt, self.DEFAULT[pt])
        n = len(self.calls(pt)) - 1
        if callable(a):
            return a(view)
        if isinstance(a, list):
            return a[min(n, len(a) - 1)]
        return a


def bid(c):
    return {"action": "bid", "ceiling_lakh": c}


def player(key="p", base=50, overseas=False, capped=True, set_no=1, rtm_team=None):
    return Player(key, key.upper(), overseas, capped, base, set_no=set_no, rtm_team=rtm_team)


def team(code, purse=10_000, squad=18, overseas=0, rtm=RtmCards()):
    return Team(code, purse, squad, overseas, rtm)


def room(season, teams, bidders, seed=0):
    return Room(load_season(season), {t.code: t for t in teams}, bidders, seed)


# ------------------------------------------------------------------ ladder
def test_grid_snapping_2023_style_grid():
    lad = load_season(2026).ladder
    assert lad.next_price(125) == 130
    assert lad.next_price(130) == 140
    assert lad.next_price(190) == 200
    assert lad.next_price(200) == 220
    assert lad.next_price(95) == 100
    assert lad.next_price(500) == 520          # 2024 / 2026: 20-lakh steps above 5 cr


def test_grid_2025_band_above_5_cr():
    lad = load_season(2025).ladder
    assert lad.next_price(500) == 525
    assert lad.next_price(525) == 550
    assert lad.next_price(480) == 500
    assert lad.next_price(200) == 220


def test_ladder_path_on_path_previous():
    lad = load_season(2026).ladder
    assert lad.path(125, 160) == [125, 130, 140, 150, 160]
    assert lad.path(200, 200) == [200]
    assert lad.on_path(125, 130) and lad.on_path(125, 160)
    assert not lad.on_path(125, 135)
    assert not lad.on_path(125, 120)           # below the base
    assert lad.previous(125, 140) == 130
    assert lad.previous(125, 125) is None
    assert lad.previous(125, 135) is None      # not on the path


# ------------------------------------------------------------------ treasurer
def test_max_legal_bid_formula():
    tr = Treasurer(load_season(2026))          # min base 30
    assert tr.max_legal_bid(team("A", purse=1000, squad=15)) == 1000 - 2 * 30      # needs 3, keeps 2 slots' money
    assert tr.max_legal_bid(team("A", purse=1000, squad=17)) == 1000               # needs 1: nothing reserved
    assert tr.max_legal_bid(team("A", purse=1000, squad=18)) == 1000               # already at the minimum
    assert tr.max_legal_bid(team("A", purse=5000, squad=0)) == 5000 - 17 * 30
    assert tr.max_legal_bid(team("A", purse=100, squad=0)) == 0                    # reserve exceeds the purse
    assert Treasurer(load_season(2025)).max_legal_bid(team("A", purse=1000, squad=15)) == 1000 - 2 * 30


def test_squad_and_overseas_limits_block_bids():
    tr = Treasurer(load_season(2026))
    full = team("A", squad=25)
    eight = team("B", overseas=8)
    ind, ovs = player(overseas=False), player(overseas=True)
    assert not tr.can_take(full, ind) and tr.max_affordable(full, ind) == 0
    assert tr.can_take(eight, ind) and not tr.can_take(eight, ovs)
    assert not tr.can_bid(eight, ovs, 50) and tr.can_bid(eight, ind, 50)
    assert not tr.can_bid(team("C", purse=100), ind, 101)


def test_full_and_overseas_capped_teams_are_not_asked_in_a_lot():
    full, eight, ok = Scripted(enter=bid(100)), Scripted(enter=bid(100)), Scripted(enter=bid(100))
    r = room(2026, [team("F", squad=25), team("E", overseas=8), team("O")], {"F": full, "E": eight, "O": ok})
    res = r.run_lot(player(overseas=True), "L1")
    assert not full.calls("enter") and not eight.calls("enter")
    assert res.winner == "O"
    eight2 = Scripted(enter=bid(100))
    r = room(2026, [team("E", overseas=8), team("O")], {"E": eight2, "O": Scripted()})
    r.run_lot(player(overseas=False), "L2")
    assert eight2.calls("enter")               # an Indian player: the overseas-full team is asked


# ------------------------------------------------------------------ purse and overseas pay cap
def _green(season):
    a, b = Scripted(enter=bid(2520)), Scripted(enter=[{"action": "stay_out"}, bid(2500)])   # B joins at going once
    r = room(season, [team("A", purse=5000), team("B", purse=5000)], {"A": a, "B": b})
    return r, r.run_lot(player("green", base=200, overseas=True), "G")


def test_overseas_pay_cap_2026_green():
    r, res = _green(2026)
    assert (res.winner, res.hammer, res.paid) == ("A", 2520, 1800)
    assert r.teams["A"].purse_lakh == 5000 - 2520      # purse charged the hammer, not the paid amount
    sold = r.log.of_type(E.SOLD)[0]
    assert sold.price == 2520 and sold.data["paid"] == 1800


def test_no_pay_cap_for_indians_in_2026():
    a, b = Scripted(enter=bid(2520)), Scripted(enter=[{"action": "stay_out"}, bid(2500)])
    r = room(2026, [team("A", purse=5000), team("B", purse=5000)], {"A": a, "B": b})
    res = r.run_lot(player("ind", base=200, overseas=False), "G")
    assert (res.hammer, res.paid) == (2520, 2520)


def test_no_pay_cap_in_2025():
    a, b = Scripted(enter=bid(2525)), Scripted(enter=[{"action": "stay_out"}, bid(2500)])
    r = room(2025, [team("A", purse=5000), team("B", purse=5000)], {"A": a, "B": b})
    res = r.run_lot(player("ovs", base=200, overseas=True), "G")
    assert (res.winner, res.hammer, res.paid) == ("A", 2525, 2525)
    assert r.teams["A"].purse_lakh == 5000 - 2525


# ------------------------------------------------------------------ late entry, re-entry
def test_late_entry_at_going_once():
    a, b, c = Scripted(enter=bid(100)), Scripted(enter=[{"action": "stay_out"}, bid(80)]), Scripted()
    r = room(2023, [team("A"), team("B"), team("C")], {"A": a, "B": b, "C": c})
    res = r.run_lot(player(base=50), "L")
    assert [t for t, _ in res.bids][:2] == ["A", "B"]          # A opened alone, B joined late
    assert res.bids[0] == ("A", 50) and res.bids[1] == ("B", 55)
    assert (res.winner, res.hammer) == ("A", 80)      # 50 A, 55 B, ... B 75, A 80, B cannot reach 85
    first, second = b.calls("enter")
    assert first["price_now_lakh"] is None and second["price_now_lakh"] == 50
    assert r.log.of_type(E.GOING_ONCE)[0].price == 50
    assert len(c.calls("enter")) == 2                          # the one who never joined was offered both times


def test_re_entry_once_per_lot():
    a = Scripted(enter=[bid(70), bid(200), bid(500)])
    b = Scripted(enter=[bid(55), bid(100), bid(500)])
    r = room(2023, [team("A"), team("B")], {"A": a, "B": b})
    res = r.run_lot(player(base=50), "L")
    assert res.winner == "A" and res.hammer >= 100
    assert len(a.calls("enter")) == 2 and len(b.calls("enter")) == 2     # announce + one going-once offer, never a third


def test_no_going_once_offer_to_a_team_that_cannot_afford():
    poor = Scripted(enter=bid(100))
    r = room(2023, [team("A"), team("P", purse=40)], {"A": Scripted(enter=bid(60)), "P": poor})
    r.run_lot(player(base=50), "L")
    assert not poor.calls("enter")


# ------------------------------------------------------------------ huddle, ceiling, final two
def test_huddle_raise_once_then_auto_drop():
    a = Scripted(enter=bid(50), huddle={"action": "raise_ceiling", "new_ceiling_lakh": 70})
    b = Scripted(enter=bid(100))
    r = room(2023, [team("A"), team("B")], {"A": a, "B": b})
    res = r.run_lot(player(base=50), "L")
    assert len(a.calls("huddle")) == 1                          # the second time it simply drops
    assert res.winner == "B" and 70 <= res.hammer <= 75
    assert max(p for t, p in res.bids if t == "A") <= 70


def test_invalid_second_huddle_raise_is_logged_not_applied():
    # the harness refuses a second raise_ceiling (view says ceiling_raised); room never asks anyway
    a = Scripted(enter=bid(50), huddle={"action": "raise_ceiling", "new_ceiling_lakh": 60})
    r = room(2023, [team("A"), team("B")], {"A": a, "B": Scripted(enter=bid(500))})
    r.run_lot(player(base=50), "L")
    assert all(not v["ceiling_raised"] for v in a.calls("huddle"))


def test_ceiling_above_max_affordable_is_cut():
    a = Scripted(enter=bid(10 ** 6))
    b = Scripted(enter=bid(500))
    r = room(2023, [team("A", purse=100), team("B", purse=5000)], {"A": a, "B": b})
    res = r.run_lot(player(base=50), "L")
    assert max(p for t, p in res.bids if t == "A") <= 100
    assert res.winner == "B" and res.hammer in (100, 110)
    cut = [e for e in r.log.of_type(E.DECISION) if e.team == "A" and e.data["point"] == "enter"][0]
    assert cut.data["decision"]["ceiling_lakh"] == 100 and "cut" in cut.data["reason"]


@pytest.mark.parametrize("seed", range(6))
def test_final_two_drop_by_leader_never_raises_again(seed):
    # enter: first offer bids, any later offer (going-once re-entry) stays out, so only final_two is tested
    a = Scripted(enter=[bid(500), {"action": "stay_out"}], final_two={"action": "drop"})
    b = Scripted(enter=bid(500), final_two={"action": "stay"})
    r = room(2023, [team("A"), team("B")], {"A": a, "B": b}, seed=seed)
    res = r.run_lot(player(base=50), "L")
    assert len(a.calls("final_two")) == 1 and len(b.calls("final_two")) == 1
    assert sum(t == "A" for t, _ in res.bids) <= 1                # at most the opening bid
    assert res.winner == "B" and res.hammer in (50, 55)


# ------------------------------------------------------------------ seeded pick
def _three(seed):
    bs = {c: Scripted(enter=bid(100)) for c in "ABC"}
    r = room(2023, [team(c) for c in "ABC"], bs, seed=seed)
    return r.run_lot(player(base=50), "L")


def test_simultaneous_raise_is_a_seeded_pick():
    first = {s: _three(s).bids[0][0] for s in range(30)}
    assert len(set(first.values())) > 1                           # team order really shuffles
    for s in (0, 1, 7):
        assert _three(s).bids == _three(s).bids                   # same seed, same bids
    assert _three(3).bids[0][0] == _three(3).bids[0][0]


# ------------------------------------------------------------------ silent tie-breaker
def _tie(amounts_a, amounts_b, seed=0):
    a = Scripted(enter=bid(100), tie_break=amounts_a)
    b = Scripted(enter=bid(100), tie_break=amounts_b)
    r = room(2023, [team("A", purse=100), team("B", purse=100)], {"A": a, "B": b}, seed=seed)
    return r, r.run_lot(player(base=50), "L"), a, b


def test_silent_tie_breaker_higher_sealed_amount_wins_at_current_price():
    r, res, a, b = _tie([{"amount_lakh": 5}], [{"amount_lakh": 7}])
    assert (res.winner, res.hammer) == ("B", 100)
    assert r.teams["B"].purse_lakh == 0                           # charged the price only, not the sealed amount
    assert r.teams["A"].purse_lakh == 100
    tb = r.log.of_type(E.TIE_BREAK)
    assert len(tb) == 1 and tb[0].data["attempt"] == 1


def test_silent_tie_breaker_equal_repeats_then_resolves():
    r, res, a, b = _tie([{"amount_lakh": 5}, {"amount_lakh": 5}, {"amount_lakh": 9}],
                        [{"amount_lakh": 5}, {"amount_lakh": 5}, {"amount_lakh": 3}])
    assert res.winner == "A" and res.hammer == 100
    assert len(a.calls("tie_break")) == 3 and len(b.calls("tie_break")) == 3
    assert r.log.of_type(E.TIE_BREAK)[0].data["attempt"] == 3


def test_silent_tie_breaker_still_equal_is_a_seeded_pick():
    winners = {s: _tie([{"amount_lakh": 4}], [{"amount_lakh": 4}], seed=s)[1].winner for s in range(20)}
    assert set(winners.values()) == {"A", "B"}
    assert winners[5] == _tie([{"amount_lakh": 4}], [{"amount_lakh": 4}], seed=5)[1].winner
    r, res, a, b = _tie([{"amount_lakh": 4}], [{"amount_lakh": 4}], seed=2)
    assert r.log.of_type(E.TIE_BREAK)[0].data["attempt"] == "seeded_pick"


def test_no_tie_breaker_when_a_team_can_still_raise():
    r = room(2023, [team("A", purse=100), team("B", purse=5000)],
             {"A": Scripted(enter=bid(100)), "B": Scripted(enter=bid(100))})
    r.run_lot(player(base=50), "L")
    assert not r.log.of_type(E.TIE_BREAK)


# ------------------------------------------------------------------ RTM (2025)
def _rtm(a_script, r_script, rtm=RtmCards(capped=1), r_purse=10_000, pl=None):
    a = Scripted(enter=bid(500), **a_script)
    rt = Scripted(**r_script)
    rm = room(2025, [team("A"), team("R", purse=r_purse, rtm=rtm)], {"A": a, "R": rt})
    res = rm.run_lot(pl or player("jfm", base=100, rtm_team="R"), "L")
    return rm, res, a, rt


def test_rtm_no_raise_gives_rtm_team_the_player_at_hammer_and_spends_card():
    rm, res, a, rt = _rtm({}, {"rtm_use": {"action": "use"}})
    assert (res.winner, res.hammer, res.rtm_card) == ("R", 100, "capped")
    assert rm.teams["R"].rtm.capped == 0 and rm.teams["R"].purse_lakh == 10_000 - 100
    assert rm.teams["A"].purse_lakh == 10_000
    assert not rt.calls("rtm_match")                              # nothing to match


def _raise_first(view):
    return {"action": "raise", "price_lakh": view["allowed_raise_prices"][0]}


def test_rtm_raise_then_match():
    rm, res, a, rt = _rtm({"rtm_raise": _raise_first}, {"rtm_use": {"action": "use"}, "rtm_match": {"action": "match"}})
    assert (res.winner, res.hammer, res.rtm_card) == ("R", 110, "capped")
    assert rm.teams["R"].rtm.capped == 0 and rm.teams["R"].purse_lakh == 10_000 - 110
    assert rm.teams["A"].purse_lakh == 10_000


def test_rtm_raise_then_decline_keeps_card():
    rm, res, a, rt = _rtm({"rtm_raise": _raise_first}, {"rtm_use": {"action": "use"}, "rtm_match": {"action": "decline"}})
    assert (res.winner, res.hammer, res.rtm_card) == ("A", 110, None)
    assert rm.teams["R"].rtm.capped == 1 and rm.teams["R"].purse_lakh == 10_000
    assert rm.teams["A"].purse_lakh == 10_000 - 110


def test_rtm_team_declines_to_use_card():
    rm, res, a, rt = _rtm({}, {"rtm_use": {"action": "decline"}})
    assert (res.winner, res.hammer) == ("A", 100)
    assert rm.teams["R"].rtm.capped == 1 and not a.calls("rtm_raise")


def test_rtm_wrong_card_type_is_not_asked():
    rm, res, a, rt = _rtm({}, {"rtm_use": {"action": "use"}}, rtm=RtmCards(uncapped=1))   # capped player, uncapped card
    assert not rt.calls("rtm_use") and res.winner == "A"
    rm, res, a, rt = _rtm({}, {"rtm_use": {"action": "use"}}, rtm=RtmCards())               # no card at all
    assert not rt.calls("rtm_use") and res.winner == "A"


def test_rtm_any_card_covers_either_type_and_uncapped_card_covers_uncapped():
    rm, res, a, rt = _rtm({}, {"rtm_use": {"action": "use"}}, rtm=RtmCards(any=1))
    assert res.winner == "R" and res.rtm_card == "any"
    unc = player("u", base=100, capped=False, rtm_team="R")
    rm, res, a, rt = _rtm({}, {"rtm_use": {"action": "use"}}, rtm=RtmCards(uncapped=1), pl=unc)
    assert res.winner == "R" and res.rtm_card == "uncapped"


def test_rtm_team_cannot_afford_hammer_is_not_asked():
    rm, res, a, rt = _rtm({}, {"rtm_use": {"action": "use"}}, r_purse=50)
    assert not rt.calls("rtm_use") and res.winner == "A"


def test_rtm_team_cannot_afford_the_raise():
    rm, res, a, rt = _rtm({"rtm_raise": _raise_first}, {"rtm_use": {"action": "use"}, "rtm_match": {"action": "match"}},
                          r_purse=105)
    assert (res.winner, res.hammer, res.rtm_card) == ("A", 110, None)
    assert not rt.calls("rtm_match") and rm.teams["R"].rtm.capped == 1


def test_rtm_not_used_in_seasons_without_rtm():
    a, rt = Scripted(enter=bid(500)), Scripted(rtm_use={"action": "use"})
    rm = room(2026, [team("A"), team("R", rtm=RtmCards(capped=1))], {"A": a, "R": rt})
    res = rm.run_lot(player("x", base=100, rtm_team="R"), "L")
    assert res.winner == "A" and not rt.calls("rtm_use")


def test_2025_rtm_cards_in_rules():
    cards = load_season(2025).rtm_cards
    assert sum(c.capped + c.uncapped + c.any for c in cards.values()) == 14      # 14 cards in total (press)
    assert cards["PBKS"].capped == 4 and cards["RCB"].any == 1
    assert load_season(2026).rtm_cards == {}


# ------------------------------------------------------------------ accelerated rounds, lot ids
def _rules_two_main(rounds=2):
    return dataclasses.replace(load_season(2026), accelerated_after=2, accelerated_rounds=rounds)


class Wanter:
    """Bids on players in `want`; nominates per round from `noms`."""

    def __init__(self, want=(), noms=None):
        self.want, self.noms = set(want), noms or {}
        self.entered = []

    def decide(self, view):
        pt = view["point"]
        if pt == "enter":
            self.entered.append(view["lot_id"])
            return bid(100) if view["player"]["key"] in self.want else {"action": "stay_out"}
        if pt == "nominate":
            return {"players": [k for k in self.noms.get(view["round"], []) if k in view["eligible_players"]]}
        return Scripted.DEFAULT[pt]


def test_accelerated_rounds_union_list_order_renomination_and_unique_ids():
    pool = [player(f"p{i}", set_no=i) for i in range(1, 6)]
    teams = {c: team(c, squad=10) for c in "AB"}
    bidders = {"A": Wanter(want=["p1", "p4"], noms={2: ["p4", "p2"], 3: ["p2"]}),
               "B": Wanter(want=["p3"], noms={2: ["p3", "p4"], 3: ["p2", "p5"]})}
    res = run_auction(_rules_two_main(), pool, teams, bidders, seed=1)
    called = [(l.lot_id, l.sold) for l in res.lots]
    ids = [i for i, _ in called]
    assert ids[:2] == ["2026-R1-p1", "2026-R1-p2"]                 # main phase: only 2 lots, in set order
    assert ids[2:5] == ["2026-R2-p2", "2026-R2-p3", "2026-R2-p4"]  # union of nominations, list order, p2 re-called
    assert ids[5:] == ["2026-R3-p2", "2026-R3-p5"]                 # unsold p2 can be nominated again
    assert len(set(ids)) == len(ids)
    sold = {l.player.key: l.winner for l in res.lots if l.sold}
    assert sold == {"p1": "A", "p3": "B", "p4": "A"}
    assert [l.player.key for l in res.lots if not l.sold] == ["p2", "p2", "p2", "p5"]
    nom = res.log.of_type(E.NOMINATIONS)[0]
    assert nom.data["round"] == 2


def test_accelerated_round_limit():
    pool = [player(f"p{i}", set_no=i) for i in range(1, 5)]
    teams = {c: team(c, squad=10) for c in "AB"}
    bidders = {"A": Wanter(noms={2: ["p3"], 3: ["p4"]}), "B": Wanter()}
    res = run_auction(_rules_two_main(rounds=1), pool, teams, bidders, seed=1)
    assert [l.lot_id for l in res.lots] == ["2026-R1-p1", "2026-R1-p2", "2026-R2-p3"]


def test_unique_lot_ids_for_repeated_calls_explicit_order():
    p = player("dup")
    teams = {c: team(c) for c in "AB"}
    res = run_auction(load_season(2026), [p], teams, {"A": Wanter(), "B": Wanter()}, seed=0,
                      order=[(p, 1), (p, 1), (p, 2)])
    assert [l.lot_id for l in res.lots] == ["2026-R1-dup", "2026-R1-dup-2", "2026-R2-dup"]


def test_auction_stops_when_all_teams_are_full():
    pool = [player(f"p{i}", set_no=i) for i in range(1, 6)]
    teams = {c: team(c, squad=24) for c in "AB"}
    rules = dataclasses.replace(load_season(2026), accelerated_after=None)
    res = run_auction(rules, pool, teams, {c: Wanter(want=[p.key for p in pool]) for c in "AB"}, seed=3)
    assert len(res.lots) == 2 and all(l.sold for l in res.lots)
    assert {l.winner for l in res.lots} == {"A", "B"}
    assert not res.violations()

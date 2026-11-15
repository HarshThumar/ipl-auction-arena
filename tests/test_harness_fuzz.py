"""Unit-fuzz of the bidder harness (failure register A10 and A16: invalid-action rate).

200 synthetic but realistic decision states, covering all 8 decision points. Each gets valid,
boundary and garbage answers through `bidder_api.ask`. The harness must never raise, and every
invalid answer must come back as the safe default with valid=False and a reason.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List

import pytest

from src.engine import events as E
from src.engine import load_season, run_auction
from src.engine.bidder_api import DEFAULTS, POINTS, SCHEMAS, ask, validate
from src.engine.bidders import RandomBidder
from src.engine.synth import load_teams, make_pool

TEAMS = ["CSK", "MI", "RCB", "KKR", "DC", "GT", "LSG", "PBKS", "RR", "SRH"]


# ------------------------------------------------------------------ a tiny JSON-schema check
def schema_ok(schema: Dict[str, Any], x: Any) -> bool:
    """Just the subset the SCHEMAS use: object, properties, required, enum, integer, minimum, array, string."""
    if "enum" in schema:
        return x in schema["enum"]
    t = schema.get("type")
    if t == "integer":
        return isinstance(x, int) and not isinstance(x, bool) and x >= schema.get("minimum", -math.inf)
    if t == "string":
        return isinstance(x, str)
    if t == "array":
        return isinstance(x, list) and all(schema_ok(schema["items"], i) for i in x)
    if t == "object":
        if not isinstance(x, dict) or any(k not in x for k in schema.get("required", [])):
            return False
        return all(schema_ok(sub, x[k]) for k, sub in schema.get("properties", {}).items() if k in x)
    return True


# ------------------------------------------------------------------ synthetic states
def make_view(point: str, rng: random.Random) -> Dict[str, Any]:
    purse = rng.choice([40, 300, 1200, 4340, 9000, 12500])
    squad = rng.randint(14, 25)
    need = max(0, 18 - squad)
    slots = 25 - squad
    ovs = rng.randint(0, 8)
    base = rng.choice([20, 30, 50, 75, 100, 200])
    to_bid = base + rng.choice([0, 0, 5, 10, 20, 100])
    aff = max(0, purse - max(0, need - 1) * 30) if slots > 0 else 0
    keys = [f"p{i:03d}" for i in range(rng.randint(0, 30))]
    view: Dict[str, Any] = {
        "point": point, "season": 2026, "auction_type": "mini", "lot_id": f"2026-R1-p{rng.randint(0, 99):03d}",
        "round": rng.choice([1, 2, 3]),
        "player": {"key": "p001", "name": "Player 001", "role": "bowler", "overseas": rng.random() < 0.4,
                   "capped": rng.random() < 0.5, "base_lakh": base, "set_code": "S1"},
        "price_now_lakh": None if to_bid == base else to_bid - 5, "leader": rng.choice([None, "MI"]),
        "price_to_bid": to_bid,
        "you": {"team": rng.choice(TEAMS), "purse_lakh": purse, "squad": squad, "overseas": ovs,
                "players_needed": need, "slots_left": slots, "overseas_slots_left": 8 - ovs,
                "max_affordable_lakh": aff, "purse_after_bid_lakh": purse - to_bid},
        "your_ceiling_lakh": None, "ceiling_raised": rng.random() < 0.3,
        "bids_so_far": [], "board": [], "recent_lots": [],
    }
    if point == "rtm_raise":
        view["allowed_raise_prices"] = [to_bid + 10 * i for i in range(1, rng.randint(1, 5))] if rng.random() < 0.8 else []
        view["rtm_team"] = "MI"
        view["price_to_bid"] = None
    if point in ("rtm_use", "rtm_match"):
        view["rtm_card"] = rng.choice(["capped", "uncapped", "any"])
    if point == "tie_break":
        view["price_to_bid"] = None
        view["tied_with"] = ["CSK", "MI"]
    if point == "nominate":
        view["eligible_players"] = keys
        view.pop("player"), view.pop("price_to_bid")
    return view


def answers(point: str, view: Dict[str, Any]) -> List[Any]:
    """Valid, boundary and garbage answers for one state."""
    to_bid = view.get("price_to_bid") or 0
    aff = view["you"]["max_affordable_lakh"]
    out: List[Any] = []
    if point == "enter":
        for key in ("ceiling_lakh", "limit_lakh"):
            a = "bid" if key == "ceiling_lakh" else "push"
            for c in (to_bid, to_bid + 5, aff, aff + 1, aff - 1, to_bid - 1, 0, -1, 10 ** 12, "250", " 250 ", 250.0,
                      250.5, True, None, [], float("nan"), float("inf")):
                out.append({"action": a, key: c})
        out += [{"action": "stay_out"}, {"action": "bid"}, {"action": "push"}, {"action": "BID", "ceiling_lakh": 300}]
    elif point == "huddle":
        for c in (to_bid, aff, aff + 1, to_bid - 1, -5, 10 ** 9, "300", 300.0, None, "x"):
            out.append({"action": "raise_ceiling", "new_ceiling_lakh": c})
        out += [{"action": "drop"}, {"action": "raise_ceiling"}, {"action": "bid", "ceiling_lakh": 300}]
    elif point == "final_two":
        out += [{"action": "stay"}, {"action": "drop"}, {"action": "bid"}, {"action": "STAY"}, {"action": ["stay"]}]
    elif point == "rtm_use":
        out += [{"action": "use"}, {"action": "decline"}, {"action": "match"}]
    elif point == "rtm_raise":
        allowed = view.get("allowed_raise_prices") or [0]
        out += [{"action": "no_raise"}, {"action": "raise", "price_lakh": allowed[0]},
                {"action": "raise", "price_lakh": allowed[-1]}, {"action": "raise", "price_lakh": allowed[-1] + 5},
                {"action": "raise", "price_lakh": "x"}, {"action": "raise"}, {"action": "raise", "price_lakh": -1}]
    elif point == "rtm_match":
        out += [{"action": "match"}, {"action": "decline"}, {"action": "use"}]
    elif point == "tie_break":
        for c in (0, 1, 25, 10 ** 9, -1, "30", 30.0, 30.5, None, "x", [], True):
            out.append({"amount_lakh": c})
        out.append({})
    elif point == "nominate":
        el = view["eligible_players"]
        out += [{"players": []}, {"players": el[:5]}, {"players": el + el}, {"players": ["nobody", 7, None, ["p001"]]},
                {"players": "all"}, {"players": None}, {"players": {"p001": 1}}]
    out += [None, "bid", "", 42, 3.14, True, [], [{"action": "drop"}], {}, {"action": None}, {"action": 5},
            {"action": {"x": 1}}, {"Action": "drop"}, (1, 2), b"bytes", {"nested": {"action": "drop"}}]
    return out


class Raiser:
    def __init__(self, exc: BaseException):
        self.exc = exc

    def decide(self, view):
        raise self.exc


class Fixed:
    def __init__(self, raw: Any):
        self.raw = raw

    def decide(self, view):
        return self.raw


STATES = [(p, make_view(p, random.Random(f"fuzz|{i}"))) for i, p in
          ((i, POINTS[i % len(POINTS)]) for i in range(200))]


def check_result(point: str, view: Dict[str, Any], raw: Any, res) -> None:
    dec, ok, why = res
    assert isinstance(ok, bool) and isinstance(why, str)
    assert isinstance(dec, dict)
    assert schema_ok(SCHEMAS[point], dec), f"decision {dec!r} breaks the schema of {point}"
    if not ok:
        assert dec == DEFAULTS[point], f"invalid answer {raw!r} did not become the default"
        assert why, "invalid answer without a reason"
        return
    aff = view["you"]["max_affordable_lakh"]
    to_bid = view.get("price_to_bid")
    if point == "enter" and dec["action"] != "stay_out":
        # (the engine only asks teams that can afford price_to_bid; in a state where it cannot, the cut
        # may land below it and the lot code ignores that ceiling. Noted in the report.)
        assert dec["ceiling_lakh"] <= aff and (dec["ceiling_lakh"] >= to_bid or aff < to_bid), (raw, dec)
    if point == "huddle" and dec["action"] == "raise_ceiling":
        assert not view["ceiling_raised"] and to_bid <= dec["new_ceiling_lakh"] <= aff
    if point == "rtm_raise" and dec["action"] == "raise":
        assert dec["price_lakh"] in view["allowed_raise_prices"]
    if point == "nominate":
        assert set(dec["players"]) <= set(view["eligible_players"])
        assert len(set(dec["players"])) == len(dec["players"])


def test_states_cover_all_points():
    assert {p for p, _ in STATES} == set(POINTS) and len(STATES) == 200


def test_one_schema_and_default_per_point_and_defaults_validate():
    assert set(SCHEMAS) == set(POINTS) == set(DEFAULTS)
    for p in POINTS:
        assert schema_ok(SCHEMAS[p], DEFAULTS[p]), p
        # the default is also accepted as a valid answer by the validator itself (except for the
        # points where the default is a genuine choice, which is valid too)
        view = make_view(p, random.Random(1))
        dec, ok, why = validate(p, view, dict(DEFAULTS[p]))
        assert ok and dec == DEFAULTS[p], (p, why)


def test_schema_checker_itself_rejects_bad_values():
    s = SCHEMAS["enter"]
    assert schema_ok(s, {"action": "bid", "ceiling_lakh": 5})
    assert not schema_ok(s, {"action": "bid", "ceiling_lakh": -5})
    assert not schema_ok(s, {"action": "x"})
    assert not schema_ok(s, {})
    assert not schema_ok(s, {"action": "bid", "ceiling_lakh": 2.5})


def test_fuzz_valid_boundary_and_garbage_answers():
    n_calls = n_invalid = 0
    for point, view in STATES:
        for raw in answers(point, view):
            res = ask(Fixed(raw), point, view)
            check_result(point, view, raw, res)
            n_calls += 1
            n_invalid += not res[1]
    assert n_calls > 5000
    print(f"fuzz: {n_calls} answers, {n_invalid} invalid ({100 * n_invalid / n_calls:.0f}%)")


@pytest.mark.parametrize("exc", [ValueError("x"), KeyError("k"), TypeError("t"), ZeroDivisionError(),
                                 RecursionError(), RuntimeError("boom"), AssertionError(), OSError("io")])
def test_bidder_exceptions_become_defaults(exc):
    for point, view in STATES[:16]:
        dec, ok, why = ask(Raiser(exc), point, view)
        assert not ok and dec == DEFAULTS[point] and type(exc).__name__ in why


def test_boundaries_exact():
    view = make_view("enter", random.Random(5))
    view["price_to_bid"], view["you"]["max_affordable_lakh"] = 100, 500
    ok = lambda raw: ask(Fixed(raw), "enter", view)  # noqa: E731
    assert ok({"action": "bid", "ceiling_lakh": 100})[:2] == ({"action": "bid", "ceiling_lakh": 100}, True)
    assert ok({"action": "bid", "ceiling_lakh": 99})[1] is False
    assert ok({"action": "bid", "ceiling_lakh": 500})[:2] == ({"action": "bid", "ceiling_lakh": 500}, True)
    cut = ok({"action": "bid", "ceiling_lakh": 501})
    assert cut[0]["ceiling_lakh"] == 500 and cut[1] is True and "cut" in cut[2]
    assert ok({"action": "push", "limit_lakh": 250})[0] == {"action": "push", "ceiling_lakh": 250}


def test_ask_does_not_mutate_the_view():
    point, view = STATES[0]
    import copy
    before = copy.deepcopy(view)
    ask(Fixed({"action": "bid", "ceiling_lakh": 10}), point, view)
    assert view == before


# ------------------------------------------------------------------ end to end (A10 / A16)
def test_whole_2026_auction_with_garbage_heavy_bidders():
    rules = load_season(2026)
    teams = load_teams(rules)
    pool = make_pool(rules, 120, 3, sorted(teams))
    bidders = {c: RandomBidder(seed=i, garbage=0.4) for i, c in enumerate(sorted(teams))}
    res = run_auction(rules, pool, teams, bidders, seed=3)
    assert res.violations() == []
    decisions = res.log.of_type(E.DECISION)
    invalid = [e for e in decisions if not e.data["valid"]]
    assert decisions and invalid                      # garbage was thrown and was counted
    assert all(e.data["reason"] and e.data["decision"] == DEFAULTS[e.data["point"]] for e in invalid)
    rate = len(invalid) / len(decisions)
    print(f"invalid-action rate with 40% garbage: {len(invalid)}/{len(decisions)} = {100 * rate:.1f}%")
    assert 0.2 < rate < 0.6                            # about the garbage rate, plus a few self-inflicted ones
    assert len(res.log.of_type(E.SOLD)) > 0

"""The bidder harness: what a bidder sees and what it may answer.

A bidder is any object with one method:

    decide(view: dict) -> dict

`view["point"]` says which decision is being asked for. The engine computes every number the
bidder needs (next price, purse after, max affordable, ...): the bidder never does arithmetic
(failure register A10). Any answer that is not valid for the point is logged and replaced by the
safe default (stay out / drop / decline / no raise / 0 / []), never a crash (A16).

Decision points and valid answers (money in integer lakhs):

  enter       {"action": "stay_out"}
              {"action": "bid",  "ceiling_lakh": int}   ceiling >= view["price_to_bid"]
              {"action": "push", "limit_lakh": int}     same, logged as a price push
  huddle      {"action": "drop"}
              {"action": "raise_ceiling", "new_ceiling_lakh": int}
                    only once per lot; new ceiling >= view["price_to_bid"] and <= max_affordable
  final_two   {"action": "stay"} | {"action": "drop"}
  rtm_use     {"action": "use"} | {"action": "decline"}          (2025 only, previous team)
  rtm_raise   {"action": "raise", "price_lakh": int} | {"action": "no_raise"}   (highest bidder)
  rtm_match   {"action": "match"} | {"action": "decline"}        (previous team)
  tie_break   {"amount_lakh": int}   sealed extra amount, >= 0, paid to the BCCI, not the purse
  nominate    {"players": [player_key, ...]}   accelerated round shortlist

A ceiling above max_affordable is cut down to max_affordable (and logged); the bid itself can never
break a rule because the engine checks every bid.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple

POINTS = ("enter", "huddle", "final_two", "rtm_use", "rtm_raise", "rtm_match", "tie_break", "nominate")

DEFAULTS: Dict[str, Dict[str, Any]] = {
    "enter": {"action": "stay_out"},
    "huddle": {"action": "drop"},
    "final_two": {"action": "drop"},
    "rtm_use": {"action": "decline"},
    "rtm_raise": {"action": "no_raise"},
    "rtm_match": {"action": "decline"},
    "tie_break": {"amount_lakh": 0},
    "nominate": {"players": []},
}

# JSON schemas, one per decision point (for LLM structured output and for validation docs)
SCHEMAS: Dict[str, Dict[str, Any]] = {
    "enter": {"type": "object", "properties": {
        "action": {"enum": ["stay_out", "bid", "push"]},
        "ceiling_lakh": {"type": "integer", "minimum": 0},
        "limit_lakh": {"type": "integer", "minimum": 0}}, "required": ["action"]},
    "huddle": {"type": "object", "properties": {
        "action": {"enum": ["drop", "raise_ceiling"]},
        "new_ceiling_lakh": {"type": "integer", "minimum": 0}}, "required": ["action"]},
    "final_two": {"type": "object", "properties": {"action": {"enum": ["stay", "drop"]}}, "required": ["action"]},
    "rtm_use": {"type": "object", "properties": {"action": {"enum": ["use", "decline"]}}, "required": ["action"]},
    "rtm_raise": {"type": "object", "properties": {
        "action": {"enum": ["raise", "no_raise"]},
        "price_lakh": {"type": "integer", "minimum": 0}}, "required": ["action"]},
    "rtm_match": {"type": "object", "properties": {"action": {"enum": ["match", "decline"]}}, "required": ["action"]},
    "tie_break": {"type": "object", "properties": {"amount_lakh": {"type": "integer", "minimum": 0}}, "required": ["amount_lakh"]},
    "nominate": {"type": "object", "properties": {"players": {"type": "array", "items": {"type": "string"}}}, "required": ["players"]},
}


class Bidder(Protocol):
    def decide(self, view: Dict[str, Any]) -> Dict[str, Any]: ...


def _int(x: Any) -> Optional[int]:
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, str) and x.strip().lstrip("-").isdigit():
        return int(x.strip())
    return None


def validate(point: str, view: Dict[str, Any], d: Any) -> Tuple[Dict[str, Any], bool, str]:
    """Return (decision to apply, valid?, reason). Invalid answers become the safe default."""
    default = dict(DEFAULTS[point])
    if not isinstance(d, dict):
        return default, False, "not a JSON object"
    a = d.get("action")
    to_bid = view.get("price_to_bid")
    max_aff = view.get("you", {}).get("max_affordable_lakh")
    if point == "enter":
        if a == "stay_out":
            return {"action": "stay_out"}, True, ""
        if a in ("bid", "push"):
            c = _int(d.get("ceiling_lakh") if a == "bid" else d.get("limit_lakh"))
            if c is None:
                return default, False, "missing ceiling"
            if to_bid is not None and c < to_bid:
                return default, False, f"ceiling {c} below the price to bid {to_bid}"
            reason = ""
            if max_aff is not None and c > max_aff:
                if to_bid is not None and max_aff < to_bid:
                    return default, False, f"cannot afford the price to bid {to_bid} (max_affordable {max_aff})"
                reason, c = f"ceiling cut to max_affordable {max_aff}", max_aff
            return {"action": a, "ceiling_lakh": c}, True, reason
    elif point == "huddle":
        if a == "drop":
            return {"action": "drop"}, True, ""
        if a == "raise_ceiling":
            if view.get("ceiling_raised"):
                return default, False, "ceiling already raised once in this lot"
            c = _int(d.get("new_ceiling_lakh"))
            if c is None or (to_bid is not None and c < to_bid):
                return default, False, "new ceiling missing or below the price to bid"
            if max_aff is not None and c > max_aff:
                return default, False, f"new ceiling above max_affordable {max_aff}"
            return {"action": "raise_ceiling", "new_ceiling_lakh": c}, True, ""
    elif point == "final_two":
        if a in ("stay", "drop"):
            return {"action": a}, True, ""
    elif point == "rtm_use":
        if a in ("use", "decline"):
            return {"action": a}, True, ""
    elif point == "rtm_raise":
        if a == "no_raise":
            return {"action": "no_raise"}, True, ""
        if a == "raise":
            p = _int(d.get("price_lakh"))
            if p is None or p not in view.get("allowed_raise_prices", []):
                return default, False, "raise price not one of allowed_raise_prices"
            return {"action": "raise", "price_lakh": p}, True, ""
    elif point == "rtm_match":
        if a in ("match", "decline"):
            return {"action": a}, True, ""
    elif point == "tie_break":
        amt = _int(d.get("amount_lakh"))
        if amt is None or amt < 0:
            return default, False, "amount missing or negative"
        return {"amount_lakh": amt}, True, ""
    elif point == "nominate":
        ps = d.get("players")
        if not isinstance(ps, list):
            return default, False, "players is not a list"
        allowed = set(view.get("eligible_players", []))
        keep: List[str] = []
        for k in ps:
            if isinstance(k, str) and k in allowed and k not in keep:
                keep.append(k)
        bad = len(ps) - len(keep)
        return {"players": keep}, True, (f"{bad} names ignored (not eligible or repeated)" if bad else "")
    return default, False, f"action {a!r} not valid at {point}"


def ask(bidder: Bidder, point: str, view: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, str]:
    """Call a bidder safely: any exception or bad answer becomes the safe default."""
    view = {**view, "point": point}
    try:
        raw = bidder.decide(view)
    except Exception as exc:  # a bidder bug must never break the room
        return dict(DEFAULTS[point]), False, f"bidder raised {type(exc).__name__}: {exc}"
    return validate(point, view, raw)

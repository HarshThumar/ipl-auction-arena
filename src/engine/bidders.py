"""Bidders written in plain code (no LLM). They run the whole engine end to end.

- PassBidder:      always stays out (the stub Harsh starts from).
- RandomBidder:    random answers, valid and invalid (fuzzing the harness, property tests).
- ValuationBidder: a simple sensible bidder: ceiling = base x a seeded multiplier, more when the
                   team still needs players; nominates the cheapest eligible players.
- ReplayBidder:    forces a recorded outcome (winner at the recorded hammer price) for the replay of
                   real auctions. The plan for each lot is filled in by the replay driver.
"""
from __future__ import annotations

import random
from typing import Any, Dict, Optional


class PassBidder:
    def decide(self, view: Dict[str, Any]) -> Dict[str, Any]:
        point = view["point"]
        if point == "nominate":
            return {"players": []}
        if point == "tie_break":
            return {"amount_lakh": 0}
        return {"action": {"enter": "stay_out", "huddle": "drop", "final_two": "drop", "rtm_use": "decline",
                           "rtm_raise": "no_raise", "rtm_match": "decline"}[point]}


class RandomBidder:
    """Seeded random answers, including garbage, to check the room never breaks."""

    def __init__(self, seed: int = 0, garbage: float = 0.1):
        self.rng = random.Random(seed)
        self.garbage = garbage

    def decide(self, view: Dict[str, Any]) -> Any:
        r = self.rng
        if r.random() < self.garbage:
            return r.choice([None, "bid", 42, {"action": "explode"}, {"action": "bid"},
                             {"action": "bid", "ceiling_lakh": -5}, {"action": "bid", "ceiling_lakh": "lots"},
                             {"action": "raise_ceiling", "new_ceiling_lakh": 10 ** 9}, [], {"players": "all"}])
        point = view["point"]
        aff = view["you"]["max_affordable_lakh"]
        to_bid = view.get("price_to_bid") or 0
        if point == "enter":
            if r.random() < 0.5 or aff < to_bid:
                return {"action": "stay_out"}
            return {"action": r.choice(["bid", "push"]), "ceiling_lakh": r.randint(to_bid, max(to_bid, aff)),
                    "limit_lakh": r.randint(to_bid, max(to_bid, aff))}
        if point == "huddle":
            if r.random() < 0.6 or aff < to_bid:
                return {"action": "drop"}
            return {"action": "raise_ceiling", "new_ceiling_lakh": r.randint(to_bid, max(to_bid, aff))}
        if point == "final_two":
            return {"action": r.choice(["stay", "drop"])}
        if point == "rtm_use":
            return {"action": r.choice(["use", "decline"])}
        if point == "rtm_raise":
            ps = view.get("allowed_raise_prices") or []
            return {"action": "raise", "price_lakh": r.choice(ps)} if ps and r.random() < 0.5 else {"action": "no_raise"}
        if point == "rtm_match":
            return {"action": r.choice(["match", "decline"])}
        if point == "tie_break":
            return {"amount_lakh": r.randint(0, 500)}
        if point == "nominate":
            el = view.get("eligible_players") or []
            return {"players": r.sample(el, min(len(el), r.randint(0, 10)))}
        return {}


class ValuationBidder:
    """Ceiling = base x multiplier (seeded per team and player), higher when slots must be filled."""

    def __init__(self, seed: int = 0, appetite: float = 1.0):
        self.seed = seed
        self.appetite = appetite

    def _ceiling(self, view: Dict[str, Any]) -> int:
        p, you = view["player"], view["you"]
        r = random.Random(f"{self.seed}|{you['team']}|{p['key']}")
        if r.random() > 0.45 * self.appetite + 0.3 * min(1, you["players_needed"] / 6):
            return 0
        mult = r.choice([1, 1, 1.5, 2, 3, 4, 6]) * self.appetite
        return min(you["max_affordable_lakh"], int(p["base_lakh"] * mult))

    def decide(self, view: Dict[str, Any]) -> Dict[str, Any]:
        point = view["point"]
        if point == "enter":
            c = self._ceiling(view)
            to_bid = view["price_to_bid"]
            return {"action": "bid", "ceiling_lakh": c} if c >= to_bid else {"action": "stay_out"}
        if point == "huddle":
            return {"action": "drop"}
        if point == "final_two":
            return {"action": "stay"}
        if point == "rtm_use":
            return {"action": "use"} if self._ceiling(view) >= view["price_to_bid"] else {"action": "decline"}
        if point == "rtm_raise":
            return {"action": "no_raise"}
        if point == "rtm_match":
            return {"action": "match"} if self._ceiling(view) >= view["price_to_bid"] else {"action": "decline"}
        if point == "tie_break":
            return {"amount_lakh": 0}
        if point == "nominate":
            el = view.get("eligible_players") or []
            need = view["you"]["players_needed"]
            return {"players": el[: max(need, 3)]}
        return {}


class ReplayBidder:
    """Plays one team in a replay. `plan[lot_id]` (shared, set by the driver before each lot):
        {"winner": team, "hammer": int, "runner": team|None, "runner_ceiling": int|None,
         "opener": team}  - or {} for an unsold lot.
    The opener enters at the announcement; the other of the final two enters at "going once",
    so the bids alternate and the winner places the recorded hammer price.
    `nominations[round]` (optional): list of player keys this team nominates."""

    def __init__(self, team: str, plan: Dict[str, Dict[str, Any]], nominations: Optional[Dict[int, list]] = None):
        self.team = team
        self.plan = plan
        self.nominations = nominations or {}

    def decide(self, view: Dict[str, Any]) -> Dict[str, Any]:
        point = view["point"]
        pl = self.plan.get(view["lot_id"]) or {}
        me = self.team
        if point == "enter":
            first = view["price_now_lakh"] is None
            if me == pl.get("winner"):
                if first and pl.get("opener") != me:
                    return {"action": "stay_out"}
                return {"action": "bid", "ceiling_lakh": pl["hammer"]}
            if me == pl.get("runner"):
                if first and pl.get("opener") != me:
                    return {"action": "stay_out"}
                return {"action": "bid", "ceiling_lakh": pl["runner_ceiling"]}
            return {"action": "stay_out"}
        if point == "final_two":
            return {"action": "stay"}
        if point == "nominate":
            return {"players": list(self.nominations.get(view["round"], []))}
        if point == "tie_break":
            return {"amount_lakh": 1 if me == pl.get("winner") else 0}
        return {"action": {"huddle": "drop", "rtm_use": "decline", "rtm_raise": "no_raise",
                           "rtm_match": "decline"}[point]}

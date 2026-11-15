"""The file Harsh starts from: a bidder that always passes.

The engine calls `decide(view)` every time your team has a decision to make. You return a small
dict (JSON-like). The engine does all the money maths and checks every answer. A bad answer is
logged and replaced by the safe default, so you cannot break the room.

Read docs/bidder-harness.md first. Run it:

    python -m pytest tests/test_stub_bidder.py -q
    python scripts/run_auction.py --season 2026 --seed 1 --bidders valuation

Example `view` at point "enter" (money in integer lakhs; 100 lakh = 1 crore):

    {
      "point": "enter",                     # which decision is being asked (see ANSWERS below)
      "season": 2026, "auction_type": "mini",
      "lot_id": "2026-R1-p012",             # unique id of this call of the player
      "round": 1,                           # 1 = main phase, 2+ = accelerated rounds
      "player": {"key": "p012", "name": "Player 012", "role": "bowler", "overseas": True,
                 "capped": True, "base_lakh": 100, "set_code": "S2"},
      "price_now_lakh": None,               # current price; None until the first bid
      "leader": None,                       # team code holding the current bid
      "price_to_bid": 100,                  # the next price you could bid (engine computed it)
      "you": {"team": "CSK",
              "purse_lakh": 4340,           # money left
              "squad": 16,                  # players you have now
              "overseas": 4,                # overseas players you have now
              "players_needed": 2,          # players still needed to reach the minimum squad (18)
              "slots_left": 9,              # room left up to the maximum squad (25)
              "overseas_slots_left": 4,
              "max_affordable_lakh": 4310,  # the most you may bid (keeps money to fill the squad)
              "purse_after_bid_lakh": 4240},# purse if you win at price_to_bid
      "your_ceiling_lakh": None,            # your current ceiling if you are in the fight
      "ceiling_raised": False,              # True once you used your one huddle raise on this lot
      "bids_so_far": [{"team": "MI", "price_lakh": 100}],
      "board": [{"team": "MI", "purse_lakh": 2000, "squad": 15, "overseas": 5, "slots_left": 10,
                 "overseas_slots_left": 3, "players_needed": 3}],   # every team, public
      "recent_lots": [{"lot_id": "...", "player": "...", "sold": True, "team": "RCB", "price_lakh": 250}]
    }

Some points add fields: "rtm_use" and "rtm_match" add "rtm_card"; "rtm_raise" adds "rtm_team" and
"allowed_raise_prices"; "tie_break" adds "tied_with" (and price_to_bid is None); "nominate" adds
"eligible_players" (a list of player keys) and has no "player" or "price_to_bid".

ANSWERS (anything else becomes the default and is marked invalid in the log):

    enter      {"action": "stay_out"}                          default
               {"action": "bid",  "ceiling_lakh": 300}         300 >= price_to_bid; cut to max_affordable
               {"action": "push", "limit_lakh": 300}           same as bid, logged as a price push
    huddle     {"action": "drop"}                              default
               {"action": "raise_ceiling", "new_ceiling_lakh": 400}   once per lot, <= max_affordable
    final_two  {"action": "stay"} | {"action": "drop"}         default drop
    rtm_use    {"action": "use"} | {"action": "decline"}       default decline (2025 only)
    rtm_raise  {"action": "raise", "price_lakh": 450} | {"action": "no_raise"}   price from allowed_raise_prices
    rtm_match  {"action": "match"} | {"action": "decline"}     default decline
    tie_break  {"amount_lakh": 25}                             sealed extra amount >= 0; default 0
    nominate   {"players": ["p012", "p033"]}                   keys from eligible_players; default []
"""
from __future__ import annotations

from typing import Any, Dict


class MyBidder:
    """Always passes. Replace the body of `decide` step by step (see docs/bidder-harness.md)."""

    def __init__(self, seed: int = 0):
        self.seed = seed          # keep it: the same view must always give the same answer

    def decide(self, view: Dict[str, Any]) -> Dict[str, Any]:
        point = view["point"]     # always present: one of the eight points above

        if point == "enter":
            # To bid you would write, for example:
            #   if view["player"]["base_lakh"] <= 100 and view["you"]["max_affordable_lakh"] >= 300:
            #       return {"action": "bid", "ceiling_lakh": 300}
            return {"action": "stay_out"}
        if point == "huddle":
            return {"action": "drop"}
        if point == "final_two":
            return {"action": "drop"}
        if point == "rtm_use":
            return {"action": "decline"}
        if point == "rtm_raise":
            return {"action": "no_raise"}
        if point == "rtm_match":
            return {"action": "decline"}
        if point == "tie_break":
            return {"amount_lakh": 0}
        if point == "nominate":
            return {"players": []}
        return {}                 # unknown point: the engine treats it as invalid

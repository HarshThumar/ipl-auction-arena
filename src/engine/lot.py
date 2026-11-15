"""One lot: live open ascending bidding, then RTM (2025) or the silent tie-breaker, then sold/unsold.

Room rules and their sources: data/reference/engine_rules.yaml and docs/L1-plan.md section 3.

How a lot runs:
1. The player is announced at his base price. Every team that has room for him and can afford the
   base is asked `enter` (stay out / bid with a ceiling / push with a limit).
2. Bidding: the price moves up the season's grid. Among active teams that are not leading and whose
   ceiling covers the next price, one raises (several at once: seeded pick). The code raises for
   them (autopilot): the bidder only set a ceiling.
3. A non-leading active team whose ceiling is below the next price is asked `huddle`: drop, or raise
   its ceiling once per lot (never above max_affordable).
4. The first time only two teams are left in the fight, both are asked `final_two` (stay / drop).
5. When nobody will raise, the auctioneer calls "going once": every team that is out (never entered
   or dropped) and can afford the next price gets one more `enter` offer per lot (late entry and
   re-entry are both seen in real auctions).
6. Silent tie-breaker: if the leader cannot raise and a challenger could match the current price
   but not raise it, both are at their limit: each gives a sealed extra amount (to the BCCI, not
   from the purse); the higher wins at the current price.
7. RTM (2025 only): when the hammer would fall, the player's previous team may use a card; the
   highest bidder may then raise once; the previous team matches or declines.
8. Sold: the purse is charged the hammer price; the player is paid min(hammer, cap) for overseas
   players in seasons with the overseas pay cap.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.engine import events as E
from src.engine.bidder_api import Bidder, ask
from src.engine.ledger import Player, Team, Treasurer
from src.engine.season_rules import SeasonRules

OUT, ACTIVE, DROPPED = "out", "active", "dropped"


@dataclass
class LotResult:
    lot_id: str
    player: Player
    sold: bool
    winner: Optional[str] = None
    hammer: Optional[int] = None
    paid: Optional[int] = None
    rtm_card: Optional[str] = None
    bids: List[tuple] = field(default_factory=list)


@dataclass
class _Seat:
    status: str = OUT
    ceiling: int = 0
    raised_once: bool = False
    reentry_offered: bool = False
    final_two_asked: bool = False
    push: bool = False


class Room:
    """Shared state of one auction: rules, teams, bidders, log, seed."""

    def __init__(self, rules: SeasonRules, teams: Dict[str, Team], bidders: Dict[str, Bidder],
                 seed: int = 0, log: Optional[E.EventLog] = None):
        self.rules = rules
        self.teams = teams
        self.bidders = bidders
        self.seed = seed
        self.tr = Treasurer(rules)
        self.log = log or E.EventLog()
        self.history: List[Dict[str, Any]] = []   # finished lots, public

    # ---------------------------------------------------------------- views
    def board(self) -> List[Dict[str, Any]]:
        return [{"team": t.code, "purse_lakh": t.purse_lakh, "squad": t.squad, "overseas": t.overseas,
                 "slots_left": self.tr.slots_left(t), "overseas_slots_left": self.tr.overseas_slots_left(t),
                 "players_needed": self.tr.players_needed(t)} for t in self.teams.values()]

    def view(self, code: str, p: Player, lot_id: str, rnd: int, price: Optional[int],
             leader: Optional[str], to_bid: Optional[int], bids: List[tuple], seat: Optional[_Seat],
             **extra: Any) -> Dict[str, Any]:
        t = self.teams[code]
        aff = self.tr.max_affordable(t, p)
        return {
            "season": self.rules.season, "auction_type": self.rules.auction_type,
            "lot_id": lot_id, "round": rnd,
            "player": {"key": p.key, "name": p.name, "role": p.role, "overseas": p.overseas,
                       "capped": p.capped, "base_lakh": p.base_lakh, "set_code": p.set_code},
            "price_now_lakh": price, "leader": leader, "price_to_bid": to_bid,
            "you": {"team": code, "purse_lakh": t.purse_lakh, "squad": t.squad, "overseas": t.overseas,
                    "players_needed": self.tr.players_needed(t), "slots_left": self.tr.slots_left(t),
                    "overseas_slots_left": self.tr.overseas_slots_left(t), "max_affordable_lakh": aff,
                    "purse_after_bid_lakh": (t.purse_lakh - to_bid) if to_bid is not None else None},
            "your_ceiling_lakh": seat.ceiling if seat and seat.status == ACTIVE else None,
            "ceiling_raised": bool(seat and seat.raised_once),
            "bids_so_far": [{"team": a, "price_lakh": b} for a, b in bids],
            "board": self.board(),
            "recent_lots": self.history[-5:],
            **extra,
        }

    def _ask(self, code: str, point: str, view: Dict[str, Any], lot_id: str) -> Dict[str, Any]:
        d, ok, why = ask(self.bidders[code], point, view)
        self.log.add(E.DECISION, lot_id, code, view.get("price_to_bid"), point=point, decision=d, valid=ok, reason=why)
        return d

    # ---------------------------------------------------------------- the lot
    def run_lot(self, p: Player, lot_id: str, rnd: int = 1) -> LotResult:
        rules, tr, log = self.rules, self.tr, self.log
        rng = random.Random(f"{self.seed}|{lot_id}")
        order = list(self.teams)
        rng.shuffle(order)                     # team order shuffled per lot and seed (A7)
        seats = {c: _Seat() for c in order}
        price: Optional[int] = None
        leader: Optional[str] = None
        bids: List[tuple] = []
        log.add(E.LOT_ANNOUNCED, lot_id, price=p.base_lakh, player=p.name, key=p.key, base=p.base_lakh,
                overseas=p.overseas, capped=p.capped, set_code=p.set_code, round=rnd)

        def to_bid() -> int:
            return p.base_lakh if price is None else tr.next_price(price)

        def V(code: str, **extra: Any) -> Dict[str, Any]:
            return self.view(code, p, lot_id, rnd, price, leader, to_bid(), bids, seats[code], **extra)

        def offer_entry(code: str) -> None:
            s = seats[code]
            d = self._ask(code, "enter", V(code), lot_id)
            if d["action"] in ("bid", "push"):
                s.status, s.ceiling, s.push = ACTIVE, d["ceiling_lakh"], d["action"] == "push"
            elif s.status == ACTIVE:
                s.status = DROPPED

        # 1. announce: every team with room and money for the base price
        for c in order:
            if tr.can_bid(self.teams[c], p, p.base_lakh):
                offer_entry(c)

        while True:
            nxt = to_bid()
            # 3. huddles for active challengers whose ceiling is below the next price
            for c in order:
                s = seats[c]
                if s.status != ACTIVE or c == leader:
                    continue
                t = self.teams[c]
                if not tr.can_bid(t, p, nxt):
                    continue                    # handled below (tie-breaker or drop)
                if s.ceiling < nxt:
                    if s.raised_once:
                        s.status = DROPPED
                        log.add(E.DROPPED, lot_id, c, nxt, why="ceiling reached")
                        continue
                    d = self._ask(c, "huddle", V(c), lot_id)
                    if d["action"] == "raise_ceiling":
                        s.ceiling, s.raised_once = d["new_ceiling_lakh"], True
                    else:
                        s.status = DROPPED
                        log.add(E.DROPPED, lot_id, c, nxt, why="huddle drop")
            # 4. final two
            active = [c for c in order if seats[c].status == ACTIVE or c == leader]
            if price is not None and len(active) == 2 and not any(seats[c].final_two_asked for c in active):
                for c in active:
                    seats[c].final_two_asked = True
                    d = self._ask(c, "final_two", V(c), lot_id)
                    if d["action"] == "drop":
                        if c != leader:
                            seats[c].status = DROPPED
                            log.add(E.DROPPED, lot_id, c, nxt, why="final two drop")
                        else:                            # leader's bid stands; it will not raise again
                            seats[c].ceiling, seats[c].raised_once = price, True
            willing = [c for c in order if c != leader and seats[c].status == ACTIVE
                       and seats[c].ceiling >= nxt and tr.can_bid(self.teams[c], p, nxt)]
            if willing:
                c = rng.choice(willing)           # several paddles at once: seeded pick
                price, leader = nxt, c
                bids.append((c, price))
                log.add(E.BID, lot_id, c, price, push=seats[c].push)
                continue
            # 6. silent tie-breaker: leader at its limit and a challenger can match but not raise
            if price is not None and rules.silent_tie_breaker and not tr.can_bid(self.teams[leader], p, nxt):
                tied = [c for c in order if c != leader and seats[c].status == ACTIVE
                        and seats[c].ceiling >= price and tr.can_bid(self.teams[c], p, price)
                        and not tr.can_bid(self.teams[c], p, nxt)]
                if tied:
                    leader = self._tie_break([leader] + tied, p, lot_id, rnd, price, leader, bids, seats, rng)
                    break
            # active challengers that cannot afford the next price are out
            for c in order:
                if c != leader and seats[c].status == ACTIVE and not tr.can_bid(self.teams[c], p, nxt):
                    seats[c].status = DROPPED
                    log.add(E.DROPPED, lot_id, c, nxt, why="cannot afford the next price")
            # 5. going once: late entry / re-entry, one offer per team per lot
            log.add(E.GOING_ONCE, lot_id, price=price if price is not None else p.base_lakh)
            entered = False
            for c in order:
                s = seats[c]
                if c == leader or s.status == ACTIVE or s.reentry_offered:
                    continue
                if not tr.can_bid(self.teams[c], p, nxt):
                    continue
                s.reentry_offered = True
                if s.status == OUT and price is None:
                    continue                    # was asked at the announcement and nobody has bid
                offer_entry(c)
                entered = entered or s.status == ACTIVE
            if not entered:
                break

        if price is None:
            log.add(E.UNSOLD, lot_id, key=p.key)
            res = LotResult(lot_id, p, False)
            self.history.append({"lot_id": lot_id, "player": p.name, "sold": False})
            return res

        winner, hammer, card = leader, price, None
        # 7. RTM
        if rules.rtm and p.rtm_team and p.rtm_team in self.teams and p.rtm_team != winner:
            winner, hammer, card = self._rtm(p, lot_id, rnd, winner, hammer, bids)

        t = self.teams[winner]
        tr.apply_purchase(t, p, hammer, card)
        paid = rules.paid_for(hammer, p.overseas)
        log.add(E.SOLD, lot_id, winner, hammer, key=p.key, paid=paid, purse_after=t.purse_lakh,
                rtm_card=card, overseas=p.overseas)
        self.history.append({"lot_id": lot_id, "player": p.name, "sold": True, "team": winner, "price_lakh": hammer})
        return LotResult(lot_id, p, True, winner, hammer, paid, card, bids)

    # ---------------------------------------------------------------- tie-breaker
    def _tie_break(self, teams: List[str], p: Player, lot_id: str, rnd: int, price: int, leader: str,
                   bids: List[tuple], seats: Dict[str, _Seat], rng: random.Random) -> str:
        for attempt in range(1, 4):
            amounts = {}
            for c in teams:
                v = self.view(c, p, lot_id, rnd, price, leader, None, bids, seats[c], tied_with=teams)
                amounts[c] = self._ask(c, "tie_break", v, lot_id)["amount_lakh"]
            top = max(amounts.values())
            best = [c for c in teams if amounts[c] == top]
            if len(best) == 1:
                self.log.add(E.TIE_BREAK, lot_id, best[0], price, teams=teams, amounts=amounts, attempt=attempt)
                return best[0]
            teams = best
        w = rng.choice(sorted(teams))           # still equal after three rounds: seeded pick
        self.log.add(E.TIE_BREAK, lot_id, w, price, teams=teams, amounts=amounts, attempt="seeded_pick")
        return w

    # ---------------------------------------------------------------- RTM
    def _rtm(self, p: Player, lot_id: str, rnd: int, winner: str, hammer: int, bids: List[tuple]):
        tr, rtm_code = self.tr, p.rtm_team
        rt = self.teams[rtm_code]
        card = tr.rtm_card_for(rt, p)
        if card is None or not tr.can_bid(rt, p, hammer):
            return winner, hammer, None
        d = self._ask(rtm_code, "rtm_use", self.view(rtm_code, p, lot_id, rnd, hammer, winner, hammer, bids, None,
                                                     rtm_card=card), lot_id)
        if d["action"] != "use":
            return winner, hammer, None
        self.log.add(E.RTM_USED, lot_id, rtm_code, hammer, card=card)
        wt = self.teams[winner]
        aff = tr.max_affordable(wt, p)
        allowed = [x for x in tr.r.ladder.path(hammer, aff) if hammer < x <= aff]
        d = self._ask(winner, "rtm_raise", self.view(winner, p, lot_id, rnd, hammer, winner, None, bids, None,
                                                     rtm_team=rtm_code, allowed_raise_prices=allowed), lot_id)
        if d["action"] != "raise":
            self.log.add(E.RTM_RESULT, lot_id, rtm_code, hammer, matched=True, raised=False)
            return rtm_code, hammer, card
        new = d["price_lakh"]
        self.log.add(E.RTM_RAISE, lot_id, winner, new)
        if not tr.can_bid(rt, p, new):
            self.log.add(E.RTM_RESULT, lot_id, winner, new, matched=False, raised=True, why="cannot afford the raise")
            return winner, new, None
        d = self._ask(rtm_code, "rtm_match", self.view(rtm_code, p, lot_id, rnd, new, winner, new, bids, None,
                                                       rtm_card=card), lot_id)
        if d["action"] == "match":
            self.log.add(E.RTM_RESULT, lot_id, rtm_code, new, matched=True, raised=True)
            return rtm_code, new, card
        self.log.add(E.RTM_RESULT, lot_id, winner, new, matched=False, raised=True)
        return winner, new, None

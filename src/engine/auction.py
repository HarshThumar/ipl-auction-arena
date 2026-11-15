"""A whole auction: sets in order, then accelerated rounds; or an explicit order (replay).

Schedule (simulation):
  main phase  - sets in official order (set_no), random order inside a set (seeded). If the season
                has `accelerated.after_lots` (engine_rules.yaml), only that many lots are called in set
                order; otherwise every set is called.
  accelerated - each team nominates players from those not yet called plus those unsold; the union
                is called in list order (set, then name). Up to `accelerated.rounds` rounds; a
                player unsold in one round can be nominated again in the next.
Every call of a player is its own lot with a unique id "<season>-R<round>-<key>" (G4).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from src.engine import events as E
from src.engine.bidder_api import Bidder
from src.engine.ledger import Player, Team
from src.engine.lot import LotResult, Room
from src.engine.season_rules import SeasonRules


@dataclass
class AuctionResult:
    room: Room
    lots: List[LotResult] = field(default_factory=list)
    start: Dict[str, Team] = field(default_factory=dict)

    @property
    def log(self) -> E.EventLog:
        return self.room.log

    def violations(self, final_min_squad: bool = False) -> List[str]:
        out = []
        for t in self.room.teams.values():
            out += self.room.tr.violations(t, final=final_min_squad)
        return out


def _lot_id(season: int, rnd: int, key: str, used: set) -> str:
    base = f"{season}-R{rnd}-{key}"
    lid, n = base, 1
    while lid in used:
        n += 1
        lid = f"{base}-{n}"
    used.add(lid)
    return lid


def _all_full(room: Room) -> bool:
    return all(room.tr.slots_left(t) <= 0 for t in room.teams.values())


def run_auction(rules: SeasonRules, pool: Sequence[Player], teams: Dict[str, Team], bidders: Dict[str, Bidder],
                seed: int = 0, order: Optional[Sequence[Tuple[Player, int]]] = None,
                before_lot=None) -> AuctionResult:
    """Run an auction. `order` = explicit [(player, round)] (replay); else the set schedule.
    `before_lot(room, player, lot_id, round)` is called before each lot (the replay driver uses it)."""
    start = {k: v.copy() for k, v in teams.items()}
    room = Room(rules, teams, bidders, seed)
    res = AuctionResult(room, start=start)
    used: set = set()
    room.log.add(E.AUCTION_STARTED, season=rules.season, seed=seed, teams=sorted(teams),
                 pool=len(pool), explicit_order=order is not None)

    def call(p: Player, rnd: int) -> LotResult:
        lid = _lot_id(rules.season, rnd, p.key, used)
        if before_lot:
            before_lot(room, p, lid, rnd)
        r = room.run_lot(p, lid, rnd)
        res.lots.append(r)
        return r

    if order is not None:
        cur = None
        for p, rnd in order:
            if rnd != cur:
                room.log.add(E.ROUND_STARTED, round=rnd, phase="main" if rnd == 1 else "accelerated")
                cur = rnd
            call(p, rnd)
    else:
        rng = random.Random(f"{seed}|schedule")
        by_set: Dict[int, List[Player]] = {}
        for p in pool:
            by_set.setdefault(p.set_no if p.set_no is not None else 10 ** 6, []).append(p)
        main: List[Player] = []
        for s in sorted(by_set):
            grp = sorted(by_set[s], key=lambda x: x.key)
            rng.shuffle(grp)                    # order inside a set: random draw (seeded)
            main += grp
        n_main = rules.accelerated_after if rules.accelerated_after else len(main)
        room.log.add(E.ROUND_STARTED, round=1, phase="main", lots=min(n_main, len(main)))
        called, sold = set(), set()
        for p in main[:n_main]:
            if _all_full(room):
                break
            r = call(p, 1)
            called.add(p.key)
            if r.sold:
                sold.add(p.key)
        list_order = {p.key: i for i, p in enumerate(sorted(pool, key=lambda x: ((x.set_no or 10 ** 6), x.key)))}
        by_key = {p.key: p for p in pool}
        for rnd in range(2, 2 + rules.accelerated_rounds):
            if _all_full(room):
                break
            eligible = sorted((k for k in by_key if k not in sold), key=list_order.get)
            if not eligible:
                break
            noms: Dict[str, List[str]] = {}
            for code in sorted(room.teams):
                t = room.teams[code]
                if room.tr.slots_left(t) <= 0:
                    continue
                v = {"season": rules.season, "round": rnd, "lot_id": f"{rules.season}-R{rnd}-nominate",
                     "you": {"team": code, "purse_lakh": t.purse_lakh, "squad": t.squad,
                             "players_needed": room.tr.players_needed(t), "slots_left": room.tr.slots_left(t),
                             "overseas_slots_left": room.tr.overseas_slots_left(t),
                             "max_affordable_lakh": room.tr.max_legal_bid(t)},
                     "eligible_players": eligible, "board": room.board()}
                noms[code] = room._ask(code, "nominate", v, v["lot_id"])["players"]
            room.log.add(E.NOMINATIONS, round=rnd, by_team=noms)
            chosen = sorted({k for ks in noms.values() for k in ks}, key=list_order.get)
            if not chosen:
                break
            room.log.add(E.ROUND_STARTED, round=rnd, phase="accelerated", lots=len(chosen))
            for k in chosen:
                if _all_full(room):
                    break
                r = call(by_key[k], rnd)
                called.add(k)
                if r.sold:
                    sold.add(k)

    room.log.add(E.AUCTION_ENDED, sold=sum(r.sold for r in res.lots), lots=len(res.lots))
    return res

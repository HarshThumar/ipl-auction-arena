"""Outcome replay of the real 2022-2026 auctions through the engine (L1 gate: "replays the real auctions
from the recorded outcomes with zero rule violations"; docs/L1-plan.md section 4).

For every recorded lot, in calling order, two ReplayBidders are set up so the engine must produce the
recorded winner at the recorded hammer price (or no sale for an unsold lot). Then we check:

  1. every sold lot ends with the recorded winner at the recorded hammer; every unsold lot unsold;
  2. no team breaks purse >= 0, squad <= 25, overseas <= 8 after any lot (Treasurer.violations), and the
     same again by re-reading the event log (independent of the live room state);
  3. every BID event is on the season's grid path from the base price and within that team's max legal
     bid at that moment;
  4. at the end every team has 18..25 players (retained + bought) and <= 8 overseas;
  5. the season totals (sold lots, total hammer) equal the official ones; the 2026 Cameron Green lot
     has paid 1800 and a purse charge of 2520.

Anything that cannot be replayed is a *problem* in the report. Nothing is fudged: an illegal recorded
result means the data or our rule is wrong and has to be investigated.

Inputs are committed data only: pre_auction_state, master, replay_order.csv (built locally by
scripts/build_replay_order.py), data/reference rules.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.engine import events as E
from src.engine.auction import run_auction
from src.engine.bidders import ReplayBidder
from src.engine.ledger import Player, Treasurer, teams_from_state
from src.engine.season_rules import load_season

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "processed" / "master" / "all_auctions_master.json"
STATE_DIR = ROOT / "data" / "processed" / "pre_auction_state"
ORDER = ROOT / "data" / "processed" / "auction_order" / "replay_order.csv"
RECON = ROOT / "data" / "processed" / "auction_order" / "replay_order_reconciliation.json"

SEASONS = (2022, 2023, 2024, 2025, 2026)
# official totals: lots sold and money spent in lakh (hammer; 551.7 crore = 55170 lakh)
OFFICIAL = {2022: (204, 55170), 2023: (80, 16700), 2024: (72, 23045), 2025: (182, 63915), 2026: (77, 21545)}


@dataclass
class ReplayReport:
    season: int
    seed: int = 0
    lots: int = 0
    sold: int = 0
    unsold: int = 0
    hammer_total_lakh: int = 0
    official_sold: int = 0
    official_hammer_lakh: int = 0
    outcomes_exact: int = 0
    max_squad: int = 0
    min_squad: int = 0
    max_overseas: int = 0
    log_events: int = 0
    log_digest: str = ""
    order_basis: Dict[str, int] = field(default_factory=dict)
    problems: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    reconciliation: Dict[str, Any] = field(default_factory=dict)
    alt_grid_lots: List[str] = field(default_factory=list)  # sold lots replayed on the other step grid
    moves: List[str] = field(default_factory=list)          # lots of unknown position moved earlier
    infeasible: List[int] = field(default_factory=list)    # order positions of lots that could not be replayed

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> Dict[str, Any]:
        return {"season": self.season, "seed": self.seed, "ok": self.ok, "lots": self.lots, "sold": self.sold,
                "unsold": self.unsold, "official_sold": self.official_sold,
                "hammer_total_lakh": self.hammer_total_lakh, "official_hammer_lakh": self.official_hammer_lakh,
                "outcomes_exact": self.outcomes_exact, "min_squad": self.min_squad, "max_squad": self.max_squad,
                "max_overseas": self.max_overseas, "log_events": self.log_events, "log_digest": self.log_digest,
                "order_basis": self.order_basis, "alt_grid_lots": self.alt_grid_lots, "moves": self.moves,
                "problems": self.problems, "notes": self.notes,
                "reconciliation": self.reconciliation}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _entity_key(r: dict) -> str:
    return r["cricsheet_id"] if r.get("cricsheet_id") else "n:" + _norm(r["player"])


def load_inputs(season: int):
    master = [r for r in json.loads(MASTER.read_text(encoding="utf-8")) if r["season"] == season]
    state = json.loads((STATE_DIR / f"{season}.json").read_text(encoding="utf-8"))
    order = [r for r in csv.DictReader(open(ORDER, encoding="utf-8")) if int(r["season"]) == season]
    order.sort(key=lambda r: int(r["seq"]))
    return master, state, order


def replay_season(season: int, seed: int = 0, max_moves: int = 12) -> ReplayReport:
    """Replay one season. Lots whose position is not known from a source (order_basis set_insert,
    not_ordered, accelerated_inferred) are placed by set number first. If a recorded sale is then
    impossible at that position (no team could have bid the price before the hammer), the lot is moved
    earlier, but never before the last narrated (live_blog) lot, to the earliest position of the unordered block where it works
    (the move can make a later lot fail, which is then handled the same way, up to `max_moves` moves).
    Every such move is listed in the report notes; a lot with a known position is never moved."""
    master, state, order = load_inputs(season)
    moves: List[str] = []
    rep = _replay(season, seed, master, state, order)
    for _ in range(max_moves):
        bad = [f for f in rep.infeasible if order[f]["order_basis"] != "live_blog"]
        if not bad:
            break
        i = bad[0]
        lo = max([j for j in range(i) if order[j]["order_basis"] == "live_blog" and order[j]["round"] == "1"], default=-1) + 1
        best = None
        for j in range(lo, i):
            trial = order[:j] + [order[i]] + order[j:i] + order[i + 1:]
            r2 = _replay(season, seed, master, state, trial)
            if i_pos(trial, order[i]) in r2.infeasible:
                continue
            best = (j, trial, r2)
            break
        if best is None:
            break
        j, order, rep = best
        moves.append(f"{order[j]['player']} (set {order[j]['set_no'] or '?'}): moved from position {i + 1} to {j + 1}")
    rep.moves = moves
    return rep


def i_pos(order, row) -> int:
    return next(k for k, r in enumerate(order) if r is row)


def _replay(season: int, seed: int, master, state, order) -> ReplayReport:
    rep = ReplayReport(season, seed)
    rep.infeasible = []
    rules = load_season(season)
    tr = Treasurer(rules)
    lad = rules.ladder
    # Above 3 cr the auctioneer chooses the step (BCCI: "minimum 20 lakh"). Only where a season's own
    # recorded prices show both steps (2024) does engine_rules.yaml list an alternative grid; a lot is
    # replayed on it only if its hammer is not on the main grid, and each such lot is listed.
    alt_ladders = list(rules.alt_ladders)
    lot_rules: Dict[str, Any] = {}
    alt_lots: List[str] = []
    rep.official_sold, rep.official_hammer_lakh = OFFICIAL[season]
    teams = teams_from_state(state["teams"], rules)

    # ---- the recorded outcome per player (a player can have an unsold and a sold master row)
    rows: Dict[str, dict] = {}
    for r in master:
        k = _entity_key(r)
        if k not in rows or r["status"] == "sold":
            rows[k] = r
    if sum(1 for r in master if r["status"] == "sold") != sum(1 for r in rows.values() if r["status"] == "sold"):
        rep.problems.append("a player has two sold rows in the master")

    # ---- the lots in calling order
    players: List[Tuple[Player, int]] = []
    expect: Dict[Tuple[str, int], dict] = {}
    pos_of: Dict[Tuple[str, int], int] = {}
    for i, o in enumerate(order):
        r = rows.get(o["key"])
        if r is None:
            rep.problems.append(f"replay_order row {o['seq']} ({o['player']}) is not in the master")
            continue
        rnd = int(o["round"])
        nat = r.get("nationality")
        sold_here = o["status"] == "sold"
        if sold_here and nat not in ("India", "Overseas"):
            rep.problems.append(f"{r['player']}: sold but nationality missing in the master")
        base = r.get("base_lakh")
        if base is None:
            if sold_here:
                rep.problems.append(f"{r['player']}: sold but base price missing in the master")
            base = rules.min_base_lakh
        p = Player(key=o["key"], name=r["player"], overseas=(nat != "India"), capped=(r.get("capped") == "capped"),
                   base_lakh=int(base), set_no=int(o["set_no"]) if o["set_no"] else None)
        players.append((p, rnd))
        expect[(o["key"], rnd)] = {"sold": sold_here, "row": r}
        pos_of[(o["key"], rnd)] = i
        rep.order_basis[o["order_basis"]] = rep.order_basis.get(o["order_basis"], 0) + 1
    in_order = {o["key"] for o in order}
    for k, r in rows.items():
        if k not in in_order:
            rep.problems.append(f"{r['player']} ({r['status']}): in the master but not placed in replay_order")
    rep.lots = len(players)

    # ---- the ReplayBidders, one per team, sharing one plan dict that before_lot fills
    plan: Dict[str, dict] = {}
    bidders = {c: ReplayBidder(c, plan) for c in teams}
    pre_green: Dict[str, int] = {}

    def before_lot(room, p: Player, lot_id: str, rnd: int) -> None:
        for t in room.teams.values():                      # state after the previous lot
            for v in tr.violations(t):
                rep.problems.append(f"before {lot_id}: {v}")
        room.rules, room.tr = rules, Treasurer(rules)
        ex = expect[(p.key, rnd)]
        if not ex["sold"]:
            plan[lot_id] = {}
            return
        r = ex["row"]
        w, h, b = r["winner"], int(r["hammer_lakh"]), p.base_lakh
        pos = pos_of[(p.key, rnd)]
        if w not in room.teams:
            rep.problems.append(f"{lot_id} {p.name}: winner {w} is not a team of this season")
            plan[lot_id] = {}
            return
        if p.name == "Cameron Green" and season == 2026:
            pre_green["purse"] = room.teams[w].purse_lakh
        lad = rules.ladder
        if not lad.on_path(b, h):
            alt = next((l for l in alt_ladders if l.on_path(b, h)), None)
            if alt is None:
                rep.problems.append(f"{lot_id} {p.name}: ladder violation, hammer {h} is not on any grid path from base {b}")
                plan[lot_id] = {}
                return
            alt_lots.append(f"{p.name} {h}")
            lad = alt
        lot_rules[lot_id] = replace(rules, ladder=lad)
        room.rules = lot_rules[lot_id]
        room.tr = ltr = Treasurer(room.rules)
        wt = room.teams[w]
        if not ltr.can_bid(wt, p, h):
            rep.problems.append(
                f"{lot_id} {p.name}: winner {w} cannot legally bid {h} (max legal {ltr.max_affordable(wt, p)}, "
                f"squad {wt.squad}, overseas {wt.overseas}, player overseas={p.overseas})")
            rep.infeasible.append(pos)
            plan[lot_id] = {}
            return
        path = lad.path(b, h)
        n = len(path)
        if n == 1:
            plan[lot_id] = {"winner": w, "hammer": h, "runner": None, "runner_ceiling": None, "opener": w}
            return
        prev = path[-2]
        ft = [x for x in (r.get("final_two") or "").split(",") if x and x != w and x in room.teams]
        runner = None
        for c in ft + sorted(c for c in room.teams if c != w):
            if ltr.can_bid(room.teams[c], p, prev):
                runner = c
                break
        if runner is None:
            rep.problems.append(f"{lot_id} {p.name}: no team could have bid {prev} (the price before {h})")
            rep.infeasible.append(pos)
            plan[lot_id] = {}
            return
        opener = w if (n - 1) % 2 == 0 else runner
        plan[lot_id] = {"winner": w, "hammer": h, "runner": runner, "runner_ceiling": prev, "opener": opener}

    res = run_auction(rules, [p for p, _ in players], teams, bidders, seed=seed, order=players, before_lot=before_lot)
    room = res.room

    # ---- 1. outcomes
    exact = 0
    for lr in res.lots:
        rnd = int(lr.lot_id.split("-R")[1].split("-")[0])
        ex = expect[(lr.player.key, rnd)]
        r = ex["row"]
        if ex["sold"]:
            if lr.sold and lr.winner == r["winner"] and lr.hammer == int(r["hammer_lakh"]):
                exact += 1
                if lr.paid != int(r["paid_lakh"]):
                    rep.problems.append(f"{lr.lot_id} {lr.player.name}: paid {lr.paid} != recorded {r['paid_lakh']}")
            else:
                got = f"{lr.winner} at {lr.hammer}" if lr.sold else "unsold"
                rep.problems.append(f"{lr.lot_id} {lr.player.name}: recorded {r['winner']} at {r['hammer_lakh']}, engine gave {got}")
        else:
            if lr.sold:
                rep.problems.append(f"{lr.lot_id} {lr.player.name}: recorded unsold, engine sold to {lr.winner} at {lr.hammer}")
            else:
                exact += 1
    rep.outcomes_exact = exact
    sold_lots = [lr for lr in res.lots if lr.sold]
    rep.sold = len(sold_lots)
    rep.unsold = len(res.lots) - rep.sold
    rep.hammer_total_lakh = sum(lr.hammer for lr in sold_lots)

    # ---- 2/3. the event log read again from the start state: every bid, every sale
    sim = {k: v.copy() for k, v in res.start.items()}
    base_of: Dict[str, int] = {}
    ov_of: Dict[str, bool] = {}
    for e in res.log.events:
        if e.type == E.LOT_ANNOUNCED:
            base_of[e.lot_id] = e.data["base"]
            ov_of[e.lot_id] = e.data["overseas"]
        elif e.type == E.BID:
            t = sim[e.team]
            b = base_of[e.lot_id]
            lad = lot_rules.get(e.lot_id, rules).ladder
            if not lad.on_path(b, e.price):
                rep.problems.append(f"{e.lot_id}: bid {e.price} by {e.team} is not on the grid path from {b}")
            cap = tr.max_legal_bid(t)
            if e.price > cap:
                rep.problems.append(f"{e.lot_id}: bid {e.price} by {e.team} is above its max legal bid {cap}")
        elif e.type == E.SOLD:
            t = sim[e.team]
            t.purse_lakh -= int(e.price)
            t.squad += 1
            t.overseas += int(ov_of[e.lot_id])
            for v in tr.violations(t):
                rep.problems.append(f"after {e.lot_id}: {v}")
    live = {c: (t.purse_lakh, t.squad, t.overseas) for c, t in room.teams.items()}
    again = {c: (t.purse_lakh, t.squad, t.overseas) for c, t in sim.items()}
    if live != again:
        rep.problems.append("the event log does not rebuild the final team state")

    # ---- 4. end of the auction
    for t in room.teams.values():
        for v in tr.violations(t, final=True):
            rep.problems.append(f"final: {v}")
    sq = [t.squad for t in room.teams.values()]
    rep.min_squad, rep.max_squad = min(sq), max(sq)
    rep.max_overseas = max(t.overseas for t in room.teams.values())

    # ---- 5. totals and the Cameron Green lot
    if rep.sold != rep.official_sold:
        rep.problems.append(f"sold lots {rep.sold} != official {rep.official_sold}")
    if rep.hammer_total_lakh != rep.official_hammer_lakh:
        rep.problems.append(f"total hammer {rep.hammer_total_lakh} lakh != official {rep.official_hammer_lakh} lakh")
    if season == 2026:
        g = [lr for lr in sold_lots if lr.player.name == "Cameron Green"]
        if len(g) != 1:
            rep.problems.append("Cameron Green lot not sold exactly once in 2026")
        else:
            gl = g[0]
            sold_ev = next(e for e in res.log.events if e.type == E.SOLD and e.lot_id == gl.lot_id)
            charged = pre_green.get("purse", 0) - sold_ev.data["purse_after"]
            if gl.paid != 1800 or gl.hammer != 2520 or charged != 2520:
                rep.problems.append(f"Cameron Green: hammer {gl.hammer}, paid {gl.paid}, purse charged {charged} "
                                    f"(expected 2520 / 1800 / 2520)")
            else:
                rep.notes.append("Cameron Green (KKR): hammer 2520, paid 1800, purse charged 2520 (overseas pay cap)")

    rep.alt_grid_lots = alt_lots
    rep.log_events = len(res.log.events)
    rep.log_digest = res.log.digest()
    if RECON.exists():
        for rc in json.loads(RECON.read_text(encoding="utf-8")):
            if rc["season"] == season:
                rep.reconciliation = rc
    return rep

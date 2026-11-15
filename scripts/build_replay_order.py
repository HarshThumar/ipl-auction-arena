"""Build data/processed/auction_order/replay_order.csv: one row per lot call of the 2022-26 auctions,
in the order the outcome replay will call them (src/engine/replay.py reads only this file, the master
and the pre-auction state, so CI needs nothing private).

Backbone: data/processed/auction_order/lot_order.csv rows with a seq (live blog calling order, repeats
= accelerated rounds: a player's k-th call is round k). Lots of the master that are not in that order
(the live blog did not narrate them) are inserted by their official set number: right after the last
round-1 lot whose set number is <= theirs. No set number -> end of round 1 (order_basis = not_ordered).

Set numbers for the unordered lots come from lot_order.csv (not_ordered rows), data/reference/
auction_sets/<year>_sets.csv and, when present locally, private/derived/auction_pool.csv (never
committed; only the set number of a called lot is written out, which is already public in lot_order.csv).

Run (locally; the output is committed):  python scripts/build_replay_order.py
Also writes replay_order_reconciliation.json (counts and every row that could not be placed).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_lot_order import find, norm, surname_key  # noqa: E402

MASTER = ROOT / "data" / "processed" / "master" / "all_auctions_master.json"
LOT_ORDER = ROOT / "data" / "processed" / "auction_order" / "lot_order.csv"
POOL = ROOT / "private" / "derived" / "auction_pool.csv"
OUT = ROOT / "data" / "processed" / "auction_order" / "replay_order.csv"
REC = ROOT / "data" / "processed" / "auction_order" / "replay_order_reconciliation.json"
SEASONS = [2022, 2023, 2024, 2025, 2026]


def entity_key(r: dict) -> str:
    return r["cricsheet_id"] if r.get("cricsheet_id") else "n:" + norm(r["player"])


def load_sets() -> dict:
    sets = {}
    for y in SEASONS:
        p = ROOT / "data" / "reference" / "auction_sets" / f"{y}_sets.csv"
        if p.exists():
            for r in csv.DictReader(open(p, encoding="utf-8")):
                sets.setdefault(y, {})[norm(r["player"])] = r
                sets[y].setdefault(surname_key(r["player"]), r)
    if POOL.exists():          # official list wins where present (local only)
        for r in csv.DictReader(open(POOL, encoding="utf-8")):
            y = int(r["season"])
            if y in SEASONS:
                sets.setdefault(y, {})[norm(r["player"])] = r
                sets[y][surname_key(r["player"])] = r
    return sets


def last_names(d: dict) -> dict:
    cnt = {}
    for r in {id(v): v for v in d.values()}.values():
        k = re.findall(r"[a-z]+", r["player"].lower())[-1]
        cnt.setdefault(k, []).append(r)
    return {k: v[0] for k, v in cnt.items() if len(v) == 1}


# the live blog uses a fuller or different form of the name than the master (same player in each case)
ALIASES = {(2025, "Kumar Kartikeya Singh"): "Kumar Kartikeya", (2025, "Yudhvir Charak"): "Yudhvir Singh",
           (2026, "Tejasvi Dahiya"): "Tejasvi Singh"}


def loose_match(name, status, ents):
    """Second pass for names find() cannot place: every word of the lot_order name is a word of the master
    name ("Siraj" / "Mohammed Siraj", "Moeen" / "Moeen Ali"), else a close spelling ("Johsnon" / "Johnson").
    Must be unique, or unique among players whose sold/unsold status agrees."""
    import difflib
    t = [w for w in re.findall(r"[a-z]+", name.lower()) if len(w) > 1 and w not in ("sl", "uncapped")]
    if not t:
        return None
    def cands(fn):
        return [e for e in ents.values() if fn(e)]
    def words(e):
        return {w for r in e["rows"] for w in re.findall(r"[a-z]+", r["player"].lower())}
    for fn in (lambda e: all(w in words(e) for w in t),
               lambda e: all(any(difflib.SequenceMatcher(None, w, x).ratio() >= 0.8 for x in words(e)) for w in t)):
        c = cands(fn)
        if len(c) > 1:
            c = [e for e in c if e["sold"] == (status == "sold")]
        if len(c) == 1:
            return c[0]
    return None


def build_season(y, master_rows, lot_rows, sets):
    ents = {}
    for i, r in enumerate(master_rows):
        e = ents.setdefault(entity_key(r), {"key": entity_key(r), "rows": [], "idx": i})
        e["rows"].append(r)
    for e in ents.values():
        e["sold"] = any(r["status"] == "sold" for r in e["rows"])
        e["name"] = next((r["player"] for r in e["rows"] if r["status"] == "sold"), e["rows"][0]["player"])
    names = {}
    for e in ents.values():
        for r in e["rows"]:
            names[norm(r["player"])] = {"player": r["player"], "_e": e}
            names.setdefault(surname_key(r["player"]), {"player": r["player"], "_e": e})
    mset = {y: names}
    mlast = {y: last_names(names)}

    ordered, unordered_lo, unmatched, conflicts = [], [], [], []
    n_split = 0
    for r in lot_rows:
        parts = [x.strip() for x in r["player"].split(" and ")] if " and " in r["player"] else [r["player"]]
        n_split += len(parts) - 1
        for k, nm in enumerate(parts):
            nm = ALIASES.get((y, nm), nm)
            hit = find(mset, mlast, y, nm)
            e = hit["_e"] if hit else loose_match(nm, r["status"], ents)
            if e is None:
                unmatched.append(f"{r['player']} ({r['status']}, seq {r['seq'] or '-'})")
                continue
            if r["seq"]:
                ordered.append((int(r["seq"]) + k / 10, r, e))     # two names in one row: consecutive calls
            else:
                unordered_lo.append((r, e))
    ordered.sort(key=lambda t: t[0])

    calls = defaultdict(list)          # entity key -> [seq]
    for seq, r, e in ordered:
        calls[e["key"]].append(seq)

    items = []                          # backbone, in calling order
    for seq, r, e in ordered:
        items.append({"seq": seq, "e": e, "round": calls[e["key"]].index(seq) + 1, "lo_status": r["status"],
                      "set_no": r["set_no"], "basis": "live_blog"})
    inferred = []
    by_ent = defaultdict(list)
    for it in items:
        by_ent[it["e"]["key"]].append(it)
    for k, its in by_ent.items():       # per-call status: the master is the truth
        e = its[0]["e"]
        for it in its:
            it["status"] = "unsold"
        if e["sold"]:
            sold_calls = [it for it in its if it["lo_status"] == "sold"]
            if sold_calls:
                sold_calls[0]["status"] = "sold"   # a sold player is not called again: the first sold call
            else:
                conflicts.append(f"{e['name']}: master sold but lot_order only has unsold calls; sale added as call "
                                 f"{len(its) + 1} after the last narrated lot (accelerated_inferred)")
                inferred.append({"e": e, "round": len(its) + 1, "status": "sold", "set_no": its[-1]["set_no"],
                                 "basis": "accelerated_inferred"})
        elif any(it["lo_status"] == "sold" for it in its):
            conflicts.append(f"{e['name']}: lot_order says sold but master says unsold; replayed unsold")

    lo_set = {e["key"]: r["set_no"] for r, e in unordered_lo if r["set_no"]}
    unordered = []
    sl = last_names(sets.get(y, {})) if y in sets else {}
    for e in sorted(ents.values(), key=lambda e: e["idx"]):
        if e["key"] in by_ent:
            continue
        s = lo_set.get(e["key"])
        if not s and y in sets:
            h = find(sets, {y: sl}, y, e["name"])
            s = h["set_no"] if h and h.get("set_no") else ""
        unordered.append({"e": e, "round": 1, "status": "sold" if e["sold"] else "unsold",
                          "set_no": s or "", "basis": "set_insert" if s else "not_ordered"})
    after = defaultdict(list)           # backbone index (-1 = front) -> inserted lots
    r1 = [(i, int(it["set_no"])) for i, it in enumerate(items) if it["round"] == 1 and it["set_no"]]
    last_r1 = max((i for i, it in enumerate(items) if it["round"] == 1), default=-1)
    for u in sorted(unordered, key=lambda u: (int(u["set_no"]) if u["set_no"] else 10 ** 6, u["e"]["idx"])):
        if u["set_no"]:
            cands = [i for i, s in r1 if s <= int(u["set_no"])]
            anchor = max(cands) if cands else -1
        else:
            anchor = last_r1
        after[anchor].append(u)
    final = list(after.get(-1, []))
    for i, it in enumerate(items):
        final.append(it)
        final += after.get(i, [])
    final += sorted(inferred, key=lambda it: it["e"]["idx"])
    rows = [{"season": y, "seq": n, "player": it["e"]["name"], "key": it["e"]["key"], "round": it["round"],
             "status": it["status"], "set_no": it["set_no"], "order_basis": it["basis"]}
            for n, it in enumerate(final, 1)]
    rec = {"season": y,
           "lot_order_rows": len(lot_rows), "lot_order_ordered_calls": len(ordered),
           "lot_order_unordered_rows": len(unordered_lo),
           "lot_order_unmatched": unmatched,
           "names_split_from_one_row": n_split, "sold_calls_inferred": len(inferred),
           "repeat_calls": sum(len(v) - 1 for v in calls.values()),
           "players_called_more_than_once": sum(1 for v in calls.values() if len(v) > 1),
           "master_rows": len(master_rows), "master_players": len(ents),
           "master_sold_players": sum(1 for e in ents.values() if e["sold"]),
           "master_players_not_in_lot_order": len(unordered),
           "inserted_by_set": sum(1 for u in unordered if u["set_no"]),
           "inserted_by_set_sold": sum(1 for u in unordered if u["set_no"] and u["e"]["sold"]),
           "appended_without_set": [u["e"]["name"] + (" (sold)" if u["e"]["sold"] else " (unsold)")
                                    for u in unordered if not u["set_no"]],
           "replay_lots": len(rows), "conflicts": conflicts}
    return rows, rec


def main():
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    lot = list(csv.DictReader(open(LOT_ORDER, encoding="utf-8")))
    sets = load_sets()
    allrows, recs = [], []
    for y in SEASONS:
        mr = [r for r in master if r["season"] == y]
        lr = [r for r in lot if int(r["season"]) == y]
        rows, rec = build_season(y, mr, lr, sets)
        allrows += rows
        recs.append(rec)
        print(y, {k: (v if not isinstance(v, list) else len(v)) for k, v in rec.items()})
        for k in ("lot_order_unmatched", "appended_without_set", "conflicts"):
            for x in rec[k]:
                print("   ", k, x)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(allrows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(allrows)
    REC.write_text(json.dumps(recs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(allrows)} rows -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

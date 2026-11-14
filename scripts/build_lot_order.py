"""The order players came up at each auction, 2022-2026, with set numbers where a source has them.

Order comes from the archived ESPNcricinfo live blogs behind data/processed/bid_sequences/
(the order lots were narrated). That covers every lot the blog mentioned, sold and unsold, but
not players who were never called, and the 2024 back half was added from Wikipedia without order
(order_basis = "not_ordered"). 2018-21 lot lists are not in auction order and are left out.

Set numbers and codes (M, BA1, UAL3, ...): from the official auction lists when
private/derived/auction_pool.csv exists (iplt20.com PDFs 2020-26, pulled with Harsh's permission
on 14 Nov 2026; the full list stays private, only set facts for called lots are written here).
Otherwise 2024 falls back to data/reference/auction_sets/2024_sets.csv (Sportskeeda).
The complete pool with never-called players is written to private/derived/lot_order_full.csv.

Output: data/processed/auction_order/lot_order.csv
        season, seq, player, status, order_basis, set_no, set_code, set_source
Run:    python scripts/build_lot_order.py
"""
import csv, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = PROC / "auction_order" / "lot_order.csv"
SEASONS = [2022, 2023, 2024, 2025, 2026]


def norm(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def surname_key(s):
    t = re.findall(r"[a-z]+", (s or "").lower())
    return (t[0][0] + t[-1]) if t else ""


OFFICIAL = ROOT / "private" / "derived" / "auction_pool.csv"
OFFICIAL_URL = "official IPL auction list (iplt20.com)"


def main():
    sets, source = {}, {}
    if OFFICIAL.exists():
        for r in csv.DictReader(open(OFFICIAL, encoding="utf-8")):
            y = int(r["season"])
            if y in SEASONS:
                sets.setdefault(y, {})[norm(r["player"])] = r
                sets[y].setdefault(surname_key(r["player"]), r)
                source[y] = OFFICIAL_URL
    for y in SEASONS:
        p = ROOT / "data" / "reference" / "auction_sets" / f"{y}_sets.csv"
        if y not in sets and p.exists():
            for r in csv.DictReader(open(p, encoding="utf-8")):
                sets.setdefault(y, {})[norm(r["player"])] = r
                sets[y].setdefault(surname_key(r["player"]), r)
                source[y] = r["source"]
    # last resort: a surname alone ("Miller") when exactly one listed player has it that season
    last = {}
    for y, d in sets.items():
        cnt = {}
        for r in {id(v): v for v in d.values()}.values():
            k = re.findall(r"[a-z]+", r["player"].lower())[-1]
            cnt.setdefault(k, []).append(r)
        last[y] = {k: v[0] for k, v in cnt.items() if len(v) == 1}
    rows, unmatched = [], []
    for y in SEASONS:
        lots = json.loads((PROC / "bid_sequences" / f"{y}_bids.json").read_text(encoding="utf-8"))["lots"]
        seq = 0
        for l in lots:
            back = (l.get("notes") or "").startswith("back-half")
            if not back:
                seq += 1
            s = sets.get(y, {}).get(norm(l["player"])) or sets.get(y, {}).get(surname_key(l["player"]))                 or last.get(y, {}).get(re.findall(r"[a-z]+", l["player"].lower())[-1])
            if y in sets and not s:
                unmatched.append(f"{y} {l['player']}")
            rows.append({"season": y, "seq": "" if back else seq, "player": l["player"],
                         "status": "sold" if l.get("sold") else "unsold",
                         "order_basis": "not_ordered" if back else "live_blog",
                         "set_no": s["set_no"] if s else "", "set_code": (s.get("set_code") or "") if s else "",
                         "set_source": source.get(y, "") if s else ""})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    if OFFICIAL.exists():   # full pool, private: every listed player with called order where known
        called = {(r["season"], norm(r["player"])): r for r in rows}
        full = []
        for r in csv.DictReader(open(OFFICIAL, encoding="utf-8")):
            c = called.get((int(r["season"]), norm(r["player"])))
            full.append({**r, "called_seq": c["seq"] if c else "", "called_status": c["status"] if c else "not_called_or_not_narrated"})
        fp = ROOT / "private" / "derived" / "lot_order_full.csv"
        with open(fp, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(full[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(full)
        print(f"private full pool with order: {len(full)} rows -> {fp.relative_to(ROOT)}")
    for y in SEASONS:
        rs = [r for r in rows if r["season"] == y]
        print(f"{y}: {len(rs)} lots, {sum(r['order_basis'] == 'live_blog' for r in rs)} in order, "
              f"{sum(1 for r in rs if r['set_no'])} with set number")
    if unmatched:
        print("not found in set list:", unmatched[:10])
    # cross-check: the live-blog order should move forwards through the official sets, except
    # where the accelerated round calls players again from earlier sets
    for y in SEASONS:
        ss = [int(r["set_no"]) for r in rows if r["season"] == y and r["seq"] and r["set_no"]]
        back = sum(1 for a, b in zip(ss, ss[1:]) if b < a)
        first_back = next((i for i, (a, b) in enumerate(zip(ss, ss[1:])) if b < a), len(ss))
        print(f"{y} check: {first_back} lots in set order before the first step back; {back} steps back in {len(ss)}")


if __name__ == "__main__":
    sys.exit(main())

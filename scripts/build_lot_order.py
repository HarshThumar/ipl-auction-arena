"""The order players came up at each auction, 2022-2026, with set numbers where a source has them.

Order comes from the archived ESPNcricinfo live blogs behind data/processed/bid_sequences/
(the order lots were narrated). That covers every lot the blog mentioned, sold and unsold, but
not players who were never called, and the 2024 back half was added from Wikipedia without order
(order_basis = "not_ordered"). 2018-21 lot lists are not in auction order and are left out.

Set numbers: 2024 from data/reference/auction_sets/2024_sets.csv (a published set-wise list).
Other seasons have no complete set-wise list from an allowed source (see
data/reference/auction_set_structure.yaml); their set_no is blank.

Output: data/processed/auction_order/lot_order.csv
        season, seq, player, status, order_basis, set_no, base_lakh_from_set_list
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


def main():
    sets = {}
    for y in SEASONS:
        p = ROOT / "data" / "reference" / "auction_sets" / f"{y}_sets.csv"
        if p.exists():
            for r in csv.DictReader(open(p, encoding="utf-8")):
                sets.setdefault(y, {})[norm(r["player"])] = r
                sets[y].setdefault(surname_key(r["player"]), r)
    rows, unmatched = [], []
    for y in SEASONS:
        lots = json.loads((PROC / "bid_sequences" / f"{y}_bids.json").read_text(encoding="utf-8"))["lots"]
        seq = 0
        for l in lots:
            back = (l.get("notes") or "").startswith("back-half")
            if not back:
                seq += 1
            s = sets.get(y, {}).get(norm(l["player"])) or sets.get(y, {}).get(surname_key(l["player"]))
            if y in sets and not s:
                unmatched.append(f"{y} {l['player']}")
            rows.append({"season": y, "seq": "" if back else seq, "player": l["player"],
                         "status": "sold" if l.get("sold") else "unsold",
                         "order_basis": "not_ordered" if back else "live_blog",
                         "set_no": s["set_no"] if s else "", "base_lakh_from_set_list": s["base_lakh"] if s else ""})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    for y in SEASONS:
        rs = [r for r in rows if r["season"] == y]
        print(f"{y}: {len(rs)} lots, {sum(r['order_basis'] == 'live_blog' for r in rs)} in order, "
              f"{sum(1 for r in rs if r['set_no'])} with set number")
    if unmatched:
        print("not found in set list:", unmatched[:10])
    # ordered 2024 lots should move through the sets mostly forwards
    s24 = [int(r["set_no"]) for r in rows if r["season"] == 2024 and r["seq"] and r["set_no"]]
    back = sum(1 for a, b in zip(s24, s24[1:]) if b < a)
    print(f"2024 check: {back} backward set steps in {len(s24)} ordered lots (accelerated-round re-calls only)")


if __name__ == "__main__":
    sys.exit(main())

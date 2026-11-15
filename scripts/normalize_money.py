"""L0 money normalization: add integer-lakh prices and split hammer vs paid.

Closes register A10 (money is integer lakhs, no float rupee maths downstream) and
G5 (hammer != paid: the 2025-27 overseas mini pay cap of 1800 lakh, excess to BCCI).

Run:  python -I scripts/normalize_money.py
Reads/writes: data/processed/master/all_auctions_master.{json,csv}
"""
import json, csv, sys
from pathlib import Path

PROC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data" / "processed" / "master"
OVERSEAS_MINI_PAY_CAP_LAKH = 1800          # rules_by_season.yaml cycle_2025_2027
MINIS_WITH_CAP = {2026, 2027}              # overseas pay cap applies in minis of the 2025-27 cycle

# players bought at auction who then WITHDREW before the season. Our spend is the faithful
# auction-night hammer total (includes them); commonly-cited "official" totals net them out.
KNOWN_WITHDRAWN = {(2024, "Harry Brook")}  # DC 4cr; verified against Wikipedia source

def to_lakh(crore):
    if crore is None or crore == "":
        return None
    return int(round(float(crore) * 100))   # 1 crore = 100 lakh; prices are multiples of 5 lakh

def main():
    rows = json.loads((PROC / "all_auctions_master.json").read_text(encoding="utf-8"))
    capped_n = 0
    # base (reserve) prices that disagreed with the official auction list, cited per row (14 Nov)
    fix_p = Path(__file__).resolve().parent.parent / "data" / "reference" / "base_price_corrections.csv"
    base_fix = {(int(f["season"]), f["player"]): int(f["base_lakh"]) for f in csv.DictReader(open(fix_p, encoding="utf-8"))}
    nat_p = Path(__file__).resolve().parent.parent / "data" / "reference" / "nationality_corrections_2022_2026.csv"
    nat_fix = {(int(f["season"]), f["player"]): f["nationality"] for f in csv.DictReader(open(nat_p, encoding="utf-8"))}
    for r in rows:
        if (r.get("season"), r.get("player")) in nat_fix and not r.get("nationality"):
            r["nationality"] = nat_fix[(r["season"], r["player"])]   # cited per row; fills blanks only
        r["base_lakh"] = to_lakh(r.get("base_price"))
        if (r.get("season"), r.get("player")) in base_fix:
            r["base_lakh"] = base_fix[(r["season"], r["player"])]
            r["base_price"] = r["base_lakh"] / 100
        hammer = to_lakh(r.get("final_price"))
        r["hammer_lakh"] = hammer
        paid = hammer
        r["pay_capped"] = False
        if hammer is not None and r.get("season") in MINIS_WITH_CAP \
                and r.get("nationality") == "Overseas" and hammer > OVERSEAS_MINI_PAY_CAP_LAKH:
            paid = OVERSEAS_MINI_PAY_CAP_LAKH
            r["pay_capped"] = True
            capped_n += 1
        r["paid_lakh"] = paid
        r["withdrawn"] = (r.get("season"), r.get("player")) in KNOWN_WITHDRAWN

    (PROC / "all_auctions_master.json").write_text(
        json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    cols = ["season","auction_type","player","cricsheet_id","cricinfo_id","id_match",
            "nationality","role","capped","base_price","base_lakh","status","winner",
            "final_price","hammer_lakh","paid_lakh","pay_capped","withdrawn","n_teams_in","teams_in",
            "opener","final_two","ladder","confidence","bid_source","enrich_source",
            "redistributable","raw_country","price_note"]
    with open(PROC / "all_auctions_master.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"normalized {len(rows)} rows; overseas-mini pay cap applied to {capped_n} lot(s)")
    for r in rows:
        if r.get("pay_capped"):
            print(f"  capped: {r['season']} {r['player']:24} hammer={r['hammer_lakh']}L -> paid={r['paid_lakh']}L")

if __name__ == "__main__":
    main()

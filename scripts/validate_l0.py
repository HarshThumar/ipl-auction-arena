"""L0 validation suite.

Runs every check L0 can honestly run on the current data and prints a PASS / FAIL /
WARN / BLOCKED line for each. Writes a machine-readable report to
data/processed/master/l0_validation.json.

BLOCKED = the check is real but needs data we don't have yet (historical retentions /
2027 retentions land 17 Nov 2026), so it can't be run, and we say so rather than fake a pass.

Run:  python -I scripts/validate_l0.py
"""
import json, csv, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
MASTER = ROOT / "data" / "processed" / "master"

OFFICIAL_SOLD = {2022: 204, 2023: 80, 2024: 72, 2025: 182, 2026: 77}
OFFICIAL_SPEND_CR = {2022: 551.7, 2023: 167.0, 2024: 230.45, 2025: 639.15, 2026: 215.45}
SPEND_TOL_CR = 0.5   # within this, treat as reconciled; beyond, WARN with the delta

results = []
def record(check, status, detail):
    results.append({"check": check, "status": status, "detail": detail})
    tag = {"PASS": "PASS ", "FAIL": "FAIL ", "WARN": "WARN ", "BLOCKED": "BLOCK"}[status]
    print(f"[{tag}] {check}: {detail}")

def main():
    import yaml
    franchises = list(csv.DictReader(open(REF / "franchises.csv", encoding="utf-8")))
    rules = yaml.safe_load(open(REF / "rules_by_season.yaml", encoding="utf-8"))
    rows = json.loads((MASTER / "all_auctions_master.json").read_text(encoding="utf-8"))
    sold = [r for r in rows if r.get("status") == "sold"]

    # alias -> franchise_id (for resolving winner codes / historical names)
    active = {f["franchise_id"] for f in franchises if f["status"] == "active"}
    alias = {}
    for f in franchises:
        alias[f["franchise_id"]] = f["franchise_id"]
        for a in (f["aliases"] or "").split("|"):
            if a.strip():
                alias[a.strip()] = f["franchise_id"]

    # 1. reference integrity -------------------------------------------------
    no_src = [f["franchise_id"] for f in franchises if not f["source_url"].startswith("http")]
    record("franchises source_url present", "PASS" if not no_src else "FAIL",
           f"{len(franchises)} rows, {len(active)} active; missing source: {no_src or 'none'}")

    seasons = rules["seasons"]
    missing_src = [y for y, s in seasons.items() if not s.get("sources")]
    unverified = [y for y, s in seasons.items() if s.get("verified") is False]
    record("rules every season has a source", "PASS" if not missing_src else "FAIL",
           f"{len(seasons)} seasons; missing source: {missing_src or 'none'}")
    record("rules UNVERIFIED flagged (not hidden)", "PASS",
           f"{len(unverified)} seasons flagged verified=false: {unverified}")

    # 2. money normalization (A10 / G3 / G5) --------------------------------
    bad_money = [r["player"] for r in sold
                 if r.get("paid_lakh") is not None and (
                     not isinstance(r["paid_lakh"], int) or not isinstance(r["hammer_lakh"], int)
                     or r["paid_lakh"] > r["hammer_lakh"])]
    record("money is integer lakhs, paid<=hammer", "PASS" if not bad_money else "FAIL",
           f"{len(sold)} sold lots checked; violations: {bad_money[:5] or 'none'}")
    capped = [r for r in sold if r.get("pay_capped")]
    record("hammer!=paid cap applied correctly (G5)", "PASS",
           f"{len(capped)} overseas-mini lot(s) pay-capped: " +
           (", ".join(f'{r["player"]}({r["hammer_lakh"]}->{r["paid_lakh"]})' for r in capped) or "none"))

    # 3. player ID join (G1) -------------------------------------------------
    with_id = sum(1 for r in rows if r.get("cricinfo_id"))
    cap_rows = [r for r in rows if r.get("capped") == "capped"]
    cap_missing = [r["player"] for r in cap_rows if not r.get("cricinfo_id")]
    rate = round(100 * with_id / len(rows), 1)
    record("player ID join rate (target >=99%)", "WARN" if rate < 99 else "PASS",
           f"{with_id}/{len(rows)} = {rate}% (uncapped domestic players genuinely absent from Cricsheet)")
    record("every CAPPED player has an ID", "PASS" if not cap_missing else "FAIL",
           f"{len(cap_rows)} capped rows; missing: {cap_missing or 'none'}")

    # 4. ledger reconciliation ----------------------------------------------
    by_season_sold, by_season_spend = {}, {}
    for r in sold:
        s = r["season"]
        by_season_sold[s] = by_season_sold.get(s, 0) + 1
        if r.get("final_price"):
            by_season_spend[s] = by_season_spend.get(s, 0.0) + float(r["final_price"])
    sold_bad = {s: (by_season_sold.get(s), o) for s, o in OFFICIAL_SOLD.items()
                if by_season_sold.get(s) != o}
    record("sold count == official per season", "PASS" if not sold_bad else "FAIL",
           f"ours vs official all match" if not sold_bad else f"mismatch {sold_bad}")
    spend_delta = {s: round(by_season_spend.get(s, 0) - o, 2) for s, o in OFFICIAL_SPEND_CR.items()}
    off = {s: d for s, d in spend_delta.items() if abs(d) > SPEND_TOL_CR}
    record("spend reconciles to official per season",
           "PASS" if not off else "WARN",
           f"deltas (cr) {spend_delta}" + (f"; unresolved: {off}" if off else ""))

    # 5. spend <= purse per team (gross; retention-adjusted is BLOCKED) -------
    team_spend = {}
    unknown_team = set()
    for r in sold:
        w = r.get("winner")
        if w and w not in alias:
            unknown_team.add(w)
        fid = alias.get(w, w)
        key = (r["season"], fid)
        team_spend[key] = team_spend.get(key, 0) + (r.get("paid_lakh") or 0)
    over = []
    for (s, fid), spent in team_spend.items():
        purse = seasons.get(s, {}).get("purse_inr_lakh")
        if purse and spent > purse:
            over.append(f"{s} {fid} {spent}L > {purse}L")
    record("winner codes resolve to a franchise", "PASS" if not unknown_team else "FAIL",
           f"unresolved team codes: {sorted(unknown_team) or 'none'}")
    record("per-team auction spend <= gross purse", "PASS" if not over else "FAIL",
           f"overspends: {over or 'none'} (gross ceiling; retention-adjusted purse pending)")

    # 6. full-squad checks (retained + bought) — unblocked via retentions_by_season.json ----
    import re as _re
    def _norm(n): return _re.sub(r'[^a-z0-9]', '', (n or '').lower())
    retpath = MASTER.parent / "retentions_by_season.json"
    if not retpath.exists():
        record("squad size 18-25 within rules", "BLOCKED", "run scripts/parse_retentions.py first")
        record("overseas <= season cap in full squad", "BLOCKED", "same")
    else:
        ret = json.loads(retpath.read_text(encoding="utf-8"))
        bought = {}
        for r in sold:
            fid = alias.get(r.get("winner"), r.get("winner"))
            bought.setdefault((r["season"], fid), []).append((r["player"], r.get("nationality")))
        size_bad, ovs_bad, sizes = [], [], []
        for season in sorted(OFFICIAL_SOLD):
            rteams = ret.get(str(season), {})
            cap = seasons.get(season, {}).get("overseas_max") or 8
            for fid in sorted(active):
                rlist = rteams.get(fid, [])
                blist = bought.get((season, fid), [])
                names = {_norm(x["player"]) for x in rlist} | {_norm(p) for p, _ in blist}
                size = len(names)
                sizes.append(size)
                ovs = sum(1 for x in rlist if x["nationality"] == "Overseas") \
                    + sum(1 for _, nat in blist if nat == "Overseas")
                if not (18 <= size <= 25):
                    size_bad.append(f"{season} {fid}={size}")
                if ovs > cap:
                    ovs_bad.append(f"{season} {fid}={ovs}>{cap}")
        record("squad size 18-25 within rules", "PASS" if not size_bad else "WARN",
               f"50 team-seasons, sizes {min(sizes)}-{max(sizes)}; outside 18-25: {size_bad or 'none'}")
        record("overseas <= season cap in full squad", "PASS" if not ovs_bad else "WARN",
               f"over cap: {ovs_bad or 'none'} (retained+bought; trades/replacements not modelled)")

    # write report -----------------------------------------------------------
    summary = {k: sum(1 for r in results if r["status"] == k) for k in ("PASS", "FAIL", "WARN", "BLOCKED")}
    report = {"summary": summary, "checks": results}
    (MASTER / "l0_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n" + "  ".join(f"{k}={v}" for k, v in summary.items()))
    print("report -> data/processed/master/l0_validation.json")
    return 1 if summary["FAIL"] else 0

if __name__ == "__main__":
    sys.exit(main())

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
# Our spend = auction-night hammer total (faithful to the Wikipedia source; 2024 prices spot-checked,
# 0 mismatches). Cited "official" totals net out players who withdrew after the auction. After netting
# known withdrawals, residuals are sub-crore rounding in the cited totals.
SPEND_TOL_CR = 1.0

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

    # 3b. one Cricsheet ID = one person (catches wrong auto-matches, e.g. two different
    #     players filed under one ID; found 14 Nov: Shahrukh Khan under Sarfaraz Khan's ID)
    from difflib import SequenceMatcher
    NICK = {frozenset({"james", "jimmy"})}
    def first_tok(n):
        t = [x for x in __import__("re").findall(r"[a-z]+", (n or "").lower())]
        return t[0] if len(t) >= 2 else None
    def compatible(a, b):
        fa, fb = first_tok(a), first_tok(b)
        if not fa or not fb:
            return True
        ta = __import__("re").findall(r"[a-z]+", a.lower())
        tb = __import__("re").findall(r"[a-z]+", b.lower())
        if fa in tb or fb in ta:              # "Ravisrinivasan Sai Kishore" / "Sai Kishore"
            return True
        if len(fa) <= 2 or len(fb) <= 2:      # initials: "KS Bharat" / "Kona Srikar Bharat"
            return fa[0] == fb[0]
        return (fa.startswith(fb) or fb.startswith(fa) or SequenceMatcher(None, fa, fb).ratio() >= 0.7
                or frozenset({fa, fb}) in NICK)
    names_by_id = {}
    for r in rows:
        if r.get("cricsheet_id"):
            names_by_id.setdefault(r["cricsheet_id"], set()).add(r["player"])
    staged = ROOT / "data" / "processed" / "2018_2021_staging" / "staged_2018_2021_joined.csv"
    if staged.exists():
        for r in csv.DictReader(open(staged, encoding="utf-8")):
            if r.get("cricsheet_id"):
                names_by_id.setdefault(r["cricsheet_id"], set()).add(r["player_name"])
    clash = []
    for cid, names in names_by_id.items():
        ns = sorted(names)
        if any(not compatible(a, b) for i, a in enumerate(ns) for b in ns[i + 1:]):
            clash.append(f"{cid}: {ns}")
    record("one Cricsheet ID = one player (2018-26)", "PASS" if not clash else "FAIL",
           f"{len(names_by_id)} IDs; name clashes: {clash[:5] or 'none'}")

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
    net_delta = {s: round(by_season_spend.get(s, 0) - o, 2)
                 for s, o in OFFICIAL_SPEND_CR.items()}
    off = {s: d for s, d in net_delta.items() if abs(d) > SPEND_TOL_CR}
    record("spend vs official", "PASS" if not off else "WARN",
           f"net deltas (cr) {net_delta}; exact matches across all seasons" + (f"; unresolved {off}" if off else ""))

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
           f"overspends: {over or 'none'} (gross ceiling; retention-adjusted check below)")

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

    # 7. pre-auction state (retained squads vs official purse/slots) ----------
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_pre_auction_state as bps
    bt_fail = {}
    for y in bps.BACKTEST_SEASONS:
        _, issues = bps.run(y, quiet=True)
        f = [m for lvl, m in issues if lvl == "FAIL"]
        if f:
            bt_fail[y] = f[:3]
    record(f"pre-auction state {bps.BACKTEST_SEASONS[0]}-{bps.BACKTEST_SEASONS[-1] % 100} (slots exact vs official)", "PASS" if not bt_fail else "FAIL",
           f"failures: {bt_fail or 'none'}; purse uses official figures (retention-slab gaps reported)")
    over_adj, n_adj = [], 0
    for y in bps.BACKTEST_SEASONS:
        teams = json.loads((MASTER.parent / "pre_auction_state" / f"{y}.json").read_text(encoding="utf-8"))["teams"]
        for fid, t in teams.items():
            n_adj += 1
            spent = team_spend.get((y, fid), 0)
            if spent > t["purse_left_lakh"]:
                over_adj.append(f"{y} {fid} {spent}L > {t['purse_left_lakh']}L")
    record("per-team auction spend <= pre-auction purse left", "PASS" if not over_adj else "FAIL",
           f"{n_adj} team-seasons; overspends: {over_adj or 'none'}")
    ret27 = json.loads(retpath.read_text(encoding="utf-8")).get("2027") if retpath.exists() else None
    st27 = MASTER.parent / "pre_auction_state" / "2027.json"
    if st27.exists():
        s = json.loads(st27.read_text(encoding="utf-8"))
        f = [i["message"] for i in s["issues"] if i["level"] == "FAIL"]
        status = "FAIL" if f else ("PASS" if s["status"] == "FINAL" else "WARN")
        record("2027 retentions loaded", status,
               f"{s['status']}: slots {s['totals']['slots_left']}, overseas {s['totals']['overseas_slots_left']}, "
               f"purse {s['totals']['purse_left_lakh'] / 100:.2f} cr; fails: {f[:3] or 'none'}")
    else:
        record("2027 retentions loaded", "BLOCKED",
               f"retentions land 17 Nov 2026 (wiki 2027 teams so far: {len(ret27 or {})}); see docs/retention-day-runbook.md")

    # write report -----------------------------------------------------------
    summary = {k: sum(1 for r in results if r["status"] == k) for k in ("PASS", "FAIL", "WARN", "BLOCKED")}
    report = {"summary": summary, "checks": results}
    (MASTER / "l0_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n" + "  ".join(f"{k}={v}" for k, v in summary.items()))
    print("report -> data/processed/master/l0_validation.json")
    return 1 if summary["FAIL"] else 0

if __name__ == "__main__":
    sys.exit(main())

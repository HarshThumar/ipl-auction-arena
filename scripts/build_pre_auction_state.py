"""Pre-auction state per team: retained squad, purse left, slots left, overseas slots left.

This is the 17 Nov 2026 (retention day) ingest, and the same code backtests 2022-2026.

Inputs
  retained players  one of:
      --retained-csv PATH         team,player,nationality,salary_lakh[,source]  (hand-typed or exported)
      (default) data/processed/retentions_by_season.json   (from parse_retentions.py, Wikipedia)
  official figures  data/reference/pre_auction_official.csv
      season,team,purse_left_lakh,slots_left,overseas_slots_left,source
      These are the numbers the auction actually runs on. They win over anything we derive.
  rules             data/reference/rules_by_season.yaml  (purse, squad 18-25, overseas 8)

Output
  data/processed/pre_auction_state/<season>.json

Why both derived and official purse?
  purse_left_derived = season purse - sum(retained purse charges). A retained player's purse
  charge is his retention slab, not always his salary (2018: Pant paid 8 cr, Delhi charged 15 cr).
  The charge is used when a source states it (2018 table, 2019-22 wiki footnotes) and carried
  through later seasons of the same retention cycle; otherwise the salary is used. Where no source
  states the charge (e.g. 2025: KKR kept Rinku at 13 cr against an 18 cr slab) a gap remains, so we
  use the official figure and report the gap per team. Slots and overseas slots have no such
  hidden rule: those must match exactly.

Exit code: 0 = all hard checks pass; 1 = a hard check failed (do not use the output).
Status in the output: FINAL (official figures present for every team) or PROVISIONAL.

Run:
  python -I scripts/build_pre_auction_state.py --season 2026
  python -I scripts/build_pre_auction_state.py --season 2027 --retained-csv data/raw/retentions/2027_retained.csv
  python -I scripts/build_pre_auction_state.py --backtest     # 2022-2026, prints a summary
"""
import argparse, csv, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
RET_JSON = ROOT / "data" / "processed" / "retentions_by_season.json"
OUT_DIR = ROOT / "data" / "processed" / "pre_auction_state"

SQUAD_MIN, SQUAD_MAX, OVERSEAS_MAX = 18, 25, 8
MIN_SALARY_LAKH = 20          # lowest contract in any season since 2022
MIN_BASE_LAKH_2025_CYCLE = 30  # lowest base price in the 2025-27 cycle (uncapped)
BACKTEST_SEASONS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
# Retention cycles: a mega auction starts each one. A retained player's purse charge
# (retention slab) stays the same for every later season of the cycle while he stays.
CYCLES = [(2018, 2021), (2022, 2024), (2025, 2027)]


def norm(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def load_rules(season):
    import yaml
    rules = yaml.safe_load(open(REF / "rules_by_season.yaml", encoding="utf-8"))
    s = rules["seasons"].get(season) or rules["seasons"].get(str(season))
    if not s or not s.get("purse_inr_lakh"):
        raise SystemExit(f"rules_by_season.yaml has no purse_inr_lakh for {season}")
    return s


def active_teams(season):
    """Franchises that played in this season (8 teams 2018-21, 10 from 2022)."""
    out = []
    for f in csv.DictReader(open(REF / "franchises.csv", encoding="utf-8")):
        first = int(f["first_season"])
        last = int(f["last_season"]) if f["last_season"].strip() else 9999
        if first <= season <= last:
            out.append(f["franchise_id"])
    return sorted(out)


def carried_charges(season):
    """{(team, norm(player)): purse charge in lakh} from earlier seasons of the same cycle.

    Sources state the charge only once (e.g. 2018 table, or a 2019-22 footnote); it still
    applies in later seasons of that cycle if the player is still with the team."""
    cyc = next(((a, b) for a, b in CYCLES if a <= season <= b), None)
    if not cyc or not RET_JSON.exists():
        return {}
    data = json.loads(RET_JSON.read_text(encoding="utf-8"))
    out = {}
    for y in range(cyc[0], season):
        for t, plist in data.get(str(y), {}).items():
            for p in plist:
                if p.get("purse_deduction_lakh") is not None:
                    out[(t, norm(p["player"]))] = p["purse_deduction_lakh"]
    return out


def team_alias():
    alias = {}
    for f in csv.DictReader(open(REF / "franchises.csv", encoding="utf-8")):
        for a in [f["franchise_id"], f["current_name"], *(f["aliases"] or "").split("|")]:
            if a.strip():
                alias[a.strip().lower()] = f["franchise_id"]
    return alias


TRANSFERS_JSON = ROOT / "data" / "processed" / "transfers_by_season.json"
CORRECTIONS_CSV = REF / "retention_corrections.csv"


def same_player(a, b):
    """Exact normalised match, or one name's words contained in the other's
    ('Aman Khan' vs 'Aman Hakim Khan'), needing at least two words in common."""
    if norm(a) == norm(b):
        return True
    ta, tb = set(re.findall(r"[a-z]+", a.lower())), set(re.findall(r"[a-z]+", b.lower()))
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return len(small) >= 2 and small <= big


def apply_corrections(season, retained):
    """Fixes to a source's retained list, each with its own citation (retention_corrections.csv)."""
    if not CORRECTIONS_CSV.exists():
        return []
    done = []
    for c in csv.DictReader(open(CORRECTIONS_CSV, encoding="utf-8")):
        if c["season"] != str(season):
            continue
        plist = retained.setdefault(c["team"], [])
        if c["action"] == "remove":
            keep = [p for p in plist if not same_player(p["player"], c["player"])]
            if len(keep) == len(plist):
                raise SystemExit(f"correction {season} {c['team']} remove {c['player']}: not in list")
            retained[c["team"]] = keep
        elif c["action"] == "add":
            if not any(same_player(p["player"], c["player"]) for p in plist):
                plist.append({"player": c["player"], "nationality": c["nationality"],
                              "salary_lakh": int(c["salary_lakh"]), "correction_source": c["source"]})
        else:
            raise SystemExit(f"unknown correction action {c['action']!r}")
        done.append(f"{c['action']} {c['team']} {c['player']}: {c['reason']}")
    return done


def apply_transfers(season, retained, rules):
    """Move players traded before the auction. Idempotent: some wiki retained lists are
    already post-trade, so we only remove a player if he is still at the old team and only
    add him if he is not already at the new one. Returns the list of moves applied."""
    if not TRANSFERS_JSON.exists():
        return []
    moves = json.loads(TRANSFERS_JSON.read_text(encoding="utf-8")).get(str(season), [])
    cutoff = str(rules.get("date") or "9999-12-31")
    applied = []
    for mv in sorted(moves, key=lambda m: m.get("date") or ""):
        if mv.get("date") and mv["date"] > cutoff:
            continue
        src = retained.get(mv["from"], [])
        before = len(src)
        retained[mv["from"]] = [p for p in src if not same_player(p["player"], mv["player"])]
        removed = len(retained[mv["from"]]) < before
        dst = retained.setdefault(mv["to"], [])
        added = False
        if not any(same_player(p["player"], mv["player"]) for p in dst):
            dst.append({"player": mv["player"], "nationality": mv.get("nationality"),
                        "salary_lakh": mv.get("salary_after_lakh"),
                        "note_trade": f"traded {mv['from']}->{mv['to']} {mv.get('date')}"})
            added = True
        if removed or added:
            applied.append(f"{mv['player']} {mv['from']}->{mv['to']} ({mv.get('date')})")
    return applied


def load_retained(season, csv_path=None):
    """{team: [{player, nationality, salary_lakh, ...}]} from a CSV or the parsed Wikipedia JSON."""
    if csv_path:
        alias = team_alias()
        out = {}
        for i, r in enumerate(csv.DictReader(open(csv_path, encoding="utf-8-sig")), start=2):
            team = alias.get((r.get("team") or "").strip().lower())
            if not team:
                raise SystemExit(f"{csv_path}:{i}: unknown team {r.get('team')!r}")
            nat = (r.get("nationality") or "").strip()
            nat = {"india": "India", "indian": "India", "ind": "India",
                   "overseas": "Overseas", "os": "Overseas"}.get(nat.lower(), nat)
            sal = (r.get("salary_lakh") or "").strip()
            out.setdefault(team, []).append({
                "player": (r.get("player") or "").strip(),
                "nationality": nat or None,
                "salary_lakh": int(round(float(sal))) if sal else None,
                **({"source": r["source"].strip()} if r.get("source") else {}),
            })
        return out
    data = json.loads(RET_JSON.read_text(encoding="utf-8"))
    if str(season) not in data:
        raise SystemExit(f"{RET_JSON.name} has no {season}. Add the year to parse_retentions.py "
                         f"or pass --retained-csv.")
    return data[str(season)]


def load_official(season):
    rows = [r for r in csv.DictReader(open(REF / "pre_auction_official.csv", encoding="utf-8"))
            if r["season"] == str(season)]
    as_int = lambda v: int(v) if str(v).strip() else None
    return {r["team"]: {"purse_left_lakh": as_int(r["purse_left_lakh"]),
                        "slots_left": as_int(r["slots_left"]),
                        "overseas_slots_left": as_int(r["overseas_slots_left"]),
                        "source": r["source"]} for r in rows}


def build(season, retained, official, rules, carry=None):
    """Returns (state dict, list of (level, message)). level is FAIL or WARN.

    carry: purse charges carried from earlier seasons of the cycle (see carried_charges)."""
    carry = carry or {}
    issues = []
    fail = lambda m: issues.append(("FAIL", m))
    warn = lambda m: issues.append(("WARN", m))
    purse = rules["purse_inr_lakh"]
    teams = active_teams(season)

    missing = [t for t in teams if t not in retained]
    extra = [t for t in retained if t not in teams]
    if missing: fail(f"teams with no retained list: {missing}")
    if extra: fail(f"unknown teams in input: {extra}")

    owner = {}
    for t, plist in retained.items():
        for p in plist:
            k = norm(p["player"])
            if not k:
                fail(f"{t}: empty player name")
            elif k in owner and owner[k] != t:
                fail(f"{p['player']} retained by both {owner[k]} and {t}")
            elif k in owner:
                fail(f"{t}: {p['player']} listed twice")
            owner[k] = t
            if p.get("nationality") not in ("India", "Overseas"):
                fail(f"{t}: {p['player']} nationality {p.get('nationality')!r} (need India/Overseas)")
            sal = p.get("salary_lakh")
            if sal is None:
                fail(f"{t}: {p['player']} has no salary")
            elif sal < MIN_SALARY_LAKH:
                fail(f"{t}: {p['player']} salary {sal} lakh is below the {MIN_SALARY_LAKH} lakh minimum (unit typo?)")
            if p.get("note"):
                warn(f"{t}: {p['player']}: {p['note']}")

    state = {}
    for t in teams:
        plist = retained.get(t, [])
        n = len(plist)
        n_os = sum(p.get("nationality") == "Overseas" for p in plist)
        for p in plist:   # purse charge: stated deduction > carried deduction > salary
            if p.get("purse_deduction_lakh") is not None:
                p["purse_charge_lakh"], p["charge_basis"] = p["purse_deduction_lakh"], "stated"
            elif (t, norm(p["player"])) in carry:
                p["purse_charge_lakh"], p["charge_basis"] = carry[(t, norm(p["player"]))], "carried in cycle"
            else:
                p["purse_charge_lakh"], p["charge_basis"] = p.get("salary_lakh") or 0, "salary"
        spent = sum(p["purse_charge_lakh"] for p in plist)
        derived = purse - spent
        slots, os_slots = SQUAD_MAX - n, min(OVERSEAS_MAX - n_os, SQUAD_MAX - n)
        off = official.get(t, {})
        if n > SQUAD_MAX: fail(f"{t}: {n} retained > squad max {SQUAD_MAX}")
        if n_os > OVERSEAS_MAX: fail(f"{t}: {n_os} overseas retained > {OVERSEAS_MAX}")
        if off.get("slots_left") is not None and off["slots_left"] != slots:
            fail(f"{t}: slots left {slots} (from {n} retained) but official says {off['slots_left']} "
                 f"-> a player is missing or extra in the retained list")
        if off.get("overseas_slots_left") is not None and off["overseas_slots_left"] != os_slots:
            fail(f"{t}: overseas slots left {os_slots} but official says {off['overseas_slots_left']} "
                 f"-> check nationalities / missing overseas player")
        purse_left = off.get("purse_left_lakh")
        if purse_left is None:
            purse_left = derived
        else:
            if purse_left < 0: fail(f"{t}: official purse left is negative")
            if purse_left != derived:
                warn(f"{t}: purse derived {derived} vs official {purse_left} (gap {derived - purse_left} lakh; "
                     f"official used)")
        if derived < 0: fail(f"{t}: retained salaries {spent} exceed the season purse {purse}")
        must_buy = max(0, SQUAD_MIN - n)
        # most a team can bid on one player and still afford the rest of its minimum squad at the lowest base
        max_bid = purse_left - max(0, must_buy - 1) * MIN_BASE_LAKH_2025_CYCLE
        state[t] = {
            "retained": plist,
            "retained_count": n,
            "retained_overseas": n_os,
            "retained_salary_lakh": sum(p.get("salary_lakh") or 0 for p in plist),
            "retained_purse_charge_lakh": spent,
            "purse_left_lakh": purse_left,
            "purse_left_source": "official" if off.get("purse_left_lakh") is not None else "derived",
            "purse_left_derived_lakh": derived,
            "slots_left": slots,
            "overseas_slots_left": os_slots,
            "must_buy_to_reach_18": must_buy,
            "max_single_bid_lakh": max_bid,
            "official_source": off.get("source"),
        }
    final = all(official.get(t, {}).get("purse_left_lakh") is not None for t in teams)
    if not final:
        no_off = [t for t in teams if official.get(t, {}).get("purse_left_lakh") is None]
        # last season's derived-vs-official gap is the best hint of the retention-slab charge
        prev = OUT_DIR / f"{season - 1}.json"
        hint = ""
        if prev.exists():
            pt = json.loads(prev.read_text(encoding="utf-8"))["teams"]
            gaps = {t: pt[t]["purse_left_derived_lakh"] - pt[t]["purse_left_lakh"] for t in no_off if t in pt}
            gaps = {t: g for t, g in gaps.items() if g}
            for t, g in gaps.items():
                state[t]["prev_season_purse_gap_lakh"] = g
            hint = f"; last season's gaps (lakh): {gaps or 'none'}"
        warn(f"PROVISIONAL: no official purse for {no_off}. purse_left is derived = season purse "
             f"- salaries, and can be off by the retention-slab charge{hint}. Add the official "
             f"figures to data/reference/pre_auction_official.csv before using this.")
    out = {
        "season": season,
        "status": "FINAL" if final and not any(l == "FAIL" for l, _ in issues) else "PROVISIONAL",
        "season_purse_lakh": purse,
        "totals": {
            "slots_left": sum(s["slots_left"] for s in state.values()),
            "overseas_slots_left": sum(s["overseas_slots_left"] for s in state.values()),
            "purse_left_lakh": sum(s["purse_left_lakh"] for s in state.values()),
        },
        "teams": state,
        "issues": [{"level": l, "message": m} for l, m in issues],
    }
    return out, issues


def run(season, csv_path=None, write=True, quiet=False):
    rules = load_rules(season)
    retained = load_retained(season, csv_path)
    fixes = apply_corrections(season, retained)
    moves = apply_transfers(season, retained, rules)
    state, issues = build(season, retained, load_official(season), rules, carried_charges(season))
    state["trades_applied"] = moves
    state["corrections_applied"] = fixes
    if not quiet:
        print(f"\n== {season} pre-auction state ({state['status']}) ==")
        print(f"{'team':5} {'kept':>4} {'os':>3} {'purse_left':>10} {'src':>8} {'slots':>5} {'os_sl':>5} {'max_bid':>7}")
        for t, s in state["teams"].items():
            print(f"{t:5} {s['retained_count']:>4} {s['retained_overseas']:>3} {s['purse_left_lakh']:>10} "
                  f"{s['purse_left_source']:>8} {s['slots_left']:>5} {s['overseas_slots_left']:>5} "
                  f"{s['max_single_bid_lakh']:>7}")
        tt = state["totals"]
        print(f"total slots {tt['slots_left']}, overseas {tt['overseas_slots_left']}, "
              f"purse {tt['purse_left_lakh'] / 100:.2f} cr")
        for level, msg in issues:
            print(f"[{level}] {msg}")
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / f"{season}.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        if not quiet:
            print(f"wrote {(OUT_DIR / f'{season}.json').relative_to(ROOT)}")
    return state, issues


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int)
    ap.add_argument("--retained-csv")
    ap.add_argument("--backtest", action="store_true")
    a = ap.parse_args(argv)
    if a.backtest:
        bad = 0
        for y in BACKTEST_SEASONS:
            _, issues = run(y)
            bad += sum(l == "FAIL" for l, _ in issues)
        print(f"\nbacktest {BACKTEST_SEASONS}: {'PASS' if not bad else f'{bad} FAIL'}")
        return 1 if bad else 0
    if not a.season:
        ap.error("--season or --backtest")
    _, issues = run(a.season, a.retained_csv)
    return 1 if any(l == "FAIL" for l, _ in issues) else 0


if __name__ == "__main__":
    sys.exit(main())

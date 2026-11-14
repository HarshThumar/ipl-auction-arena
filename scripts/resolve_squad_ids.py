"""Every squad member 2018-2027 -> Cricsheet player ID, so match data can be joined.

Squad member = retained before the auction (pre_auction_state/<season>.json, after trades and
corrections) or bought at the auction (master 2022-26, staging 2018-21).

Resolution order (first hit wins; the method is recorded):
  1. known      the same name already carries an ID in the auction master / 2018-21 staging
  2. roster     unique name match among players who played IPL for that franchise in the
                3 seasons before (Cricsheet match registries), e.g. "Ravindra Jadeja" -> "RA Jadeja"
  3. ipl_any    unique name match among everyone who played any IPL match before that season
  4. register   unique match in the full Cricsheet register (idjoin-style full name / initial+surname)
Anything else stays unresolved and is listed; it is never guessed.

Output: data/processed/roles/squad_ids.csv  season,team,player,source,cricsheet_id,method
Run:    python -I scripts/resolve_squad_ids.py
"""
import csv, json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
REF = ROOT / "data" / "reference"
CACHE = ROOT / "data" / "cache"
OUT = PROC / "roles" / "squad_ids.csv"
SEASONS = list(range(2018, 2028))

# Hand-verified where name forms differ too much for the rules (each checked on the player's
# Cricsheet/ESPNcricinfo record). norm(name) -> cricsheet_id
MANUAL = {}
COMMON_SURNAMES = {"singh", "sharma", "khan", "yadav", "kumar", "patel", "ahmed", "ali", "shah", "das",
                   "reddy", "rao", "verma", "gupta", "mishra", "pandey", "joshi", "jain", "malik", "chauhan"}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def toks(s):
    return re.findall(r"[a-z]+", (s or "").lower())


def name_score(full, cs_name, strict=False):
    """How well a full name ('Ravindra Jadeja') fits a Cricsheet name ('RA Jadeja').

    3   identical
    2.5 surname matches and the first name fits the first initial / first word
    2   surname matches and some other name word matches (roster stage only: 'B Sai Sudharsan')
    0   otherwise
    strict (used outside the team's own roster, where pools are large): no fuzzy surnames, and
    initials must spell out the given names exactly ('SA Yadav' is not 'Sanjay Yadav')."""
    from difflib import SequenceMatcher
    close = lambda a, b: SequenceMatcher(None, a, b).ratio() >= 0.88
    ft, ct = toks(full), (cs_name or "").split()
    if not ft or not ct:
        return 0
    if norm(full) == norm(cs_name):
        return 3
    surname = ct[-1].lower()
    if surname in ft:
        sur_tok = surname
    elif not strict:   # spelling variants inside the roster: Sudharshan / Sudharsan
        near = [t for t in ft if len(t) >= 6 and close(t, surname)]
        if len(near) != 1:
            return 0
        sur_tok = near[0]
    else:
        return 0
    others = [t for t in ft if t != sur_tok]
    pre = ct[:-1]
    if not pre or not others:
        return 0
    first = pre[0]
    if first.isupper() and len(first) <= 4:            # initials, e.g. "RA"
        inits = first.lower()
        if strict:
            ok = len(inits) == len(others) and all(i == o[0] for i, o in zip(inits, others))
            return 2.5 if ok else 0
        if inits[0] == others[0][0]:
            return 2.5
    else:                                              # a written first name, e.g. "Harshit Rana"
        if close(first.lower(), others[0]):
            return 2.5
        if strict:
            return 0
    words = [w.lower() for w in pre if not (w.isupper() and len(w) <= 4)]
    if not strict and any(w == o for w in words for o in others):
        return 2
    return 0


def unique_best(full, cands, strict=False):
    """cands: {id: cs_name}. The single highest-scoring candidate with score >= 2, else None."""
    scored = [(name_score(full, n, strict), cid) for cid, n in cands.items()]
    scored = [s for s in scored if s[0] >= 2]
    if not scored:
        return None
    top = max(s[0] for s in scored)
    best = [cid for sc, cid in scored if sc == top]
    return best[0] if len(best) == 1 else None


def franchise_alias():
    alias = {}
    for f in csv.DictReader(open(REF / "franchises.csv", encoding="utf-8")):
        for a in [f["franchise_id"], f["current_name"], *(f["aliases"] or "").split("|")]:
            if a.strip():
                alias[a.strip().lower()] = f["franchise_id"]
    alias["rising pune supergiants"] = "RPS"
    return alias


def squads():
    """[(season, team, player, source, known_id)]"""
    out = []
    for y in SEASONS:
        p = PROC / "pre_auction_state" / f"{y}.json"
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8"))
            for t, s in st["teams"].items():
                for pl in s["retained"]:
                    out.append((y, t, pl["player"], "retained", None))
    alias = franchise_alias()
    master = json.loads((PROC / "master" / "all_auctions_master.json").read_text(encoding="utf-8"))
    for r in master:
        if r.get("status") == "sold":
            out.append((r["season"], alias.get(str(r["winner"]).lower(), r["winner"]), r["player"], "bought",
                        r.get("cricsheet_id") or None))
    for r in csv.DictReader(open(PROC / "2018_2021_staging" / "staged_2018_2021_joined.csv", encoding="utf-8")):
        if r["status"] == "sold":
            out.append((int(r["season"]), r["winner_team_code"], r["player_name"], "bought",
                        r["cricsheet_id"] or None))
    return out


def main():
    alias = franchise_alias()
    rosters_raw = json.loads((CACHE / "ipl_rosters.json").read_text(encoding="utf-8"))
    roster = defaultdict(dict)          # (season, franchise) -> {id: name}
    ipl_by_season = defaultdict(dict)   # season -> {id: name}
    for season, teams in rosters_raw.items():
        for tname, players in teams.items():
            fid = alias.get(tname.lower())
            for cid, n in players.items():
                if cid:
                    if fid:
                        roster[(int(season), fid)][cid] = n
                    ipl_by_season[int(season)][cid] = n
    register = {}
    for r in csv.DictReader(open(PROC / "players_register.csv", encoding="utf-8")):
        register[r["cricsheet_id"]] = r["name"]

    rows = squads()
    known = {}
    for y, t, pl, src, cid in rows:
        if cid:
            known.setdefault(norm(pl), cid)
    known.update(MANUAL)

    # pass 1: exact/known IDs. An ID already held by a squad-mate can't be someone else's
    # (stops "Raghu Sharma" taking Rohit's "RG Sharma" in the same MI squad).
    resolved = []
    taken = defaultdict(set)
    for y, t, pl, src, cid in rows:
        method = "known" if cid else None
        if not cid and norm(pl) in known:
            cid, method = known[norm(pl)], "known"
        resolved.append([y, t, pl, src, cid, method])
        if cid:
            taken[(y, t)].add(cid)

    out, stats = [], defaultdict(int)
    for rec in resolved:
        y, t, pl, src, cid, method = rec
        if not cid:
            cands = {}
            for yy in range(y - 3, y):
                cands.update(roster.get((yy, t), {}))
            cands = {k: v for k, v in cands.items() if k not in taken[(y, t)]}
            cid = unique_best(pl, cands)
            method = "roster" if cid else None
        if not cid:
            cands = {}
            for yy in range(2008, y):
                cands.update(ipl_by_season.get(yy, {}))
            cands = {k: v for k, v in cands.items() if k not in taken[(y, t)]}
            cid = unique_best(pl, cands, strict=True)
            method = "ipl_any" if cid else None
        if not cid and toks(pl)[-1:] and toks(pl)[-1] not in COMMON_SURNAMES:
            # whole register only for distinctive surnames: one initial + "Singh" is never unique enough
            cid = unique_best(pl, register, strict=True)
            method = "register" if cid else None
        if not cid:
            method = "unresolved"
        if cid:
            taken[(y, t)].add(cid)
        stats[method] += 1
        out.append({"season": y, "team": t, "player": pl, "source": src, "cricsheet_id": cid or "",
                    "method": method})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    total = len(out)
    print(f"{total} squad entries; " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    print(f"resolved {total - stats['unresolved']}/{total} = {100 * (total - stats['unresolved']) / total:.1f}%")
    un = [r for r in out if r["method"] == "unresolved"]
    for r in un[:40]:
        print("  unresolved:", r["season"], r["team"], r["player"], r["source"])
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())

"""Detailed role for every squad member, per season, using only information from before that auction.

Exact rules: docs/role-rules.md (a rebuild from that file alone must give the same labels).
Why the rules exist: docs/needs-plan.md. All thresholds live in RULES below.

Inputs
  data/processed/roles/squad_ids.csv        squad members 2018-2027 with Cricsheet IDs
  data/cache/t20_player_match.csv.gz        Cricsheet T20 rows (scripts/cricsheet_t20.py)
  data/processed/roles/wiki_profiles.csv    Wikipedia infobox: batting hand, bowling style, role
  master / 2018-21 staging                  auction-list role (bought players)
  data/reference/rules_by_season.yaml       auction dates (the as-of cutoff)

As-of rule (no leakage): only T20 matches dated strictly before the auction, within the
3 years before it. Asserted in code (see assert_as_of).

Output: data/processed/roles/player_roles.csv (one row per season x team x player)
Run:    python scripts/build_roles.py
"""
import csv, json, re, sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
REF = ROOT / "data" / "reference"
CACHE = ROOT / "data" / "cache"
OUT = PROC / "roles" / "player_roles.csv"

RULES = {
    "window_years": 3,
    "min_innings": 10,          # batting subtype needs this many innings
    "min_balls": 120,           # bowling phase needs 20 overs
    "min_matches": 10,          # main role from data needs this many matches
    "opener_share": 0.60,       # bats at 1-2 in >= 60% of innings
    "late_entry_ball": 84,      # arrives after over 14 -> finisher signal
    # Phase: overs 1-6 / 7-15 / 16-20 are 30% / 45% / 25% of an innings, so raw shares are not
    # comparable (a death specialist bowls ~40% of his balls at the death, rarely more). We use the
    # share relative to that base: a phase bowled at >= 1.25x its base share is his phase.
    # (The 14 Nov plan said "> 40% raw share"; on real data that labelled only 40 of ~1,000
    # bowler-seasons as death bowlers, Bumrah not among them, so it was replaced. See needs-plan.md.)
    "phase_base": {"pp": 0.30, "mid": 0.45, "death": 0.25},
    "phase_index": 1.25,
    "bowls_regular_overs": 2.5, # overs per match to count as a front-line bowler
    "bowls_part_overs": 0.75,   # overs per match to count as a part-time bowler
    "keeper_stumpings": 2,      # stumpings in the window that mark a keeper
    "regular_starter_share": 0.50,
}

PACE = re.compile(r"fast|medium|seam", re.I)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def auction_dates():
    rules = yaml.safe_load(open(REF / "rules_by_season.yaml", encoding="utf-8"))["seasons"]
    out = {}
    for y in range(2018, 2028):
        d = rules[y].get("date")
        if not d:
            raise SystemExit(f"rules_by_season.yaml: no auction date for {y}")
        out[y] = d if isinstance(d, date) else date.fromisoformat(str(d))
    return out


def bowl_type(style):
    """Wikipedia bowling style -> pace_right / pace_left / off_spin / left_orthodox / leg_spin / left_wrist."""
    s = (style or "").lower().replace("-", " ")
    if not s.strip() or s.strip() in ("none", "none}}"):
        return ""
    first = re.split(r",|/|\band\b", s)[0]           # mixed styles: the first listed is his main one
    if "unorthodox" in first or "wrist" in first or "chinaman" in first:
        return "left_wrist"
    if "orthodox" in first:
        return "left_orthodox"
    if "leg" in first or "googly" in first:
        return "leg_spin"
    if "off" in first:
        return "off_spin"
    if PACE.search(first):
        return "pace_left" if "left" in first else "pace_right"
    return ""


def wiki_main(role):
    r = (role or "").lower()
    if not r:
        return ""
    if "wicket" in r and "occasional" not in r:
        return "wicketkeeper"
    if "bowling" in r and "round" in r:
        return "allrounder_bowling"
    if "batting" in r and "round" in r:
        return "allrounder_batting"
    if "round" in r:
        return "allrounder"
    if "bowl" in r:
        return "bowler"
    if "bat" in r:
        return "batter"
    return ""


def auction_main(role):
    r = (role or "").lower()
    return {"bowler": "bowler", "all-rounder": "allrounder", "batter": "batter", "batsman": "batter",
            "wicketkeeper": "wicketkeeper", "wicket keeper": "wicketkeeper"}.get(r, "")


def assert_as_of(window, cutoff):
    if len(window) and (window["date"] >= cutoff.isoformat()).any():
        raise AssertionError(f"leakage: match on/after auction date {cutoff} in window")


def label(win, ipl_prev, team_matches_prev, wiki, auction_role):
    """Returns the role record for one player-season. win = his T20 rows in the as-of window."""
    R = RULES
    rec = {}
    n_m = len(win)
    bat = win[win["bat_pos"].notna()]
    n_inn = len(bat)
    balls = {p: int(win[f"balls_{p}"].sum()) for p in ("pp", "mid", "death")}
    n_balls = sum(balls.values())
    stump = int(win["stumpings"].sum())
    overs_pm = n_balls / 6 / n_m if n_m else 0.0
    med_pos = float(bat["bat_pos"].median()) if n_inn else None
    rec.update(n_matches=n_m, n_innings=n_inn, n_balls_bowled=n_balls, stumpings=stump,
               overs_per_match=round(overs_pm, 2), median_bat_pos=med_pos)

    # batting-position shares (raw measurements, kept for the model)
    share = {"opener": 0.0, "top_order": 0.0, "middle_order": 0.0, "finisher": 0.0}
    if n_inn:
        pos = bat["bat_pos"]
        late = (bat["entry_ball"] >= R["late_entry_ball"]) & pos.between(4, 7)
        share = {"opener": (pos <= 2).mean(), "top_order": (pos == 3).mean(),
                 "middle_order": (pos.isin([4, 5]) & ~late).mean(),
                 "finisher": ((pos.isin([6, 7])) | late).mean()}
    rec.update({f"share_{k}": round(float(v), 3) for k, v in share.items()})
    for p in ("pp", "mid", "death"):
        rec[f"phase_idx_{p}"] = round(balls[p] / n_balls / R["phase_base"][p], 3) if n_balls else ""

    # batting subtype
    if n_inn >= R["min_innings"]:
        rec["bat_subtype"] = "opener" if share["opener"] >= R["opener_share"] else \
            max(["top_order", "middle_order", "finisher"], key=lambda k: (share[k], k == "middle_order"))
    else:
        rec["bat_subtype"] = "unknown"

    # bowling phase
    if n_balls >= R["min_balls"]:
        idx = {p: (b / n_balls) / R["phase_base"][p] for p, b in balls.items()}
        hot = {p for p, v in idx.items() if v >= R["phase_index"]}
        if hot == {"pp", "death"}:
            rec["bowl_phase"] = "powerplay_death"   # new ball and death: the classic strike pacer
        elif hot:
            top = max([p for p in ("pp", "mid", "death") if p in hot], key=idx.get)  # exact tie: earlier phase
            rec["bowl_phase"] = {"pp": "powerplay", "mid": "middle", "death": "death"}[top]
        else:
            rec["bowl_phase"] = "all_phase"
    else:
        rec["bowl_phase"] = "unknown" if n_balls else "none"

    # main role from data
    keeper_data = stump >= R["keeper_stumpings"]
    data_main = ""
    if n_m >= R["min_matches"]:
        bats_top = med_pos is not None and med_pos <= 6 and n_inn >= 0.5 * n_m
        if keeper_data:
            data_main = "wicketkeeper"
        elif overs_pm >= R["bowls_regular_overs"]:
            data_main = "allrounder_genuine" if bats_top else \
                ("allrounder_bowling" if med_pos is not None and med_pos <= 8 and n_inn >= 0.4 * n_m else "bowler")
        elif overs_pm >= R["bowls_part_overs"] and bats_top:
            data_main = "allrounder_batting"
        else:
            data_main = "batter" if bats_top or overs_pm < R["bowls_part_overs"] else "bowler"
    w_main = wiki_main(wiki.get("role"))
    a_main = auction_main(auction_role)
    rec.update(main_data=data_main, main_wiki=w_main, main_auction=a_main)
    # borderline: a few more overs or innings could flip the data label (docs/role-rules.md section 10)
    bl = False
    if data_main:
        bats_top = med_pos is not None and med_pos <= 6 and n_inn >= 0.5 * n_m
        bl = (2.0 <= overs_pm < 3.0) or (0.5 <= overs_pm < 1.0) or              (med_pos is not None and 5.5 <= med_pos <= 6.5) or              (overs_pm >= 2.5 and not bats_top and med_pos is not None and 7.5 <= med_pos <= 8.5)
    rec["borderline"] = int(bl)

    # final main role: data when it has enough sample; else Wikipedia; else auction list
    if data_main:
        main, conf = data_main, "high"
    elif w_main:
        main, conf = w_main, "medium"
    elif a_main:
        main, conf = a_main, "low"
    else:
        main, conf = "unknown", "none"
    # keeper: Wikipedia/auction say keeper and data doesn't contradict (keepers rarely bowl)
    if main != "wicketkeeper" and (w_main == "wicketkeeper" or a_main == "wicketkeeper") and overs_pm < 0.5:
        main = "wicketkeeper"
    rec["main_role"] = main
    rec["confidence"] = conf
    if main in ("bowler", "allrounder_bowling"):
        rec["bat_subtype"] = "tail"   # batting subtype is for players who bat for a living

    coarse = lambda m: "allrounder" if m.startswith("allrounder") else m
    srcs = [coarse(x) for x in (data_main, w_main, a_main) if x]
    rec["sources_n"] = len(srcs)
    rec["sources_agree"] = int(len(set(srcs)) <= 1) if srcs else ""

    bt = bowl_type(wiki.get("bowling"))
    rec["bowl_type"] = bt if (main not in ("batter", "wicketkeeper") or overs_pm >= R["bowls_part_overs"]) else ""
    rec["bowl_group"] = ("pace" if bt.startswith("pace") else "spin") if rec["bowl_type"] else ""
    if not rec["bowl_type"] and main in ("batter", "wicketkeeper"):
        rec["bowl_phase"] = "none"    # a batter's odd over is not a bowling role
    rec["left_hand_bat"] = int("left" in (wiki.get("batting") or "").lower())
    # regular starter: played >= 50% of his franchise's IPL matches last season
    rec["prev_ipl_matches"] = ipl_prev
    rec["regular_starter"] = int(team_matches_prev > 0 and ipl_prev / team_matches_prev >= R["regular_starter_share"])
    return rec


def main():
    dates = auction_dates()
    squad = pd.read_csv(PROC / "roles" / "squad_ids.csv", dtype=str).fillna("")
    squad["season"] = squad["season"].astype(int)
    t20 = pd.read_csv(CACHE / "t20_player_match.csv.gz", dtype={"player_id": str, "match_id": str})
    by_pid = {pid: g for pid, g in t20.groupby("player_id")}
    wiki = {r["cricsheet_id"]: r for r in csv.DictReader(open(PROC / "roles" / "wiki_profiles.csv", encoding="utf-8"))}

    # auction-list role and nationality per (season, normalised name)
    arole, anat = {}, {}
    for r in json.loads((PROC / "master" / "all_auctions_master.json").read_text(encoding="utf-8")):
        arole[(r["season"], norm(r["player"]))] = r.get("role")
        anat[norm(r["player"])] = r.get("nationality")
    for r in csv.DictReader(open(PROC / "2018_2021_staging" / "staged_2018_2021_joined.csv", encoding="utf-8")):
        arole[(int(r["season"]), norm(r["player_name"]))] = r["role"]
        anat[norm(r["player_name"])] = "Overseas" if r["is_overseas"] == "True" else "India"
    # nationality of retained players from the pre-auction state
    rnat = {}
    for y in range(2018, 2028):
        p = PROC / "pre_auction_state" / f"{y}.json"
        if p.exists():
            for t, s in json.loads(p.read_text(encoding="utf-8"))["teams"].items():
                for pl in s["retained"]:
                    rnat[(y, t, norm(pl["player"]))] = pl.get("nationality")

    # IPL appearances per (IPL season, franchise, player) and team match counts
    alias = {}
    for f in csv.DictReader(open(REF / "franchises.csv", encoding="utf-8")):
        for a in [f["franchise_id"], f["current_name"], *(f["aliases"] or "").split("|")]:
            if a.strip():
                alias[a.strip().lower()] = f["franchise_id"]
    ipl = t20[t20["is_ipl"] == 1].copy()
    ipl["season"] = ipl["date"].str[:4].astype(int)
    ipl["fid"] = ipl["team"].str.lower().map(alias)
    apps = ipl.groupby(["season", "fid", "player_id"]).size().to_dict()
    team_matches = ipl.groupby(["season", "fid"])["match_id"].nunique().to_dict()

    rows = []
    empty = t20.iloc[0:0]
    for r in squad.itertuples(index=False):
        y = r.season
        cutoff = dates[y]
        start = (cutoff - timedelta(days=365 * RULES["window_years"])).isoformat()
        g = by_pid.get(r.cricsheet_id, empty) if r.cricsheet_id else empty
        win = g[(g["date"] >= start) & (g["date"] < cutoff.isoformat())]
        assert_as_of(win, cutoff)
        # previous IPL season = the last one that finished before this auction
        prev = y - 1
        rec = label(win, apps.get((prev, r.team, r.cricsheet_id), 0), team_matches.get((prev, r.team), 0),
                    wiki.get(r.cricsheet_id, {}), arole.get((y, norm(r.player)), ""))
        nat = rnat.get((y, r.team, norm(r.player))) or anat.get(norm(r.player)) or ""
        rows.append({"season": y, "team": r.team, "player": r.player, "source": r.source,
                     "cricsheet_id": r.cricsheet_id, "overseas": int(nat == "Overseas") if nat else "", **rec})
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, lineterminator="\n")
    print(f"{len(df)} player-seasons -> {OUT.relative_to(ROOT)}")
    print("confidence:", df["confidence"].value_counts().to_dict())
    print("main_role:", df["main_role"].value_counts().to_dict())
    print("bat_subtype:", df["bat_subtype"].value_counts().to_dict())
    print("bowl_type:", df["bowl_type"].replace("", "-").value_counts().to_dict())
    print("bowl_phase:", df["bowl_phase"].value_counts().to_dict())
    agree = df[df["sources_n"] >= 2]["sources_agree"].astype(int)
    print(f"main role agreement where >=2 sources: {agree.mean():.1%} of {len(agree)}")


if __name__ == "__main__":
    sys.exit(main())

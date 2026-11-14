"""Cricsheet ball-by-ball -> one row per player per T20 match (batting + bowling + fielding).

Source: Cricsheet (https://cricsheet.org), Open Data Commons Attribution License (ODC-BY).
Input:  data/raw/cricsheet/<year>_male_json.zip  (download: https://cricsheet.org/downloads/<year>_male_json.zip)
Output: data/cache/t20_player_match.csv.gz   (derived, rebuilt on demand; not committed)
        data/cache/ipl_rosters.json           {season: {team name: {cricsheet_id: name}}}

Only 20-over men's matches (match_type T20/IT20, 6-ball overs). The Hundred and super overs are excluded.

Phases:
  pp:    overs 1-6   (deliveries 0.1 - 5.6)
  mid:   overs 7-15  (deliveries 6.1 - 14.6)
  death: overs 16-20 (deliveries 15.1 - 19.6)

Columns:
  match_id, date, event, is_ipl, team, player_id, player
  batting: bat_pos, entry_ball, balls_faced, runs, bat_dismissed
           bat_runs_pp/mid/death, bat_balls_pp/mid/death, bat_dots_pp/mid/death,
           bat_fours_pp/mid/death, bat_sixes_pp/mid/death, bat_out_pp/mid/death
  bowling: balls_pp/mid/death (legacy), bowl_balls, bowl_runs, bowl_wkts, bowl_dots,
           bowl_fours, bowl_sixes, bowl_wides, bowl_noballs,
           bowl_balls_pp/mid/death, bowl_runs_pp/mid/death, bowl_wkts_pp/mid/death,
           bowl_dots_pp/mid/death, bowl_fours_pp/mid/death, bowl_sixes_pp/mid/death
  fielding: catches, stumpings, run_outs

Run: python -I scripts/cricsheet_t20.py
"""
import csv, gzip, json, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "cricsheet"
CACHE = ROOT / "data" / "cache"
OUT = CACHE / "t20_player_match.csv.gz"
ROSTERS = CACHE / "ipl_rosters.json"

COLS = [
    # Metadata
    "match_id", "date", "event", "is_ipl", "team", "player_id", "player",
    # Batting totals
    "bat_pos", "entry_ball", "balls_faced", "runs", "bat_dismissed",
    # Batting by phase
    "bat_runs_pp", "bat_runs_mid", "bat_runs_death",
    "bat_balls_pp", "bat_balls_mid", "bat_balls_death",
    "bat_dots_pp", "bat_dots_mid", "bat_dots_death",
    "bat_fours_pp", "bat_fours_mid", "bat_fours_death",
    "bat_sixes_pp", "bat_sixes_mid", "bat_sixes_death",
    "bat_out_pp", "bat_out_mid", "bat_out_death",
    # Bowling legacy (legal balls bowled per phase)
    "balls_pp", "balls_mid", "balls_death",
    # Bowling totals
    "bowl_balls", "bowl_runs", "bowl_wkts", "bowl_dots",
    "bowl_fours", "bowl_sixes", "bowl_wides", "bowl_noballs",
    # Bowling by phase
    "bowl_balls_pp", "bowl_balls_mid", "bowl_balls_death",
    "bowl_runs_pp", "bowl_runs_mid", "bowl_runs_death",
    "bowl_wkts_pp", "bowl_wkts_mid", "bowl_wkts_death",
    "bowl_dots_pp", "bowl_dots_mid", "bowl_dots_death",
    "bowl_fours_pp", "bowl_fours_mid", "bowl_fours_death",
    "bowl_sixes_pp", "bowl_sixes_mid", "bowl_sixes_death",
    # Fielding
    "catches", "stumpings", "run_outs"
]


def phase(over_idx):
    return "pp" if over_idx < 6 else ("mid" if over_idx < 15 else "death")


def match_rows(mid, d):
    info = d["info"]
    if info.get("match_type") not in ("T20", "IT20") or info.get("balls_per_over", 6) != 6:
        return []
    event = (info.get("event") or {}).get("name", "")
    if "hundred" in event.lower():
        return []
    reg = info.get("registry", {}).get("people", {})
    date = info["dates"][0]
    is_ipl = event == "Indian Premier League"
    stats = {}

    def st(team, name):
        key = (team, name)
        if key not in stats:
            stats[key] = {
                # Batting
                "bat_pos": None, "entry_ball": None,
                "balls_faced": 0, "runs": 0, "bat_dismissed": 0,
                "bat_runs_pp": 0, "bat_runs_mid": 0, "bat_runs_death": 0,
                "bat_balls_pp": 0, "bat_balls_mid": 0, "bat_balls_death": 0,
                "bat_dots_pp": 0, "bat_dots_mid": 0, "bat_dots_death": 0,
                "bat_fours_pp": 0, "bat_fours_mid": 0, "bat_fours_death": 0,
                "bat_sixes_pp": 0, "bat_sixes_mid": 0, "bat_sixes_death": 0,
                "bat_out_pp": 0, "bat_out_mid": 0, "bat_out_death": 0,
                # Bowling legacy
                "balls_pp": 0, "balls_mid": 0, "balls_death": 0,
                # Bowling totals
                "bowl_balls": 0, "bowl_runs": 0, "bowl_wkts": 0, "bowl_dots": 0,
                "bowl_fours": 0, "bowl_sixes": 0, "bowl_wides": 0, "bowl_noballs": 0,
                # Bowling by phase
                "bowl_balls_pp": 0, "bowl_balls_mid": 0, "bowl_balls_death": 0,
                "bowl_runs_pp": 0, "bowl_runs_mid": 0, "bowl_runs_death": 0,
                "bowl_wkts_pp": 0, "bowl_wkts_mid": 0, "bowl_wkts_death": 0,
                "bowl_dots_pp": 0, "bowl_dots_mid": 0, "bowl_dots_death": 0,
                "bowl_fours_pp": 0, "bowl_fours_mid": 0, "bowl_fours_death": 0,
                "bowl_sixes_pp": 0, "bowl_sixes_mid": 0, "bowl_sixes_death": 0,
                # Fielding
                "catches": 0, "stumpings": 0, "run_outs": 0,
            }
        return stats[key]

    teams = list(info.get("players", {}).keys())
    for team, names in info.get("players", {}).items():
        for n in names:
            st(team, n)

    for inn in d.get("innings", []):
        if inn.get("super_over"):
            continue
        bat_team = inn["team"]
        bowl_team = next((t for t in teams if t != bat_team), None)
        order, legal = [], 0
        for ov in inn.get("overs", []):
            ph = phase(ov["over"])
            for dl in ov["deliveries"]:
                for who in (dl["batter"], dl["non_striker"]):
                    if who not in order:
                        order.append(who)
                        s = st(bat_team, who)
                        s["bat_pos"], s["entry_ball"] = len(order), legal
                ex = dl.get("extras", {})
                is_wide = "wides" in ex
                is_nb = "noballs" in ex
                runs_bat = dl["runs"]["batter"]
                runs_bowl = runs_bat + ex.get("wides", 0) + ex.get("noballs", 0)
                is_legal = not (is_wide or is_nb)
                non_bdry = dl.get("non_boundary", False)

                b = st(bat_team, dl["batter"])
                b["runs"] += runs_bat
                b["bat_runs_" + ph] += runs_bat
                if not is_wide:
                    b["balls_faced"] += 1
                    b["bat_balls_" + ph] += 1
                    if runs_bat == 0:
                        b["bat_dots_" + ph] += 1
                if not non_bdry:
                    if runs_bat == 4:
                        b["bat_fours_" + ph] += 1
                    elif runs_bat == 6:
                        b["bat_sixes_" + ph] += 1

                bw = st(bowl_team, dl["bowler"])
                bw["bowl_runs"] += runs_bowl
                bw["bowl_runs_" + ph] += runs_bowl
                if is_wide:
                    bw["bowl_wides"] += 1
                if is_nb:
                    bw["bowl_noballs"] += 1
                if is_legal:
                    bw["balls_" + ph] += 1
                    bw["bowl_balls"] += 1
                    bw["bowl_balls_" + ph] += 1
                    legal += 1
                    if dl["runs"]["total"] == 0:
                        bw["bowl_dots"] += 1
                        bw["bowl_dots_" + ph] += 1
                if not non_bdry:
                    if runs_bat == 4:
                        bw["bowl_fours"] += 1
                        bw["bowl_fours_" + ph] += 1
                    elif runs_bat == 6:
                        bw["bowl_sixes"] += 1
                        bw["bowl_sixes_" + ph] += 1

                for w in dl.get("wickets", []):
                    kind = w.get("kind", "")
                    out_p = w.get("player_out")
                    # retired hurt / retired not out are not dismissals (batting average convention)
                    if out_p and kind not in ("retired hurt", "retired not out"):
                        po = st(bat_team, out_p)
                        po["bat_dismissed"] = 1
                        po["bat_out_" + ph] = 1
                    if kind in ("bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"):
                        bw["bowl_wkts"] += 1
                        bw["bowl_wkts_" + ph] += 1
                    if kind == "caught and bowled":
                        bw["catches"] += 1
                    else:
                        for f in w.get("fielders", []):
                            fname = f.get("name")
                            if fname and not f.get("substitute"):
                                fs = st(bowl_team, fname)
                                if kind == "caught":
                                    fs["catches"] += 1
                                elif kind == "stumped":
                                    fs["stumpings"] += 1
                                elif kind == "run out":
                                    fs["run_outs"] += 1

    out = []
    for (team, name), s in stats.items():
        out.append({"match_id": mid, "date": date, "event": event, "is_ipl": int(is_ipl), "team": team,
                    "player_id": reg.get(name, ""), "player": name, **s})
    return out


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    zips = sorted(RAW.glob("*_male_json.zip"))
    if not zips:
        raise SystemExit(f"no Cricsheet zips in {RAW}")
    n_match, rosters = 0, {}
    with gzip.open(OUT, "wt", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for z in zips:
            zf = zipfile.ZipFile(z)
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                d = json.loads(zf.read(name))
                rows = match_rows(name[:-5], d)
                if not rows:
                    continue
                n_match += 1
                w.writerows(rows)
                if rows[0]["is_ipl"]:
                    season = rows[0]["date"][:4]
                    for r in rows:
                        rosters.setdefault(season, {}).setdefault(r["team"], {})[r["player_id"]] = r["player"]
            print(f"{z.name}: done ({n_match} T20 matches so far)")
    ROSTERS.write_text(json.dumps(rosters, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({n_match} matches) and {ROSTERS.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())

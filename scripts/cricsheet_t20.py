"""Cricsheet ball-by-ball -> one row per player per T20 match (batting + bowling + keeping signals).

Source: Cricsheet (https://cricsheet.org), Open Data Commons Attribution License (ODC-BY).
Input:  data/raw/cricsheet/<year>_male_json.zip  (download: https://cricsheet.org/downloads/<year>_male_json.zip)
Output: data/cache/t20_player_match.csv.gz   (derived, rebuilt on demand; not committed)
        data/cache/ipl_rosters.json           {season: {team name: {cricsheet_id: name}}}

Only 20-over men's matches (match_type T20/IT20, 6-ball overs). The Hundred and super overs are excluded.

Columns
  match_id, date, event, is_ipl, team, player_id, player
  bat_pos       1-based order of arrival at the crease (openers 1, 2); blank if he did not bat
  entry_ball    legal balls already bowled in the innings when he arrived (0 for openers)
  balls_faced, runs
  balls_pp, balls_mid, balls_death   legal balls bowled in overs 1-6, 7-15, 16-20
  stumpings     dismissals as the stumping fielder (a keeper signal)

Run: python -I scripts/cricsheet_t20.py
"""
import csv, gzip, json, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "cricsheet"
CACHE = ROOT / "data" / "cache"
OUT = CACHE / "t20_player_match.csv.gz"
ROSTERS = CACHE / "ipl_rosters.json"
COLS = ["match_id", "date", "event", "is_ipl", "team", "player_id", "player", "bat_pos", "entry_ball",
        "balls_faced", "runs", "balls_pp", "balls_mid", "balls_death", "stumpings"]


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
            stats[key] = {"bat_pos": None, "entry_ball": None, "balls_faced": 0, "runs": 0,
                          "balls_pp": 0, "balls_mid": 0, "balls_death": 0, "stumpings": 0}
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
                is_wide, is_nb = "wides" in ex, "noballs" in ex
                b = st(bat_team, dl["batter"])
                b["runs"] += dl["runs"]["batter"]
                if not is_wide:
                    b["balls_faced"] += 1
                if not (is_wide or is_nb):
                    st(bowl_team, dl["bowler"])["balls_" + ph] += 1
                    legal += 1
                for w in dl.get("wickets", []):
                    if w.get("kind") == "stumped":
                        for f in w.get("fielders", []):
                            if f.get("name") and not f.get("substitute"):
                                st(bowl_team, f["name"])["stumpings"] += 1
                    # a batter dismissed before facing (e.g. run out non-striker) still batted
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

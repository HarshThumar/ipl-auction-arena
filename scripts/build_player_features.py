"""Point-in-time performance numbers for every relevant player before every auction, 2018-2027.

For auction season Y with auction date D (rules_by_season.yaml), only matches dated strictly
before D are read. Five windows, each a column prefix:
  t20_       every men's T20/IT20 match in our Cricsheet download (which starts 1 Jan 2014,
             so this is "since 2014", not a full career)
  ipl_       IPL matches since 2014
  last3y_    all T20s in the 1,095 days before D (the same window as the role labels)
  last12m_   all T20s in the 365 days before D (current form)
  prev_ipl_  IPL matches in calendar year Y-1 (the season just before the auction)

Per window: counts (matches, innings, runs, balls, outs, fours, sixes, dots; balls, runs, wickets,
dots bowled; catches, stumpings, run-outs; balls and runs per phase) and rates (average, strike
rate, dot %, boundary %, economy, bowling strike rate and average, per-phase strike rate and
economy). Phases: powerplay overs 1-6, middle 7-15, death 16-20.

**A rate is blank when its denominator is 0**, never 0: a player who never bowled has no
economy, and a bowler with no wickets has no bowling average. The counts are kept, so a model can
see the sample size behind every rate.

Conventions: bowler runs = runs off the bat + wides + no-balls (byes and leg-byes are not his);
bowler wickets exclude run-outs and retirements; "retired hurt" and "retired not out" are not
dismissals. Boundaries count only real boundaries (Cricsheet `non_boundary` excluded).

Players: everyone with a Cricsheet ID in any squad list, auction list (2018-26) or IPL match.
`--all` writes every player in the data instead (to data/cache/, for the 2027 pool on 3 Dec).

Source: Cricsheet ball-by-ball data (ODC-BY), via scripts/cricsheet_t20.py.
Output: data/processed/player_features/features_by_season.csv.gz
Run:    python scripts/build_player_features.py [--all]
"""
import argparse, csv, json, sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
CACHE = ROOT / "data" / "cache"
OUT = PROC / "player_features" / "features_by_season.csv.gz"
OUT_ALL = CACHE / "player_features_all.csv.gz"
SEASONS = list(range(2018, 2028))
PH = ("pp", "mid", "death")

SUM_COLS = (["runs", "balls_faced", "bat_dismissed",
             "bowl_balls", "bowl_runs", "bowl_wkts", "bowl_dots", "bowl_fours", "bowl_sixes",
             "bowl_wides", "bowl_noballs", "catches", "stumpings", "run_outs"]
            + [f"bat_{k}_{p}" for k in ("runs", "balls", "dots", "fours", "sixes", "out") for p in PH]
            + [f"bowl_{k}_{p}" for k in ("balls", "runs", "wkts", "dots") for p in PH])


def auction_dates():
    rules = yaml.safe_load(open(ROOT / "data" / "reference" / "rules_by_season.yaml", encoding="utf-8"))["seasons"]
    out = {}
    for y in SEASONS:
        d = rules[y].get("date")
        if not d:
            raise SystemExit(f"rules_by_season.yaml: no auction date for {y}")
        out[y] = d if isinstance(d, date) else date.fromisoformat(str(d))
    return out


def rate(num, den, scale=1.0):
    """num/den*scale rounded to 2 places; NaN (written blank) when den is 0."""
    return (num * scale / den.where(den > 0)).round(2)


def window_features(g, prefix):
    """g: match rows of one window grouped by player_id -> DataFrame of features with prefix."""
    s = g[SUM_COLS].sum()
    s["matches"] = g.size()
    s["bat_inns"] = g["bat_pos"].count()
    f = pd.DataFrame(index=s.index)
    f["matches"] = s["matches"]
    f["bat_inns"] = s["bat_inns"]
    f["runs"] = s["runs"]
    f["balls_faced"] = s["balls_faced"]
    f["outs"] = s["bat_dismissed"]
    fours = sum(s[f"bat_fours_{p}"] for p in PH)
    sixes = sum(s[f"bat_sixes_{p}"] for p in PH)
    dots = sum(s[f"bat_dots_{p}"] for p in PH)
    f["fours"], f["sixes"] = fours, sixes
    f["bat_avg"] = rate(s["runs"], s["bat_dismissed"])
    f["bat_sr"] = rate(s["runs"], s["balls_faced"], 100)
    f["bat_dot_pct"] = rate(dots, s["balls_faced"], 100)
    f["bat_bdry_pct"] = rate(fours + sixes, s["balls_faced"], 100)
    f["balls_per_six"] = rate(s["balls_faced"], sixes)
    for p in PH:
        f[f"bat_balls_{p}"] = s[f"bat_balls_{p}"]
        f[f"bat_sr_{p}"] = rate(s[f"bat_runs_{p}"], s[f"bat_balls_{p}"], 100)
    f["bowl_balls"] = s["bowl_balls"]
    f["bowl_runs"] = s["bowl_runs"]
    f["bowl_wkts"] = s["bowl_wkts"]
    f["bowl_econ"] = rate(s["bowl_runs"], s["bowl_balls"], 6)
    f["bowl_sr"] = rate(s["bowl_balls"], s["bowl_wkts"])
    f["bowl_avg"] = rate(s["bowl_runs"], s["bowl_wkts"])
    f["bowl_dot_pct"] = rate(s["bowl_dots"], s["bowl_balls"], 100)
    f["bowl_bdry_pct"] = rate(s["bowl_fours"] + s["bowl_sixes"], s["bowl_balls"], 100)
    f["bowl_extras_per_over"] = rate(s["bowl_wides"] + s["bowl_noballs"], s["bowl_balls"], 6)
    for p in PH:
        f[f"bowl_balls_{p}"] = s[f"bowl_balls_{p}"]
        f[f"bowl_wkts_{p}"] = s[f"bowl_wkts_{p}"]
        f[f"bowl_econ_{p}"] = rate(s[f"bowl_runs_{p}"], s[f"bowl_balls_{p}"], 6)
    f["catches"], f["stumpings"], f["run_outs"] = s["catches"], s["stumpings"], s["run_outs"]
    return f.add_prefix(prefix)


def relevant_ids(t20):
    ids = set(t20.loc[t20["is_ipl"] == 1, "player_id"])
    for r in csv.DictReader(open(PROC / "roles" / "squad_ids.csv", encoding="utf-8")):
        ids.add(r["cricsheet_id"])
    for r in json.loads((PROC / "master" / "all_auctions_master.json").read_text(encoding="utf-8")):
        ids.add(r.get("cricsheet_id") or "")
    for r in csv.DictReader(open(PROC / "2018_2021_staging" / "staged_2018_2021_joined.csv", encoding="utf-8")):
        ids.add(r["cricsheet_id"])
    ids.discard("")
    return ids


def build(t20, dates, keep_ids=None):
    names = t20.drop_duplicates("player_id", keep="last").set_index("player_id")["player"]
    out = []
    for y in SEASONS:
        cut = dates[y]
        before = t20[t20["date"] < cut.isoformat()]
        if keep_ids is not None:
            before = before[before["player_id"].isin(keep_ids)]
        assert (before["date"] < cut.isoformat()).all(), "leakage"
        wins = {
            "t20_": before,
            "ipl_": before[before["is_ipl"] == 1],
            "last3y_": before[before["date"] >= (cut - timedelta(days=1095)).isoformat()],
            "last12m_": before[before["date"] >= (cut - timedelta(days=365)).isoformat()],
            "prev_ipl_": before[(before["is_ipl"] == 1) & (before["date"].str[:4] == str(y - 1))],
        }
        parts = [window_features(w.groupby("player_id"), p) for p, w in wins.items()]
        df = pd.concat(parts, axis=1).copy()
        count_cols = [c for c in df.columns if not any(c.endswith(k) for k in
                      ("_avg", "_sr", "_pct", "_econ", "_six", "_over")) and "_sr_" not in c and "_econ_" not in c]
        df[count_cols] = df[count_cols].fillna(0).astype(int)   # no rows in a window = 0 matches
        df = df.copy()
        df.insert(0, "player", names.reindex(df.index).values)
        df.insert(0, "as_of_date", cut.isoformat())
        df.insert(0, "season", y)
        df.index.name = "cricsheet_id"
        out.append(df.reset_index())
        print(f"{y}: as of {cut}, {len(df)} players")
    return pd.concat(out, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="every player in the data, written to data/cache/")
    args = ap.parse_args()
    cols = ["match_id", "date", "is_ipl", "player_id", "player", "bat_pos"] + SUM_COLS
    t20 = pd.read_csv(CACHE / "t20_player_match.csv.gz", usecols=cols, dtype={"player_id": str, "match_id": str})
    t20 = t20[t20["player_id"].notna() & (t20["player_id"] != "")]
    dates = auction_dates()
    df = build(t20, dates, None if args.all else relevant_ids(t20))
    out = OUT_ALL if args.all else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, lineterminator="\n", compression="gzip")
    print(f"{len(df)} rows x {len(df.columns)} columns -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())

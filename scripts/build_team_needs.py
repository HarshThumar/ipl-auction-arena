"""What each franchise needed going into each auction, 2018-2026 (and 2027 once retentions land).

A need is computed, not quoted: for every role cell (openers, finishers, keepers, death bowlers,
wrist spinners, ...) compare
  have       how many such players the team held after retentions and trades (pre-auction squad)
  typical    the median count of that cell in final squads (retained + bought) of ALL teams in
             EARLIER seasons only; 2018 has no earlier season in this data, so its typical is blank
  need       max(0, typical - have)
  lost       how many of that cell the team released: last season's final squad minus this
             season's pre-auction squad (blank when there is no last season for the team)
plus have_starters: retained players in the cell who were regular starters last season.

No leakage: the pre-auction squad uses only `source == "retained"` rows of the season, and the
typical squad uses only seasons before it. Both are asserted below; nothing bought at the auction
being predicted is read.

Input:  data/processed/roles/player_roles.csv (scripts/build_roles.py)
        data/processed/pre_auction_state/<season>.json (slots and purse, for context columns)
Output: data/processed/team_needs/needs_long.csv   one row per season, team, cell
        data/processed/team_needs/needs_wide.csv   one row per season, team; need_<cell> columns
Run:    python scripts/build_team_needs.py
"""
import csv, json, statistics, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = PROC / "team_needs"

# cell -> test on a player_roles row. Cells overlap on purpose (a death bowler is also pace).
CELLS = {
    "opener":           lambda r: r["bat_subtype"] == "opener",
    "top_middle_order": lambda r: r["bat_subtype"] in ("top_order", "middle_order"),
    "finisher":         lambda r: r["bat_subtype"] == "finisher",
    "wicketkeeper":     lambda r: r["main_role"] == "wicketkeeper",
    "allrounder":       lambda r: r["main_role"].startswith("allrounder"),
    "pace":             lambda r: r["bowl_type"] in ("pace_right", "pace_left"),
    "left_arm_pace":    lambda r: r["bowl_type"] == "pace_left",
    "finger_spin":      lambda r: r["bowl_type"] in ("off_spin", "left_orthodox"),
    "wrist_spin":       lambda r: r["bowl_type"] in ("leg_spin", "left_wrist"),
    "powerplay_bowler": lambda r: r["bowl_phase"] in ("powerplay", "powerplay_death"),
    "death_bowler":     lambda r: r["bowl_phase"] in ("death", "powerplay_death"),
    "overseas":         lambda r: r["overseas"] == "1",
    "unknown_role":     lambda r: r["confidence"] in ("none", "low"),
}
NO_NEED = {"unknown_role"}   # reported for honesty, never turned into a need


def counts(rows):
    c = {k: 0 for k in CELLS}
    s = {k: 0 for k in CELLS}
    for r in rows:
        for k, f in CELLS.items():
            if f(r):
                c[k] += 1
                s[k] += r["regular_starter"] == "1"
    return c, s


def main():
    roles = list(csv.DictReader(open(PROC / "roles" / "player_roles.csv", encoding="utf-8")))
    by = defaultdict(list)                      # (season, team, source) -> rows
    for r in roles:
        by[(int(r["season"]), r["team"], r["source"])].append(r)
    seasons = sorted({k[0] for k in by})
    teams_in = defaultdict(set)
    for (y, t, src) in by:
        teams_in[y].add(t)

    final = {}                                  # (season, team) -> cell counts of the final squad
    for y in seasons:
        for t in teams_in[y]:
            final[(y, t)] = counts(by[(y, t, "retained")] + by[(y, t, "bought")])[0]

    long_rows, wide_rows = [], []
    for y in seasons:
        state_p = PROC / "pre_auction_state" / f"{y}.json"
        state = json.loads(state_p.read_text(encoding="utf-8"))["teams"] if state_p.exists() else {}
        base_seasons = [s for s in seasons if s < y]
        assert all(s < y for s in base_seasons), "typical squad must use earlier seasons only"
        typical = {}
        for k in CELLS:
            vals = [final[(s, t)][k] for s in base_seasons for t in teams_in[s]]
            typical[k] = statistics.median(vals) if vals else None
        for t in sorted(teams_in[y]):
            pre = by[(y, t, "retained")]
            assert all(r["source"] == "retained" and int(r["season"]) == y for r in pre), "leakage"
            have, starters = counts(pre)
            prev = final.get((y - 1, t))
            wide = {"season": y, "team": t, "retained_n": len(pre),
                    "slots_left": state.get(t, {}).get("slots_left", ""),
                    "overseas_slots_left": state.get(t, {}).get("overseas_slots_left", ""),
                    "purse_left_lakh": state.get(t, {}).get("purse_left_lakh", ""),
                    "baseline_seasons": f"{base_seasons[0]}-{base_seasons[-1]}" if base_seasons else ""}
            for k in CELLS:
                tp = typical[k]
                need = "" if tp is None or k in NO_NEED else max(0, tp - have[k])
                lost = "" if prev is None else max(0, prev[k] - have[k])
                long_rows.append({"season": y, "team": t, "cell": k, "have": have[k],
                                  "have_starters": starters[k], "typical": "" if tp is None else tp,
                                  "need": need, "lost_in_release": lost})
                wide[f"have_{k}"] = have[k]
                wide[f"need_{k}"] = need
            wide_rows.append(wide)

    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("needs_long.csv", long_rows), ("needs_wide.csv", wide_rows)):
        with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    print(f"{len(wide_rows)} team-seasons, {len(CELLS)} cells -> {OUT.relative_to(ROOT)}")
    for y in seasons[-1:]:
        print(f"{y} needs (cells with need > 0):")
        for wr in wide_rows:
            if wr["season"] == y:
                n = {k: wr[f"need_{k}"] for k in CELLS if wr[f"need_{k}"] not in ("", 0, 0.0)}
                print(f"  {wr['team']:5} slots {wr['slots_left']:>2}  " + ", ".join(f"{k} {v:g}" for k, v in n.items()))


if __name__ == "__main__":
    sys.exit(main())

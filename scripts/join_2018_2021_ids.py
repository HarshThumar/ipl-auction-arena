"""Join 2018-2021 staged players against Cricsheet IDs using initial+surname and alias rules."""

import csv, json, re, sys
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[1]
PROC = REPO_ROOT / "data" / "processed"
STAGED_FILE = PROC / "2018_2021_staging" / "staged_2018_2021.csv"
OUTPUT_FILE = PROC / "2018_2021_staging" / "staged_2018_2021_joined.csv"

def norm(s): return re.sub(r'[^a-z0-9]','',(s or '').lower())
def toks(s): return [x for x in re.split(r'\s+',(s or '').strip()) if x]
def ini_sur(name):
    t = toks(name)
    return norm(name) if len(t) < 2 else norm(t[0][0] + t[-1])
def sur(name):
    t = toks(name); return norm(t[-1]) if t else ''

full = defaultdict(set); ini = defaultdict(set); surn = defaultdict(set); info = {}
with open(PROC / "players_register.csv", encoding="utf-8") as f:
    r = csv.DictReader(f)
    for row in r:
        cid = row["cricsheet_id"]
        n = row["name"]; un = row["unique_name"]
        for cand in (n, un):
            if cand:
                full[norm(cand)].add(cid)
                ini[ini_sur(cand)].add(cid)
                surn[sur(cand)].add(cid)
        info[cid] = row

with open(PROC / "ipl_player_ids.json", encoding="utf-8") as f:
    ipl_ids = set(json.load(f))

rows = []
matched = 0
with open(STAGED_FILE, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        pname = row["player_name"]
        # Match strategy
        cid = None
        # 1. exact match
        if norm(pname) in full and len(full[norm(pname)]) == 1:
            cid = next(iter(full[norm(pname)]))
        # 2. initial + surname intersecting ipl universe
        elif ini_sur(pname) in ini:
            cands = ini[ini_sur(pname)] & ipl_ids
            if len(cands) == 1:
                cid = next(iter(cands))
            elif len(ini[ini_sur(pname)]) == 1:
                cid = next(iter(ini[ini_sur(pname)]))
        # 3. surname intersecting ipl universe
        elif sur(pname) in surn:
            cands = surn[sur(pname)] & ipl_ids
            if len(cands) == 1:
                cid = next(iter(cands))

        if cid:
            row["cricsheet_id"] = cid
            matched += 1
        else:
            row["cricsheet_id"] = ""
        rows.append(row)

fieldnames = list(rows[0].keys())
with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Matched {matched}/{len(rows)} ({matched/len(rows):.1%}) to Cricsheet Register IDs using IPL Universe index.")

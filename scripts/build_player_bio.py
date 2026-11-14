"""Date of birth and international record for every relevant player, then capped status per auction.

Outputs
  data/processed/players/player_bio.csv
      cricsheet_id, player, cricinfo_id, date_of_birth, dob_source, intl_team, intl_full_member,
      first_intl_date, last_intl_date, n_tests, n_odis, n_t20is
  data/processed/players/capped_by_season.csv
      season, cricsheet_id, player, as_of_date, age_at_auction, capped, capped_basis, years_since_last_intl

Sources
  Date of birth: Wikidata property P569, found through P2697 (ESPNcricinfo player ID, taken from the
  Cricsheet register). Wikidata is CC0.
  International matches: Cricsheet full-history archives tests_male_json.zip, odis_male_json.zip,
  t20s_male_json.zip (ODC-BY) in data/raw/cricsheet_intl/ (download from https://cricsheet.org/downloads/).
  Only the playing XI listed in each match counts.

Capped as of an auction (season Y, date D), first rule that fits:
  1. Played a Test, ODI or T20I for a full-member nation before D -> capped ("intl_before_auction"),
     except the 2025-27 rule below.
  2. Indian player, season >= 2025, and his last international was more than 5 years before D ->
     uncapped ("indian_5yr_rule"). The rule also needs "no BCCI central contract", which open data
     can't show; the 5-year gap alone is used and this is noted.
  3. No international match in Cricsheet, but an auction list for an earlier-or-same season calls
     him capped -> capped ("auction_list"). This covers caps older than Cricsheet's coverage.
  4. Otherwise uncapped ("no_intl_record"). Associate-nation internationals give "associate".
Cricsheet internationals start about 2002 (ODIs/Tests) and 2005 (T20Is), so a player whose only
caps are older and who never appears in an auction list is wrongly uncapped; this is rare for
2018+ auctions.

Run: python scripts/build_player_bio.py   (needs network for Wikidata the first time; cached)
"""
import csv, json, sys, time, urllib.parse, urllib.request, zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw" / "cricsheet_intl"
CACHE = ROOT / "data" / "cache"
OUT_DIR = PROC / "players"
UA = {"User-Agent": "ipl-auction-arena-research/0.1"}
FULL_MEMBERS = {"India", "Australia", "England", "South Africa", "New Zealand", "Pakistan", "Sri Lanka",
                "West Indies", "Bangladesh", "Afghanistan", "Zimbabwe", "Ireland"}
SEASONS = list(range(2018, 2028))


def relevant_ids():
    ids, names = set(), {}
    for r in csv.DictReader(open(PROC / "roles" / "squad_ids.csv", encoding="utf-8")):
        if r["cricsheet_id"]:
            ids.add(r["cricsheet_id"]); names.setdefault(r["cricsheet_id"], r["player"])
    for r in json.loads((PROC / "master" / "all_auctions_master.json").read_text(encoding="utf-8")):
        if r.get("cricsheet_id"):
            ids.add(r["cricsheet_id"]); names.setdefault(r["cricsheet_id"], r["player"])
    for r in csv.DictReader(open(PROC / "2018_2021_staging" / "staged_2018_2021_joined.csv", encoding="utf-8")):
        if r["cricsheet_id"]:
            ids.add(r["cricsheet_id"]); names.setdefault(r["cricsheet_id"], r["player_name"])
    import pandas as pd
    f = pd.read_csv(PROC / "player_features" / "features_by_season.csv.gz", usecols=["cricsheet_id", "player"], dtype=str)
    for cid, n in f.drop_duplicates("cricsheet_id").itertuples(index=False):
        ids.add(cid); names.setdefault(cid, n)
    return ids, names


def intl_records():
    """{cricsheet_id: {"dates": [...], "teams": Counter, "fmt": Counter}} from the three archives."""
    rec = defaultdict(lambda: {"dates": [], "teams": Counter(), "fmt": Counter()})
    for fn, fmt in (("tests_male_json.zip", "test"), ("odis_male_json.zip", "odi"), ("t20s_male_json.zip", "t20i")):
        p = RAW / fn
        if not p.exists():
            raise SystemExit(f"missing {p}; download https://cricsheet.org/downloads/{fn}")
        zf = zipfile.ZipFile(p)
        for name in zf.namelist():
            if not name.endswith(".json"):
                continue
            info = json.loads(zf.read(name))["info"]
            reg = info.get("registry", {}).get("people", {})
            d = info["dates"][0]
            for team, players in info.get("players", {}).items():
                for pl in players:
                    cid = reg.get(pl)
                    if cid:
                        r = rec[cid]
                        r["dates"].append(d)
                        r["teams"][team] += 1
                        r["fmt"][fmt] += 1
        print(f"{fn}: read")
    return rec


def wikidata_dob(cricinfo_ids):
    cache = CACHE / "wikidata_dob.json"
    got = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    todo = sorted(set(cricinfo_ids) - set(got))
    for i in range(0, len(todo), 200):
        chunk = todo[i:i + 200]
        vals = " ".join(f'"{x}"' for x in chunk)
        q = (f"SELECT ?id ?dob WHERE {{ VALUES ?id {{{vals}}} ?item wdt:P2697 ?id . "
             f"OPTIONAL {{ ?item wdt:P569 ?dob . }} }}")
        url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q)
        for attempt in range(4):
            try:
                res = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read())
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        found = defaultdict(set)
        for b in res["results"]["bindings"]:
            if "dob" in b:
                found[b["id"]["value"]].add(b["dob"]["value"][:10])
        for x in chunk:
            # two different birth dates on Wikidata = ambiguous: keep none rather than guess
            got[x] = sorted(found[x])[0] if len(found[x]) == 1 else ("" if not found[x] else "AMBIGUOUS")
        time.sleep(1)
    cache.write_text(json.dumps(got), encoding="utf-8")
    return got


def auction_capped_flags():
    """{(cricsheet_id): first season an auction list calls him capped}"""
    first = {}
    for r in json.loads((PROC / "master" / "all_auctions_master.json").read_text(encoding="utf-8")):
        if r.get("cricsheet_id") and r.get("capped") == "capped":
            first[r["cricsheet_id"]] = min(first.get(r["cricsheet_id"], 9999), r["season"])
    return first


def main():
    ids, names = relevant_ids()
    ci = {}
    for r in csv.DictReader(open(PROC / "players_register.csv", encoding="utf-8")):
        if r["cricsheet_id"] in ids and r["key_cricinfo"]:
            ci[r["cricsheet_id"]] = r["key_cricinfo"]
    dob = wikidata_dob(ci.values())
    intl = intl_records()

    bio = []
    for cid in sorted(ids):
        r = intl.get(cid)
        team = r["teams"].most_common(1)[0][0] if r else ""
        d = dob.get(ci.get(cid, ""), "")
        bio.append({"cricsheet_id": cid, "player": names.get(cid, ""), "cricinfo_id": ci.get(cid, ""),
                    "date_of_birth": d if d not in ("", "AMBIGUOUS") else "",
                    "dob_source": "wikidata" if d not in ("", "AMBIGUOUS") else ("wikidata_ambiguous" if d else ""),
                    "intl_team": team, "intl_full_member": int(team in FULL_MEMBERS) if team else "",
                    "first_intl_date": min(r["dates"]) if r else "", "last_intl_date": max(r["dates"]) if r else "",
                    "n_tests": r["fmt"]["test"] if r else 0, "n_odis": r["fmt"]["odi"] if r else 0,
                    "n_t20is": r["fmt"]["t20i"] if r else 0})

    rules = yaml.safe_load(open(ROOT / "data" / "reference" / "rules_by_season.yaml", encoding="utf-8"))["seasons"]
    auction_capped = auction_capped_flags()
    nat = {}
    for y in SEASONS:
        p = PROC / "pre_auction_state" / f"{y}.json"
        if p.exists():
            for t, s in json.loads(p.read_text(encoding="utf-8"))["teams"].items():
                for pl in s["retained"]:
                    nat[pl["player"]] = pl.get("nationality")
    by_id = {b["cricsheet_id"]: b for b in bio}
    caps = []
    for y in SEASONS:
        D = rules[y]["date"]
        D = D if isinstance(D, date) else date.fromisoformat(str(D))
        for cid, b in by_id.items():
            r = intl.get(cid)
            before = [x for x in (r["dates"] if r else []) if x < D.isoformat()]
            last = max(before) if before else ""
            yrs = round((D - date.fromisoformat(last)).days / 365.25, 2) if last else ""
            if before and b["intl_full_member"] == 1:
                indian = b["intl_team"] == "India"
                if indian and y >= 2025 and yrs > 5:
                    capped, basis = "uncapped", "indian_5yr_rule"
                else:
                    capped, basis = "capped", "intl_before_auction"
            elif before:
                capped, basis = "associate", "intl_before_auction"
            elif auction_capped.get(cid, 9999) <= y:
                capped, basis = "capped", "auction_list"
            else:
                capped, basis = "uncapped", "no_intl_record"
            age = ""
            if b["date_of_birth"]:
                age = round((D - date.fromisoformat(b["date_of_birth"])).days / 365.25, 2)
            caps.append({"season": y, "cricsheet_id": cid, "player": b["player"], "as_of_date": D.isoformat(),
                         "age_at_auction": age, "capped": capped, "capped_basis": basis,
                         "years_since_last_intl": yrs})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in (("player_bio.csv", bio), ("capped_by_season.csv", caps)):
        with open(OUT_DIR / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    n = len(bio)
    print(f"{n} players: date of birth {sum(1 for b in bio if b['date_of_birth'])}, "
          f"ambiguous {sum(1 for b in bio if b['dob_source'] == 'wikidata_ambiguous')}, "
          f"international record {sum(1 for b in bio if b['first_intl_date'])}")
    print("capped basis (all seasons):", dict(Counter(c["capped_basis"] for c in caps)))


if __name__ == "__main__":
    sys.exit(main())

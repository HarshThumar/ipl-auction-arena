"""Parse retained/kept players per team per season from cached Wikipedia wikitext.

Source: Wikipedia "List of 20XX IPL personnel changes" (CC BY-SA), cached under
data/raw/enrichment_recon/wiki_<year>_wikitext.json. Output:
data/processed/retentions_by_season.json  = {season: {franchise_id: [ {player, nationality, salary_lakh} ]}}

Run (downloaded data -> isolated):  python -I scripts/parse_retentions.py
"""
import json, re, csv, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "enrichment_recon"
REF = ROOT / "data" / "reference"
OUT = ROOT / "data" / "processed" / "retentions_by_season.json"
YEARS = [2022, 2023, 2024, 2025, 2026]

# headings that hold the retained-player tables (exclude "Retention policy")
SEC_NAMES = ("retained players", "retained player", "player retention")

def load_alias():
    alias = {}
    for f in csv.DictReader(open(REF / "franchises.csv", encoding="utf-8")):
        alias[f["current_name"].lower()] = f["franchise_id"]
        alias[f["franchise_id"].lower()] = f["franchise_id"]
        for a in (f["aliases"] or "").split("|"):
            if a.strip():
                alias[a.strip().lower()] = f["franchise_id"]
    return alias

def wikitext(year):
    d = json.load(open(RAW / f"wiki_{year}_wikitext.json", encoding="utf-8"))
    wt = d["parse"]["wikitext"]
    return wt["*"] if isinstance(wt, dict) else wt

def sections(wt):
    """All retention-table blocks: each heading match -> text up to the next heading of any level."""
    blocks = []
    for m in re.finditer(r'(==+)\s*([^=\n]+?)\s*\1', wt):
        title = m.group(2).strip().lower()
        if any(title == n or title.startswith(n) for n in SEC_NAMES):
            start = m.end()
            nxt = re.search(r'\n==+', wt[start:])
            blocks.append(wt[start: start + nxt.start()] if nxt else wt[start:])
    return blocks

def inrconvert_to_lakh(s):
    m = re.search(r'\{\{INRConvert\|([\d.]+)\|c', s)
    if m:
        return int(round(float(m.group(1)) * 100))
    m = re.search(r'\{\{INRConvert\|([\d.]+)\|l', s)
    if m:
        return int(round(float(m.group(1))))
    return None

def nationality(s):
    m = re.search(r'\{\{cr\|([^}|]+)', s)
    if not m:
        return None
    code = m.group(1).strip()
    return "India" if code.upper() in ("IND", "INDIA") else "Overseas"

def parse_year(year, alias):
    blocks = sections(wikitext(year))
    if not blocks:
        return {}, "no retention section found"
    teams = {}
    seen = set()
    for sec in blocks:
        rows = re.split(r'\n\|-', sec)          # wiki table rows
        cur = None
        for row in rows:
            # team anchor: a colspan header, a bold header, or a table caption (|+) carrying [[Team]]
            if "colspan" in row or "'''" in row or "|+" in row:
                for link in re.findall(r'\[\[([^\]|]+)', row):
                    fid = alias.get(link.strip().lower())
                    if fid:
                        cur = fid
                        teams.setdefault(cur, [])
                        break
            if cur and "{{cr|" in row:
                # player name: {{sortname|First|Last}} or [[Player]]
                sm = re.search(r'\{\{sortname\|([^}|]+)\|([^}|]+)', row)
                if sm:
                    player = f"{sm.group(1).strip()} {sm.group(2).strip()}"
                else:
                    links = re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]', row)
                    player = next((lk.strip() for lk in links if not alias.get(lk.strip().lower())), None)
                if player and (cur, player) not in seen:
                    seen.add((cur, player))
                    teams[cur].append({
                        "player": player,
                        "nationality": nationality(row),
                        "salary_lakh": inrconvert_to_lakh(row),
                    })
    return teams, "ok"

def main():
    alias = load_alias()
    out = {}
    for y in YEARS:
        teams, status = parse_year(y, alias)
        n = sum(len(v) for v in teams.values())
        out[str(y)] = teams
        print(f"{y}: {status}; teams={len(teams)} players={n}  " +
              ", ".join(f"{t}:{len(p)}" for t, p in sorted(teams.items())))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT))

if __name__ == "__main__":
    main()

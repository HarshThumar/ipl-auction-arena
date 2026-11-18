"""Parse retained/kept players per team per season from cached Wikipedia wikitext.

Source: Wikipedia "List of 20XX IPL personnel changes" (CC BY-SA), cached under
data/raw/enrichment_recon/wiki_<year>_wikitext.json. Output:
data/processed/retentions_by_season.json  = {season: {franchise_id: [ {player, nationality, salary_lakh} ]}}

Run (downloaded data -> isolated):  python -I scripts/parse_retentions.py
Refresh one year from Wikipedia first:  python -I scripts/parse_retentions.py --fetch 2027
"""
import json, re, csv, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "enrichment_recon"
REF = ROOT / "data" / "reference"
OUT = ROOT / "data" / "processed" / "retentions_by_season.json"
YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]   # plus any later year whose wikitext is cached
WIKI_API = ("https://en.wikipedia.org/w/api.php?action=parse&prop=wikitext&format=json"
            "&page=List_of_{year}_Indian_Premier_League_personnel_changes")

def fetch(year):
    """Download the year's personnel-changes wikitext into the cache (overwrites)."""
    import urllib.request
    req = urllib.request.Request(WIKI_API.format(year=year), headers={"User-Agent": "ipl-auction-arena-research/0.1"})
    raw = urllib.request.urlopen(req, timeout=60).read()
    d = json.loads(raw)
    if "parse" not in d:
        raise SystemExit(f"Wikipedia returned no page for {year}: {str(d)[:200]}")
    (RAW / f"wiki_{year}_wikitext.json").write_bytes(raw)
    print(f"fetched {year}: revid {d['parse'].get('revid')}")

def years():
    cached = sorted(int(p.stem.split("_")[1]) for p in RAW.glob("wiki_*_wikitext.json"))
    return sorted(set(YEARS) | {y for y in cached if y > max(YEARS)})

# headings that hold the retained-player tables (exclude "Retention policy")
SEC_NAMES = ("retained players", "retained player", "player retention", "retention policy")

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

MONEY = re.compile(r'\{\{INRConvert\|([\d.]+)\|([cl])|₹\s*([\d.]+)\s*(crore|cr|lakh|lac)', re.I)

def money_values(s):
    """Every money value in the row, in column order, as lakh."""
    out = []
    for m in MONEY.finditer(s):
        if m.group(1):
            v, unit = float(m.group(1)), m.group(2).lower()
        else:
            v, unit = float(m.group(3)), ("c" if m.group(4).lower().startswith("cr") else "l")
        out.append(int(round(v * 100)) if unit == "c" else int(round(v)))
    return out

def inrconvert_to_lakh(s):
    vals = money_values(s)
    return vals[0] if vals else None

FLAG = re.compile(r'\{\{(?:cr|flagicon|flag)\|([^}|]+)', re.I)

def nationality(s):
    m = FLAG.search(s)
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
        # wiki table rows. '|}' (table end) also splits, so a team's last player
        # can't share a chunk with the next team's caption and be filed under it.
        rows = re.split(r'\n\|[-}]', sec)
        # a real "Purse deduction" column header (2018), not the phrase inside a footnote
        has_deduction = bool(re.search(r'^!.*purse deduction', sec, re.I | re.M))
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
            if cur and FLAG.search(row):
                # player name: {{sortname|First|Last}} or [[Player]]
                sm = re.search(r'\{\{sortname\|([^}|]+)\|([^}|]+)', row)
                if sm:
                    player = f"{sm.group(1).strip()} {sm.group(2).strip()}"
                else:
                    links = re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]', row)
                    player = next((lk.strip() for lk in links if not alias.get(lk.strip().lower())), None)
                if not player:
                    player = plain_name(row)   # unlinked name, e.g. "| Abishek Porel" (2024)
                if player:
                    player = re.sub(r'\s*\([^)]*\)\s*$', '', player).strip()  # "Arshdeep Singh (cricketer)"
                if player and (cur, player) not in seen:
                    seen.add((cur, player))
                    sal = inrconvert_to_lakh(row)
                    entry = {"player": player, "nationality": nationality(row), "salary_lakh": sal}
                    vals = money_values(row)
                    # footnote form (2019-22): "...the actual purse deduction ... was {{INRConvert|15|c}}"
                    fm = re.search(r'purse deduction.*?(\{\{INRConvert\|[\d.]+\|[cl])', row, re.I | re.S)
                    if fm:
                        entry["purse_deduction_lakh"] = money_values(fm.group(1))[0]
                    elif has_deduction and len(vals) >= 2:   # 2018: "Purse deduction" column after salary
                        entry["purse_deduction_lakh"] = vals[1]
                    # Every IPL contract is >= 20 lakh. A value below that is a wiki unit typo
                    # ("{{INRConvert|7.75|l}}" for 7.75 crore). Correct it and say so.
                    if sal is not None and sal < 20:
                        m = re.search(r'\{\{INRConvert\|([\d.]+)\|l', row)
                        if m and float(m.group(1)) < 20:
                            entry["salary_lakh"] = int(round(float(m.group(1)) * 100))
                            entry["note"] = f"wiki says {m.group(1)} lakh (below the 20 lakh minimum); read as crore"
                    teams[cur].append(entry)
    return teams, "ok"

def plain_name(row):
    """First table cell that is plain text (not a number, flag, salary or team link)."""
    for line in row.split("\n"):
        line = line.strip()
        if not line or line[0] not in "|!" or line.startswith(("|+", "{|", "|}")):
            continue
        cell = line.lstrip("|!").strip()
        if "|" in cell and "{{" not in cell.split("|")[0]:
            cell = cell.split("|", 1)[1].strip()   # drop attributes: scope="row" | Name
        if (not cell or cell.isdigit() or "{{" in cell or "[[" in cell or "₹" in cell
                or cell.lower().startswith(("player", "nationality", "salary", "no."))):
            continue
        return cell
    return None

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                      "august", "september", "october", "november", "december"], 1)}

def parse_date(cell):
    """'{{Dts|20 January 2021}}' / '31 July 2019' -> '2021-01-20'."""
    m = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', cell or "")
    if m and m.group(2).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None

def parse_transfers(year, alias):
    """Pre-auction trades from the 'Transfers' section: [{player, nationality, from, to,
    salary_before_lakh, salary_after_lakh, date}]. Rowspan dates carry down to the next rows."""
    wt = wikitext(year)
    m = re.search(r'\n(==+)\s*Transfers\s*\1', wt)
    if not m:
        return []
    sec = wt[m.end():]
    nxt = re.search(r'\n==', sec)
    sec = sec[: nxt.start()] if nxt else sec
    out, last_date = [], None
    for row in re.split(r'\n\|[-}]', sec):
        if not FLAG.search(row):
            continue
        cells = [c.strip() for c in re.split(r'\|\||\n\|', "\n" + row) if c.strip()]
        teams = []
        for c in cells:
            for link in re.findall(r'\[\[([^\]|]+)', c):
                fid = alias.get(link.strip().lower())
                if fid:
                    teams.append(fid)
                    break
        if len(teams) < 2:
            # rowspan rows (e.g. 2019 Dhawan trade: Shankar, Nadeem, Abhishek Sharma) carry the
            # From/To cells of the row above, so they hold no team links of their own
            if not teams and out:
                teams = [out[-1]["from"], out[-1]["to"]]
            else:
                continue
        links = re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]', row)
        player = next((lk.strip() for lk in links if not alias.get(lk.strip().lower())), None)
        if not player:
            continue
        player = re.sub(r'\s*\([^)]*\)\s*$', '', player).strip()
        d = next((parse_date(c) for c in cells if parse_date(c)), None)
        last_date = d or last_date
        # money cells in order: salary before, (from), (to), salary after
        vals = money_values(re.sub(r'<ref.*?(</ref>|/>)', '', row, flags=re.S))
        out.append({"player": player, "nationality": nationality(row),
                    "from": teams[0], "to": teams[1],
                    "salary_before_lakh": vals[0] if vals else None,
                    "salary_after_lakh": vals[1] if len(vals) > 1 else (vals[0] if vals else None),
                    "date": last_date})
    return out

TRANSFERS_OUT = ROOT / "data" / "processed" / "transfers_by_season.json"

def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--fetch":
        fetch(int(sys.argv[2]))
    alias = load_alias()
    out, trans = {}, {}
    for y in years():
        teams, status = parse_year(y, alias)
        n = sum(len(v) for v in teams.values())
        out[str(y)] = teams
        trans[str(y)] = parse_transfers(y, alias)
        print(f"{y}: {status}; teams={len(teams)} players={n} transfers={len(trans[str(y)])}  " +
              ", ".join(f"{t}:{len(p)}" for t, p in sorted(teams.items())))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    TRANSFERS_OUT.write_text(json.dumps(trans, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT), "and", TRANSFERS_OUT.relative_to(ROOT))

if __name__ == "__main__":
    main()

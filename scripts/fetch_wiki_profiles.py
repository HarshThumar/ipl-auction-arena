"""Wikipedia infobox facts (batting hand, bowling style, role) for every resolved squad player.

Route: Cricsheet ID -> ESPNcricinfo ID (Cricsheet register) -> Wikidata (property P2697,
ESPNcricinfo player ID) -> English Wikipedia article -> {{Infobox cricketer}} fields.
Source: Wikipedia, CC BY-SA 4.0 (attributed in SOURCES.md). Only three short factual fields are kept.

Output: data/processed/roles/wiki_profiles.csv
        cricsheet_id, cricinfo_id, wiki_title, batting, bowling, role
Cache:  data/cache/wiki_infobox/<batch>.json (raw API replies; not committed)

Run: python -I scripts/fetch_wiki_profiles.py
"""
import csv, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
CACHE = ROOT / "data" / "cache" / "wiki_infobox"
OUT = PROC / "roles" / "wiki_profiles.csv"
UA = {"User-Agent": "ipl-auction-arena-research/0.1"}


def get(url, data=None):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            return json.loads(urllib.request.urlopen(req, timeout=90).read())
        except Exception as e:  # network hiccup / rate limit: back off and retry
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def wikidata_titles(cricinfo_ids):
    out = {}
    ids = sorted(cricinfo_ids)
    for i in range(0, len(ids), 200):
        vals = " ".join(f'"{x}"' for x in ids[i:i + 200])
        q = (f"SELECT ?id ?article WHERE {{ VALUES ?id {{{vals}}} ?item wdt:P2697 ?id . "
             f"?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }}")
        url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q)
        for b in get(url)["results"]["bindings"]:
            out[b["id"]["value"]] = urllib.parse.unquote(b["article"]["value"].rsplit("/wiki/", 1)[1]).replace("_", " ")
        time.sleep(1)
    return out


def wikitexts(titles):
    """{requested title: wikitext} following redirects, 50 titles per request, cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    out = {}
    titles = sorted(set(titles))
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        cf = CACHE / f"{abs(hash(tuple(batch))) % 10**12}.json"
        if cf.exists():
            d = json.loads(cf.read_text(encoding="utf-8"))
        else:
            params = {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                      "format": "json", "formatversion": "2", "redirects": "1", "titles": "|".join(batch)}
            d = get("https://en.wikipedia.org/w/api.php", urllib.parse.urlencode(params).encode())
            cf.write_text(json.dumps(d), encoding="utf-8")
            time.sleep(1)
        q = d.get("query", {})
        back = {}
        for n in q.get("normalized", []):
            back[n["to"]] = n["from"]
        for r in q.get("redirects", []):
            back[r["to"]] = back.get(r["from"], r["from"])
        for pg in q.get("pages", []):
            revs = pg.get("revisions")
            if revs:
                out[back.get(pg["title"], pg["title"])] = revs[0]["slots"]["main"]["content"]
    return out


def field(wt, name):
    # [ \t]* not \s*: an empty field must not swallow the next line ("| bowling =\n| role = ...")
    m = re.search(r"\|[ \t]*" + name + r"[ \t]*=[ \t]*([^\n]*)", wt)
    if not m:
        return ""
    v = m.group(1)
    v = re.sub(r"<ref[^>]*/>|<ref.*?</ref>|<!--.*?-->", "", v)
    v = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\{\{[^}]*\}\}|<[^>]+>|'''?", "", v)
    return v.strip(" |").strip()


def main():
    squad = list(csv.DictReader(open(PROC / "roles" / "squad_ids.csv", encoding="utf-8")))
    ids = {r["cricsheet_id"] for r in squad if r["cricsheet_id"]}
    ci = {}
    for r in csv.DictReader(open(PROC / "players_register.csv", encoding="utf-8")):
        if r["cricsheet_id"] in ids and r["key_cricinfo"]:
            ci[r["cricsheet_id"]] = r["key_cricinfo"]
    titles = wikidata_titles(set(ci.values()))
    texts = wikitexts(titles.values())
    rows = []
    for cid in sorted(ids):
        c = ci.get(cid, "")
        t = titles.get(c, "")
        wt = texts.get(t, "")
        rows.append({"cricsheet_id": cid, "cricinfo_id": c, "wiki_title": t,
                     "batting": field(wt, "batting"), "bowling": field(wt, "bowling"), "role": field(wt, "role")})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    has = lambda k: sum(1 for r in rows if r[k])
    print(f"{n} players: cricinfo id {sum(1 for r in rows if r['cricinfo_id'])}, wiki article {has('wiki_title')}, "
          f"batting {has('batting')}, bowling {has('bowling')}, role {has('role')}")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())

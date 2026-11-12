"""Step 1 of the L0 rebuild: merge bid sequences + enrichment into the master table.

Args: <bid_sequences dir> <enriched dir> <out master dir> <processed dir (register index)>
Writes: master/*.json, all_auctions_master.{csv,json}, team_summary.json, validation.json
NOTE: re-running this alone wipes later steps; always run the full pipeline (docs/L0-STATUS.md).
"""
import json, csv, sys, re
from pathlib import Path

BIDS = Path(sys.argv[1])        # .../bid_sequences
ENR  = Path(sys.argv[2])        # .../enriched
OUT  = Path(sys.argv[3])        # .../master  (created)
PROC = Path(sys.argv[4])        # .../processed (for register index)
OUT.mkdir(parents=True, exist_ok=True)
YEARS=[2022,2023,2024,2025,2026]
OFFICIAL_SOLD={2022:204,2023:80,2024:72,2025:182,2026:77}
OFFICIAL_SPEND={2022:551.7,2023:167,2024:230.45,2025:639.15,2026:215.45}
# players genuinely omitted from the Wikipedia sold table (verified vs raw ESPN); backfilled explicitly
KNOWN_WIKI_MISSING={2025:[("Moeen Ali","KKR",2.0),("Satyanarayana Raju","MI",0.3)]}

def norm(s):
    return re.sub(r'[^a-z0-9]','',(s or '').lower())
def initial_form(name):
    t=[x for x in re.split(r'\s+',(name or '').strip()) if x]
    if len(t)<2: return norm(name)
    return norm(t[0][0]+t[-1])
def firstlast(name):
    t=[x for x in re.split(r'\s+',(name or '').strip()) if x]
    if len(t)<2: return norm(name)
    return norm(t[0]+t[-1])

# ---- register index for IDs ----
reg={}
ri=PROC/"players_register_index.json"
if ri.exists():
    reg=json.loads(ri.read_text(encoding="utf-8"))
def lookup_ids(name):
    for k in (norm(name), initial_form(name), firstlast(name)):
        v=reg.get(k)
        if v and not v.get("collision"):
            return {"cricsheet_id":v.get("cricsheet_id"),"cricinfo_id":v.get("cricinfo_id")}, "exact" if k==norm(name) else "alias"
    for k in (norm(name), initial_form(name), firstlast(name)):
        v=reg.get(k)
        if v and v.get("collision"):
            return {"cricsheet_id":None,"cricinfo_id":None}, "collision"
    return {"cricsheet_id":None,"cricinfo_id":None}, "unmatched"

master_all=[]; team_summary={}; valid={}
for y in YEARS:
    enr_f=ENR/f"{y}_sold_enriched.json"
    bids_f=BIDS/f"{y}_bids.json"
    if not enr_f.exists():
        print(f"[WARN] {y}: enriched file missing, skipping"); continue
    enr=json.loads(enr_f.read_text(encoding="utf-8"))
    bids=json.loads(bids_f.read_text(encoding="utf-8"))
    # high-precision ESPN-sold match: full-name strong keys; initial+surname only when surname unique both sides
    from collections import defaultdict, Counter
    def lasttok(n):
        t=[x for x in re.split(r'\s+',(n or '').strip()) if x]; return norm(t[-1]) if t else ''
    espn_sold=[l for l in bids["lots"] if l["sold"]]
    byid={id(l):l for l in espn_sold}
    espn_strong=defaultdict(set); espn_if=defaultdict(set); espn_last=Counter()
    for l in espn_sold:
        for k in {norm(l["player"]),firstlast(l["player"])}: espn_strong[k].add(id(l))
        espn_if[initial_form(l["player"])].add(id(l))
        espn_last[lasttok(l["player"])]+=1
    wiki_last=Counter(lasttok(e["player"]) for e in enr["lots"])
    def match_espn(name):
        for k in (norm(name),firstlast(name)):
            s=espn_strong.get(k)
            if s and len(s)==1: return byid[next(iter(s))]
        sn=lasttok(name)
        if wiki_last[sn]==1 and espn_last.get(sn,0)==1:
            s=espn_if.get(initial_form(name))
            if s and len(s)==1: return byid[next(iter(s))]
        return None
    rows=[]; price_disagree=[]; idstat={"exact":0,"alias":0,"collision":0,"unmatched":0}; bid_attached=0; matched_espn_ids=set()
    # SOLD spine from Wikipedia-enriched
    for e in enr["lots"]:
        em=match_espn(e["player"])
        ids,how=lookup_ids(e["player"]); idstat[how]+=1
        steps=(em.get("bid_steps") if em else []) or []
        row={
            "season":y,"auction_type":bids.get("auction_type"),
            "player":e["player"],
            "cricsheet_id":ids["cricsheet_id"],"cricinfo_id":ids["cricinfo_id"],"id_match":how,
            "nationality":e.get("nationality"),"raw_country":e.get("raw_country"),
            "role":e.get("role"),"capped":e.get("capped"),
            "base_price":e.get("base_price"),
            "status":"sold","winner":e.get("team"),"final_price":e.get("final_price"),
            "price_note":e.get("price_note",""),
            "opener":(steps[0]["team"] if steps else ""),
            "teams_in":",".join(dict.fromkeys(s["team"] for s in steps)),
            "n_teams_in":len(dict.fromkeys(s["team"] for s in steps)),
            "final_two":",".join([t for t in ((em.get("final_two") if em else []) or []) if t]),
            "ladder":" -> ".join(f'{s["team"]} {s["price"]}' for s in steps),
            "confidence":(em.get("confidence") if em else "outcome_only"),
            "bid_source":"ESPNcricinfo" if em else None,
            "enrich_source":"Wikipedia(CC BY-SA)",
            "narration_quote":(em.get("narration_quote") if em else ""),
            "redistributable":True,
        }
        if em: bid_attached+=1; matched_espn_ids.add(id(em))
        # price disagreement ESPN vs Wikipedia
        if em and em.get("final_price") is not None and e.get("final_price") is not None:
            if abs(em["final_price"]-e["final_price"])>0.051:
                price_disagree.append({"player":e["player"],"espn":em["final_price"],"wiki":e["final_price"]})
        if em and em.get("winner") and e.get("team") and em["winner"]!=e["team"]:
            price_disagree.append({"player":e["player"],"espn_team":em.get("winner"),"wiki_team":e.get("team")})
        rows.append(row)
    # Backfill the genuine shortfall vs official with EXPLICIT verified players (2025 only; others=0)
    n_missing=max(0, OFFICIAL_SOLD[y]-len(enr["lots"]))
    espn_sold_added=0; seen_extra=set(); added_players=[]
    known=KNOWN_WIKI_MISSING.get(y,[])
    for (pname,pteam,pprice) in known[:n_missing]:
        seen_extra.add(norm(pname)); added_players.append(f'{pname}({pteam} {pprice})')
        ids,how=lookup_ids(pname); idstat[how]+=1
        rows.append({
            "season":y,"auction_type":bids.get("auction_type"),"player":pname,
            "cricsheet_id":ids["cricsheet_id"],"cricinfo_id":ids["cricinfo_id"],"id_match":how,
            "nationality":None,"raw_country":None,"role":None,"capped":None,"base_price":None,
            "status":"sold","winner":pteam,"final_price":pprice,
            "price_note":"omitted from Wikipedia sold table; outcome verified vs raw ESPN live blog",
            "opener":"","teams_in":"","n_teams_in":0,"final_two":"","ladder":"",
            "confidence":"outcome_only","bid_source":None,"enrich_source":None,
            "narration_quote":"","redistributable":True,
        })
        espn_sold_added+=1
    if espn_sold_added<n_missing:
        print(f"[WARN] {y}: needed {n_missing} backfill but only {espn_sold_added} known-missing listed")
    sold_names={norm(e["player"]) for e in enr["lots"]} | {firstlast(e["player"]) for e in enr["lots"]} | seen_extra
    # UNSOLD layer from ESPN (not licence-clean, no wiki enrichment)
    unsold_n=0
    for l in bids["lots"]:
        if l["sold"]: continue
        if norm(l["player"]) in sold_names or firstlast(l["player"]) in sold_names:
            continue  # was later sold / already represented
        ids,how=lookup_ids(l["player"])
        rows.append({
            "season":y,"auction_type":bids.get("auction_type"),"player":l["player"],
            "cricsheet_id":ids["cricsheet_id"],"cricinfo_id":ids["cricinfo_id"],"id_match":how,
            "nationality":None,"raw_country":None,"role":None,"capped":None,
            "base_price":l.get("base_price"),
            "status":"unsold","winner":"","final_price":None,"price_note":"",
            "opener":"","teams_in":"","n_teams_in":0,"final_two":"","ladder":"",
            "confidence":"unsold_narrated","bid_source":"ESPNcricinfo","enrich_source":None,
            "narration_quote":l.get("narration_quote",""),
            "redistributable":False,  # unsold names from ESPN prose, not licence-clean
        })
        unsold_n+=1
    # team summary (sold only)
    ts={}
    for r in rows:
        if r["status"]=="sold" and r["winner"]:
            t=ts.setdefault(r["winner"],{"buys":0,"spend":0.0,"indian":0,"overseas":0})
            t["buys"]+=1; t["spend"]+=(r["final_price"] or 0)
            if r["nationality"]=="India": t["indian"]+=1
            elif r["nationality"]=="Overseas": t["overseas"]+=1
    for t in ts.values(): t["spend"]=round(t["spend"],2)
    team_summary[y]=ts
    sold_rows=[r for r in rows if r["status"]=="sold"]
    spend=round(sum(r["final_price"] or 0 for r in sold_rows),2)
    valid[y]={
        "sold":len(sold_rows),"official_sold":OFFICIAL_SOLD[y],"sold_ok":len(sold_rows)==OFFICIAL_SOLD[y],
        "spend":spend,"official_spend":OFFICIAL_SPEND[y],
        "unsold_narrated":unsold_n,
        "espn_sold_added":espn_sold_added,"espn_sold_added_players":added_players,
        "bid_ladders_attached":bid_attached,
        "id_match":idstat,"id_fill_pct":round(100*(idstat["exact"]+idstat["alias"])/max(1,len(sold_rows)),1),
        "price_disagreements":price_disagree,
        "nationality_missing_sold":sum(1 for r in sold_rows if not r["nationality"]),
        "role_missing_sold":sum(1 for r in sold_rows if not r["role"]),
        "capped_missing_sold":sum(1 for r in sold_rows if not r["capped"]),
    }
    master_all.extend(rows)
    (OUT/f"{y}_master.json").write_text(json.dumps({"season":y,"rows":rows},indent=1,ensure_ascii=False),encoding="utf-8")

# combined outputs
(OUT/"all_auctions_master.json").write_text(json.dumps(master_all,ensure_ascii=False),encoding="utf-8")
cols=["season","auction_type","player","cricsheet_id","cricinfo_id","id_match","nationality","role","capped",
      "base_price","status","winner","final_price","n_teams_in","teams_in","opener","final_two","ladder",
      "confidence","bid_source","enrich_source","redistributable","narration_quote","raw_country","price_note"]
with open(OUT/"all_auctions_master.csv","w",newline="",encoding="utf-8") as fh:
    w=csv.DictWriter(fh,fieldnames=cols,extrasaction="ignore"); w.writeheader()
    for r in master_all: w.writerow(r)
(OUT/"team_summary.json").write_text(json.dumps(team_summary,indent=2,ensure_ascii=False),encoding="utf-8")
(OUT/"validation.json").write_text(json.dumps(valid,indent=2,ensure_ascii=False),encoding="utf-8")

print("=== MASTER BUILD ===")
for y in YEARS:
    if y not in valid: continue
    v=valid[y]
    print(f"{y}: sold {v['sold']}/{v['official_sold']} ({'OK' if v['sold_ok'] else 'MISMATCH'}) | spend {v['spend']}/{v['official_spend']} | unsold {v['unsold_narrated']} | ladders {v['bid_ladders_attached']} | ID {v['id_fill_pct']}% ({v['id_match']}) | disagree {len(v['price_disagreements'])} | miss nat/role/cap {v['nationality_missing_sold']}/{v['role_missing_sold']}/{v['capped_missing_sold']}")
print("rows total:",len(master_all),"| files -> master/*.json, all_auctions_master.csv/json, team_summary.json, validation.json")

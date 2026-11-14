"""Step 2 of the L0 rebuild: Cricsheet ID join (exact / verified alias / initial+surname tiers).

Run:  python scripts/idjoin.py apply [processed dir]   (omit 'apply' for a dry-run report)
ALIAS holds 23 hand-verified players; every capped player resolves. 91% overall (accepted 11 Nov).
"""
import csv, json, re, sys
from pathlib import Path
from collections import defaultdict, Counter
PROC=Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).resolve().parent.parent/"data"/"processed"
APPLY = len(sys.argv)>1 and sys.argv[1]=="apply"

def norm(s): return re.sub(r'[^a-z0-9]','',(s or '').lower())
def toks(s): return [x for x in re.split(r'\s+',(s or '').strip()) if x]
def ini_sur(name):
    t=toks(name)
    return norm(name) if len(t)<2 else norm(t[0][0]+t[-1])
def sur(name):
    t=toks(name); return norm(t[-1]) if t else ''

# Guard against wrong auto-matches found 14 Nov (e.g. Emanjot Chahal -> YS Chahal,
# Syed Mehdi Hasan -> Shakib Al Hasan): the given name must fit the register's first name/initial.
def first_name_ok(auction_name, reg_name):
    from difflib import SequenceMatcher
    a, r = toks(auction_name), toks(reg_name)
    if len(a) < 2 or len(r) < 2:
        return True                      # one-word names: nothing to compare
    a0, r0 = a[0].lower().strip("."), r[0].strip(".")
    if r0.isupper() and len(r0) <= 4:    # register initials, e.g. "YS Chahal", "PVD Chameera"
        return a0[:1] in r0.lower() or a0 in [t.lower() for t in r[1:-1]]   # "M Prasidh Krishna"
    r0 = r0.lower()
    return (a0.startswith(r0) or r0.startswith(a0) or SequenceMatcher(None, a0, r0).ratio() >= 0.8
            or a0 in [t.lower() for t in r[1:-1]])
# Hand-verified: these auction names are NOT the register player the rules would pick
# (the real player has no Cricsheet record), so they stay unmatched.
REJECT = {"mangeshyadav", "rameshkumar", "syedmehdihasan", "emanjotchahal", "pankajjaiswal", "kaushaltambe",
          "namantiwari"}   # 14 Nov: register "Naman Tiwari" is a Cyprus player (only Cyprus matches)

# build register indexes
full=defaultdict(set); ini=defaultdict(set); surn=defaultdict(set); info={}; regname={}
with open(PROC/"players_register.csv",encoding="utf-8") as fh:
    r=csv.DictReader(fh)
    cols=r.fieldnames
    for row in r:
        cid=row.get("cricsheet_id"); ci=row.get("key_cricinfo") or None
        info[cid]={"cricinfo":ci}
        regname[cid]=row.get("name")
        for nm in {row.get("name"),row.get("unique_name")}:
            if not nm: continue
            full[norm(nm)].add(cid)
            ini[ini_sur(nm)].add(cid)
            surn[sur(nm)].add(cid)
print("register cols:",cols[:6],"...")
print("register rows indexed:",len(info))

# authoritative set of cricsheet_ids that have appeared in IPL (Cricsheet match registries)
IPL=set(json.load(open(PROC/"ipl_player_ids.json")))
print("IPL-player id universe:",len(IPL))

def _uniq_ipl(cands):
    inter=[c for c in cands if c in IPL]
    return inter[0] if len(inter)==1 else None

# hand-verified aliases (register row chosen by name identity; 4 web-verified against ESPNcricinfo).
# maps norm(auction name) -> cricsheet_id ; cricinfo id is read from the register (not hardcoded).
ALIAS={
 "camerongreen":"eaa76d3c","dwaynebravo":"87e562a9","fabianallen":"b52ffbbd","finnallen":"bf74b130",
 "dineshkarthik":"c03f1114","kusalmendis":"5d1e7582","kamindumendis":"08548b13","saikishore":"c7a995d3",
 "charithasalanka":"732c038e","danlawrence":"4b685e2d","jiteshsharma":"800d2d97","dwainepretoruius":"11614d87",
 "joshphillipe":"39086549","bsaisudharshan":"d5130a30","vaibhavsooryavanshi":"470f446b","leusduplooy":"6e6fb538",
 "mohammedazharudeen":"4ae89f36","prabhsimransingh":"9418198b","laurieevans":"1c513d54",
 "rinkusingh":"0a509d6b","karnsharma":"119678fd","waninduhasaranga":"a97c8ec2","jamiesmith":"c834c290",
 "shahrukhkhan":"7dcb9bc9","bhagathvarma":"5438ffba",
 "rasikhsalamdar":"b8527c3d","rasikhdar":"b8527c3d","rasikhsalam":"b8527c3d",
 "rassievanderdussen":"9948e262",
 "mohitsharma":"759ac88f",   # India's MM Sharma (CSK/GT/DC); the register's "Mohit Sharma" is a Mexico player
}

def lookup(name):
    cid,ci,how=_lookup(name)
    if cid and how in ("ini","full_ipl","ini_ipl","surname_ipl") and not first_name_ok(name, regname[cid]):
        return None,None,"rejected_guard"
    return cid,ci,how

def _lookup(name):
    if norm(name) in REJECT: return None,None,"unmatched"
    a=ALIAS.get(norm(name))
    if a and a in info: return a,info[a]["cricinfo"],"alias"
    k=norm(name)
    if len(full.get(k,()))==1:
        cid=next(iter(full[k])); return cid,info[cid]["cricinfo"],"full"
    k2=ini_sur(name)
    if len(ini.get(k2,()))==1:
        cid=next(iter(ini[k2])); return cid,info[cid]["cricinfo"],"ini"
    # collision: disambiguate by "actually played IPL"
    if full.get(k):
        cid=_uniq_ipl(full[k])
        if cid: return cid,info[cid]["cricinfo"],"full_ipl"
    if ini.get(k2):
        cid=_uniq_ipl(ini[k2])
        if cid: return cid,info[cid]["cricinfo"],"ini_ipl"
    # last resort: surname unique among IPL players (catches middle-name filing e.g. Dinesh->KD Karthik)
    s=sur(name)
    if s and surn.get(s):
        cid=_uniq_ipl(surn[s])
        if cid: return cid,info[cid]["cricinfo"],"surname_ipl"
    if full.get(k) or ini.get(k2): return None,None,"collision"
    return None,None,"unmatched"

rows=json.loads((PROC/"master"/"all_auctions_master.json").read_text(encoding="utf-8"))
by_year=defaultdict(lambda:Counter()); filled=0; before=0; unmatched_samples=defaultdict(list)
for x in rows:
    before += 1 if x.get("cricinfo_id") else 0
    cs,ci,how=lookup(x["player"])
    by_year[x["season"]][how]+=1
    if APPLY:
        x["cricsheet_id"]=cs; x["cricinfo_id"]=ci; x["id_match"]=how
    if ci: filled+=1
    elif how in ("collision","unmatched") and len(unmatched_samples[x["season"]])<8:
        unmatched_samples[x["season"]].append(f'{x["player"]}({how})')

tot=len(rows)
print(f"\nID fill: before(name-match v1)={before}/{tot}  ->  now={filled}/{tot}  ({round(100*filled/tot,1)}%)")
for y in sorted(by_year):
    c=by_year[y]; got=c['full']+c['ini']+c['full_ipl']+c['ini_ipl']+c['surname_ipl']+c['alias']; n=sum(c.values())
    print(f"  {y}: {got}/{n} ({round(100*got/n)}%)  alias={c['alias']} full={c['full']} ini={c['ini']} +ipl={c['full_ipl']+c['ini_ipl']} +surn={c['surname_ipl']} collision={c['collision']} unmatched={c['unmatched']}")
    print(f"       still missing e.g.: {unmatched_samples[y][:6]}")

if APPLY:
    (PROC/"master"/"all_auctions_master.json").write_text(json.dumps(rows,ensure_ascii=False),encoding="utf-8")
    # rewrite csv
    cols=["season","auction_type","player","cricsheet_id","cricinfo_id","id_match","nationality","role","capped",
          "base_price","status","winner","final_price","n_teams_in","teams_in","opener","final_two","ladder",
          "confidence","bid_source","enrich_source","redistributable","narration_quote","raw_country","price_note"]
    with open(PROC/"master"/"all_auctions_master.csv","w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=cols,extrasaction="ignore"); w.writeheader()
        for x in rows: w.writerow(x)
    print("APPLIED: master json/csv rewritten with improved IDs")

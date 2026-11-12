"""Step 4 of the L0 rebuild: render the static HTML viewer from the master dir.

Run:  python scripts/build_view.py data/processed/master
"""
import json, sys
from pathlib import Path
M=Path(sys.argv[1])  # master dir
rows=json.loads((M/"all_auctions_master.json").read_text(encoding="utf-8"))
team=json.loads((M/"team_summary.json").read_text(encoding="utf-8"))
val=json.loads((M/"validation.json").read_text(encoding="utf-8"))

HEAD="""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>IPL Auction Master</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--mut:#697086;--line:#e6e8ee;--accent:#0b7285;--sold:#0b7285;--unsold:#b45309;--ind:#1d4ed8;--ovs:#9333ea}
@media(prefers-color-scheme:dark){:root{--bg:#0d0e12;--card:#161922;--ink:#e6e9ef;--mut:#99a1b3;--line:#242a36;--accent:#38bec9;--sold:#38bec9;--unsold:#f59e0b;--ind:#60a5fa;--ovs:#c084fc}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:22px 16px 72px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--mut);margin:0 0 16px;font-size:12.5px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:9px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:11px 13px}
.card h3{margin:0 0 5px;font-size:11px;color:var(--mut);font-weight:600;letter-spacing:.03em;text-transform:uppercase}
.card .big{font-size:18px;font-weight:700}.card .row{display:flex;justify-content:space-between;font-size:11.5px;color:var(--mut);margin-top:2px}
.controls{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:11px;position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:5}
select,input{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:6px 8px;font-size:12.5px}
input{flex:1;min-width:150px}
.bar{font-size:12.5px;color:var(--mut);margin:0 0 9px}.bar b{color:var(--ink)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);font-size:12.5px;vertical-align:top}
th{font-size:10.5px;text-transform:uppercase;letter-spacing:.03em;color:var(--mut);cursor:pointer;position:sticky;top:50px;background:var(--card)}
tr.lot{cursor:pointer}tr.lot:hover td{background:rgba(127,127,127,.06)}
.px{font-variant-numeric:tabular-nums;font-weight:600}
.badge{display:inline-block;padding:1px 6px;border-radius:999px;font-size:10.5px;font-weight:600}
.b-sold{color:var(--sold);border:1px solid var(--sold)}.b-unsold{color:var(--unsold);border:1px solid var(--unsold)}
.nat-India{color:var(--ind)}.nat-Overseas{color:var(--ovs)}
.det{background:rgba(127,127,127,.05)}.det td{padding:11px 13px}
.ladder{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin:5px 0}
.step{background:var(--card);border:1px solid var(--line);border-radius:7px;padding:2px 7px;font-size:11.5px;font-variant-numeric:tabular-nums}
.step.win{border-color:var(--accent);color:var(--accent);font-weight:700}
.arrow{color:var(--mut)}.q{color:var(--mut);font-style:italic;font-size:11.5px;margin-top:5px}.kv{font-size:11.5px;color:var(--mut);margin-top:3px}
.muted{color:var(--mut)}.flag{font-size:10.5px;padding:1px 5px;border:1px solid var(--unsold);color:var(--unsold);border-radius:6px}
@media(max-width:720px){.hide-sm{display:none}}
</style></head><body><div class=wrap>
<h1>IPL Auction Master &middot; 2022&ndash;2026</h1>
<p class=sub>Complete enriched SOLD ledger (role / nationality / capped / base / price + bid ladders + Cricsheet IDs), cross-checked to official counts & spend. Enrichment: <b>Wikipedia CC BY-SA</b>. Bid ladders: ESPNcricinfo (facts). <b>Unsold rows are ESPN-narrated only, not a complete pool, and flagged not-for-redistribution.</b> Cricsheet ID join ~50% (name-matching limit). Prices &#8377; crore (hammer).</p>
<div class=cards id=cards></div>
<div class=controls>
<select id=fy></select><select id=ft></select>
<select id=fs><option value=all>All status</option><option value=sold>Sold</option><option value=unsold>Unsold</option></select>
<select id=fn><option value=all>Any nationality</option><option>India</option><option>Overseas</option></select>
<select id=fr><option value=all>Any role</option></select>
<select id=fcap><option value=all>Any cap</option><option>capped</option><option>uncapped</option><option>associate</option></select>
<input id=fq placeholder="Search player...">
</div>
<p class=bar id=bar></p>
<table><thead><tr>
<th data-k=player>Player</th><th data-k=season class=hide-sm>Yr</th><th data-k=nationality class=hide-sm>Nat</th>
<th data-k=role class=hide-sm>Role</th><th data-k=capped class=hide-sm>Cap</th><th data-k=base_price class=hide-sm>Base</th>
<th data-k=status>Status</th><th data-k=winner>Won by</th><th data-k=final_price>Price</th>
<th data-k=opener class=hide-sm>Opener</th><th data-k=confidence>Detail</th>
</tr></thead><tbody id=tb></tbody></table>
<p class=sub style="margin-top:12px" id=foot></p>
</div><script>
"""

TAIL="""
const $=s=>document.querySelector(s);
const yrs=[...new Set(DATA.map(r=>''+r.season))].sort();
const roles=[...new Set(DATA.map(r=>r.role).filter(Boolean))].sort();
const teams=[...new Set(DATA.map(r=>r.winner).filter(Boolean))].sort();
function sum(a){return a.reduce((x,y)=>x+y,0)}
let ch='';
yrs.forEach(y=>{const r=DATA.filter(x=>''+x.season==y);const sold=r.filter(x=>x.status=='sold');
 const sp=sum(sold.map(x=>x.final_price||0));const ind=sold.filter(x=>x.nationality=='India').length;const ovs=sold.filter(x=>x.nationality=='Overseas').length;
 ch+=`<div class=card><h3>${y}</h3><div class=big>${sold.length} sold</div><div class=row><span>spend</span><span>₹${sp.toFixed(1)}cr</span></div><div class=row><span>Ind/Ovs</span><span>${ind}/${ovs}</span></div><div class=row><span>unsold*</span><span>${r.length-sold.length}</span></div></div>`});
$('#cards').innerHTML=ch;
$('#fy').innerHTML='<option value=all>All years</option>'+yrs.map(y=>`<option>${y}</option>`).join('');
$('#ft').innerHTML='<option value=all>All teams</option>'+teams.map(t=>`<option>${t}</option>`).join('');
$('#fr').innerHTML='<option value=all>Any role</option>'+roles.map(t=>`<option>${t}</option>`).join('');
let sortK='final_price',sortDir=-1;
function esc(s){return(s==null?'':''+s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function rows(){
 const y=$('#fy').value,t=$('#ft').value,st=$('#fs').value,n=$('#fn').value,ro=$('#fr').value,ca=$('#fcap').value,q=$('#fq').value.toLowerCase();
 let r=DATA.filter(x=>(y=='all'||''+x.season==y)&&(t=='all'||x.winner==t)&&(st=='all'||x.status==st)&&(n=='all'||x.nationality==n)&&(ro=='all'||x.role==ro)&&(ca=='all'||x.capped==ca)&&(!q||x.player.toLowerCase().includes(q)));
 r.sort((a,b)=>{let x=a[sortK],z=b[sortK];if(x==null)x=-1;if(z==null)z=-1;if(typeof x=='string')return sortDir*x.localeCompare(z);return sortDir*(x-z)});
 return r;
}
function render(){
 const r=rows();const sold=r.filter(x=>x.status=='sold');const sp=sum(sold.map(x=>x.final_price||0));
 $('#bar').innerHTML=`<b>${r.length}</b> rows &middot; <b>${sold.length}</b> sold &middot; spend <b>₹${sp.toFixed(2)}cr</b> &middot; Indian <b>${sold.filter(x=>x.nationality=='India').length}</b> / Overseas <b>${sold.filter(x=>x.nationality=='Overseas').length}</b> &middot; with bid ladder <b>${r.filter(x=>x.ladder).length}</b>`;
 let h='';
 r.forEach((x,i)=>{
  h+=`<tr class=lot data-i=${i}><td>${esc(x.player)}</td><td class=hide-sm>${x.season}</td>`+
     `<td class="hide-sm nat-${x.nationality||''}">${x.nationality?x.nationality[0]:'&ndash;'}</td>`+
     `<td class=hide-sm>${esc(x.role)||'&ndash;'}</td><td class=hide-sm>${x.capped?x.capped[0].toUpperCase():'&ndash;'}</td>`+
     `<td class=hide-sm>${x.base_price==null?'&ndash;':x.base_price}</td>`+
     `<td><span class="badge ${x.status=='sold'?'b-sold':'b-unsold'}">${x.status}</span></td>`+
     `<td>${esc(x.winner)||'&ndash;'}</td><td class=px>${x.final_price==null?'&ndash;':x.final_price}</td>`+
     `<td class=hide-sm>${esc(x.opener)||'&ndash;'}</td><td>${x.ladder?'ladder':x.confidence.replace('_',' ')}</td></tr>`;
 });
 const tb=$('#tb');tb.innerHTML=h;
 tb.querySelectorAll('tr.lot').forEach(tr=>tr.onclick=()=>{
   const x=r[+tr.dataset.i];const nx=tr.nextElementSibling;
   if(nx&&nx.classList.contains('det')){nx.remove();return}
   let d='<div class=ladder>';
   if(x.ladder){x.ladder.split(' -> ').forEach((s,j,a)=>{const w=j==a.length-1;d+=`<span class="step${w?' win':''}">${esc(s)}</span>`+(j<a.length-1?'<span class=arrow>&rarr;</span>':'')})}
   else d+='<span class=muted>No bid-by-bid narration &mdash; outcome only.</span>';
   d+='</div>';
   if(x.final_two)d+=`<div class=kv>Final two: ${esc(x.final_two)}</div>`;
   d+=`<div class=kv>cricinfo id: ${esc(x.cricinfo_id)||'&ndash;'} &middot; cricsheet: ${esc(x.cricsheet_id)||'&ndash;'} (${esc(x.id_match)}) &middot; role ${esc(x.role)||'?'} &middot; ${esc(x.capped)||'?'} &middot; ${esc(x.raw_country)||''}</div>`;
   d+=`<div class=kv>enrich: ${esc(x.enrich_source)||'&ndash;'} &middot; bids: ${esc(x.bid_source)||'&ndash;'} ${x.redistributable?'':'<span class=flag>not for redistribution</span>'}</div>`;
   if(x.narration_quote)d+=`<div class=q>&ldquo;${esc(x.narration_quote)}&rdquo;</div>`;
   if(x.price_note)d+=`<div class=kv>note: ${esc(x.price_note)}</div>`;
   const row=document.createElement('tr');row.className='det';row.innerHTML=`<td colspan=11>${d}</td>`;tr.after(row);
 });
}
document.querySelectorAll('th').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(k==sortK)sortDir*=-1;else{sortK=k;sortDir=['player','winner','opener','confidence','status','nationality','role','capped'].includes(k)?1:-1}render()});
['#fy','#ft','#fs','#fn','#fr','#fcap','#fq'].forEach(s=>$(s).addEventListener('input',render));
$('#foot').innerHTML='Files: data/processed/master/ (all_auctions_master.csv/json, team_summary.json, validation.json). *Unsold = ESPN-narrated subset only, flagged not-for-redistribution. Sold ledger reconciles to official counts & spend; Cricsheet ID join ~50% pending exact-ID extraction.';
render();
"""
html=HEAD+"const DATA="+json.dumps(rows,ensure_ascii=False)+";\nconst TEAM="+json.dumps(team,ensure_ascii=False)+";\n"+TAIL+"</script></body></html>"
(M/"master_ledger.html").write_text(html,encoding="utf-8")
print("wrote",M/"master_ledger.html",len(html),"bytes; rows",len(rows))

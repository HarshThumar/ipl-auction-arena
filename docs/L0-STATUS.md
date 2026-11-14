# L0 — Clean data foundation: status

*Living status for Level 0 ([levels.md](levels.md)). Updated as checks move. L0 closes register rows G1–G8, D2, D3.*

Run the gate anytime:
```
pip install -r requirements.txt     # once (pyyaml)
python scripts/validate_l0.py       # prints PASS/FAIL/WARN/BLOCKED, writes l0_validation.json
```

## Current result (last run)
**10 PASS · 0 FAIL · 3 WARN · 0 BLOCKED**  — squad/overseas un-blocked and spend deltas resolved, 12 Nov.

| Area | State | Register |
|---|---|---|
| `franchises.csv` — 15 franchises, aliases, source per row | ✅ PASS | G2 |
| `rules_by_season.yaml` — 2008–2027, integer lakhs, UNVERIFIED flagged | ✅ PASS | G7 |
| `fx_usd_inr.csv` — USD-era conversion | ✅ PASS | G3 |
| Money = integer lakhs, `paid ≤ hammer` | ✅ PASS | A10 |
| Hammer vs paid split (overseas-mini 18cr cap) | ✅ PASS | G5 |
| Every **capped** player has a Cricsheet/ESPN ID | ✅ PASS | G1 |
| Sold count == official (204/80/72/182/77) | ✅ PASS | — |
| Per-team spend ≤ gross purse | ✅ PASS | — |
| Winner codes resolve to a franchise | ✅ PASS | G2 |
| Squad size 18–25 (retained + bought) | ⚠️ 48/50 clean (3 off-by-one) | — |
| Overseas ≤ cap in full squad | ⚠️ 49/50 clean (1 off-by-one) | — |
| Licences attributed, no banned sources redistributed | ✅ (SOURCES.md) | G8 |

## Open items (WARN) — real gaps, not hidden
1. **Player ID join = 91%, target was ≥99%.** The shortfall is entirely **uncapped domestic players who have never played a Cricsheet-tracked match**, so no ID exists to join to. Every *capped* player is matched and collisions were reviewed. **DECISION — ACCEPTED (Harsh, 11 Nov 2026):** 91% stands as L0-sufficient. Rationale: the 99% bar is unreachable via Cricsheet for never-played players; all capped/known players are matched, which is what the price and DNA layers actually use. No second ID source will be chased for now; revisit only if a later level needs IDs for uncapped lots.
2. ~~Spend vs official, small deltas~~ — **RESOLVED (14 Nov).** Six lots carried wrong prices from clerical errors in the cross-check tables (2022 Aneeshwar Gautam ₹20L, Ashok Sharma ₹55L; 2023 Prerak Mankad ₹20L, Donavon Ferreira ₹50L, Rajan Kumar ₹70L; 2024 Kartik Tyagi ₹60L). After correcting them, **gross auction spend matches the official totals to 0.00 Cr in all 5 seasons** (2022: 551.7 Cr, 2023: 167.0 Cr, 2024: 230.45 Cr, 2025: 639.15 Cr, 2026: 215.45 Cr). This also corrects the 12 Nov explanation: the official 2024 total *includes* Harry Brook (DC, ₹4 Cr, later withdrew), so he is no longer netted out. PASS.

3. **Squad / overseas off-by-ones (3 of 50 team-seasons):** 2024 SRH = 26, 2026 SRH = 26, 2026 RCB = 9 overseas. Parses are clean (verified player lists, no artifacts). Cause: the `retained + bought` reconstruction is a **pre-trade snapshot** — post-auction **trades/releases** (which we don't model, G5) bring these within the 25/8 caps by season start. Accept as documented.

## Resolved 12 Nov
- **Historical retentions loaded** ([scripts/parse_retentions.py](../scripts/parse_retentions.py) → `data/processed/retentions_by_season.json`, 2022–26, from Wikipedia CC BY-SA). This un-blocked the squad-size and overseas-cap checks for all historical years. **2027 retentions land 17 Nov** and slot straight in.

## Rebuild from scratch (reproducibility)
Order matters — each step rewrites the master, so run all four in sequence:
```
python scripts/build_master.py data/processed/bid_sequences data/processed/enriched data/processed/master data/processed
python scripts/idjoin.py apply
python scripts/normalize_money.py
python scripts/build_view.py data/processed/master
python scripts/validate_l0.py
```
**Verified 12 Nov:** a clean rebuild in a temp folder matched the committed master exactly (1019 rows, 0 field differences). CI (`.github/workflows/l0.yml`) runs the gate on every push.

## Point-in-time store (D2 / C5)
Convention established now, enforced when features begin: **every derived feature carries an `as_of` date**, and nothing dated after an auction may be used to predict that auction. The raw auction facts are naturally as-of their auction date. No model features exist yet (they start at L2), so there is nothing to leak yet — the mechanism is in place before the first feature is written.

## What "L0 done" needs
- [x] franchises.csv + rules_by_season.yaml with a source per row
- [x] money in integer lakhs + FX table; hammer vs paid separated
- [x] validation suite runs in one command
- [x] ID join decision recorded — **91% accepted** (Harsh, 11 Nov 2026)
- [x] **spend deltas resolved** (12 Nov) — withdrawn player (Harry Brook) + sub-crore rounding; prices verified faithful to source
- [x] **historical retentions loaded → squad/overseas checks un-blocked** (12 Nov); 2027 slots in on the 17th
- [ ] point-in-time store exercised by the first real feature (L2)

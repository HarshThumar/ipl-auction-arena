# L0 — Clean data foundation: status

*Living status for Level 0 ([levels.md](levels.md)). Updated as checks move. L0 closes register rows G1–G8, D2, D3.*

Run the gate anytime:
```
pip install -r requirements.txt     # once (pyyaml)
python scripts/validate_l0.py       # prints PASS/FAIL/WARN/BLOCKED, writes l0_validation.json
```

## Current result (last run)
**16 PASS · 0 FAIL · 1 WARN · 1 BLOCKED** (15 Nov). The only WARN is the accepted ID join, now 89.5% after wrong matches were removed (below). The only BLOCKED item is the 2027 retentions, due 17 Nov ([runbook](retention-day-runbook.md)).

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
| Per-team spend ≤ pre-auction purse left (official, 50 team-seasons) | ✅ PASS | — |
| Pre-auction state 2018–26: slots and overseas slots match the official figures exactly | ✅ PASS | — |
| One Cricsheet ID = one player (2018–26) | ✅ PASS | — |
| 2027 retentions loaded | ⛔ BLOCKED until 17 Nov | — |
| Winner codes resolve to a franchise | ✅ PASS | G2 |
| Squad size 18–25 (retained + bought) | ✅ 50/50 | — |
| Overseas ≤ cap in full squad | ✅ 50/50 | — |
| Licences attributed, no banned sources redistributed | ✅ (SOURCES.md) | G8 |

## Open items (WARN) — real gaps, not hidden
1. **Player ID join = 91%, target was ≥99%.** The shortfall is entirely **uncapped domestic players who have never played a Cricsheet-tracked match**, so no ID exists to join to. Every *capped* player is matched and collisions were reviewed. **DECISION — ACCEPTED (Harsh, 11 Nov 2026):** 91% stands as L0-sufficient. Rationale: the 99% bar is unreachable via Cricsheet for never-played players; all capped/known players are matched, which is what the price and DNA layers actually use. No second ID source will be chased for now; revisit only if a later level needs IDs for uncapped lots.
2. ~~Spend vs official, small deltas~~ — **RESOLVED (14 Nov).** Six lots carried wrong prices from clerical errors in the cross-check tables (2022 Aneeshwar Gautam ₹20L, Ashok Sharma ₹55L; 2023 Prerak Mankad ₹20L, Donavon Ferreira ₹50L, Rajan Kumar ₹70L; 2024 Kartik Tyagi ₹60L). After correcting them, **gross auction spend matches the official totals to 0.00 Cr in all 5 seasons** (2022: 551.7 Cr, 2023: 167.0 Cr, 2024: 230.45 Cr, 2025: 639.15 Cr, 2026: 215.45 Cr). This also corrects the 12 Nov explanation: the official 2024 total *includes* Harry Brook (DC, ₹4 Cr, later withdrew), so he is no longer netted out. PASS.

3. ~~Squad / overseas off-by-ones~~: **RESOLVED (14 Nov).** These weren't trades. They were two bugs in `parse_retentions.py`:
   - A team's last retained player was filed under the next team.
   - Players without a wiki link were dropped.

   Both are fixed. A wiki unit typo (2024 Padikkal "7.75 lakh") is now corrected and flagged. All 50 team-seasons are within 18–25 and the overseas cap, and the slot counts match the official pre-auction tables exactly ([scripts/build_pre_auction_state.py](../scripts/build_pre_auction_state.py), [data/reference/pre_auction_official.csv](../data/reference/pre_auction_official.csv)).

4. **Wrong ID matches removed (14 Nov).** The new "one Cricsheet ID = one player" check found loose fuzzy matches that gave two different players the same ID, e.g. Rasikh Salam → Raza Ali Dar, Shahrukh Khan → a different S Khan, Bhagath Varma → Tilak Varma, Emanjot Chahal → Yuzvendra Chahal. The matchers now need the first name to fit, and the verified aliases are listed in [scripts/idjoin.py](../scripts/idjoin.py). The join rate fell from 91.0% to **89.5% (912/1019)** because wrong IDs became blanks. A blank is better than a wrong player.
5. ~~Junk names in 2025 unsold rows~~: **RESOLVED (14 Nov).** Five unsold rows carried narration fragments instead of a clean name ("SL's Nissanka", "Warner", "'Uncapped' Chawla", and two "A and B" lines). [data/reference/unsold_name_corrections.csv](../data/reference/unsold_name_corrections.csv) maps each to the real player(s) with a cited unsold list, and `build_master.py` applies it. "Warner" and "'Uncapped' Chawla" were duplicates of rows that already existed and are dropped; the two pair lines are split. Row count stays 1019, and no sold row, price or winner changed (checked by a full before/after diff).

6. **More wrong IDs found by a nationality check (14 Nov).** With international caps loaded, a new check compares each Indian auction player with the country his ID has played for. It found that "Mohit Sharma" (2018–20, 2023, 2025) carried a **Mexico** player's ID and "Naman Tiwari" (2025–26) a **Cyprus** player's ID. Both are fixed in `idjoin.py` and `join_2018_2021_ids.py`. Three Indian domestic players who later played for the USA or UAE (Milind Kumar, Shubham Ranjane, Akshdeep Nath) are the same people, and the check allows that. Check: "Indian players' IDs are not another country's internationals", PASS.
7. **2018–21 overseas flags (14 Nov).** The raw 2018–21 table marked R Ashwin and Ricky Bhui as overseas and Ashton Turner as Indian. They are fixed through the cited [nationality_corrections_2018_2021.csv](../data/reference/nationality_corrections_2018_2021.csv). Prices and winners are unchanged.

8. **Official auction lists (15 Nov).** The official iplt20.com auction-list PDFs for 2020-26 were downloaded with Harsh's permission and parsed privately (2,898 listed players; counts match the reported pool sizes). What they changed or confirmed:
   - **17 base prices** in the master differed from the official reserve price and are corrected through [base_price_corrections.csv](../data/reference/base_price_corrections.csv) (one PDF URL per row). No hammer price or winner changed.
   - **Capped status:** our rule-based status agrees with the official C/U flag for 796 of 810 matched players (98.3%). The misses are players capped between the list date and the auction, and Afghans (Cricsheet has no Afghanistan internationals). The official flag now takes priority where the player is in the list.
   - **Date of birth:** the official list is now the first source. Wikidata agreed with it for only 408 of 455 players, so Wikidata is the fallback.
   - **Sets:** each called lot 2022-26 now has its official set number and code in `lot_order.csv`. The live-blog order runs forward through the sets until the accelerated round, as expected.
   - **2018 and 2019** (added 15 Nov): there was no PDF for these years. The official lists were published as tables on iplt20.com news pages, and archived copies were used: 578 players in 2018 and 351 in 2019, both matching the reported pool sizes. 2018 has set numbers. 2019 has none.
   - **Four more 2018–20 overseas flags fixed** from those lists (Javon Searles and Zahir Khan Pakteen are overseas; Pankaj Jaswal and Sandeep Bavanaka are Indian), cited in [nationality_corrections_2018_2021.csv](../data/reference/nationality_corrections_2018_2021.csv). The gate still passes, and no price or winner changed.
   - **Lot order 2018–21:** only sold players are known and not in calling order, so they are listed as `not_ordered` with their official set (2018, 2020, 2021).

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
- [x] ID join decision recorded — **91% accepted** (Harsh, 11 Nov 2026); 89.5% after removing wrong matches (14 Nov)
- [x] **spend deltas resolved** (12 Nov) — withdrawn player (Harry Brook) + sub-crore rounding; prices verified faithful to source
- [x] **historical retentions loaded → squad/overseas checks un-blocked** (12 Nov); 2027 slots in on the 17th
- [ ] point-in-time store exercised by the first real feature (L2)

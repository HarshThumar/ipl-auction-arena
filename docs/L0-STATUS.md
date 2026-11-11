# L0 — Clean data foundation: status

*Living status for Level 0 ([levels.md](levels.md)). Updated as checks move. L0 closes register rows G1–G8, D2, D3.*

Run the gate anytime:
```
pip install -r requirements.txt     # once (pyyaml)
python scripts/validate_l0.py       # prints PASS/FAIL/WARN/BLOCKED, writes l0_validation.json
```

## Current result (last run)
**9 PASS · 0 FAIL · 2 WARN · 2 BLOCKED**

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
| Licences attributed, no banned sources redistributed | ✅ (SOURCES.md) | G8 |

## Open items (WARN) — real gaps, not hidden
1. **Player ID join = 91%, target was ≥99%.** The shortfall is entirely **uncapped domestic players who have never played a Cricsheet-tracked match**, so no ID exists to join to. Every *capped* player is matched and collisions were reviewed. **DECISION — ACCEPTED (Harsh, 11 Nov 2026):** 91% stands as L0-sufficient. Rationale: the 99% bar is unreachable via Cricsheet for never-played players; all capped/known players are matched, which is what the price and DNA layers actually use. No second ID source will be chased for now; revisit only if a later level needs IDs for uncapped lots.
2. **Spend vs official, small deltas (cr):** 2022 +0.75, 2023 +0.8, **2024 +4.4**, 2025/2026 exact. Sold *counts* match exactly, and the 2024 top prices all verify against the real auction (Starc 24.75, Cummins 20.5, D. Mitchell 14, Harshal 11.75…) — so no headline price is wrong. The deltas are all **small and positive** (≈2% in 2024), which points to either (a) rounding in the single "official total" figure hardcoded in the check, or (b) an included edge lot (bought-then-withdrawn, or an accelerated re-entry) that official totals treat differently. **Not a broken price.** Definitive resolution = a manual lot-by-lot diff against the official list (iplt20 is verify-only, no scraping); deferred, low severity.

## Blocked on data (cannot run yet, by design)
3. **Squad size 18–25** and **overseas ≤ cap in the full squad** — need the **retained players** per team (auction buys alone aren't the full squad). Historical retentions are on Wikipedia; **2027 retentions land 17 Nov 2026**. These flip from BLOCKED once retentions are loaded.

## Point-in-time store (D2 / C5)
Convention established now, enforced when features begin: **every derived feature carries an `as_of` date**, and nothing dated after an auction may be used to predict that auction. The raw auction facts are naturally as-of their auction date. No model features exist yet (they start at L2), so there is nothing to leak yet — the mechanism is in place before the first feature is written.

## What "L0 done" needs
- [x] franchises.csv + rules_by_season.yaml with a source per row
- [x] money in integer lakhs + FX table; hammer vs paid separated
- [x] validation suite runs in one command
- [x] ID join decision recorded — **91% accepted** (Harsh, 11 Nov 2026)
- [ ] spend deltas explained or accepted
- [ ] retentions loaded → squad/overseas checks un-blocked
- [ ] point-in-time store exercised by the first real feature (L2)

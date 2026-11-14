# Team needs, 2018–2027: plan

*Approved by Harsh on 14 Nov 2026. This is component F's computed half. The expert-stated half follows separately.*

**Goal:** for every team before every auction from 2018 on, record what it needed, worked out from facts known **before** that auction:
- money and slots: purse, slots left, overseas slots left;
- role gaps, using a detailed role for every player.

## Role taxonomy (one label per player per season, as of that auction's date)

| Main role | Subtype | Rule (default thresholds) |
|---|---|---|
| Batter | opener / top order / middle order / finisher | Opener: bats at 1–2 in ≥60% of innings. Top order: mostly bats at 3. Middle order: mostly 4–5. Finisher: mostly 6–7, or usually comes in after over 14 |
| Wicketkeeper | keeper-opener / keeper-middle / keeper-finisher | Keeper flag, then the batting rule |
| All-rounder | batting / bowling / genuine | Batting: top 6, under 2 overs a match. Bowling: 3+ overs a match, bats at 7 or lower. Genuine: both |
| Bowler (pace) | right-arm / left-arm | From bowling style |
| Bowler (spin) | off-spin / left-arm orthodox / leg-spin / left-arm wrist / mystery | From bowling style |
| Bowling phase (anyone who bowls) | powerplay / middle / death / all-phase | The phase with over 40% of his overs (PP 1–6, middle 7–15, death 16–20). None over 40% means all-phase |

**Tags:** Indian/overseas, capped/uncapped, left-hand bat, regular starter (played ≥50% of his team's matches last season).

**Minimum sample:** 10 innings or 20 overs of T20 in the 3 years before the auction. Below that, the subtype is `unknown` and the label is marked low-confidence. Nothing is guessed.

## Sources
1. **Cricsheet ball-by-ball T20 data** (ODC-BY, attributed): batting position, entry over, overs by phase, stumpings.
2. **Wikipedia infobox** (CC BY-SA, attributed): bowling style, batting hand, role.
3. **Auction-list role** (already in our data): main role, used as a fallback and a cross-check.

## Steps
| Step | Output | Done when |
|---|---|---|
| 1 | Pre-auction state 2018–21 (retentions, purse deductions, pre-auction trades, cited corrections) | Slots match the official figures exactly (**done 14 Nov**: 2019, 2020, 2021 and 2023, 2024, 2026 all exact) |
| 2a | Cricsheet T20 player-match table plus a coverage report | Coverage known per season, including uncapped players |
| 2b | Role engine → `data/processed/roles/` | Every player-season labelled, with confidence and source agreement |
| 3 | Team needs → `data/processed/team_needs/` | One record per team-season |
| 4 | Cross-verification (below) | All pass, or results reported |

## Cross-verification
1. Official numbers: slots and overseas slots match exactly.
2. A golden set of about 40 players everyone agrees on, as unit tests. Harsh confirms or edits the draft.
3. Agreement across the three sources for main role, with disagreements listed.
4. Hand comparison with ESPNcricinfo's playing-role labels on a random sample of 100 (target ≥85%).
5. Stability: label flips between seasons are flagged.
6. Date check: no input is dated on or after the auction (enforced in code).
7. Blind rebuild: an independent agent re-derives 5 team-seasons.
8. Held-out years: code frozen on 2018–24, then on 2025–26 we test whether flagged needs predict what teams bought, against chance and a slots-only baseline. Test only, never tuned on.
9. Later: agreement with expert-stated needs.

## Failure modes (added to the register as N1–N6)
- N1: taxonomy drift between sources.
- N2: the typical-squad template uses future seasons (leakage).
- N3: missing pre-auction trades.
- N4: uncapped players with no data.
- N5: tuning on held-out years.
- N6: player ID mismatches when joining sources.

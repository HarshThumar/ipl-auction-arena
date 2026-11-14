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
| All-rounder | batting / bowling / genuine | As built (`RULES` in `build_roles.py`): "bats top" = median position ≤6 and bats in ≥50% of matches. Genuine: 2.5+ overs a match and bats top. Bowling: 2.5+ overs a match, median position ≤8 and bats in ≥40% of matches. Batting: 0.75–2.5 overs a match and bats top. 2.5+ overs otherwise is a bowler |
| Bowler (pace) | right-arm / left-arm | From bowling style |
| Bowler (spin) | off-spin / left-arm orthodox / leg-spin / left-arm wrist | From bowling style |
| Bowling phase (anyone who bowls) | powerplay / middle / death / powerplay+death / all-phase | Phase index = his share of balls in a phase ÷ the normal share (PP 30%, middle 45%, death 25%). Index ≥1.25 marks the phase; PP and death both ≥1.25 is powerplay+death. None means all-phase |

**Tags:** Indian/overseas, capped/uncapped, left-hand bat, regular starter (played ≥50% of his team's matches last season).

**Minimum sample:** 10 innings or 20 overs of T20 in the 3 years before the auction. Below that, the subtype is `unknown` and the label is marked low-confidence. Nothing is guessed.

## Sources
1. **Cricsheet ball-by-ball T20 data** (ODC-BY, attributed): batting position, entry over, overs by phase, stumpings.
2. **Wikipedia infobox** (CC BY-SA, attributed): bowling style, batting hand, role.
3. **Auction-list role** (already in our data): main role, used as a fallback and a cross-check.

### Changes made while building (14 Nov)
- **Phase rule.** The planned "over 40% of his overs" rule labelled only 40 death bowlers in 1,964 player-seasons, because the middle overs are 9 of 20 overs and dominate everyone's share. It now compares each phase with its normal share (above). The new-ball-plus-death pacer (Bumrah, Arshdeep, Bhuvneshwar) gets its own `powerplay_death` label.
- **"Mystery" spin dropped.** No open source records it; Wikipedia gives Narine as off-break and Varun Chakravarthy as leg-break. Not guessed.
- **Capped/uncapped tag** not computed yet for retained players.
- **Keeper sub-labels** come from the batting subtype column, not a separate label.
- **Domestic T20 coverage is thin.** Cricsheet has 261 Syed Mushtaq Ali matches for 2019, 8 for 2024 and none for 2025, so many uncapped players have subtype `unknown`.

## Results (14 Nov)
- **IDs:** 1,896 of 1,964 squad entries (96.5%) resolved to a Cricsheet ID ([scripts/resolve_squad_ids.py](../scripts/resolve_squad_ids.py)); the rest are listed, never guessed.
- **Roles:** [player_roles.csv](../data/processed/roles/player_roles.csv), one row per player per team-season, with the data, Wikipedia and auction-list labels side by side.
- **Needs:** [needs_long.csv](../data/processed/team_needs/needs_long.csv) and [needs_wide.csv](../data/processed/team_needs/needs_wide.csv), 82 team-seasons (2018–26) × 13 cells. 2018 has no typical squad (no earlier season in our data).
- **Checks:** [roles-check.md](roles-check.md) (agreement, stability, hand-check sheet) and [needs-check.md](needs-check.md) (held-out test).
- **Held-out result, honestly:** needs alone do **not** beat the slots-only baseline on the pooled score (r 0.747 vs 0.770). They do beat it on the within-cell score (0.336 vs 0.299), which asks which team buys more of a kind. Needs are a model feature, not a forecast on their own.

## Steps
| Step | Output | Done when |
|---|---|---|
| 1 | Pre-auction state 2018–21 (retentions, purse deductions, pre-auction trades, cited corrections) | Slots match the official figures exactly (**done 14 Nov**: 2019, 2020, 2021 and 2023, 2024, 2026 all exact) |
| 2a | Cricsheet T20 player-match table plus a coverage report | Coverage known per season, including uncapped players (**done 14 Nov**) |
| 2b | Role engine → `data/processed/roles/` | Every player-season labelled, with confidence and source agreement (**done 14 Nov**) |
| 3 | Team needs → `data/processed/team_needs/` | One record per team-season (**done 14 Nov**) |
| 4 | Cross-verification (below) | All pass, or results reported (**reported 14 Nov**; items 2, 4 and 7 wait on Harsh) |

## Cross-verification
1. Official numbers: slots and overseas slots match exactly.
2. A golden set of about 40 players everyone agrees on, as unit tests. Harsh confirms or edits the draft (27 in [tests/test_roles_needs.py](../tests/test_roles_needs.py)).
3. Agreement across the three sources for main role, with disagreements listed.
4. Hand comparison with ESPNcricinfo's playing-role labels on a random sample of 100 (target ≥85%). Sheet: [handcheck_sample.csv](../data/processed/roles/handcheck_sample.csv), not yet filled in.
5. Stability: label flips between seasons are flagged.
6. Date check: no input is dated on or after the auction (enforced in code).
7. Blind rebuild: an independent agent re-derived 5 team-seasons (2019 CSK, 2021 KKR, 2023 GT, 2025 MI, 2026 SRH; 123 players) from this document alone, without seeing the code or output. **Done 14 Nov.** Agreement on the 96 high-confidence players: bowling type 95.8%, bowling phase 95.8%, batting subtype 88.5%, main role 81.2%. Almost every main-role difference sits on the bowler / bowling-all-rounder line (Cummins, Deepak Chahar, Harbhajan) or the batter / batting-all-rounder line (Abhishek Sharma, Will Jacks, Nitish Rana). The written all-rounder rule had drifted from the code (2 and 3 overs in the text, 2.5 in the code), so the table above now states the rule as built. The all-rounder borderline is the least reliable label; treat all-rounder kinds as soft.
8. Held-out years: code frozen before scoring, then on 2019–26 (each season's needs built from earlier seasons only) we test whether flagged needs predict what teams bought, against chance and a slots-only baseline. Test only, never tuned on.
9. Later: agreement with expert-stated needs.

## Failure modes (added to the register as N1–N6)
- N1: taxonomy drift between sources.
- N2: the typical-squad template uses future seasons (leakage).
- N3: missing pre-auction trades.
- N4: uncapped players with no data.
- N5: tuning on held-out years.
- N6: player ID mismatches when joining sources.

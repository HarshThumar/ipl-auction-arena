# Role rules: exact specification

This is the full rule set behind `data/processed/roles/player_roles.csv`. It is written so that someone who never sees the code can rebuild every label and get the same answer. [needs-plan.md](needs-plan.md) explains why the rules exist; this file says exactly what they are. If the code and this file disagree, that is a bug.

## 0. Inputs

| Input | File | Used for |
|---|---|---|
| Squad lists | `data/processed/roles/squad_ids.csv` | season, team, player, source, cricsheet_id |
| Match rows | `data/cache/t20_player_match.csv.gz` (built by `scripts/cricsheet_t20.py`) | one row per player per men's T20/IT20 match |
| Wikipedia facts | `data/processed/roles/wiki_profiles.csv` | `batting`, `bowling`, `role` text |
| Auction-list role | `data/processed/master/all_auctions_master.json` (2022–26, field `role`); `data/processed/2018_2021_staging/staged_2018_2021_joined.csv` (field `role`) | matched on season plus normalised name |
| Auction dates | `data/reference/rules_by_season.yaml`, field `date` per season | the cutoff |

**Normalised name** means lower case with every character outside a–z and 0–9 removed.

## 1. The window

For season Y with auction date D:
- **Start** is D minus 1,095 days (3 × 365, not calendar years).
- The window holds the player's match rows with `start ≤ date < D`, compared as ISO date strings. The auction day itself is never included.
- If the player has no cricsheet_id, or no rows in the window, then every count below is 0.

## 2. Measurements (computed for everyone)

| Name | Definition |
|---|---|
| `n_matches` | Rows in the window |
| `n_innings` | Rows with `bat_pos` not blank |
| `balls_pp`, `balls_mid`, `balls_death` | Sums of those columns |
| `n_balls_bowled` | balls_pp + balls_mid + balls_death |
| `stumpings` | Sum of `stumpings` |
| `overs_per_match` | n_balls_bowled ÷ 6 ÷ n_matches. It is 0 when n_matches = 0, and **all matches count, not only the ones he bowled in** |
| `median_bat_pos` | Median of `bat_pos` over his innings, where the middle two are averaged; blank if n_innings = 0 |
| `bats_top` | median_bat_pos ≤ 6 **and** n_innings ≥ 0.5 × n_matches |

Batting-position shares are over his innings only (`n_innings` ≥ 1). A **late** innings is one with `entry_ball ≥ 84` (he arrived after over 14) **and** `bat_pos` from 4 to 7.

| Share | Innings counted |
|---|---|
| `share_opener` | bat_pos 1 or 2 |
| `share_top` | bat_pos 3 |
| `share_middle` | bat_pos 4 or 5, and not late |
| `share_finisher` | bat_pos 6 or 7, or late |

Positions 8 and above are in no share.

**Phase index** applies when n_balls_bowled > 0. For each phase p, it is (balls_p ÷ n_balls_bowled) ÷ base_p, with base_pp = 0.30, base_mid = 0.45 and base_death = 0.25. The overs are 1–6, 7–15 and 16–20.

## 3. Batting subtype (provisional; step 7 may override)

1. If n_innings < 10, the subtype is `unknown`.
2. If share_opener ≥ 0.60, it is `opener`.
3. Otherwise take the largest of share_top, share_middle and share_finisher, giving `top_order`, `middle_order` or `finisher`. **On an exact tie, middle_order wins**; between top_order and finisher, top_order wins.

## 4. Bowling phase (provisional; step 8 may override)

1. If n_balls_bowled = 0, the phase is `none`.
2. If n_balls_bowled is from 1 to 119, it is `unknown` (fewer than 20 overs).
3. Otherwise, the hot phases are those with an index ≥ 1.25.
   - If the hot set is exactly {pp, death}, the phase is `powerplay_death`.
   - Any other non-empty hot set gives the hot phase with the highest index: `powerplay`, `middle` or `death`.
   - An empty hot set gives `all_phase`.

## 5. Main role from data (`main_data`)

This is blank if n_matches < 10. Otherwise, apply the first rule that fits:

1. If stumpings ≥ 2, `wicketkeeper`.
2. If overs_per_match ≥ 2.5:
   - if bats_top, `allrounder_genuine`;
   - else if median_bat_pos ≤ 8 and n_innings ≥ 0.4 × n_matches, `allrounder_bowling`;
   - otherwise `bowler`.
3. If overs_per_match ≥ 0.75 and bats_top, `allrounder_batting`.
4. If bats_top or overs_per_match < 0.75, `batter`.
5. Otherwise `bowler`.

## 6. Main role from Wikipedia and from the auction list

**Wikipedia (`main_wiki`).** Take the `role` text in lower case and apply the first rule that fits:

1. Empty gives blank.
2. Contains "wicket" and not "occasional" gives `wicketkeeper`.
3. Contains "bowling" and "round" gives `allrounder_bowling`.
4. Contains "batting" and "round" gives `allrounder_batting`.
5. Contains "round" gives `allrounder`.
6. Contains "bowl" gives `bowler`.
7. Contains "bat" gives `batter`.
8. Anything else gives blank.

**Auction list (`main_auction`).** Take the role in lower case:

| Role text | Result |
|---|---|
| bowler | `bowler` |
| all-rounder | `allrounder` |
| batter, batsman | `batter` |
| wicketkeeper, wicket keeper | `wicketkeeper` |
| anything else | blank |

Retained players usually have no auction-list role.

## 7. Final main role and confidence

1. If main_data is not blank, use it with confidence `high`.
2. Else if main_wiki is not blank, use it with `medium`.
3. Else if main_auction is not blank, use it with `low`.
4. Otherwise the role is `unknown` with confidence `none`.
5. **Keeper override:** if the role is not wicketkeeper, main_wiki or main_auction is `wicketkeeper`, and overs_per_match < 0.5, the role becomes `wicketkeeper`. Confidence does not change.
6. If the final role is `bowler` or `allrounder_bowling`, the batting subtype becomes `tail`, even when it was unknown.

## 8. Bowling type

Map the Wikipedia `bowling` text as follows:

1. Lower-case it and turn hyphens into spaces. Empty, "none" or "none}}" gives blank.
2. Keep only the part before the first ",", "/" or the word "and". This is his main style.
3. In that part, apply the first rule that fits:

| The part contains | Result |
|---|---|
| "unorthodox", "wrist" or "chinaman" | `left_wrist` |
| "orthodox" | `left_orthodox` |
| "leg" or "googly" | `leg_spin` |
| "off" | `off_spin` |
| "fast", "medium" or "seam" | `pace_left` if it contains "left", else `pace_right` |
| none of these | blank |

The type is **kept** unless the final role is `batter` or `wicketkeeper` and overs_per_match < 0.75. In that case it is blank.

If the type is then blank and the role is `batter` or `wicketkeeper`, the bowling phase becomes `none`.

The bowl group is `pace` for pace_*, `spin` for the other types, and blank otherwise.

## 9. Tags

| Tag | Rule |
|---|---|
| `left_hand_bat` | 1 if the Wikipedia `batting` text contains "left" |
| `regular_starter` | 1 if, in the IPL season Y−1, he played ≥ 50% of that franchise's IPL matches (Cricsheet IPL rows only; franchise names mapped through `franchises.csv` aliases) |
| `overseas` | Nationality from the pre-auction state (retained players) or the auction list |

## 10. Borderline flag

`borderline` = 1 when main_data is not blank and **any** of these hold:

| Condition | Why it is close |
|---|---|
| 2.0 ≤ overs_per_match < 3.0 | Near the 2.5 front-line bowler line |
| 0.5 ≤ overs_per_match < 1.0 | Near the 0.75 part-timer line |
| 5.5 ≤ median_bat_pos ≤ 6.5 | Near the top-6 line |
| overs_per_match ≥ 2.5, not bats_top, and 7.5 ≤ median_bat_pos ≤ 8.5 | Near the bowling all-rounder line |

A borderline label could flip with a few more overs or innings. Models should use the measurements in section 2, not the borderline label alone.

## 11. Exact details (gaps found by the blind rebuild, 14 Nov)

- **Date key:** season Y uses `seasons[Y].date` in `rules_by_season.yaml`. That is the auction held *before* season Y, so season 2026 uses 2025-12-16.
- **Auction-list lookup:** for 2022–26, use the master JSON (name field `player`); for 2018–21, use the staging CSV (name field `player_name`). If one season plus normalised name has several rows, the **last** row read wins.
- **Wikipedia join:** on `cricsheet_id`, where ids are unique.
- **Blank `bat_pos`** means he did not bat. Positions are whole numbers.
- **Ties in section 3:** if all three shares tie, middle_order wins.
- **Ties in section 4:** if two hot phases have exactly the same index, the earlier phase in the order pp, mid, death wins.
- **The word "and" in section 8** matches as a whole word only (regex `and`), so "standard" does not split. The table is applied top to bottom, so "unorthodox" is caught by the first row before "orthodox".
- **Section 7.6 overrides section 3:** a bowler or bowling all-rounder is `tail` even with fewer than 10 innings.
- **Section 8's phase rule overrides section 4:** a batter or keeper with a blank bowling type gets phase `none`, even when section 4 gave `unknown`.
- **Section 10:** a blank median_bat_pos is never in range.
- **Players with no cricsheet_id** get zero counts (section 1). The squad `source` column is not used for labels.

**Blind rebuild result (14 Nov):** an agent given only this file, not the code, relabelled 8 team-seasons (194 players: 2018 MI, 2019 CSK, 2021 KKR, 2022 LSG, 2023 GT, 2024 RCB, 2025 MI, 2026 SRH). **Every field matched for all 194 players (100%):** counts, all three main-role sources, final role, confidence, batting subtype, bowling type, phase and borderline. The gaps it listed are the bullets above.

This shows the rules are complete and repeatable. It does **not** show the labels are true; only the hand check against ESPNcricinfo measures that.

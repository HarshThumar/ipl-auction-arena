# Spec: `build_decision_dataset.py` (L3 decision dataset)

*Written 15 Nov 2026 for the implementer (agy); Harsh reviews the diff. This is the one blocker before L3 training. It does **not** touch the bidder agent (Harsh writes that himself, rule #3).*

> **Status: BUILT & VERIFIED — 15 Nov 2026.** `scripts/build_decision_dataset.py` (+ root entry `build_decision_dataset.py`), `tests/test_decision_dataset.py` (9 tests green), output in `data/processed/decisions/` (5,405 rows: 4,989 RAISE / 416 DROP; 2025–26 held out). Two review faults found and fixed: (1) `is_final_two` leaked the eventual final-two into early rows (1,029 rows → **0**; the leakage test now actively guards it); (2) RTM lots wrongly dropped the top open bidder (now excluded — Deccan vs SRH ruled distinct per `franchises.csv`). **Still pending for the L3 gate:** the shared LoRA + identity-embedding training must beat LightGBM on held-out log-loss. v2 cricket features remain null placeholders (separate later pass).

## 0. Goal in one line
Turn our reconstructed bid trails (2018–26) into a clean table of **decision rows** `{state → RAISE | DROP}`, computed strictly **as-of** each decision, that trains **both** the shared LoRA (+ identity embedding) **and** the LightGBM baseline from the *same* rows (levels [L2](levels.md)/[L3](levels.md)).

The script's only job is the **canonical feature table**. Turning a row into an LLM prompt is a *separate* script — do **not** put prompt/text serialization in here (one source of truth).

---

## 1. Inputs (read-only; all already committed, licence-clean)
| Input | Path | Use |
|---|---|---|
| Bid trails | `data/processed/bid_sequences/{year}_bids.json` | the `lots[].bid_steps` ladders |
| Master (source of truth) | `data/processed/master/all_auctions_master.csv` | calling order, final price, winner, role, base — **wins on any disagreement** (decision #14) |
| Retentions | `data/processed/retentions_by_season.json` | starting purse/slots after retentions |
| Season rules | `data/reference/rules_by_season.yaml` | purse, squad min/max, overseas cap, increment ladder, RTM-by-season |
| Franchises | `data/reference/franchises.csv` | **lineage** → canonical `franchise_id` (KXIP→PBKS rename shares identity; Deccan→SRH per this file, do not hardcode) |

**Reuse, don't reinvent:** cross-lot purse/slots/overseas/needs accounting already exists in `src/engine/ledger.py` (and the Treasurer logic). Drive state from the engine so this dataset can never diverge from the L1 engine. Only the *intra-lot* dynamics (current price, rival, who's active) come from parsing `bid_steps`.

---

## 2. Bid-trail schema (verified)
```json
{ "season": 2024, "lots": [
  { "player": "Rovman Powell", "base_price": 1, "sold": true, "winner": "RR",
    "final_price": 7.4, "final_two": ["RR","KKR"],
    "bid_steps": [ {"team":"KKR","price":2}, {"team":"RR","price":5.4},
                   {"team":"KKR","price":7.2}, {"team":"RR","price":7.4} ],
    "confidence": "partial", "provenance": {"source":"withheld"} } ] }
```
**Unit trap:** files mix crore (2022–26, e.g. `7.4`) and lakh (2018, e.g. `200`). **Normalize everything to integer lakhs** (L0 convention). Detect the unit per file/row by reconciling against the master's price; if it can't be reconciled, drop the lot and log it.

---

## 3. How to build a decision row (the core rule)

For each lot, walk the recorded ascending ladder. Label only what the data actually witnesses — **never invent participation.**

- **RAISE row:** every `bid_step` is a raise by that team. Emit a row for `(team = step.team, action = RAISE)` whose state is the ladder **just before** that step (the price they're matching, the current rival, etc.).
- **DROP row:** every **losing participant** drops exactly once — at the state where the price went above the last bid they made (i.e. they declined to top it). The losing finalist (`final_two` minus `winner`) drops at `final_price`. A team that raised earlier and never reappears drops at the step that topped them.
- **Winner:** all RAISE, **no DROP** (they never stopped).

So a 4-step war between 2 teams → 4 RAISE + 1 DROP. Expect **RAISE-heavy imbalance** — report it (§6), handle with class weights in training (not here).

**Uncontested / single-step lots:** emit the one RAISE (open-at-base, won) with `contested = false`. Keep them but flag so training can downweight — they carry almost no war signal.

---

## 4. Features (the `state` = X of each row)

All **as-of the decision point**. Group below; mark v1 (must) / v2 (if available, else null). LightGBM reads these columns directly; the LoRA serializer reads the same columns later.

**Identifiers (not features — for joins/splits):** `season`, `lot_id`, `player`, `set_no`, `step_index`, `confidence`, `contested`.

**Label:** `action ∈ {RAISE, DROP}`.

**Identity (v1):** `franchise_id` (lineage-resolved, the embedding token later), `era` (rule-era bucket, e.g. pre-2018/2018-21/2022-24/2025+ — so training can era-weight; 2018 alone is ~⅓ of contested ladders).

**Lot / player (v1):** `role`, `is_overseas`, `capped`, `base_price_lakhs`. **(v2):** age, Powerplay SR, death-over economy, vs-spin/vs-pace, home-ground fit, post-2023 Impact-Player flag — join from `data/processed/enriched/` + Cricsheet; null-fill and add `*_isnull` flags where missing.

**Auction state as-of (v1, from the engine ledger at lot start + ladder position):** `current_price_lakhs` (the price being decided), `next_increment_lakhs`, `lots_done`, `set_no`, `spend_so_far_lakhs`, `spend_pace_vs_expected`.

**Deciding team T (v1, from engine ledger):** `purse_left_lakhs`, `slots_left`, `overseas_left`, `role_gap[role]` (need for this player's role), `is_final_two`.

**Opponent (v1):** `rival_id` (team currently holding top bid), `rival_purse_left_lakhs`, `rival_slots_left`, `rival_role_gap`, `n_active_estimate` (if derivable from the ladder, else null).

**Pool scarcity (v1 — legitimately known as-of, the set list is published):** `same_role_remaining` (count of comparable players in *later* sets), `same_role_avg_base`. **Never** use their future *prices*.

---

## 5. What must NOT be in it (leakage & honesty)
- **No post-decision info** in any feature: not `final_price`, not `winner`, not `final_two`, not any later lot's realized price. (Pool *counts* of upcoming players are fine; their prices are not.)
- **No fabricated rows** — no DROP for a team with zero evidence it was in the lot; no synthetic intermediate bids.
- **No train/test bleed:** `2025` and `2026` fully held out; within 2018–24 split **by season** (leave-one-season-out folds), never random rows — rows from one lot must never span train and test.
- **No outcome in X** (winner/price are labels-of-the-world, not inputs).
- **No hand-authored team "DNA"** — identity is only `franchise_id` + computed features.
- **No source name anywhere** in code, columns, values, or the manifest — provenance stays `"withheld"`.
- **Don't serialize prompts here** (separate script).

---

## 6. Outputs
Write to `data/processed/decisions/`:
- `decision_rows.parquet` — the table (typed, deterministic row order, seeded).
- `decision_rows_sample.csv` — first ~500 rows for eyeballing.
- `schema.json` — data dictionary: every column, type, v1/v2, null policy, as-of note.
- `manifest.json` — row counts total + **label balance per team and per season**, contested vs uncontested, lots dropped + reason, discrepancies vs master, feature list, config used, input file hashes, output content hash.
- `splits.json` — the leave-one-season-out fold assignment (by season, not row).

Config block at top of the script (paths, `seed`, `holdout_seasons=[2025,2026]`, `unit=lakhs`). CLI: `python build_decision_dataset.py --out data/processed/decisions/ --seed 0`. Idempotent.

---

## 7. Tests to ship with it (`tests/test_decision_dataset.py`)
1. **Leakage guard:** assert no feature column name or value derives from `final_price`/`winner`/`final_two`; assert `purse_left` at a row uses only prior-lot prices.
2. **Label correctness:** every RAISE row's team == its `bid_step.team`; every DROP row's team is a losing participant; winner has no DROP.
3. **Monotonic ladder:** prices non-decreasing within each lot; last step == `final_price` (in lakhs) or lot is dropped+logged.
4. **Engine invariants:** `purse_left ≥ 0`, slots/overseas within season rules at every row (reuse engine checks).
5. **Reconciliation:** per-lot winner & final price match the master; mismatches resolve to master and are logged.
6. **Determinism:** run twice → identical output hash.
7. **Unit:** all monetary columns integer lakhs.
8. **Split integrity:** no `lot_id` appears in two folds; 2025–26 absent from train/val.
9. **Balance reported:** manifest has non-empty per-team/per-season label counts.

---

## 8. Constraints
Pure Python + `pandas`/`pyarrow`; reuse `src/engine` for state; **no network**; reads only committed processed data. Respect the L0 as-of convention. Keep it under one module + its test. Flag anything ambiguous back to Harsh rather than guessing (esp. franchise-identity sharing for Deccan→SRH, and any lot where units can't be reconciled).

## 9. Done when
Tests green; `manifest.json` shows sane per-team/season balance; a spot-check of 5 contested lots reproduces the RAISE/DROP story by hand; LightGBM can train on it and the LoRA serializer (later) can read the same columns.

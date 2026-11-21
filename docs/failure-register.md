# Failure-mode register: IPL Auction Arena

*Created 11 Nov 2026 from a literature and post-mortem search. **Rule: before a level runs any training, fitting or evaluation, every High (H) row owned by that level and all earlier levels must be Closed.** Rows owned by L8 are marked *Deferred (L8)* and do not block L0–L7.***

- **Closed** means the detection test exists in the repo, runs in CI and passes, or the mitigation is in the code and has a test.
- **Sev:** H (High) / M (Medium) / L (Low).
- **UV:** no published source; the row comes from standard practice or reasoning.
- Bracketed numbers like [1] point to the sources at the end.
- **Status** values: Open / In progress / Closed / Won't fix (with reason) / Deferred (L8).

**First 6 to close:**
1. D1 (contamination)
2. D2 + C5 (point-in-time data)
3. A10 (money in code)
4. H3 (auctioneer property tests)
5. D5 (pre-registration)
6. D6 (baselines)

## A. Bidding agents

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| A1 | **Budget myopia:** spends early, then can't fill the squad minimum | H | Runs ending with slots × base > purse; purse-left curve vs real | Auctioneer computes **max legal bid = purse − (min slots left − 1) × min base** and rejects anything above it; send remaining needs every turn | AucArena: rule bidders beat most LLMs [1] | Closed, engine side (15 Nov): Treasurer.max_legal_bid enforced on every bid (src/engine/ledger.py), checked on every BID in the property tests and the replay; remaining needs are in every bidder view. Bidder side at L3 |
| A2 | **Overbidding / winner's curse** on stars | H | Sim vs actual price on the top-10 lots; % of wins above the price model's p90 | **Ceiling discipline** (revised 12 Nov for live bidding): the agent sets a ceiling before bidding starts and code enforces it; it may raise it **once per lot, only in a huddle, only up to code's `max_affordable`**, logged with a reason; show the price band | [1][2] | Open |
| A3 | **Ignoring remaining needs** (4th keeper) | H | Wins in roles where the gap = 0 | Structured role-gap vector each turn; post-hoc audit | [1] | Open |
| A4 | **Non-monotonic / irrational bids** | M | Monotonicity checker; re-entry rate | Code autopilot raises below the ceiling; the LLM only decides at 3 points (enter / huddle / final two); fuzz the decision points for contradictions | [1] | Open |
| A5 | **Anchoring** on the base price or last bid | M | Change only the displayed base price; measure the shift | Show the valuation band first; anchor-shuffled tests | [4][3] | Open |
| A6 | **Herding** | M | Bidders-per-lot distribution vs real | Agents see public bids live (as in the real room), never others' reasoning; compare herding with real bidders-per-lot | [5][6] | Open |
| A7 | **Position/order bias** | M | Win rate by agent index (chi-square) | Seeded random pick among teams willing to raise at the same price; shuffle team order per seed | [7] | Open |
| A8 | **Collusion-like restraint** | M | Star prices and unsold rate vs real; isolated-agent rerun | No inter-agent messages | [9] | Open |
| A9 | **Refusal / passivity** | M | Participation rate per agent | Neutral "simulation" framing; engagement threshold | [1] | Open |
| A10 | **Crore/lakh arithmetic errors** | H | Unit-fuzz suite: 200 synthetic states → invalid-action rate | **All money is integer lakhs in code; the LLM never does arithmetic**; the auctioneer supplies next bid and purse-after | [1][10] | Closed, engine side (15 Nov): all money is integer lakhs; the engine gives next price, purse after, max affordable; tests/test_harness_fuzz.py (200 states, 5,475 answers, every invalid answer → safe default, never a crash; garbage-bidder auction 0 violations). LLM bidder rate measured at L3 |
| A11 | **Pretraining reputation / hallucinated stats override our data** | H | **Name-swap / anonymised-player test**; check cited stats against our table | Stats in the prompt; anonymised-ID ablation | [11] | Open |
| A12 | **Sycophancy to card wording** | M | Neutral vs loaded wording of the same card → spend delta | Numeric, neutral cards | [12] | Open |
| A13 | **Persona drift** over 80+ lots | M | Card-consistency vs lot index | **Stateless calls**: re-inject card + state on every lot | [13] | Open |
| A14 | **Prompt-wording sensitivity** | H | ≥5 paraphrased templates; report the spread | Report ranges; choose the template on old auctions only | [3] | Open |
| A15 | **Nondeterminism / seed variance** | M | ≥20 seeds per config; confidence intervals | Fixed seed, temperature 0, Ollama with 1 parallel request (still not a guarantee) | [14] | Open |
| A16 | **Output-format / tool-call failures** (3–8B models) | H | Parse-failure and retry rate per model | a strict JSON schema per decision point (enter / huddle / final two; see architecture.md A5); free-text reasoning, then convert; a failure counts as a logged "drop" | [15][16] | Open |
| A17 | **4-bit quantisation hurts numeric reasoning** | M | Q4 vs Q8 on the fuzz suite | Q8 for ≤3B models; maths stays in code | [17] | Open |
| A18 | **Variance collapse:** 10 same-model agents behave alike | H | Between-agent variance in spend, role mix and bidders per lot; compare with real between-team variance | Distinct numeric DNA; report it if it collapses (a finding in itself) | Fidelity-paradox lit (see research doc) | Open |
| A19 | **Price-push gone wrong:** agent pushes a rival, rival drops, agent is stuck with an unwanted player | M | Push rate, push-stuck rate and stuck spend per agent; compare with how often real teams end up with "push" buys (anecdotal) | Push limit can never exceed code's `max_affordable`; stuck buys stay legal; report the rate | UV | Open |
| A20 | **Call budget blow-up** from live decisions + huddle arguments (wall-clock overruns the Dec timeline) | M | Calls and minutes per seed, per version | ≤3 decision points per involved team per lot; cache every call; few seeds in dev; collapse the war room to one call in dev only | stack.md | Open |

## B. Expert-needs extraction

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| B1 | **Hallucinated needs** | H | Every need needs a **verbatim quote**; string match + manual audit of 50 | Reject anything without a quote | [18] | Open |
| B2 | **Misattributed team** | H | The quote must sit in that team's section | Split articles by team first | [18] | Open |
| B3 | **Syndicated duplicates inflate the consensus** | M | MinHash clusters | Count distinct outlets | UV | Open |
| B4 | **Outlet concentration** | M | HHI by outlet | Cap per outlet | UV | Open |
| B5 | **Temporal mixing** (pre-retention pieces, pages edited after the auction) | H | Published and updated dates before the cutoff; flag needs naming already retained or released players | **Wayback as-of snapshots**; drop "updated" pages | [19] | Open |
| B6 | **Opinion turned into fact** | L | Audit a sample | Keep "expert X says" | [18] | Open |

## C. Team identity (embedding + behavioural features)
*DNA card dropped 15 Nov (decision #16); identity is now a learned embedding + code-computed behavioural features. These rows carry over — same risks, new mechanism.*

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| C1 | **Unfaithful behavioural features** | H | Atomic-check each feature against the stats table | **Features computed in code**, never LLM-authored; every value traces to a number | [20] | Open |
| C2 | **Cherry-picking famous buys** | M | Features vs full spend distribution | Fixed feature set, mandatory fields | UV | Open |
| C3 | **Era skew** (2018 dominates the trails) | M | Shuffle/reweight era → feature delta | Pre-aggregate and era-weight; era flag in state | [21] | Open |
| C4 | **Pretraining stereotypes** ("CSK loves veterans") | M | Zero/shuffle the identity embedding; compare | Identity is learned from data; shuffle-test it | [22] | Open |
| C5 | **Leakage:** features/embedding see the target auction | H | Cutoff date on every feature; split by season | **As-of features**, time-sliced per auction | [25] | Open |
| C6 | **Identity has no signal in minis** (AuctionIQ found team habits ≈ chance) | H | **Zeroed- and shuffled-embedding ablations** | This is the main hypothesis to test, not an assumption | AuctionIQ | Open |

## D. Backtesting and forecasting

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| D1 | **The model already knows the Dec 2025 results** | H | Probe "who bought X in IPL 2026, for how much?"; named vs anonymised scores; lookahead propensity | Backtest models with training cutoff **before Dec 2025** (check each); **the Gemini fallback can't be used for backtests**; the 16 Dec 2026 live run is the clean test | [23][24][11][31] | **Closed** (21 Nov): green CI run 44881445435 (L0 data gate) + 44881445439 (L1 engine tests) on commit 18ce59b. guard in code. `src/eval/contamination.py` passes a model only for auctions after its public release date (qwen2.5:7b released 2024-09-19: clean for the 2025, 2026, 2027 seasons, *possibly contaminated* for 2023 and 2024); Gemini and unknown models refused. Tests: `tests/test_l2_eval.py::test_release_after_auction_is_flagged`, `::test_held_out_seasons_are_clean_for_qwen25`, `::test_gemini_and_unknown_models_refused`. The 13–14 Nov probe tested the wrong model and relied on self-report (correction in contamination-probe.md). |
| D2 | **Feature leakage** (stats/squads dated after the auction) | H | As-of timestamp on every feature | **Point-in-time feature store**; Kapoor & Narayanan checklist | [25] | **Closed** (21 Nov): green CI run 44881445435 (L0 data gate) + 44881445439 (L1 engine tests) on commit 18ce59b. `as_of` convention set (L0-STATUS.md). Enforced in L2 code (21 Nov): forward-chaining split (train on seasons < scored season), lot baselines read only earlier seasons + that season's pre-auction purses; whole-lot fields (`contested`, `confidence`) banned as features. Tests: `tests/test_l2_eval.py::test_forward_split_never_trains_on_target_or_future`, `::test_last_price_uses_only_earlier_seasons`, `::test_features_exclude_forbidden_and_outcomes`. |
| D3 | **Survivorship** (defunct teams) | M | Franchise coverage | Defunct teams in the price model, not in DNA | UV | In progress — defunct franchises in `franchises.csv` |
| D4 | **Small sample** (~70–80 sales per mini, ~7 buys per team) | H | Bootstrap CIs | Pooled/hierarchical models; **no per-team skill claims**; leave-one-auction-out | UV | Open |
| D5 | **Overfitting / forking paths** on one backtest | H | Log every config tried | Freeze configs on Dec 2022 + Dec 2023; **pre-register**; run Dec 2025 once | [26] | Open |
| D6 | **Wrong or weak baselines** | H | Must include base price, last price, the price model alone, **AuctionIQ rule agents**, **single-prompt LLM**, **JioStar pundit mock**, the expert-consensus-only rule | – | [1] | In progress (21 Nov): built in `src/eval/` and `scripts/run_l2_baselines.py`: base price, last price, LightGBM decision model (with and without team identity), league and team DROP-rate priors; **AuctionIQ** scored with its own code (`scripts/score_auctioniq.py`: value model out-of-sample on 2023 and 2024, its 2024 simulation flagged tuning set; aggregates only, rule #7). Still to add: single-prompt LLM (flagged possibly contaminated on 2023/2024), JioStar mock (Dec 2025, scored at L5), price-model-alone, expert-consensus-only rule |
| D7 | **Metric gaming** (unsold/base-price lots are easy) | M | Log-price MAE on sold lots; price-weighted team accuracy; Brier | Report AuctionIQ's metric set + calibration | UV | **Closed** (21 Nov, first scores in docs/L2-baselines.md): AuctionIQ metric set + Brier + lot-level bootstrap CIs in `src/eval/metrics.py`; price metrics on sold lots only; tests in `tests/test_l2_eval.py`. |
| D8 | **Mega vs mini mixing** | M | Results split by auction type | Evaluate minis separately; mega only as training context | UV | **Closed** (21 Nov, first scores in docs/L2-baselines.md): L2 scores minis only (2023 and 2024 seasons); megas are training context only. Test: `tests/test_l2_eval.py::test_l2_scores_minis_only`. |

## E. Price / dropout model

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| E0 | **No *public* bid-by-bid dataset exists** | H | – | A **reconstructed** bid-trail dataset now exists (2018–26, 326 contested lots with full ladders, ~5.1k steps, per-row provenance) and drives the L3 `state → RAISE/DROP` rows. It is still **incomplete and censored** (most lots outcome-only; raises seen only up to each team's drop), so deep bid-level modelling (Haile–Tamer bounds, sequence transformers) stays L8 | rules-and-data.md §3 | Deferred (L8) — reconstructed set feeds L3; deep modelling after 16 Dec |
| E1 | **Censoring:** the hammer price only bounds valuations | H | – | Interval-censored / survival model with bounds (Haile & Tamer) | [27] | Deferred (L8) — after the 16 Dec auction |
| E2 | **Incomplete live-blog bids** | H | Chain consistent with final price and increments | Flag partial lots; two sources | UV | Deferred (L8) — after the 16 Dec auction |
| E3 | **Selection bias:** only contested lots are narrated | H | Logged vs official lots | Uncontested = single-bidder; model the narration probability | UV | Deferred (L8) — after the 16 Dec auction |
| E4 | **Regime changes** (2014 INR, 2018 squad rules, 2022 10 teams, 2023 Impact Player, 2025 overseas cap) | H | Residuals by year | Era features; store hammer and paid separately | [28] | Open |
| E5 | **Class imbalance** (unsold/base) | M | PR-AUC | Hurdle model | UV | Open |
| E6 | **Lot-order effects** | M | Residual vs lot index | Order features | [8] | Open |

## F. 2-Stage Hierarchical LoRA (L3–L5)

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| F1 | **Overfitting on thin team data** | H | Held-out-auction loss | Low rank (r=8–16), low LR on team adapters, fall back to Stage 1 Shared LoRA for GT/LSG | UV | In progress (L3) — Stage 1 shared foundation regularizes all teams |
| F2 | **Memorising names and outcomes** | H | Anonymised-name score vs named score | Train on features and IDs, not names; player attributes anonymised in training rows | UV | In progress (L3) — feature schema masks specific names during fine-tune |
| F3 | **Losing instruction-following / formatting** | M | Action validity rate | Restricted logit head on binary tokens (`RAISE` vs `DROP`) — eliminates JSON generation | [29] | Closed (15 Nov): logit head predicts RAISE/DROP directly; engine does all rule & money handling |
| F4 | **Eval leakage from random split** | H | Held-out auction validation | Strict split by auction: train on 2018–2022, hold out Dec 2023 mini-auction | [25] | In progress (L3) — dataset generator splits strictly by season |
| F5 | **Number tokenisation / arithmetic errors** | M | Arithmetic consistency checks | Engine handles all increment steps and budget math; model only decides binary RAISE/DROP | [10] | Closed (15 Nov): engine computes next increment; model never predicts numbers |
| F6 | **Team conditioning ignored** | M | Swap/shuffle the identity embedding → output probability delta | The learned team-identity embedding gives each team a distinct policy; verified by a swap-delta check | UV | In progress (L3) — verified via embedding swap-delta check |

## G. Data engineering

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| G1 | **Player entity resolution** | H | Join rate against official lists; collision report | **Cricsheet Register IDs** | UV | **Closed** (21 Nov): green CI run 44881445435 (L0 data gate) + 44881445439 (L1 engine tests) on commit 18ce59b. `validate_l0.py` (capped-ID check PASS; 91% overall accepted). |
| G2 | Renames / new vs renamed franchises | M | – | `franchises.csv` (rules-and-data.md §2) | – | In progress — `franchises.csv` + winner-code check PASS. Closes on first green CI |
| G3 | **Units:** USD 2008–13, lakh/crore | H | Range checks | Integer lakhs + as-of FX table | rules-and-data.md | **Closed** (21 Nov): green CI run 44881445435 (L0 data gate) + 44881445439 (L1 engine tests) on commit 18ce59b. integer lakhs + `fx_usd_inr.csv`; money check PASS. |
| G4 | Accelerated rounds / re-entries | M | One lot ID per (auction, round, player) | – | [30] | Closed (15 Nov): one lot id per (season, round, player), repeats suffixed; tests in test_engine_rules.py and test_engine_properties.py |
| G5 | **Hammer ≠ paid** (tie-breaks, 18cr overseas cap), withdrawals, replacements, trades | M | – | Store hammer and paid separately; status flags | [28] | In progress — hammer/paid/withdrawn columns; cap check PASS. Trades/replacements not modelled yet |
| G6 | Increments differ by year | M | Consecutive bids match the table | Year-specific table | UV | Closed (15 Nov): per-season grid in data/reference/engine_rules.yaml with basis; every BID checked on the grid path (property tests); every recorded 2022-26 hammer is on its season grid (replay; 2024 used both 20 and 25 steps above 5 cr, as the auctioneer may) |
| G7 | **Rules table errors** (conflicting previews, e.g. 2026 purse 125 vs 151cr) | H | Every rule row has a source URL; conflicts listed | Prefer BCCI/iplt20 documents; mark UNVERIFIED | rules-and-data.md | **Closed** (21 Nov): green CI run 44881445435 (L0 data gate) + 44881445439 (L1 engine tests) on commit 18ce59b. rules source + UNVERIFIED checks PASS. |
| G8 | **Licence violations** | M | Licence column per source | Don't redistribute iplt20 or CC BY-NC data; attribute ODC-BY / CC BY-SA | rules-and-data.md §3 | In progress — SOURCES.md; no iplt20/CC BY-NC data in repo |

## H. Simulation validity

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| H1 | **The arena doesn't reproduce real auction patterns** | H | KS tests: bidders per lot, price/base ratio, unsold rate, purse-left curve | **L4 gate** before calling anything a forecast | [32] | Open |
| H2 | One rogue agent inflates prices | M | Swap one agent for a rule bidder | Circuit breaker | UV | Open |
| H3 | **Auctioneer bugs / nondeterminism** | H | **Property tests** (hypothesis): purse ≥ 0, squad 18–25, overseas ≤ 8; log replay reproduces the run exactly | Event-sourced, seeded log; **replay real auctions through the engine (L1)** | UV | Closed (15 Nov): event log with rebuild + digest; tests/test_engine_properties.py (155 hypothesis auctions: purse ≥ 0, squad ≤ 25, overseas ≤ 8, same seed → same digest, log rebuild = live state) and tests/test_replay.py (2022-26 real auctions replayed, 0 violations, squads 18-25 at the end) |
| H4 | Missing private information (injuries, intent) | L | – | Document the scope | UV | Open |
| H5 | **Pre-registration not verifiable** | H | – | Freeze predictions; **SHA-256 hash posted publicly + Zenodo/OSF DOI before 16 Dec** | [26] | Open |
| H6 | **Bidding wars don't look like real ones** (wrong openers, wrong final-two pairs, wars too long or too short) | M | Simulated opening bidder / final-two pairs / number of teams in each war vs real ones from live blogs, where available | Live bidding engine (L1); report the gap; full check moves to L8 if live-blog reconstruction isn't ready | UV | Open |

## N. Computed team needs (added 14 Nov 2026, see [needs-plan.md](needs-plan.md))

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| N1 | **Taxonomy drift between sources** (data, Wikipedia and the auction list call a player different things) | M | Three-way agreement report, [roles-check.md](roles-check.md) (data vs Wikipedia 83.5%); blind rebuild of 5 team-seasons (main role 81%, bowling type and phase 96%), then from the exact spec [role-rules.md](role-rules.md): 8 team-seasons, 100% on every field | Fixed priority: data (10+ matches) > Wikipedia > auction list; confidence column | UV | In progress (hand check of 100 pending) |
| N2 | **Typical squad uses future seasons** (leakage) | H | `test_needs_use_no_purchases`, `test_first_season_has_no_baseline` | Typical squad = earlier seasons only; pre-auction squad = retained rows only; both asserted in `build_team_needs.py`; role window ends before the auction date (`assert_as_of`) | [25] | Closed |
| N3 | **Missing pre-auction trades** | H | Slots and overseas slots vs official figures, 2018–26 | Transfers parsed from Wikipedia and applied before the auction; backtest exact in all published seasons | UV | Closed |
| N4 | **Uncapped players with no data** | M | Count of `confidence` none/low per team (the `unknown_role` cell) | Never guessed: subtype `unknown`; Wikipedia/auction role used only as labelled fallback | UV | Open (Cricsheet has almost no domestic T20 after 2023) |
| N5 | **Tuning on held-out years** | H | – | Needs rules were fixed before `check_needs.py` ran; every predictor tried is reported, including the one added after the first lost | [25] | Closed |
| N6 | **Wrong player ID when joining sources** | H | `validate_l0.py` "one Cricsheet ID = one player"; unresolved list printed | Strict name rules outside the team's roster, first-name guard, claim exclusion in a squad, common surnames never matched register-wide | UV | Closed |

## Sources
1. AucArena https://arxiv.org/html/2310.05746v3
2. LLM bidders https://arxiv.org/abs/2507.09083
3. Sclar et al., prompt format https://arxiv.org/abs/2310.11324
4. Anchoring https://arxiv.org/abs/2511.05766, https://arxiv.org/abs/2505.15392
5. Herding https://arxiv.org/abs/2505.21588
6. Social influence https://arxiv.org/abs/2507.22467
7. Option-order bias https://arxiv.org/abs/2309.03882
8. Declining-price anomaly https://econpapers.repec.org/paper/arxpapers/1905.00853.htm
9. Algorithmic collusion https://arxiv.org/abs/2404.00806
10. Tokenisation https://arxiv.org/abs/2402.14903
11. Glasserman & Lin https://arxiv.org/abs/2309.17322
12. Sycophancy https://arxiv.org/abs/2310.13548
13. Persona drift https://arxiv.org/abs/2402.10962
14. Nondeterminism (secondary) https://community.openai.com/t/defeating-nondeterminism-in-llm-inference/1358623
15. BFCL https://gorilla.cs.berkeley.edu/leaderboard.html
16. Let Me Speak Freely https://arxiv.org/abs/2408.02442
17. Quantisation https://arxiv.org/pdf/2507.04023
18. Not Wrong, But Untrue https://arxiv.org/abs/2509.25498
19. ESPNcricinfo live page https://www.espncricinfo.com/auction/ipl-2026-auction-1515016/live-updates
20. Faithfulness https://arxiv.org/pdf/2512.03503, FaithBench https://arxiv.org/pdf/2410.13210
21. Lost in the Middle https://aclanthology.org/2024.tacl-1.9/
22. Bias Runs Deep https://arxiv.org/abs/2311.04892
23. Lookahead propensity https://arxiv.org/abs/2512.23847
24. Time Travel in LLMs https://arxiv.org/abs/2308.08493
25. Kapoor & Narayanan https://reproducible.cs.princeton.edu/
26. Preregistration for agents https://arxiv.org/pdf/2606.11217
27. Haile & Tamer https://www.its.caltech.edu/~mshum/gradio/papers/HaileTamer2003.pdf
28. IPL 2026 rules https://thesportstak.com/cricket/ipl/story/ipl-2026-auction-rules-explained-salary-caps-purse-limits-overseas-player-guideline-3220162-2025-12-11
29. LoRA forgets less https://arxiv.org/abs/2405.09673
30. Accelerated process https://crictracker.com/crictracker-explainers/ipl-auction-2025-what-is-the-accelerated-process-in-mega-auction-explained
31. DatedGPT https://arxiv.org/html/2603.11838
32. Larooij & Törnberg https://arxiv.org/abs/2504.03274

*Sources [4], [14], [17], [18], [20] and [26] were read only as abstracts or secondary summaries. Check their numbers before quoting them publicly.*

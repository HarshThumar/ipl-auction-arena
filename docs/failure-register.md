# Failure-mode register: IPL Auction Arena

*Created 11 Nov 2026 from a literature and post-mortem search. **Rule: nothing is trained, fitted or generated for evaluation (DNA cards, dropout model, LoRA, backtests) until every High (H) row is Closed.***

- **Closed** means the detection test exists in the repo, runs in CI and passes, or the mitigation is in the code and has a test.
- **Sev:** H (High) / M (Medium) / L (Low).
- **UV:** no published source; the row comes from standard practice or reasoning.
- Bracketed numbers like [1] point to the sources at the end.
- **Status** values: Open / In progress / Closed / Won't fix (with reason).

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
| A1 | **Budget myopia:** spends early, then can't fill the squad minimum | H | Runs ending with slots × base > purse; purse-left curve vs real | Auctioneer computes **max legal bid = purse − (min slots left − 1) × min base** and rejects anything above it; send remaining needs every turn | AucArena: rule bidders beat most LLMs [1] | Open |
| A2 | **Overbidding / winner's curse** on stars | H | Sim vs actual price on the top-10 lots; % of wins above the price model's p90 | **Commit-then-bid:** the agent declares a reservation price before the lot and code enforces it; show the price band | [1][2] | Open |
| A3 | **Ignoring remaining needs** (4th keeper) | H | Wins in roles where the gap = 0 | Structured role-gap vector each turn; post-hoc audit | [1] | Open |
| A4 | **Non-monotonic / irrational bids** | M | Monotonicity checker; re-entry rate | Proxy bidding (one reservation price per lot; code runs the clock) | [1] | Open |
| A5 | **Anchoring** on the base price or last bid | M | Change only the displayed base price; measure the shift | Show the valuation band first; anchor-shuffled tests | [4][3] | Open |
| A6 | **Herding** | M | Bidders-per-lot distribution vs real | Agents see only public bids, never others' reasoning | [5][6] | Open |
| A7 | **Position/order bias** | M | Win rate by agent index (chi-square) | Seeded random tie-break; shuffle team order | [7] | Open |
| A8 | **Collusion-like restraint** | M | Star prices and unsold rate vs real; isolated-agent rerun | No inter-agent messages | [9] | Open |
| A9 | **Refusal / passivity** | M | Participation rate per agent | Neutral "simulation" framing; engagement threshold | [1] | Open |
| A10 | **Crore/lakh arithmetic errors** | H | Unit-fuzz suite: 200 synthetic states → invalid-action rate | **All money is integer lakhs in code; the LLM never does arithmetic**; the auctioneer supplies next bid and purse-after | [1][10] | In progress — data is integer lakhs; LLM-no-arithmetic + unit-fuzz suite land at L1/L3 |
| A11 | **Pretraining reputation / hallucinated stats override our data** | H | **Name-swap / anonymised-player test**; check cited stats against our table | Stats in the prompt; anonymised-ID ablation | [11] | Open |
| A12 | **Sycophancy to card wording** | M | Neutral vs loaded wording of the same card → spend delta | Numeric, neutral cards | [12] | Open |
| A13 | **Persona drift** over 80+ lots | M | Card-consistency vs lot index | **Stateless calls**: re-inject card + state on every lot | [13] | Open |
| A14 | **Prompt-wording sensitivity** | H | ≥5 paraphrased templates; report the spread | Report ranges; choose the template on old auctions only | [3] | Open |
| A15 | **Nondeterminism / seed variance** | M | ≥20 seeds per config; confidence intervals | Fixed seed, temperature 0, Ollama with 1 parallel request (still not a guarantee) | [14] | Open |
| A16 | **Output-format / tool-call failures** (3–8B models) | H | Parse-failure and retry rate per model | JSON schema `{action, max_price}`; free-text reasoning, then convert; a failure counts as a logged "drop" | [15][16] | Open |
| A17 | **4-bit quantisation hurts numeric reasoning** | M | Q4 vs Q8 on the fuzz suite | Q8 for ≤3B models; maths stays in code | [17] | Open |
| A18 | **Variance collapse:** 10 same-model agents behave alike | H | Between-agent variance in spend, role mix and bidders per lot; compare with real between-team variance | Distinct numeric DNA; report it if it collapses (a finding in itself) | Fidelity-paradox lit (see research doc) | Open |

## B. Expert-needs extraction

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| B1 | **Hallucinated needs** | H | Every need needs a **verbatim quote**; string match + manual audit of 50 | Reject anything without a quote | [18] | Open |
| B2 | **Misattributed team** | H | The quote must sit in that team's section | Split articles by team first | [18] | Open |
| B3 | **Syndicated duplicates inflate the consensus** | M | MinHash clusters | Count distinct outlets | UV | Open |
| B4 | **Outlet concentration** | M | HHI by outlet | Cap per outlet | UV | Open |
| B5 | **Temporal mixing** (pre-retention pieces, pages edited after the auction) | H | Published and updated dates before the cutoff; flag needs naming already retained or released players | **Wayback as-of snapshots**; drop "updated" pages | [19] | Open |
| B6 | **Opinion turned into fact** | L | Audit a sample | Keep "expert X says" | [18] | Open |

## C. Franchise DNA cards

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| C1 | **Unfaithful claims** | H | Atomic-claim check against the stats table | **Facts computed in code; the LLM only rephrases**; every claim cites a number | [20] | Open |
| C2 | **Cherry-picking famous buys** | M | Claims vs full spend distribution | Template with mandatory fields | UV | Open |
| C3 | **Recency / lost-in-the-middle** | M | Shuffle era order → card delta | Pre-aggregate by era | [21] | Open |
| C4 | **Pretraining stereotypes** ("CSK loves veterans") | M | Generate with names masked; compare | Mask, then verify | [22] | Open |
| C5 | **Leakage:** a backtest card includes the target auction | H | Cutoff date on every card | **Time-sliced cards** as of each auction | [25] | Open |
| C6 | **DNA has no signal in minis** (AuctionIQ found team habits ≈ chance) | H | **Shuffled-DNA and no-DNA ablations** | This is the main hypothesis to test, not an assumption | AuctionIQ | Open |

## D. Backtesting and forecasting

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| D1 | **The model already knows the Dec 2025 results** | H | Probe "who bought X in IPL 2026, for how much?"; named vs anonymised scores; lookahead propensity | Backtest models with training cutoff **before Dec 2025** (check each); **the Gemini fallback can't be used for backtests**; the 16 Dec 2026 live run is the clean test | [23][24][11][31] | Open |
| D2 | **Feature leakage** (stats/squads dated after the auction) | H | As-of timestamp on every feature | **Point-in-time feature store**; Kapoor & Narayanan checklist | [25] | In progress — `as_of` convention set (L0-STATUS.md); enforced from the first L2 feature |
| D3 | **Survivorship** (defunct teams) | M | Franchise coverage | Defunct teams in the price model, not in DNA | UV | In progress — defunct franchises in `franchises.csv` |
| D4 | **Small sample** (~70–80 sales per mini, ~7 buys per team) | H | Bootstrap CIs | Pooled/hierarchical models; **no per-team skill claims**; leave-one-auction-out | UV | Open |
| D5 | **Overfitting / forking paths** on one backtest | H | Log every config tried | Freeze configs on Dec 2022 + Dec 2023; **pre-register**; run Dec 2025 once | [26] | Open |
| D6 | **Wrong or weak baselines** | H | Must include base price, last price, the price model alone, **AuctionIQ rule agents**, **single-prompt LLM**, **JioStar pundit mock**, the expert-consensus-only rule | – | [1] | Open |
| D7 | **Metric gaming** (unsold/base-price lots are easy) | M | Log-price MAE on sold lots; price-weighted team accuracy; Brier | Report AuctionIQ's metric set + calibration | UV | Open |
| D8 | **Mega vs mini mixing** | M | Results split by auction type | Evaluate minis separately; mega only as training context | UV | Open |

## E. Price / dropout model

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| E0 | **No bid-by-bid dataset exists** | H | – | Dec build: the price model uses final outcomes (censored). Partial bidder reconstruction from live blogs is L8 (after 16 Dec) | rules-and-data.md §3 | Open |
| E1 | **Censoring:** the hammer price only bounds valuations | H | – | Interval-censored / survival model with bounds (Haile & Tamer) | [27] | Open |
| E2 | **Incomplete live-blog bids** | H | Chain consistent with final price and increments | Flag partial lots; two sources | UV | Open |
| E3 | **Selection bias:** only contested lots are narrated | H | Logged vs official lots | Uncontested = single-bidder; model the narration probability | UV | Open |
| E4 | **Regime changes** (2014 INR, 2018 squad rules, 2022 10 teams, 2023 Impact Player, 2025 overseas cap) | H | Residuals by year | Era features; store hammer and paid separately | [28] | Open |
| E5 | **Class imbalance** (unsold/base) | M | PR-AUC | Hurdle model | UV | Open |
| E6 | **Lot-order effects** | M | Residual vs lot index | Order features | [8] | Open |

## F. LoRA (after 16 Dec, L8)

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| F1 | Overfitting | H | Held-out-auction loss | Low rank, early stopping, leave-one-auction-out | UV | Open |
| F2 | **Memorising names and outcomes** | H | Anonymised-name score | Train on features and IDs, not names | UV | Open |
| F3 | Losing JSON / instruction-following | M | Format pass rate before and after | Mix in general data | [29] | Open |
| F4 | Eval leakage from a random split | H | – | Split by auction | [25] | Open |
| F5 | Number tokenisation | M | Digit-error analysis | Predict the number of increments as a class | [10] | Open |
| F6 | Team conditioning ignored | M | Swap the team token → output delta | – | UV | Open |

## G. Data engineering

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| G1 | **Player entity resolution** | H | Join rate against official lists; collision report | **Cricsheet Register IDs** | UV | In progress — `validate_l0.py` (capped-ID check PASS; 91% overall accepted). Closes on first green CI |
| G2 | Renames / new vs renamed franchises | M | – | `franchises.csv` (rules-and-data.md §2) | – | In progress — `franchises.csv` + winner-code check PASS. Closes on first green CI |
| G3 | **Units:** USD 2008–13, lakh/crore | H | Range checks | Integer lakhs + as-of FX table | rules-and-data.md | In progress — integer lakhs + `fx_usd_inr.csv`; money check PASS. Closes on first green CI |
| G4 | Accelerated rounds / re-entries | M | One lot ID per (auction, round, player) | – | [30] | Open |
| G5 | **Hammer ≠ paid** (tie-breaks, 18cr overseas cap), withdrawals, replacements, trades | M | – | Store hammer and paid separately; status flags | [28] | In progress — hammer/paid/withdrawn columns; cap check PASS. Trades/replacements not modelled yet |
| G6 | Increments differ by year | M | Consecutive bids match the table | Year-specific table | UV | Open |
| G7 | **Rules table errors** (conflicting previews, e.g. 2026 purse 125 vs 151cr) | H | Every rule row has a source URL; conflicts listed | Prefer BCCI/iplt20 documents; mark UNVERIFIED | rules-and-data.md | In progress — rules source + UNVERIFIED checks PASS. Closes on first green CI |
| G8 | **Licence violations** | M | Licence column per source | Don't redistribute iplt20 or CC BY-NC data; attribute ODC-BY / CC BY-SA | rules-and-data.md §3 | In progress — SOURCES.md; no iplt20/CC BY-NC data in repo |

## H. Simulation validity

| # | Failure | Sev | Detect | Mitigate | Src | Status |
|---|---|---|---|---|---|---|
| H1 | **The arena doesn't reproduce real auction patterns** | H | KS tests: bidders per lot, price/base ratio, unsold rate, purse-left curve | **L4 gate** before calling anything a forecast | [32] | Open |
| H2 | One rogue agent inflates prices | M | Swap one agent for a rule bidder | Circuit breaker | UV | Open |
| H3 | **Auctioneer bugs / nondeterminism** | H | **Property tests** (hypothesis): purse ≥ 0, squad 18–25, overseas ≤ 8; log replay reproduces the run exactly | Event-sourced, seeded log; **replay real auctions through the engine (L1)** | UV | Open |
| H4 | Missing private information (injuries, intent) | L | – | Document the scope | UV | Open |
| H5 | **Pre-registration not verifiable** | H | – | Freeze predictions; **SHA-256 hash posted publicly + Zenodo/OSF DOI before 16 Dec** | [26] | Open |

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

# Levels: IPL Auction Arena goals, from L0 to L9

*Set 11 Nov 2026. Each level is harder than the one before it, and each has a "done when" test you can check. **No level may be skipped**, because each one is the gate for the next. The register rows each level must close are in brackets ([failure-register.md](failure-register.md)). The **depth** of L1/L3/L4 (how deep the agents and the auction go) is locked in [architecture.md](architecture.md) — read it with this file.*

| Level | Name | Done when | Closes | Target date |
|---|---|---|---|---|
| **L0** | **Clean data foundation** | `franchises.csv` and `rules_by_season.yaml` have a source URL on every row. Every player maps to one Cricsheet Register ID (join rate ≥ 99%, collisions reviewed). Money is in integer lakhs with an FX table for 2008–13. Hammer and paid prices are stored separately. A point-in-time feature store with an as-of date on every feature. The validation suite passes: spend ≤ purse, squads and overseas within each season's rules, ledger reconciles season to season | G1–G8, D2, D3 | 22 Nov |
| **L1** | **Engine that matches reality** | The auctioneer **replays the real 2022, 2023, 2024 and 2025 auctions** from the recorded outcomes with zero rule violations. Property tests pass (purse ≥ 0, squad 18–25, overseas ≤ 8, log replay is identical). Max legal bid is enforced. Accelerated rounds are modelled | H3, A1 (engine side), A10 | 25 Nov |
| **L2** | **Know the bar (baselines)** | Scored on the Dec 2025 mini with AuctionIQ's metrics (sold/unsold AUC, buyer in top 3, % of prices inside the 80% interval, Spearman, log-price MAE, Brier). Baselines: base price; last price paid; a GBM/hedonic price model; **AuctionIQ** (run its MIT code, or reimplement it and say so); **single-prompt LLM** ("ask Gemini"); the **JioStar 2026 pundit mock** | D6, D7, D8 | 29 Nov |
| **L3** | **One bidder that never does anything stupid** | One LLM bidder on the chosen local model: **0 invalid actions** on the 200-state unit-fuzz suite; never left unable to fill the squad; monotone reservation prices; parse failures < 1%; tested on ≥ 5 paraphrased templates; Q4 vs Q8 checked | A2–A5, A9, A10, A12, A14, A16, A17 | 3 Dec |
| **L4** | **An arena that behaves like a real auction** | 10 agents. Statistical tests (KS) do not reject the real distributions of bidders per lot, price/base ratio, unsold rate and purse-left curve on 2022–2024 minis. No position bias (chi-square). Between-agent variance compared with real between-team variance. Results come from ≥ 20 seeds | H1, H2, A6–A8, A13, A15, A18 | 7 Dec |
| **L5** | **Beat the bar honestly** | On leakage-controlled backtests (leave-one-auction-out over Dec 2022 and Dec 2023; Dec 2025 only with a model whose training cutoff is before Dec 2025, or anonymised players), the arena **matches or beats AuctionIQ on ≥ 2 of 4 main metrics**, with bootstrap CIs. **The contamination probe has run and is reported.** Losing is acceptable if it's reported honestly | D1, D4, D5, A11 | 10 Dec |
| **L6** | **Answer the real question: does franchise history help?** | Ablations: **DNA vs shuffled DNA vs no DNA vs DNA + expert needs**. DNA cards pass the faithfulness check (every claim traced to a number). Expert-needs extraction passes the quote audit. A clear yes or no, with CIs (AuctionIQ says "no" for minis, so either answer is news) | C1–C6, B1–B6 | 12 Dec |
| **L7** | **Pre-registered live forecast** 🎯 *(the 16 Dec headline)* | Before the auction: the final 2027 pool (out 3 Dec) is run with ≥ 20 seeds. Predictions frozen (P(sold), buyer distribution, price interval per player). **SHA-256 hash posted publicly + Zenodo/OSF DOI** before the hammer falls. Static site with per-franchise pages. After the auction: **5-way scorecard** (LLM arena vs AuctionIQ-style rules vs single-prompt LLM vs pundits (JioStar 2027 War Room, if it airs, + expert consensus) vs reality), plus a calibration plot | H5 | **Freeze 15 Dec; score 17 Dec** |
| **L8** | **Research-grade** (after the auction) | Partial bidder reconstruction from live blogs (opening bidder, final two bidders). Interval-censored price model (Haile–Tamer bounds). **Team-conditioned LoRA vs prompt DNA** (split by auction, anonymised names). Preprint written | E0–E6, F1–F6 | Jan 2027 |
| **L9** | **Transfer** (optional) | The same engine and method run on a different auction (WPL, or DoT spectrum auctions) with only a new rules config and data adapter | – | Optional |

**Cut line if time runs short before 16 Dec:** L0–L4 and L7 are mandatory. L5 and L6 shrink to "report what we have, with CIs". L8–L9 are after the auction by design.

**"10/10" means L7 + L6 + L5 done honestly.** That is a timestamped forecast nobody else made, scored in public against pundits and the best existing model, and it answers a real question.

---

## Depth lock (12 Nov 2026) — the showcase is agent craft; see [architecture.md](architecture.md)
The purpose beyond the forecast is to **showcase how deep a well-engineered agent can be, inside an auction that feels real.** These deepen the existing levels (they do not add new numbered ones):

| Level | Baseline "done when" (above) | Depth locked on top (architecture.md) |
|---|---|---|
| **L1** | engine replays real auctions, zero violations | **Living auction:** real player **sets**, **accelerated round**, **RTM**, live board; an **auctioneer agent** that calls the room (Part B, M1–M2) |
| **L3** | one bidder, 0 invalid actions on the fuzz suite | **Deep bidder:** memory stream + reflection + planning (cognitive core), **Scout/Treasurer/Strategist** sub-agents, a **light opponent model** — built v0→v6, guardrails green throughout (Part A) |
| **L4** | 10 agents pass KS validity tests, ≥20 seeds | **War-room deliberation** under time/partial-info budget; **bidding micro-dynamics** (wars, sniping cadence); Monte-Carlo distribution (Part B, M3–M6) |

**Floor we never drop:** the guardrailed cognitive bidder + faithful engine + auctioneer + ≥20 seeds. **Encore (L8/paper):** deep theory-of-mind, strategic jump-bidding, a self-authored skill library, inter-agent trade negotiation, and the full broadcast UI.

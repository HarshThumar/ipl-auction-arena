# IPL Auction Arena: plan

*Committed 11 Nov 2026. This is an attention, learning and research project. An "AI Captain" idea was dropped on 11 Nov.*

| File | What's in it |
|---|---|
| **plan.md** (this file) | What we're building, components, timeline, working rules |
| [levels.md](levels.md) | **Goals L0 → L9**, each with a "done when" test and a date |
| [failure-register.md](failure-register.md) | **Every known failure mode** with how to detect it, the fix and its status. **No training until every High row is Closed** |
| [rules-and-data.md](rules-and-data.md) | Sourced rules by season (2008–2027), franchise lineage, data sources and licences, data traps |
| [research-and-paper.md](research-and-paper.md) | Prior art (AuctionIQ), pundit baselines, literature, **the paper assessment and venues** |

---

## 1. What it is (one line)
**A pre-registered, timestamped forecast of the IPL 2027 mini-auction (16 Dec 2026, Goa) made by 10 franchise agents on one open model, scored in public against pundits, the best existing rule-based model and reality. It also tests whether a franchise's own history actually helps an AI predict what it will do.**

## 2. Why this beats the 6/10 version (research of 11 Nov)
1. **Closest rival: AuctionIQ.** It is rule-based, with no LLMs and no pundits, and it published nothing before its auction. Its author **found team habits ≈ chance in minis**. So "does history help an LLM?" becomes our falsifiable question rather than an assumption.
2. **No bid-by-bid dataset exists.** The December build works on final outcomes (censored); partial bid reconstruction is L8.
3. **Contamination:** current models probably already know the Dec 2025 results. **The only clean test is the live 16 Dec 2026 auction**, so the predictions are **frozen and hashed before it starts**.
4. **No one has scored LLM agents against pundit mocks and reality, in any sport.** The JioStar 2026 War Room published a full mock list, which gives us the baseline.

## 3. Components

| # | Component | Notes |
|---|---|---|
| A | **Data foundation** (L0) | `franchises.csv`, `rules_by_season.yaml`, Cricsheet Register IDs, integer lakhs + FX, hammer vs paid, point-in-time store, validation suite |
| B | **Auctioneer** (L1) | Deterministic, event-sourced, seeded; league-agnostic config; enforces max legal bid; **replays real auctions exactly** |
| C | **Baselines** (L2) | Base price, last price, GBM/hedonic, **AuctionIQ** (MIT), single-prompt LLM, JioStar pundit mock |
| D | **Bidder agent** (L3) | **Harsh writes this**. Stateless per lot; outputs `{action, max_price}` as JSON; **the LLM never does arithmetic**; commit-then-bid reservation price |
| E | **Franchise DNA cards** | Facts computed in code, LLM only rephrases; time-sliced; names masked for the stereotype check |
| F | **Expert-consensus needs** | Wayback as-of snapshots; verbatim quote required; split by team; distinct outlets; capped per outlet |
| G | **Price model** | Interval-censored / hurdle model on final outcomes; era features |
| H | **Arena + evaluation** (L4–L6) | ≥20 seeds, probabilities, calibration, KS validity tests, ablations (DNA / shuffled / none / + experts), bootstrap CIs |
| I | **Pre-registration + site** (L7) | Zenodo/OSF DOI + public SHA-256 before the auction; per-franchise fan pages; 5-way scorecard after |
| J | **Paper extras** (L8) | Partial bid reconstruction, Haile–Tamer bounds, **team-conditioned LoRA vs prompt DNA**. LoRA is tried before 16 Dec only if L0–L7 are on track by 10 Dec; otherwise it's done straight after the auction as part of the paper (same project) |

**Model:**
- **Backtests:** local Ollama, with a model whose training cutoff is **before Dec 2025** (to be checked).
- **The live forecast:** any model.
- **Gemini free tier:** a fallback, never for backtests.
- Cache every call. One call per team per set ≈ 300 calls per run.

**Brand and people rules:**
- No IPL/BCCI/team logos; not official; no betting angle.
- Model the **franchise seat**, not people: no owner chatbots, quotes, faces or voices. No broadcast footage.
- Don't scrape or redistribute iplt20.com data (its terms forbid copying).

## 4. Timeline (dates in levels.md)

| Week | Build (Claude Code) | Harsh |
|---|---|---|
| 11–16 Nov | L0 data foundation starts | Post #1 |
| 17–22 Nov | **Retentions land 17 Nov** → purses, slots. L0 done. Expert articles collected (as-of) | Review L0 |
| 23–29 Nov | L1 engine replays real auctions; L2 baselines | **Writes the bidder agent (L3)** |
| 30 Nov – 6 Dec | **Final player list 3 Dec.** L3 fuzz suite; L4 arena validity | L3 done; review |
| 7–12 Dec | L5 backtests + contamination probe; L6 ablations; site | Read results; draft posts |
| 13–15 Dec | **L7: final runs, freeze, hash, DOI** | Post 1: "10 AI franchises made their picks, hash attached" |
| 16 Dec | Live auction | Watch |
| 17–18 Dec | 5-way scorecard | Post 2: pundits vs AI vs rules vs reality |
| Late Dec – Jan | L8 + preprint | Writes the paper with Claude |

**Working rules:**
- Claude builds at full speed. Harsh writes the bidder agent himself and explains back every component before the next starts.
- Personal GitHub identity only. **Ask before** creating the public repo, posting the hash or publishing the site.

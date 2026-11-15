# IPL Auction Arena: plan

*Committed 11 Nov 2026. This is an attention, learning and research project. An "AI Captain" idea was dropped on 11 Nov.*

| File | What's in it |
|---|---|
| **plan.md** (this file) | What we're building, components, timeline, working rules |
| [levels.md](levels.md) | **Goals L0 → L9**, each with a "done when" test and a date |
| [failure-register.md](failure-register.md) | **Every known failure mode** with how to detect it, the fix and its status. **No training until every High row is Closed** |
| [rules-and-data.md](rules-and-data.md) | Sourced rules by season (2008–2027), franchise lineage, data sources and licences, data traps |
| [research-and-paper.md](research-and-paper.md) | Prior art (AuctionIQ), pundit baselines, literature, **the paper assessment and venues** |
| [architecture.md](architecture.md) | **Depth lock (12 Nov):** the deep bidder agent (L3) and the living auction world (L1/L4) — build spec |
| [launch.md](launch.md) | Launch playbook (LinkedIn + Instagram): hooks, timing, demo clip, caption guardrails |
| [stack.md](stack.md) | Tech stack & compute: the $0 rule, inference routing (local for bulk, Gemini live-only, one Cloudflare account), compute-time budget |

---

## 1. What it is (one line)
**A pre-registered, timestamped forecast of the IPL 2027 mini-auction (16 Dec 2026, Goa) made by 10 franchise agents on one open model, scored in public against pundits, the best existing rule-based model and reality. It also tests whether a franchise's own history actually helps an AI predict what it will do.**

## 2. Why this beats the 6/10 version (research of 11 Nov)
1. **Closest rival: AuctionIQ.** It is rule-based, with no LLMs and no pundits, and it published nothing before its auction. Its author **found team habits ≈ chance in minis**. So "does history help an LLM?" becomes our falsifiable question rather than an assumption.
2. **No *public* bid-by-bid dataset exists**, so we reconstructed one (2018–26: 326 contested lots with full raise-by-raise ladders, ~5.1k bid steps, from a secondary tracker reconciled with live blogs; per-row provenance). It drives the L3 `state → RAISE/DROP` decision dataset. The price model still treats final prices as censored outcomes; deeper bid-level modelling is L8.
3. **Contamination:** current models probably already know the Dec 2025 results. **The only clean test is the live 16 Dec 2026 auction**, so the predictions are **frozen and hashed before it starts**.
4. **No one has scored LLM agents against pundit mocks and reality, in any sport.** The JioStar 2026 War Room published a full mock list, which gives us the baseline.

## 3. Components

| # | Component | Notes |
|---|---|---|
| A | **Data foundation** (L0) | `franchises.csv`, `rules_by_season.yaml`, Cricsheet Register IDs, integer lakhs + FX, hammer vs paid, point-in-time store, validation suite |
| B | **Auctioneer** (L1) | Deterministic, event-sourced, seeded; league-agnostic config; **live open ascending bidding** with a full bid log; enforces max legal bid; **replays real auctions exactly**. Living-auction depth: real sets / accelerated round / RTM + an auctioneer-agent voice — [architecture.md](architecture.md) Part B |
| C | **Baselines** (L2) | Base price, last price, **LightGBM decision model (trained on identical state rows)**, **AuctionIQ** (MIT), single-prompt LLM, JioStar pundit mock |
| D | **Bidder agent & LoRA** (L3) | **Harsh writes the bidder & data pipeline**. **One shared LoRA** (general auction mechanics, trained on all teams) **+ a learned team-identity embedding** (`<CSK>`/`<MI>`/…, learned from how each team bid — not an adapter, not a card) **+ optional behavioural features** in the state. Predicts binary `RAISE` vs `DROP` from state logits; **served on Ollama** (one base + shared LoRA, rule #9). Optional rank-2 per-team deltas only as an ablation arm. State includes pool scarcity, rival purse/gaps, ball-by-ball cricket features, and auction sequence history — [architecture.md](architecture.md) Part A A0 |
| E | **Team identity (embedding + behavioural features)** | Identity is a **learned embedding**, not a hand-written card (DNA card dropped 15 Nov, decision #16). Behavioural features computed in code double as the **no-fine-tune baseline** (features-in-prompt, no LoRA) |
| F | **Expert-consensus needs** | Wayback as-of snapshots; verbatim quote required; split by team; distinct outlets; capped per outlet |
| G | **Price model** | Interval-censored / hurdle model on final outcomes; era features |
| H | **Arena + evaluation** (L4–L6) | Simulation on Ollama (≥20 seeds), logit probability sampling (calibrated with temperature scaling), KS validity tests, **identity ablation (embedding on vs zeroed vs shuffled vs features-only no-LoRA vs LightGBM)**, bootstrap CIs — [architecture.md](architecture.md) Part B |
| I | **Pre-registration + site** (L7) | Zenodo/OSF DOI + public SHA-256 before the auction; 10 fine-tuned franchise agents run 2027 pool; per-franchise fan pages; 5-way scorecard after |
| J | **Paper extras** (L8) | Post-auction analysis: GAIL-style adversarial imitation, sequence transformers over the bid log, preprint written with Claude |

**Model:**
- **Backtests:** local Ollama, with a model whose training cutoff is **before Dec 2025** (to be checked).
- **The live forecast (frozen 15 Dec):** the same local model that passed L3–L5. Gemini only as an emergency fallback if the local model fails, and if used, say so publicly.
- **Gemini free tier:** emergency fallback for the live forecast only; never for backtests or baselines.
- Cache every call. Call budget per run: at most 3 decisions (enter / huddle / final two) per **involved** team per lot, plus huddle argument calls (see architecture.md A5, register A20).

**Brand and people rules:**
- No IPL/BCCI/team logos; not official; no betting angle.
- Model the **franchise seat**, not people: no owner chatbots, quotes, faces or voices. No broadcast footage.
- Don't scrape or redistribute iplt20.com data (its terms forbid copying).

## 4. Timeline (dates in levels.md)

| Week | Build (Claude Code) | Harsh |
|---|---|---|
| 11–16 Nov | L0 data foundation starts | Post #1 |
| 17–22 Nov | **Retentions land 17 Nov** → purses, slots. L0 done. Expert articles collected (as-of) | Review L0 |
| 23–29 Nov | L2 baselines (LightGBM on decision rows + AuctionIQ); `build_decision_dataset.py` | **Writes data-conversion & trains the shared LoRA + identity embedding (L3)** |
| 30 Nov – 6 Dec | **Final player list 3 Dec.** L4 arena simulation (Ollama, logit sampling, KS tests) | Runs multi-agent simulations; reviews fidelity |
| 7–12 Dec | L5 backtests & ablations (embedding on/zeroed vs LightGBM vs features-only); site | Read results; draft posts |
| 13–15 Dec | **L7: final 2027 runs with 10 team LoRAs, freeze, hash, DOI** | Post 1: "10 fine-tuned AI franchises made their picks, hash attached" |
| 16 Dec | Live auction | Watch |
| 17–18 Dec | 5-way scorecard | Post 2: pundits vs AI vs rules vs reality |
| Late Dec – Jan | L8 + preprint | Writes the paper with Claude |

**Working rules:**
- Claude builds at full speed. Harsh writes the bidder agent himself and explains back every component before the next starts.
- Personal GitHub identity only. **Ask before** creating the public repo, posting the hash or publishing the site.

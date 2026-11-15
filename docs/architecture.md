# Architecture — deep bidder agents + a living auction

*Locked 12 Nov 2026. **Revised 12 Nov 2026 (realism pass):** we only build what a real IPL auction actually has. Secret one-shot bids are replaced by **live open bidding**, the war room argues only at **huddles**, agents read rivals from **what they bid**, and things real auctions don't have (jump-bidding, skill libraries, in-auction trades, agent-to-agent messages) are removed.*

This is the build spec for the two deep pieces: the **bidder agent** (you write this — L3) and the **living auction world** (the engine + arena — L1/L4). It sits on top of the existing level gates, it does not replace them. Every "stupid-proofing" guardrail from [failure-register.md](failure-register.md) still applies — the depth is built **on** that robustness, not instead of it.

**Design goal:** showcase how deep a well-engineered agent can be, inside an auction that works **the way the real one works**. Agents are the star; the auction is the stage.

**The realism rule:** *if a real IPL auction room doesn't have it, we don't build it.* Every feature below cites the real-world behaviour it copies.

**Hard constraints that shape every choice:**
- Runs on **free local models** (Ollama, 3–8B). This caps how much deep strategy is realistic — see the small-model notes.
- **You write the bidder** and explain each pattern back, so the build order is a learning path, not a dump.
- **No logos, no broadcast footage, no real-person voice/face/name** (rule #6). We mimic the *mechanics and drama*, build our *own* visuals and a *generic* auctioneer.
- The auctioneer's **decisions are code** (deterministic, seeded) so the property tests (H3) still hold; the LLM only ever supplies *decisions, valuations and words*, never arithmetic or outcomes.

Legend: **CORE** = ship before 16 Dec. **STRETCH** = before 16 Dec only if on track by 10 Dec. **ENCORE** = after the auction / paper (L8). **[small-model risk]** = may not work well on a 7B local model; have a fallback.

---

## How a real IPL auction works (what we copy)

| Real auction | What we build |
|---|---|
| **Open ascending bidding.** Auctioneer calls the next price (fixed increments), teams raise paddles, everyone sees who is in. | **Live bidding engine** (B1). No sealed bids. |
| Teams **react to who else is bidding** ("RCB is in, push"; "only MI left, let it go"). | Agents see public bids live (A3, A5). |
| Teams come with a **target list, a max per player, and backups**. | The plan (A1) has targets, ceilings and backups. |
| Below their max, a team just keeps raising. When the price **crosses the max, the table huddles** (coach, analyst, owner argue). | Autopilot below the ceiling (code); **huddle** = the war room (A2). |
| Teams sometimes bid **only to make a rival pay more**, and risk getting stuck with the player. | **Price-pushing** (A4), allowed, with real risk. |
| When a target is lost, the team **switches to the backup**. | Re-plan on loss (A1). |
| Everyone watches the **public board**: purses, slots, overseas left. | Opponent model (A3). |
| Teams **cannot talk to each other** during the auction; trades happen outside it. | No agent-to-agent messages (A8 in the register). No trades in the arena. |
| Increments are **fixed by the auctioneer** — nobody jump-bids. | No jump-bidding. Removed. |
| Sets in order; accelerated round from shortlists; RTM only in seasons that had it (none in the 2027 mini). | B1 mechanics. |

---

## Part A — The deep bidder agent (L3)

One franchise bidder = a cognitive agent with a war room inside it, powered by a **Two-Stage Hierarchical LoRA** served via vLLM multi-adapter inference.

### A0. Two-Stage Hierarchical LoRA & Multi-Adapter Serving — CORE
Instead of single-prompt zero-shot generation, the bidding intelligence is learned hierarchically:

```
                       [ Base Model: Qwen-2.5 7B ]
                                    │
                       ┌────────────┴────────────┐
                       │  Stage 1: Shared LoRA   │  <- Trained on all 10 franchises
                       │   (General Auction Sense)│     (Rules, purse pacing, squad limits)
                       └────────────┬────────────┘
                                    │ (branch with lower LR)
         ┌──────────────┬───────────┼───────────┬──────────────┐
         ▼              ▼           ▼           ▼              ▼
     [ CSK LoRA ]  [ MI LoRA ] [ KKR LoRA ] [ RCB LoRA ] ... [ GT/LSG ]
     (Patience,     (Young pace, (Spin fit,   (Top-order,     (Fallback to
      veterans)      power-hit)   role-value)  star-power)     Shared if thin)
```

1. **Stage 1 (Shared Foundation LoRA):**
   - Trained on all 10 franchises across 2018–2024 historical bid trails.
   - Learns universal auction dynamics: increment rules, purse pacing, squad limit awareness, and when raising is generally viable.
2. **Stage 2 (Franchise-Specific Adapters):**
   - 10 lightweight per-team adapters trained on top of Stage 1 using only that franchise's historical decisions at a lower learning rate.
   - Learns franchise-specific bidding DNA (e.g. MI's appetite for young pacers, CSK's valuation of experienced anchors).
   - Newer franchises with thinner history (GT, LSG) regularize heavily or fall back to Stage 1.
3. **vLLM Multi-LoRA Serving (10 Adapters on 1 GPU):**
   - Base model loaded once into GPU VRAM (e.g. on a single 16–24 GB GPU).
   - All 10 franchise LoRA adapters loaded concurrently into the same engine.
   - Every increment evaluated in a single batched forward pass across active teams with shared prompt prefix caching.
4. **Logit-Probability Sampling (No Free-Form Hallucinations):**
   - Restricted output head predicting binary tokens: `RAISE` vs `DROP`.
   - Sample actions directly from calibrated probabilities (calibrated via temperature scaling on held-out validation data).
   - Guarantees 0 syntax or invalid number errors while preserving organic bidding wars across Monte Carlo seeds.
5. **Richer State Representation (What real management considers):**
   - **Pool Scarcity:** Number of comparable players remaining in subsequent sets and their average quality (drives bidding wars).
   - **Opponent State & Identity:** Rival holding the bid, their remaining purse, and their squad gaps (enables strategic price-pushing).
   - **Ball-by-Ball Cricket Features:** Powerplay SR, death-over economy, performance vs spin/pace, home-ground fit, and post-2023 Impact Player era flag.
   - **Auction-So-Far Sequence State:** Number of targets missed in this role, spend pace vs expected curve.

### A1. The cognitive core (Generative-Agents style) — CORE
A **memory stream**: a time-ordered log of what the agent has seen, concluded and planned.

```
memory = { t, type: observation|reflection|plan, text, importance:1-10, embedding }
```
- **Retrieval** when facing a lot: score each memory by `α·recency + β·importance + γ·relevance(to current player)`, take top-k, inject into the prompt. (This is what lets it say *"prices are running hot tonight, I'll hold."*)
- **Planning** (copies a real team's pre-auction sheet): before lot 1 the agent writes a `plan` = purse split across role needs + **target players with a ceiling each + a backup for each target**.
  ```
  plan.targets = [{player, role, ceiling_lakhs, backup: [player, ...]}]
  ```
- **Re-plan on loss**: when a target is sold to someone else (or goes past the ceiling), the backup moves up and the purse split is redone — the way a real table switches to Plan B.
- **Reflection** every N lots / at each set boundary: summarise the top memories into higher-level insight (*"we are overpaying for pace; pivot to spin"*) and write it back as a `reflection` memory.

### A2. The war room — argues only at huddles — CORE
A real table doesn't debate every lot; it debates when a decision is hard. Same here. Three roles:

| Role | Gets | Returns |
|---|---|---|
| **Scout** | player profile + our squad gaps + the plan | `{fit_score, role_value, case}` |
| **Treasurer** | purse, slots left, needs, price band (**all math done in code**) | `{max_affordable, cost_of_going_higher, case}` |
| **Strategist** | both cases + opponent model + the plan | **`{decision, new_ceiling?, reason}`** |

**The huddle** (one argument round): Scout makes its case, Treasurer makes its case, **each may answer the other once**, then the Strategist decides. The visible Scout-vs-Treasurer tension is the showcase.

Fallback for speed ([stack.md](stack.md) lever 5): collapse to one structured call — but only for dev runs, never for the version we report.

### A3. Opponent model, learned from live bids — CORE  (deep recursive theory-of-mind is ENCORE, [small-model risk])
A **code-maintained** table per rival, updated from **public information only** — the board *and* what they have bid on:
```
rival = { purse_left, slots_left, overseas_left,
          role_gaps_estimated,          # from squad + rules
          bid_history: {role: lots_entered, lots_won},  # what they actually chased tonight
          last_drop_price_by_role }     # where they tend to quit
```
The agent reads it as plain text (*"PBKS has entered every spinner lot and has ₹40cr left — they'll go hard"*). Copies what real analysts at the table do.

### A4. Price-pushing — CORE
A real move: bid on a player you don't really want, to make a rival pay more. The agent may declare a lot as `push` with a **push limit**. The risk is real: if the rival drops first, **we bought him**. Guardrail: the push limit can never exceed what the Treasurer (code) says we can afford, so a push can hurt but can never make the squad illegal. We log every push and every push that got stuck (register A19).

### A5. The per-lot loop (live bidding)
```
1 perceive   squad_state(), player profile, plan entry, opponent snapshot
2 retrieve   top-k memories relevant to this player
3 DECIDE #1 — enter?   {stay_out | bid(ceiling) | push(limit)}         [LLM call]
4 live bidding (code runs the clock):
     - autopilot: while price < our ceiling and we are not leading -> raise (code)
     - DECIDE #2 — HUDDLE when the next price would cross our ceiling:
         war room argues -> {drop | raise_ceiling_once(new_ceiling)}   [LLM call]
     - DECIDE #3 — FINAL TWO: when exactly one rival is left,
         look at who it is + their purse -> {stay | drop}              [LLM call]
5 record     write an observation (who bid, where each team dropped, final price)
6 update     opponent model from the public bid log
7 on lost target -> re-plan (backup moves up)
8 every N lots / set boundary: reflect -> re-plan
```
At most **3 decision points per team per lot**, and only for teams actually involved. Everything between them is code — just like a real team keeps the paddle up while under its number.

### A6. Guardrails (L3's bar — non-negotiable)
- **No arithmetic in the LLM (A10):** next price, purse-after, affordability, the increment ladder — all **computed in code** and handed in. The LLM picks decisions and valuation numbers only.
- **Ceiling discipline (A2, replaces commit-then-bid):** the agent sets a ceiling **before** bidding starts and code enforces it. It may raise it **once per lot, only in a huddle**, only up to the Treasurer's `max_affordable`, and the raise is logged with a reason. This keeps the realism of a team "going over its number" without letting it chase forever.
- **Max legal bid (A1):** `purse − (min_slots_left − 1) × min_base`, enforced by the auctioneer — the agent physically cannot strand its squad.
- **Stateless re-injection (A13):** every call re-injects the DNA card + current state + retrieved memories; no hidden chat history to drift.
- **Strict JSON (A16):** every decision has a schema; a parse failure = a logged "drop", not a crash.
- **Public info only (A6/A8):** an agent sees bids, the board and its own war room — never another team's reasoning, never a message from another team.

### A7. Build order (your learning path, each a working checkpoint)
| Step | Adds | Pattern you learn | Due |
|---|---|---|---|
| **v0** | one prompt → enter/ceiling | the agent loop | CORE (by 3 Dec) |
| **v1** | **tools** (`squad_state`, `valuation`, …) | tool use / ReAct | CORE |
| **v2** | **live decisions**: enter, huddle, final two | acting in a multi-agent environment | CORE |
| **v3** | **plan with targets + ceilings + backups**, re-plan on loss | planning | CORE |
| **v4** | **memory stream + reflection** | Reflexion / Generative Agents | STRETCH (by 10 Dec) |
| **v5** | **war room argues at huddles** (Scout / Treasurer / Strategist) | multi-agent deliberation | STRETCH |
| **v6** | **opponent model from live bids + price-pushing** | theory of mind (light) | STRETCH |

- Pass the L3 fuzz/guardrail gate at **v1**, and keep it green through every later version.
- **The forecast freezes on the highest version that is green** on 13 Dec. Nothing is forced in.
- **Ladder scorecard (L5):** every version is scored on the same old auction (see [levels.md](levels.md)). One table: what each layer bought, what it cost in calls and time.

---

## Part B — The living auction world (L1 engine + L4 arena)

### B1. Faithful mechanics — CORE — this *is* L1
Event-sourced, seeded, deterministic (H3). Models the real shape:
- **Open ascending bidding**: the auctioneer calls the next price from the **real increment ladder** (`rules_by_season.yaml`); teams raise or stay down; the highest bidder when everyone else is out wins.
- **Who gets the bid when several raise at once**: real auctioneers take the first paddle they see; we use a **seeded random pick among teams willing to raise**, with team order shuffled per seed (A7 position bias).
- **Late entry allowed**: a team can join a war midway, as in real auctions.
- **Sets** in real order (marquee → batters → allrounders → pacers → spinners → uncapped…), so purse blown early strands a team when its real need comes later.
- **Accelerated round**: teams submit shortlists; unsold + remaining re-enter fast.
- **RTM** only where the season had it (2025 yes; 2022/24/26 and the 2027 mini no).
- **Live board**: purse, slots, overseas per team — enforced every bid.
- **Overseas mini cap**: hammer above ₹18cr, pay capped (hammer vs paid, G5).
- **Replays real 2022–2025 auctions with zero rule violations** (the L1 gate).

### B2. Auctioneer as an agent — CORE
Runs the room: announces each player (bio from our data), calls each price, "going once, going twice", declares sold. **Sequencing and outcomes are code** (keeps H3); an LLM only writes the **announce/flavour words**, in a **generic persona** (never a real auctioneer's name/voice).

### B3. Bidding wars are real, not reconstructed — CORE
Because bidding is now live, every lot produces a **real bid log**: who opened, every raise, where each team dropped, the final two. This is both the drama (wars, late entries, the final-two stand-off) and the data for the realism checks in L4. No fake ladder is drawn after the fact.

### B4. War-room realism — CORE
Huddles run under a **time/token budget** and **partial information** (public bids + own state only). That constraint is what makes the huddle realistic.

### B5. Monte-Carlo world — CORE (free)
Run the whole auction **≥20 seeds**, temperature 0, Ollama 1-parallel. The outcome is a **distribution**, not one script — honest error bars, and realistic (the real night could have gone many ways).

### B6. Broadcast-style playback — ENCORE / finale
Board, player cards, purse bars, the live bid cadence, the war-room argument visible — **our own visuals**, no IPL/JioStar branding. Build after the engine and agents work.

---

## Removed in the realism pass (real auctions don't have these)
| Removed | Why |
|---|---|
| Sealed one-shot "commit-then-bid" as the bidding mechanism | Real IPL bidding is open and live. (The *discipline* idea survives as the ceiling rule, A6.) |
| A drawn-after-the-fact bid ladder | Bidding is real now, so the ladder is real. |
| Strategic jump-bidding | The auctioneer fixes increments; teams can't jump. |
| Self-authored skill library (Voyager-style) | No real-world analogue in an auction room. |
| Inter-agent trade negotiation | Trades happen outside the auction. |
| Agent-to-agent messages / a "lab" where teams talk | Teams can't talk to each other in the room. |

---

## How this maps to the existing plan
| This spec | Level | Register rows it leans on |
|---|---|---|
| A1–A7 bidder depth | **L3** (bidder) | A1–A5, A9, A10, A13, A14, A16, A17, A19, A20 |
| A2 huddles / A3 opponent model / A4 pushing | **L4** (arena) + L6 | A6, A7, A8, A18, A19 |
| B1 live engine | **L1** | H3, A1, A7, G4, G5, G6 |
| B2 auctioneer agent | **L1** | H3 |
| B3–B4 bid logs / huddles | **L4** | H1, H2, H6 |
| B5 Monte-Carlo | **L4/L5** | A15, D4 |
| v0→v6 ladder scorecard | **L5** | D5 |
| B6 broadcast UI | **L7** (site) | — |
| deep recursive opponent model | **L8** (paper) | — |

## Timeline honesty
- **CORE (by 3 Dec):** live engine (B1) + auctioneer (B2) + bidder **v0–v3**.
- **STRETCH (by 10 Dec):** v4–v6. The forecast freezes on the highest green version.
- **ENCORE (post-auction / L8):** deep recursive theory-of-mind, full broadcast UI (B6) if not reached.
- **Cut order** if December gets tight: drop B6 → v6 pushing → v6 opponent model becomes the static board only → v5 war room collapses to one call. **Floor we never drop:** live engine + guardrailed bidder v3 + auctioneer + ≥20 seeds.
- **Call budget:** at most 3 decisions per involved team per lot (not every team, not every raise), plus huddle argument calls. Track it (A20); cache everything.

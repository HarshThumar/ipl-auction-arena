# Architecture — deep bidder agents + a living auction

*Locked 12 Nov 2026. This is the build spec for the two deep pieces: the **bidder agent** (you write this — L3) and the **living auction world** (the engine + arena — L1/L4). It sits on top of the existing level gates, it does not replace them. Every "stupid-proofing" guardrail from [failure-register.md](failure-register.md) still applies — the depth is built **on** that robustness, not instead of it.*

**Design goal:** not to prove a thesis — to **showcase how deep a well-engineered agent can be**, inside an auction that feels real. Agents are the star; the auction is the stage.

**Hard constraints that shape every choice:**
- Runs on **free local models** (Ollama, 3–8B). This caps how much deep strategy is realistic — see the small-model notes.
- **You write the bidder** and explain each pattern back, so the build order is a learning path, not a dump.
- **No logos, no broadcast footage, no real-person voice/face/name** (rule #6). We mimic the *mechanics and drama*, build our *own* visuals and a *generic* auctioneer.
- The auctioneer's **decisions are code** (deterministic, seeded) so the property tests (H3) still hold; the LLM only ever supplies *valuations and words*, never arithmetic or outcomes.

Legend: **CORE** = ship before 16 Dec. **ENCORE** = after the auction / paper (L8). **[small-model risk]** = may not work well on a 7B local model; have a fallback.

---

## Part A — The deep bidder agent (L3)

One franchise bidder = a cognitive agent with a team inside it. Target depth: **L9 cognitive core + L6 sub-agent team + a light L8 opponent model.**

### A1. The cognitive core (Generative-Agents style) — CORE
A **memory stream**: a time-ordered log of what the agent has seen, concluded and planned.

```
memory = { t, type: observation|reflection|plan, text, importance:1-10, embedding }
```
- **Retrieval** when facing a lot: score each memory by `α·recency + β·importance + γ·relevance(to current player)`, take top-k, inject into the prompt. (This is what lets it say *"prices are running hot tonight, I'll hold."*)
- **Reflection** every N lots / at each set boundary: summarise the top memories into higher-level insight (*"we are overpaying for pace; pivot to spin"*) and write it back as a `reflection` memory.
- **Planning**: before lot 1 the agent writes a `plan` — purse split across role needs + target players + reservation prices — and **re-plans** after reflections.

### A2. The sub-agent team (the "war room") — CORE
The agent's mind is three roles that deliberate per lot:
| Role | Gets | Returns |
|---|---|---|
| **Scout** | player profile + our squad gaps | `{fit_score, role_value, note}` |
| **Treasurer** | purse, slots left, needs, price band (**math done in code**) | `{max_affordable, discipline_flag}` |
| **Strategist** | Scout + Treasurer + opponent model + the plan | **`{action, max_price, reason}`** |

The Strategist resolves Scout-wants-him vs Treasurer-says-no. That tension, visible in the trace, is the showcase.

### A3. Light opponent model (L8-lite) — CORE  (deep L8 is ENCORE, [small-model risk])
A **code-maintained** table per rival, updated from public auction state only:
```
rival = { purse_left, slots_left, overseas_left, role_gaps_estimated }
```
The Strategist reads it as plain context (*"KKR still needs a spinner and has 40cr — they'll push"*). This is a **shallow** theory-of-mind a small model can actually use. Full recursive "I think that you think…" bidding is ENCORE — it tends to break on 7B models.

### A4. Guardrails (these are L3's existing bar — non-negotiable)
- **No arithmetic in the LLM (A10):** the Treasurer's affordability, the increment, the purse-after are all **computed in code** and handed in. The LLM only picks a *valuation* number.
- **Commit-then-bid (A2):** the agent commits a reservation price *before* the lot runs; code enforces it so it can't chase in the heat.
- **Max legal bid (A1):** `purse − (min_slots_left − 1) × min_base`, enforced by the auctioneer — the agent physically cannot strand its squad.
- **Stateless re-injection (A13):** every call re-injects the DNA card + current state + retrieved memories; there is no hidden chat history to drift.
- **Strict JSON (A16):** `{action, max_price, reason}`; a parse failure is a logged "drop", not a crash.

### A5. The per-lot loop
```
1 perceive   squad_state(), valuation(P), opponent snapshot, players_remaining()
2 retrieve   top-k memories relevant to P
3 deliberate Scout -> Treasurer -> Strategist  => {action, max_price, reason}
4 commit     code stores reservation price R   (LLM is now done for this lot)
5 (auctioneer runs the clock; see Part B)
6 record     write an observation to the memory stream; update opponent model
7 every N lots / set boundary: reflect -> re-plan
```

### A6. Build order (your learning path, each a working checkpoint)
1. **v0** one prompt → `{action, max_price}` (the toy — proves the loop).
2. **v1** give it **tools** (`squad_state`, `valuation`, …) — now it fetches.
3. **v2** add **working memory** (this auction's state + events).
4. **v3** add a **plan** it makes first and consults.
5. **v4** add **reflection** + re-planning.
6. **v5** split into **Scout / Treasurer / Strategist**.
7. **v6** add the **opponent model**.
Each step is explainable on its own (ReAct → Reflexion → Generative-Agents → multi-agent). Pass the L3 fuzz/guardrail gate at **v1 already**, and keep it green through v6.

---

## Part B — The living auction world (L1 engine + L4 arena)

Faithful enough that strategy is real and it's watchable.

### B1. Faithful mechanics (M1) — CORE  — this *is* L1
Event-sourced, seeded, deterministic (H3). Models the real shape:
- **Sets** (marquee → batters → allrounders → pacers → spinners → uncapped…) in real order — so purse blown early strands a team when its real need comes later.
- **Real increment ladder** per price band (from `rules_by_season.yaml`).
- **Accelerated round**: teams submit shortlists; unsold + remaining re-enter fast.
- **RTM** where the season had it (2025 yes; 2022/24/26 no).
- **Live board**: purse, slots, overseas per team — enforced every bid.
- **Replays real 2022–2025 auctions with zero rule violations** (the L1 gate).

### B2. Auctioneer as an agent (M2) — CORE
A component that runs the room: announces each player (bio from our data), sets base, calls bids, builds tension, declares sold. **Its sequencing and outcomes are code** (keeps determinism/H3); an LLM layer only generates the **announce/flavor words**, in a **generic persona** (never a real auctioneer's name/voice).

### B3. Bidding micro-dynamics (M3) — CORE for the *look*, ENCORE for the *strategy*
- CORE: from the committed reservation prices + the increment rules, reconstruct a plausible **bid ladder** (opener → raises → final two) and render the cadence — wars, sniping at "going twice", the pause. This is what makes it feel alive.
- ENCORE [small-model risk]: agents *strategically* jump-bidding to bluff/deter. Advanced; small models struggle. The proxy-reservation core stays the source of truth.

### B4. War-room realism (M4) — CORE
The sub-agent deliberation (A2) runs under a **time/token budget** and **partial information** (an agent sees public bids and its own state, never rivals' reasoning — A6/A8). That constraint is what makes the huddle realistic.

### B5. Monte-Carlo world (M6) — CORE (free)
Run the whole auction **≥20 seeds**, temperature 0, Ollama 1-parallel. The outcome is a **distribution**, not one script — which is both honest (error bars) and realistic (the real night could've gone many ways). This is the ≥20-seed run the plan already calls for.

### B6. Broadcast-style playback (M5) — ENCORE/finale
A visual front-end: board, player cards, purse bars, lot-by-lot cadence, the war-room chatter visible — **our own visuals**, no IPL/JioStar branding. High effort; a front-end project of its own. Build after the engine and agents work (post-core, time permitting).

---

## How this maps to the existing plan (not scope creep)
| This spec | Existing level | Register rows it leans on |
|---|---|---|
| A1–A6 bidder depth | **L3** (bidder) | A1,A2,A3,A4,A5,A9,A10,A13,A14,A16,A17 |
| A2 war-room / A3 opponent | **L4** (arena) + L6 question | A6,A7,A8,A18 |
| B1 faithful mechanics | **L1** (engine) | H3, A1, G4,G5,G6 |
| B2 auctioneer agent | **L1** | H3 |
| B3–B4 micro-dynamics / war-room | **L4** (arena) | H1,H2 |
| B5 Monte-Carlo | **L4/L5** | A15, D4 |
| B6 broadcast UI | **L7** (site) | — |
| deep L8 opponent / jump-bidding / skill library / inter-agent trades | **L8** (paper) | F*, E* |

## Timeline honesty
- **CORE (by 16 Dec):** A1–A6 (deep bidder through v6), B1 (faithful engine), B2 (auctioneer agent), B3-look, B4, B5. This alone is a deep, living auction of cognitive agents.
- **ENCORE (post-auction / paper, L8):** deep recursive theory-of-mind, strategic jump-bidding, a self-authored skill library (Voyager-style), inter-agent trade negotiation, and the full broadcast UI (B6) if not reached before.
- If December gets tight, the **cut order** is: drop B6 → simplify M3 to look-only → opponent model (A3) becomes a static needs table. The **guardrailed cognitive bidder + faithful engine + auctioneer + seeds** is the floor we do not drop.

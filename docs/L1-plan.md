# L1 plan: the auction engine

*Written 15 Nov 2026. **Status 15 Nov: built.** All parts in §2 exist and 162 tests pass; the 2022-26 replay is exact with 0 violations ([replay-report.md](replay-report.md)). The L1 gate is met on its own terms and formally passes once L0 closes (2027 retentions). Gate target 25 Nov ([levels.md](levels.md) L1). The bidder harness must be ready for Harsh by 23 Nov.*

## 0. The short answer: is it deterministic?

**The engine is 100% deterministic.** It covers rules, money, legality, lot order, the random draws inside a set, tie-breaks and the bid log. It is plain Python with a seed. The same seed and the same bidder decisions always give a byte-identical event log.

**The only non-deterministic part is the LLM bidder.** Even at temperature 0, Ollama does not promise identical output. So every LLM call is cached by a hash of (model, prompt, options). Replaying a run reads the cache and the log, so it is exact. Fresh runs vary, and that is why later levels use 20+ seeds and report ranges.

## 1. What is needed apart from the code

| Need | Status | Why it matters |
|---|---|---|
| **LLM compute** | ✅ **Decided (Harsh, 15 Nov): free cloud GPU** (Kaggle/Colab notebook running Ollama) for the big runs; develop on the laptop. Measured before deciding: Measured on this laptop (i7-1355U, no GPU, 16 GB RAM, qwen2:7b): **170 s** for one cold 1,660-token decision call, **9 s** when the prompt prefix is cached. | A mini auction is about 150 lots × ~4 interested teams × ~2 decisions, which is roughly 1,200 calls per seed. At 20-60 s each that is 7-20 hours per seed, and L4/L7 need 20+ seeds. The engine itself does not need the LLM (L1 runs with code bidders), but L3 onwards does. A free GPU gives about 1-2 s per call. |
| Model | `qwen2:7b` installed; the docs name Qwen2.5-7B or Llama-3.1-8B | Pull the chosen model once the compute decision is made |
| Real room rules per season | ✅ Researched (sources below). The unknowns are listed in §6 | Increment ladders, RTM, accelerated round, overseas pay cap |
| Replay data | ✅ All sold lots 2022-26 have a winner and price; the calling order and official sets exist | See §4 for the coverage numbers |
| 2027 inputs | ⏳ Retentions (deadline **15 Nov** per reports; our runbook said 17), official pool list (~3 Dec), trades | Needed only for the L7 forecast, not for the L1 gate |

## 2. What we build (modules)

All of it lives in `src/engine/`. The existing `auctioneer.py` and `rules.py` (5 tests) are the starting point and get extended, not thrown away.

1. **`season_rules.py`**: one `SeasonRules` object per season, loaded from `rules_by_season.yaml`. It holds:
   - purse and squad limits (18-25, overseas 8);
   - an **increment ladder per season** (see §3.2);
   - minimum base price;
   - RTM on or off, plus cards per team;
   - the overseas pay cap (minis from 2026);
   - where the accelerated round starts.
2. **`ledger.py`**: team state in integer lakhs (purse, squad, overseas, RTM cards). The **Treasurer** functions are pure:
   - `max_legal_bid = purse − (min_slots_left − 1) × min_base`;
   - `can_bid(team, price)`;
   - `next_price(price)`;
   - `purse_after(price)`.

   The LLM never does arithmetic (A10).
3. **`lot.py`**, the lot state machine: `ANNOUNCED → OPEN → BIDDING → (RTM) → SOLD | UNSOLD`.
   - Open ascending bidding on the season ladder.
   - Several teams raising at once: a seeded pick among them, with team order shuffled per seed (A7).
   - Late entry is allowed.
   - Re-entry after dropping is **not** allowed (§3.3).
   - Every raise is one event.
4. **`schedule.py`**: the calling order.
   - **Main phase:** sets in official order, random order inside a set (seeded).
   - **Accelerated round(s):** each team submits a shortlist (a code policy in L1, the agent's choice later). The union of the shortlists plus unsold players is called fast. A second round is allowed. Each call gets a unique lot ID (season, round, player), which is G4.
5. **`events.py` + `log.py`**: an append-only event log written to JSONL.
   - Event types: AUCTION_STARTED, LOT_ANNOUNCED, BID, RTM_OFFERED, RTM_USED, RTM_RAISE, SOLD, UNSOLD, ROUND_STARTED, AUCTION_ENDED.
   - **State is rebuilt from the log** (event sourcing), so "replaying the log gives the same state" is a test, not a hope (H3).
6. **`bidder_api.py`**: **the harness Harsh codes against.**
   - **3 decision points** with strict JSON:
     - `enter` → `stay_out | bid(ceiling) | push(limit)`;
     - `huddle` → `drop | raise_ceiling_once(new_ceiling)`;
     - `final_two` → `stay | drop`.
   - **Autopilot** (code) raises while the price is below the ceiling and the team is not leading.
   - A team's `ceiling` can never exceed `max_legal_bid`.
   - A bad answer is logged as a "drop", never a crash (A16).
   - The bidder sees only public information: its own state, the board, and the bids so far.
7. **`bidders/`** (code bidders, no LLM):
   - `ReplayBidder`: forces the real outcome (§4).
   - `ValuationBidder`: simple ceiling = f(base, role need, purse).
   - `RandomBidder`: for fuzzing.
   - `PassBidder`: the stub that always passes.

   These run L1 end-to-end with zero LLM calls.
8. **`board.py`**: the live board as text (purse left, slots, overseas, last 5 lots). This is what a bidder and the later broadcast UI see.
9. **`auctioneer_voice.py`**: the auctioneer agent's words, with no real person's name or voice (rule #6). In L1 it is a template ("Sold to … for …"). LLM flavour comes later and never changes an outcome.

## 3. Rules as built (real room, cited; unknowns are decided and logged)

### 3.1 Per season

| Season (auction) | Type | Purse | RTM | Overseas pay cap | Accelerated |
|---|---|---|---|---|---|
| 2022 (Feb 2022) | mega | 90 cr | no | no | day-2 wish list |
| 2023 (Dec 2022) | mini | 95 cr | no | no | after lot 86 (13 sets), 10 names per team |
| 2024 (Dec 2023) | mini | 100 cr | no | no | after lot 70 (10 sets) |
| 2025 (Nov 2024) | mega | 120 cr | **yes** | no | after lot 116 (17 sets) |
| 2026 (Dec 2025) | mini | 125 cr* | no | **yes: paid = min(hammer, 18 cr), purse charged the full hammer** | about lot 70, two rounds |
| 2027 (Dec 2026) | mini | 130 cr* | no* | yes* | per the official list |

\* Not confirmed yet. Flagged in the yaml.

### 3.2 Increment ladder per season

There is one cited table (2025 cycle: +5 up to 1 cr, +10 up to 2 cr, +20 up to 5 cr, +25 above). The agent checked every recorded price against it:

- **2022-23:** every price fits the ladder (0 off).
- **2025:** fits too, except the 125-lakh bases. The rule built: a bid snaps up to the next ladder value.
- **2022 and 2023:** every price fits the 25-lakh step above 5 cr (33 and 8 lots only fit that way).
- **2026:** every price above 5 cr sits on **+20 steps**.
- **2024:** both steps were used above 5 cr (8 lots on +20, 4 on +25): the official rule lets the auctioneer set the step above 3 cr.

So the engine uses +25 above 5 cr for 2022, 2023 and 2025, +20 for 2026 and 2027, and +20 for 2024 with +25 also accepted in the replay (corrected 15 Nov after the replay checked every price). This is inferred from the recorded prices, recorded as such, and is G6's test ("consecutive bids match the table").

### 3.3 Room mechanics: where each rule comes from (Harsh, 15 Nov: "follow the real rules exactly, nothing derived")

The full auction regulations are **not public**. The BCCI sends them to franchises, and we searched iplt20.com, bcci.tv, the archives and the news. Each rule therefore has one of three bases, and the code labels every rule with its basis:

- **Official:** an IPL/BCCI release, or a BCCI communication quoted in the press.
- **Observed:** seen in real auctions in our own recorded bid trails, with an example lot.
- **Implementation:** the real room needs *some* way to do this, no source says how, and we choose the most neutral option. Kept to the minimum and listed.

| Rule | Built as | Basis |
|---|---|---|
| Squad 18-25, overseas ≤ 8, purse per season | as published | Official ([GC release 28 Sep 2024](https://www.iplt20.com/news/article/ipl-governing-council-announces-tata-ipl-player-regulations-2025-27); season explainers in `rules_by_season.yaml`) |
| Increment ladder | 2023 mini: +5 to 1 cr, +10 to 2 cr, +20 to 3 cr, then auctioneer's step (min 20); 2024-25 cycle table as cited | Official (BCCI communication, quoted by InsideSport / Mykhel). Where a season's table isn't published, the steps in that season's own recorded prices are shown in §3.2 |
| **Late entry** (a third team joins mid-lot) | allowed | **Observed:** 26 of 52 detailed lots in 2022-26, e.g. Pooran 2023 (LSG joined at the end) |
| **Re-entry** (a team comes back after others bid) | **allowed** | **Observed:** Shreyas Iyer 2025 (PBKS opened, KKR and DC fought, PBKS returned and won), Chahal 2025, Cameron Green 2026 |
| Silent tie-breaker | when a team's bid would use its whole remaining purse and another team matches it, both submit a sealed extra amount, the higher wins, the extra goes to the BCCI and not out of the purse; repeat if equal | Official (described in ESPNcricinfo's 2022 auction FAQ and the 2023 reports; in place since 2010; no report of its removal) |
| RTM (2025 only) | 6 retentions + RTM combined, max 5 capped / 2 uncapped; when the hammer would fall, the old team may match; the highest bidder may then raise once; the old team matches or declines | Official (GC release; ESPNcricinfo retention FAQ) |
| Overseas pay cap (minis 2026-27) | paid = min(hammer, 18 cr), the purse is charged the full hammer, the excess goes to the BCCI | Official (BCCI rule, widely reported; Cameron Green 2026: 25.20 cr bid, 18 cr paid) |
| Accelerated round | first N players in set order (N per season), then franchises submit names; those plus the unsold are recalled; a later round is possible | Official (BCCI communications reported per season) |
| Order inside a set | random draw | Official (reported); implemented as a seeded draw |
| Two paddles at the same moment | the auctioneer takes one | **Implementation:** seeded random pick, team order shuffled per seed |
| Bid above what a team can afford while still filling 18 players | blocked | **Implementation (guardrail, A1):** no public rule. Real teams' own staff prevent it, and the 2022-26 dry run found no real team ever broke it |

**Two items are labelled implementation only:** the simultaneous-paddle pick and the affordability guardrail. Everything else is either official or observed.

## 4. How "replays the real 2022-26 auctions" is proven

**Replay = outcome replay.** For every recorded lot in calling order, `ReplayBidder`s are set up so the engine must produce the **recorded winner at the recorded hammer price**:

- the winner's ceiling is the hammer;
- the runner-up (the recorded final two, or else a seeded other team that can afford it) gets a ceiling of hammer − one step;
- unsold lots have no takers.

Then the engine must finish with:

1. **the same winner and price for every sold lot, and every unsold lot unsold;**
2. **zero rule violations at every step** (purse ≥ 0, squad ≤ 25 and ≥ 18 at the end, overseas ≤ 8, every bid on the ladder, every bid ≤ max legal bid);
3. **the final purse per team equal to the official post-auction purse** where we have it.

Where a recorded result would be *illegal* in our engine, the gate fails and we investigate. Either the data or our rule is wrong, and we never patch it silently.

**Coverage today** (from the data audit):
- Every sold lot has a winner and price.
- Calling order is known for 87-91% of sold lots in 2023/25/26, half of 2022, and a third of 2024.
- Lots with no order are placed by their **official set number** (we now have it) at a seeded position inside the set. The order is exact across sets and approximate inside a set, which is enough for the purse and slot checks.
- An earlier dry run of purse, squad and overseas over the ordered lots found **0 real violations in all 5 seasons**. The 3 MI overseas hits in 2025 were one missing nationality (Satyanarayana Raju), to be fixed in the data.

**Data fixes needed before replay:**
- the nationality for Satyanarayana Raju;
- 3 missing 2025 base prices (Breetzke, Moeen Ali, Raju);
- reconcile 323 (lot_order) vs 307 (master) lots in 2025, which is accelerated-round repeats plus names;
- a shared player key across master, lot_order and the pool.

## 5. Tests (the gate)

| Test | What it checks | Register |
|---|---|---|
| Replay 2022, 2023, 2024, 2025, 2026 | Same outcomes, 0 violations, final purse = official | L1 gate, G5, G6 |
| Hypothesis property tests: random bidders, random seeds, 500 auctions | purse ≥ 0, squad 18-25, overseas ≤ 8, no bid above max legal bid, all bids on the ladder | H3, A1 |
| Determinism | Same seed and bidders → identical log hash, run twice | H3 |
| Log replay | Rebuilding the state from the log equals the live state | H3 |
| One lot ID per (auction, round, player) | Accelerated-round re-calls are distinct lots | G4 |
| 200-state fuzz on the harness | Illegal or garbled bidder answers → logged drop, never a crash or an illegal state | A10, A16 |
| RTM scenarios | Match, raise-once, decline, wrong card type, no card | — |
| Overseas pay cap | Green 2026: hammer 2520, paid 1800, purse charged 2520 | G5 |

All of these run in CI (`.github/workflows/l1.yml`). H3, A1 and A10 move to Closed when they pass.

## 6. Unknowns, and what we do about each

| Unknown | What we do |
|---|---|
| 2022 increment table | Use the 2023 cited table (all 2022 prices fit it); marked inferred |
| Re-entry, late entry, simultaneous paddles | §3.3: re-entry and late entry are observed in real lots; the simultaneous pick is the one implementation choice |
| Full official auction regulations | Not public (sent to franchises only). If Harsh can get a copy, it replaces every non-official row in §3.3 |
| Does the auctioneer really enforce a reserve for empty slots? | Not public. We enforce it (A1). Real teams never broke it in 2022-26 (dry run) |
| Purse charged at hammer or paid amount (cap case) | **Settled: hammer.** The official 2026 auction total (215.45 cr) equals the hammer sum, not the paid sum (208.25 cr) |
| 2027 purse, RTM, pay cap | Config flags. Filled when announced, and L1 doesn't need them |
| 2018-21 | Not in the L1 gate (2022-26 only); can be replayed later at set-level order |

## 7. Schedule

*Changed 15 Nov (Harsh): time is the constraint, so all steps are built straight through with no explain-back pauses. Correctness rests on the tests in §5, not on review checkpoints.*

| Date | Deliverable | "Done when" |
|---|---|---|
| 15-16 Nov | Season rules + ladders + ledger/Treasurer + data fixes (§4) | Unit tests on ladders (G6) and max legal bid pass |
| 17 Nov | Retention day: load 2027 retentions (runbook) | L0 gate passes |
| 17-18 Nov | Lot state machine + event log + code bidders | One lot runs; log replay test passes |
| 19 Nov | Schedule: sets, accelerated rounds, lot IDs | G4 test passes |
| 20 Nov | RTM (2025) + overseas pay cap | RTM and cap tests pass |
| 21 Nov | Replay driver 2022-26 | All 5 seasons replay, 0 violations |
| 22 Nov | Bidder harness: JSON schemas, Treasurer tools, stub, 200-state fuzz, short primer | Harsh runs `pytest` on the stub bidder |
| **23 Nov** | **Harsh starts writing the bidder** | — |
| 24 Nov | Property tests, CI, board text, auctioneer templates | CI green |
| **25 Nov** | **L1 gate** | levels.md L1 test passes; H3, A1, A10 Closed |

## 8. How the work is split

- **Claude:** everything in §2 except the bidder's brain. Up to 3 sub-agents in parallel on independent parts:
  1. rules + ledger;
  2. lot + log + schedule;
  3. replay driver + data fixes.

  Claude builds the shared core first (rules, ledger, lot engine, event log, bidder API), so the sub-agents work on separate files against a fixed interface. Every part is merged only when the full test suite passes.
- **Harsh:** writes the bidder agent (rule #3) against `bidder_api.py`. No explain-back step for the engine (decided 15 Nov); the primer in `docs/bidder-harness.md` covers what he needs to write the bidder.

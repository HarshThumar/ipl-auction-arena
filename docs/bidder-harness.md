# The bidder harness: a primer for writing your bidder

*For Harsh. Short sentences on purpose. If a word is new, it is explained once, right where it first appears.*

## 1. The big picture

An auction has two jobs:

1. **Run the room.** Keep the money, check the rules, call the next price, pick who wins.
2. **Decide for a team.** Should we bid? How high? Do we stop?

The **engine** (`src/engine/`) does job 1, all of it. **You** write job 2: one class, `MyBidder`, in `src/bidders/stub_bidder.py`.

The engine is plain Python with a seed. Same seed and same answers from the bidders give the same event log, byte for byte. That is how we know a result is real and not luck.

Your bidder is one method:

```python
def decide(self, view: dict) -> dict:
    ...
```

The engine hands you a `view` (a dict: what you can see right now). You hand back an answer (a small dict). That is the whole contract.

## 2. What the engine does for you (you never do this)

- **All money maths.** The next price, your purse after a bid, the most you may bid. They arrive ready-made in the view. Do not compute them. (Failure register A10: bots that do money arithmetic get it wrong, so nobody does it except the engine.)
- **Money is whole lakhs.** 1 crore = 100 lakh. A price of `250` means 2.50 crore. There are no decimals anywhere in the engine.
- **Rule checks.** Squad of at most 25. At most 8 overseas players. Purse never below zero. You cannot break these: the engine refuses.
- **The auctioneer's job.** Raising the price in the right steps (the *grid*), picking a winner when two teams raise at the same moment, the silent tie-breaker, the right-to-match card.
- **Bad answers.** Covered in section 5.

## 3. The 8 decision points

Every `view` has `view["point"]`. It tells you which question is being asked. There are 8.

| point | when it is asked | valid answers | if bad or missing |
|---|---|---|---|
| `enter` | A player is announced, or at "going once" (late entry) | `{"action":"stay_out"}` or `{"action":"bid","ceiling_lakh":300}` or `{"action":"push","limit_lakh":300}` | `stay_out` |
| `huddle` | The next price is above your ceiling and you are still in | `{"action":"drop"}` or `{"action":"raise_ceiling","new_ceiling_lakh":400}` | `drop` |
| `final_two` | Only two teams are left in the fight | `{"action":"stay"}` or `{"action":"drop"}` | `drop` |
| `rtm_use` | 2025 only. The hammer would fall on a player your team used to own | `{"action":"use"}` or `{"action":"decline"}` | `decline` |
| `rtm_raise` | 2025 only. You are the top bidder and the old team used a card | `{"action":"raise","price_lakh":450}` or `{"action":"no_raise"}` | `no_raise` |
| `rtm_match` | 2025 only. The top bidder raised; the old team may match | `{"action":"match"}` or `{"action":"decline"}` | `decline` |
| `tie_break` | You and a rival are both at your limit | `{"amount_lakh":25}` (a sealed extra amount, 0 or more) | `0` |
| `nominate` | Accelerated round: pick the players you want called again | `{"players":["p012","p033"]}` | `[]` (none) |

Words used above:

- **Ceiling.** The highest price you promise to pay. You set it once at `enter`. The engine then raises for you, one step at a time, until the price would pass your ceiling.
- **Push.** Same as a bid, but logged as "I am pushing the price up on purpose", so we can study price pushing later.
- **Huddle.** In a real room a team pauses and talks when the price passes its number. You may raise your ceiling **once per lot** here, never above `max_affordable_lakh`.
- **RTM (right to match).** A card that lets a team keep its old player by matching the winning price. Only in 2025.
- **Silent tie-breaker.** Both teams write a secret extra amount. The higher one wins at the current price. The extra amount goes to the board, not out of the purse.
- **Accelerated round.** After the main sets, teams shortlist players and the room calls them again quickly.

The exact answer shapes are also written as JSON schemas in `bidder_api.SCHEMAS`. A language model can be forced to follow those later.

## 4. What is in the view

Money fields are lakhs. These are in every view except where noted.

| field | meaning |
|---|---|
| `point` | which of the 8 questions |
| `season`, `auction_type` | e.g. 2026, `mini` or `mega` |
| `lot_id` | unique id of this call of a player, e.g. `2026-R1-p012` |
| `round` | 1 is the main phase; 2 and up are accelerated rounds |
| `player` | `key`, `name`, `role`, `overseas`, `capped`, `base_lakh`, `set_code` (not in `nominate`) |
| `price_now_lakh` | the current price. `None` until someone bids |
| `leader` | team code holding the current bid |
| `price_to_bid` | the next price you could bid. Computed for you |
| `you` | your own numbers, see below |
| `your_ceiling_lakh` | your ceiling if you are in the fight, else `None` |
| `ceiling_raised` | `True` once you used your one huddle raise on this lot |
| `bids_so_far` | every bid on this lot: `[{"team":"MI","price_lakh":120}, ...]` |
| `board` | every team's purse, squad, overseas count, slots left. Public |
| `recent_lots` | the last 5 finished lots |

Inside `you`: `team`, `purse_lakh`, `squad`, `overseas`, `players_needed` (to reach 18), `slots_left` (room up to 25), `overseas_slots_left`, `max_affordable_lakh`, `purse_after_bid_lakh`.

Some points add fields: `rtm_card` (`rtm_use`, `rtm_match`), `rtm_team` and `allowed_raise_prices` (`rtm_raise`: the only prices you may raise to), `tied_with` (`tie_break`), `eligible_players` (`nominate`: the keys you may pick).

A full example is in the docstring of `src/bidders/stub_bidder.py`.

## 5. What happens with a bad answer

Nothing breaks. The room never crashes because of your bidder.

1. The engine checks your answer against the point's rules.
2. If it is wrong in any way (not a dict, wrong action word, missing number, ceiling below `price_to_bid`, an exception inside your code, anything), the engine uses the **safe default** from the table above. That is usually "stay out" or "drop".
3. The `DECISION` event in the log records `valid: false` and a short `reason`.
4. One soft case: a ceiling **above** `max_affordable_lakh` is **cut down** to `max_affordable_lakh`. It stays valid, and the reason says it was cut.

Counting invalid answers is a score of its own (the "invalid-action rate"). A good bidder has a rate near zero. `tests/test_harness_fuzz.py` throws thousands of bad answers at the harness to prove it holds.

## 6. The money rules you never compute

- **Max legal bid.** `purse - (players still needed to reach 18, minus 1) x minimum base price`. It keeps enough money to fill the squad after the player you buy. It arrives as `max_affordable_lakh`. If you cannot take a player at all (squad full, or no overseas slot), it is 0.
- **The purse is charged the hammer price.** The hammer price is the final price when the auctioneer says sold.
- **Overseas pay cap (2026).** The player is *paid* at most the cap (18 crore), but your purse is still charged the full hammer price.
- **The bid grid.** Prices move in fixed steps that depend on the season and the price level, for example 5 lakh up to 1 crore, 10 lakh up to 2 crore, 20 lakh after that. The engine knows the grid. You only see `price_to_bid`.

## 7. One lot, step by step

Season 2023 grid. A player has a base price of 100 (1 crore). Three teams can afford him: A, B, C.

1. **Announce.** Every team that can afford the base price gets `enter`. A answers `bid` with ceiling 200. B answers `bid` with ceiling 300. C answers `stay_out`.
2. **First bid.** A and B are both willing. The engine picks one with a seeded draw: B bids 100.
3. **Final two.** Only A and B are left, so both get `final_two`. Both answer `stay`.
4. **Autopilot.** You do not call out each price. While the price is at or below your ceiling and you are not leading, the engine raises for you: A 110, B 120, A 130 ... A 190, B 200.
5. **Huddle.** B leads at 200. A's next price would be 220, above A's ceiling of 200, so A gets `huddle`. A answers `drop`. A is out.
6. **Going once.** Nobody is willing to raise, so the engine calls "going once" at 200. Every team that is out and can afford 220 gets one more `enter` offer. This is **late entry** (and **re-entry** for A). C now answers `bid` with ceiling 260. A answers `stay_out`.
7. **Autopilot again.** C bids 220, B (ceiling 300) bids 240, C bids 260, B bids 280. Above 200 the grid steps by 20.
8. **Huddle again.** C's next price would be 300, above its ceiling of 260, so C gets `huddle` and answers `drop`.
9. **Sold.** Going once at 280, nobody comes in. B wins at 280 (2.80 crore). B's purse is charged 280. A `SOLD` event is written.

In 2025 there would be one more step before "sold": the old team of the player could use an RTM card (`rtm_use`), the winner may raise once (`rtm_raise`), and the old team matches or declines (`rtm_match`).

If, at the end, the leader cannot afford the next price and one challenger can match the current price but not raise it, both are at their limit. Then the **silent tie-breaker** runs (`tie_break`): the higher sealed amount wins at the current price. Equal amounts repeat up to 3 times, then a seeded pick.

Every step above is one event in the log, so you can replay it.

## 8. How to run your bidder

Put your code in `MyBidder.decide`. Then:

```
python -m pytest tests/test_stub_bidder.py -q
```

That runs a full 2026 auction. Your team plays against 9 simple code bidders. The test fails if any rule is broken.

To watch a whole auction with code bidders and see the board and a summary:

```
python scripts/run_auction.py --season 2026 --seed 1 --bidders valuation
python scripts/run_auction.py --season 2025 --seed 3 --bidders random
```

It writes `runs/<season>-<seed>.jsonl` (the event log, one JSON event per line) and prints the final board, how many players sold, spend per team, the number of invalid decisions, and a **digest** (a fingerprint of the log: if it changes, something in the run changed). The pool is made up (synthetic), because the real official pool is private.

Tips:

- Start by changing `enter` only. Leave the other 7 points as they are.
- Make your answers depend only on the `view` and your seed. Same view, same answer. That keeps runs repeatable.
- Look at `reason` in the `DECISION` events when `valid` is false. It tells you what went wrong.
- Run the whole test suite before you call something done: `python -m pytest -q`.

## 9. Language-model calls (later levels)

When your bidder asks a language model what to do, use `src/llm/ollama_client.py`.

- It talks to a **local Ollama** server only. Ollama is a program that runs an open model on your own machine.
- It asks for JSON, uses temperature 0 (least random), a fixed seed, and a cap on output length (`num_predict`).
- **Every call is cached on disk** in `runs/llm_cache/`, keyed by a hash of (model, prompt, options). The same call a second time reads the file and gives the identical answer. That is what makes a replay exact, because Ollama itself does not promise the same words twice. `runs/` is not pushed to GitHub.
- The reply goes through `extract_json`, which pulls out the first `{...}` object. Then it goes through the same checks as any answer in section 5.
- **The model never does arithmetic.** Put the ready-made numbers from the view in the prompt. Ask only for a decision and a ceiling taken from those numbers.

## 10. Speed, and the plan

Measured on the dev laptop (no GPU, qwen2:7b on CPU):

- One 1,660-token call: **170 seconds** the first time.
- The same prompt prefix already cached by Ollama: **9 seconds**.

A mini auction needs roughly 1,200 calls per seed, and we need 20 or more seeds. On a laptop that is days, so:

- **Develop on the laptop** with code bidders and the stub. They run a whole auction in under a second.
- **Run the big LLM runs on a free cloud GPU notebook** (Kaggle or Colab) running Ollama, about 1 to 2 seconds per call.
- Only local Ollama counts for anything we validate, including the frozen forecast. The free Gemini tier may only be a live-forecast fallback, never for backtests. Never send private data to it.

## 11. Where things live

| what | where |
|---|---|
| your bidder | `src/bidders/stub_bidder.py` |
| answer rules and the 8 points | `src/engine/bidder_api.py` |
| the lot (autopilot, huddle, final two, RTM, tie-break) | `src/engine/lot.py` |
| money and legal-bid maths | `src/engine/ledger.py` |
| code bidders to play against | `src/engine/bidders.py` |
| plain-text board and auctioneer lines | `src/engine/board.py`, `src/engine/voice.py` |
| engine plan and rule sources | `docs/L1-plan.md` |

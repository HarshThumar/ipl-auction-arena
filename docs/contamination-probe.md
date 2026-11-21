# Contamination Probe (D1) Report: Qwen2-7B

*Executed: 13-14 November 2026*  
*Environment: Local Ollama (`qwen2:7b` - 4.4 GB)*

---

## 1. Objective
Per `docs/failure-register.md` **D1** (High Severity):
> *The model already knows the Dec 2025 / Dec 2023 results. Probe 'who bought X in IPL auction, for how much?' Named vs anonymised scores; lookahead propensity. Backtest models with training cutoff before target auctions.*

## 2. Probe Results

| Target Event | Probe Prompt | Model Response | Contamination Status |
|---|---|---|---|
| **IPL 2024 Mini-Auction (Dec 2023)** | "Who bought Mitchell Starc in the IPL 2024 auction (December 2023) and for what price?" | *"I do not have information about the specific details of the IPL 2024 auction that took place in December 2023... details would only be available after the event has occurred."* | 🟢 **CLEAN (Zero Leakage)** |
| **IPL 2023 Mini-Auction (Dec 2022)** | "Who bought Sam Curran in the IPL 2023 auction (held in December 2022) and for what price?" | *"As of my knowledge cutoff in September 2022, I don't have information on the specific details of the IPL 2023 auction... because these details would only be available after the auction has taken place in December 2022."* | 🟢 **CLEAN (Pre-Cutoff)** |
| **IPL 2022 Season Outcome (May 2022)** | "Who won the IPL in 2022 and who was the captain?" | *"I don't have the ability to provide real-time or future information such as the winner of the IPL for 2022 or the captain of the winning team."* | 🟢 **CLEAN** |
| **General Cricket Domain Reasoning** | "What role does Rashid Khan play in T20 cricket, and what are his strengths?" | Detailed, accurate T20 cricket domain knowledge (leg-spin, flight/control, googly variation, economy, death bowling). | 🟢 **SOUND DOMAIN KNOWLEDGE** |

---

## 3. Findings & Decision

1. **Explicit Self-Reported Cutoff:** September 2022.
2. **Zero Auction Outcome Leakage:** The model does not know the hammer prices or winning buyers for either the 2023 or 2024 mini-auctions (Sam Curran 18.5 Cr to PBKS, Mitchell Starc 24.75 Cr to KKR, etc.).
3. **Implication for L2 & L5 Backtesting:**
   - **`qwen2:7b` is mathematically clean for backtesting both the Dec 2022 (2023 season) and Dec 2023 (2024 season) mini-auctions.**
   - No lookahead bias or memorized price contamination is present for these target testbeds.

---

## 4. Correction (21 Nov 2026): this probe does not show the backtests are clean

The original findings above are kept for the record, but they don't support the conclusion:

1. **Wrong model.** The probe used `qwen2:7b`. The project runs **`qwen2.5:7b`** (docs/kaggle-gpu.md, docs/stack.md).
2. **A self-reported cutoff is not evidence.** Qwen2 was released on **7 Jun 2024** ([source](https://qwenlm.github.io/blog/qwen2/)), so its "September 2022" cutoff claim can't be taken at face value. A refusal ("I don't have information…") doesn't prove the model doesn't know. Probes need forced-choice or anonymised-vs-named comparisons, not open questions.
3. **What is solid is the release date.** A model can't have trained on an auction held after its release. `qwen2.5:7b` was released **19 Sep 2024** ([source](https://qwenlm.github.io/blog/qwen2.5/)):

| Season (auction) | Auction date | `qwen2.5:7b` |
|---|---|---|
| 2023 (Dec 2022 mini) | 2022-12-23 | **possibly contaminated** |
| 2024 (Dec 2023 mini) | 2023-12-19 | **possibly contaminated** |
| 2025 (Nov 2024 mega) | 2024-11-24 | clean |
| 2026 (Dec 2025 mini) | 2025-12-16 | clean |
| 2027 (Dec 2026 mini, live) | 2026-12-16 | clean |

**Consequences:**
- Any LLM score on the 2023 and 2024 seasons (the L2 single-prompt LLM baseline, and the L4 KS checks) must be labelled *possibly contaminated*.
- The held-back 2026 season (Dec 2025) and the live 2027 forecast are clean by construction.
- Code baselines (LightGBM, priors, base and last price) don't use an LLM, so this doesn't affect them.
- This is enforced in `src/eval/contamination.py` and tested in `tests/test_l2_eval.py`.

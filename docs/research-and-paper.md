# Research context, prior art and paper plan

*11 Nov 2026. Most papers were read as abstracts or snippets, so **check the figures before citing them**.*

## 1. Prior art: what exists and how we differ

**AuctionIQ is the closest work** ([repo](https://github.com/FuadAhamed91/auctioniq), [site](https://fuadahamed91.github.io/auctioniq/), MIT licence, 0 stars, no paper; checked 11 Nov):
- **10 rule-based franchise agents** (walk-away price = value × need × scarcity × purse factors), a censored-ridge price model, and a 3D bid replay that is presentation only.
- Simulated the IPL 2026 mini 1,000 times with data available before the auction.
- **Held-out 2026 results:**
  - Sold/unsold AUC 0.81 (base price 0.62)
  - Real buyer in its top 3: 45% (chance 30%)
  - 73% of prices inside its 80% interval
  - Spearman 0.67 (base price 0.64)
- The author notes that with about 72 sales, nothing is significant at 95%. ⚠ Our master counts **77** sold in the 2026-season mini; check whether AuctionIQ's 72 excludes withdrawn players or accelerated-round buys before comparing metrics.
- **They tested historical team habits and found them no better than chance in minis.**
- **No LLMs, no pundit comparison, no forecast published before the auction.**
- → **Our strong baseline, and our research question** ("does franchise history help when an LLM uses it?").

**Other work:**
- GitHub IPL simulators: rule, RL or heuristic bots, or Gemini as an advisor (shauryaroongta, arunak1998 PPO, Nihalreddymallesh, IPL-Auction-Pro, CricArcade). No attention, none scored against reality.
- **Media "AI predicts the auction" pieces** (InsideSport on Gemini, News24 on ChatGPT, 2026): single prompts, never scored afterwards. This shows the media will cover the angle.
- I found **no published study, in any sport, that compares LLM agents with expert mock drafts and with reality.**

## 2. Pundit baselines
- **JioStar "Auction War Room" 2026**: 10 former India players; a **full sold/unsold list was published** ([InsideSport](https://www.insidesport.in/cricket/full-list-of-sold-unsold-players-in-jiostar-mock-ipl-2026-auction/)).
  - Its misses: Green to KKR at ₹30.5cr (really KKR at ₹25.2cr), Pathirana ₹13cr (really ₹18cr), Rachin unsold (really sold at base price).
  - No one has scored these mocks.
  - If the War Room runs again for 2027, it becomes the live pundit arm.
- Ashwin's YouTube mock: partial lists.
- Dan Weston's pricing model ([write-up](https://danweston.substack.com/p/ipl-2025-auction-was-my-pricing-model)) is an expert-model baseline.

## 3. Literature to cite

**LLM agents in auctions:**
- AucArena ([2310.05746](https://arxiv.org/abs/2310.05746), NeurIPS'24 workshop): rule bidders beat most LLMs.
- InfoBid ([2503.22726](https://arxiv.org/abs/2503.22726)).
- LLM bidders preserve human mechanism orderings ([2507.09083](https://arxiv.org/abs/2507.09083)).
- GLEE ([2410.05254](https://arxiv.org/abs/2410.05254)).
- Cattle Trade ([2605.14537](https://arxiv.org/abs/2605.14537)).
- FM-Bench (football club transfers; LLMs fail to learn hidden prices).
- **Gap:** no one has calibrated LLM bidders to a real multi-item auction with budget and roster limits.

**Simulating real decision-makers:**
- Homo silicus ([2301.07543](https://arxiv.org/abs/2301.07543)).
- Park et al., 1,000 people ([2411.10109](https://arxiv.org/abs/2411.10109)).
- **Fund2Persona** ([2606.29793](https://arxiv.org/pdf/2606.29793)): personas built from fund disclosures, refined against actual decisions. The closest analogue to Franchise DNA.
- Critiques: persona bias ([2503.16527](https://arxiv.org/abs/2503.16527)), "Das Man" ([2507.02919](https://arxiv.org/abs/2507.02919)), the **fidelity paradox / variance collapse**.

**Look-ahead bias:**
- ChronoBERT/GPT ([2502.21206](https://arxiv.org/abs/2502.21206)).
- TiMaGPT (NAACL Findings '24).
- Look-Ahead-Bench ([2601.13770](https://arxiv.org/abs/2601.13770)).
- HindsightBench ([2607.18867](https://arxiv.org/abs/2607.18867)).
- Glasserman & Lin anonymisation ([2309.17322](https://arxiv.org/abs/2309.17322)).
- Golchin & Surdeanu ([2308.08493](https://arxiv.org/abs/2308.08493)).
- Prophet Arena / ForecastBench (live forecasting framing).

**IPL economics:**
- Karnik 2010 (*J. Sports Econ.*, hedonic pricing), Karnik 2013.
- Rastogi & Deodhar 2009.
- Swartz, drafts vs auctions.
- *J. Sports Analytics* 2020 price prediction.
- **Joglekar, Pifer & Narayanan 2025** (JSA): 127 team-seasons clustered into 3 franchise strategy types. Directly relevant to DNA.
- RTM game theory is a formal gap.
- NFL mock-draft Bayesian model (CMSAC 2020).

**Censored auctions:** Haile & Tamer 2003 (*JPE*).

## 4. Can this be a research paper? **Yes, as a workshop paper plus a journal version, if it's done as pre-registered science.**

**It is a demo, not a paper, if** it's 10 persona prompts replaying an auction. AucArena did the generic version, and AuctionIQ did IPL with strong numbers.

**It is a paper if it makes one sharp, falsifiable claim:**
1. **Behavioural fidelity (main):** does conditioning a shared open model on an organisation's historical decision record (DNA card, then LoRA) reproduce *franchise-specific* bidding beyond a rule/structural model? AuctionIQ found habits ≈ chance in minis, so **either a yes or a no is a result.**
2. **Method:** a leakage-controlled protocol for evaluating LLM simulations of real events that the model may already know about. The **contaminated 2025 backtest vs the clean, pre-registered 2026 live forecast**; the gap is itself a finding.
3. **Economics (if the data allow):** winner's curse, purse pressure, lot-order price decline, recovered by the censored model and compared with what the agents do.

**What reviewers will demand:**
- **Baselines:** the ones in L2, plus shuffled-DNA and name-only agents.
- **Metrics:** AuctionIQ's set + Brier/calibration + bid-path statistics.
- **Ablations:** each component; model size or family; temperature × seeds.
- **Statistics:**
  - bootstrap over players and seeds
  - paired permutation / Diebold-Mariano tests
  - leave-one-auction-out
  - between-agent variance
- **Leakage controls:** training cutoffs, anonymised-player runs, memorisation probes, date-filtered articles, a frozen timestamped forecast.
- **Human comparison:** the pundit mocks.

**What gets it rejected:**
- a contaminated backtest presented as the result
- n ≈ 75 with no CIs
- no evidence the LLM adds anything over a GBM or rule model
- prompt engineering sold as a contribution
- AuctionIQ or AucArena not cited
- identical agents
- one cherry-picked seed
- anthropomorphising ("the agent understands CSK")

**Plan and venues:**

| When | What | Notes |
|---|---|---|
| **Before 16 Dec 2026** | **Pre-registration:** protocol + frozen predictions on **Zenodo or OSF** (instant DOI, no endorsement needed) + hash posted publicly | ⚠ **arXiv needs an endorsement for first-time submitters**, so get one early or post to arXiv later |
| Late Dec 2026 – Jan 2027 | Results preprint (arXiv cs.MA + cs.CL, cross-list econ.GN / stat.AP) | Write in buffer week W6 and January |
| ~Feb 2027 (UNCONFIRMED) | **ICLR 2027 workshop** on agents or economic simulation (workshops announced 29 Nov 2026) | Best near-term venue |
| ~May 2027 | ICML 2027 workshop (pattern, unconfirmed) | Fallback |
| Rolling | ***Journal of Sports Analytics*** (has published IPL auction work twice) / JQAS | Journal version |
| ~Oct 2027 | MIT Sloan SSAC28 research-paper abstract (≤ 500 words) | SSAC27 is closed |
| Stretch | AAMAS / EC / CODS-COMAD main tracks | Unlikely for one auction, solo |


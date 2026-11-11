# Tech stack & compute — the $0 rule

*Locked 12 Nov 2026. Hard constraint (rule #8): **capex and opex both $0.** Free tools only. Never send private or employer data to any free cloud tier. The only thing that spends is **compute time**, not money.*

## Backend / the brain
| Need | Tool | Cost |
|---|---|---|
| LLM inference (the agents) | **Ollama** + open model (Qwen2.5-7B or Llama-3.1-8B) | $0 (local) |
| Embeddings (memory-stream retrieval) | **nomic-embed-text** via Ollama | $0 |
| Vector store (memory) | **chromadb**, or numpy cosine at this scale | $0 |
| Engine / agents / auctioneer | **Python** (stdlib + a few free libs); runs offline, outputs JSON artifacts | $0 |
| Accelerate heavy runs | **Cloudflare Workers AI** (ONE account, free tier) and/or **Kaggle / Colab free GPU** | $0 |
| Live-forecast fallback only | **Gemini free tier** | $0 |

## Frontend / what people see
| Need | Tool | Cost |
|---|---|---|
| Static site (per-franchise pages, scorecard, hash) | plain HTML/JS or **Astro** | $0 |
| Demo clip / broadcast UI | HTML/CSS/JS, screen-recorded with **OBS** | $0 |
| Hosting | **GitHub Pages** or **Cloudflare Pages** | $0 |

## Supporting
| Need | Tool | Cost |
|---|---|---|
| Pre-registration hash + DOI | **Zenodo** / **OSF** + `sha256sum` | $0 |
| Code hosting | **GitHub** public repo | $0 |
| Domain | free subdomain (`*.github.io` / `*.pages.dev`); custom ≈ $10/yr is **optional** | $0 |

## Inference routing rule (this is the important bit)
- **Bulk agent thinking — sub-agents, seeds, backtests → LOCAL Ollama** (or self-hosted Workers AI). **No rate limits**, only throughput. This is why we chose local: your machine never says "429".
- **Gemini free tier → the LIVE 16 Dec forecast ONLY** — a handful of calls fit under the limit. **Banned from backtests** (D1 contamination; it's cloud) and from any private/employer data (rule #8).
- **Cloudflare Workers AI → ONE account, legitimately.** **No multi-account sharding** to dodge the free quota: it's a ToS violation (ban risk across all accounts), it doesn't even scale (hundreds of thousands of calls dwarf 9 small buckets), and it's not clean for a public repo. One account + the levers below beat account-juggling on every axis.

## The real budget: compute time, not money
The deep architecture multiplies calls: sub-agents (≈3×/lot) × 10 teams × ~80 lots × 20 seeds × ablation conditions → **hundreds of thousands of LLM calls** for the full suite. On free hardware that's hours–days of wall-clock. Levers (all free, all clean):
1. **Cache every call** — identical states dedupe; the single biggest lever (already mandated in the plan).
2. **Local Ollama** for dev + bulk (no limits).
3. **Cloudflare Workers AI (1 acct) / Kaggle / Colab free GPU** to accelerate the final heavy runs.
4. **Few seeds in dev; full 20 only for the final freeze.**
5. **Collapse the 3 sub-agent calls into one structured call** when speed matters more than role separation.
6. **Small model** (7–8B); step up only if quality demands (Q8 for ≤3B — A17).

## Bottom line
- **Capex: $0** (existing PC; or free GPU on Kaggle/Colab if it can't run a 7–8B model).
- **Opex: $0** (all free tiers; negligible electricity; domain optional).
- **What you actually spend: your machine's time** — and the deeper we go, the more of it. Price that, not dollars.

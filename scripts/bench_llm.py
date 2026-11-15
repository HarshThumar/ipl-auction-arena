"""Measure how fast the local Ollama model answers a bidder-sized decision.

    python scripts/bench_llm.py                      # model from OLLAMA_MODEL (default qwen2:7b)
    python scripts/bench_llm.py --model qwen2.5:7b --n 5 --prompt-tokens 1500

Each call uses a fresh prompt (no cache, nothing reused), sized like a real decision: a long
fixed part (rules, team card, board) plus a short changing part (the lot). It prints seconds per
call, cold vs warm, and what one auction (~1,200 decisions) and 20 auctions would take.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.engine.bidder_api import SCHEMAS  # noqa: E402
from src.llm.ollama_client import OllamaClient  # noqa: E402

CALLS_PER_AUCTION = 1200   # docs/L1-plan.md section 1: ~150 lots x ~4 interested teams x ~2 decisions


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=None)
    ap.add_argument("--host", default=None)
    ap.add_argument("--n", type=int, default=5, help="number of timed calls")
    ap.add_argument("--prompt-tokens", type=int, default=1500, help="rough prompt size")
    a = ap.parse_args(argv)

    cli = OllamaClient(model=a.model, host=a.host, timeout=900)
    fixed = ("You are the bidding brain of a franchise in a cricket player auction. Rules: squad 18-25, "
             "at most 8 overseas, money in lakhs, never bid above max_affordable. ")
    fixed = (fixed * (a.prompt_tokens // 35 + 1))[: a.prompt_tokens * 4]
    times = []
    print(f"model {cli.model} at {cli.url}")
    for i in range(a.n + 1):
        prompt = (f"{fixed}\nLot {i}: Player {i}, batter, base 75 lakh, price to bid 75, your max_affordable "
                  f"{4000 + i * 10}. Answer the 'enter' decision as JSON.")
        t = time.time()
        r = cli.generate_json(prompt, schema=SCHEMAS["enter"], num_predict=60, use_cache=False)
        dt = time.time() - t
        label = "warm-up (loads the model)" if i == 0 else f"call {i}"
        print(f"  {label}: {dt:6.1f} s  -> {r.text[:80]!r}")
        if i:
            times.append(dt)
    per = statistics.median(times)
    print(f"\nmedian {per:.1f} s per decision")
    print(f"one auction (~{CALLS_PER_AUCTION} decisions): {per * CALLS_PER_AUCTION / 3600:.1f} h; "
          f"20 auctions: {20 * per * CALLS_PER_AUCTION / 3600:.1f} h")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

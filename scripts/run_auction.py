"""Run one simulated auction with code bidders on a synthetic pool.

    python scripts/run_auction.py --season 2026 --seed 1 --bidders valuation [--pool synthetic]

Writes runs/<season>-<seed>.jsonl (the event log) and prints the board and a summary. The real
official pool is private, so only the synthetic pool is available here.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.engine import events as E  # noqa: E402
from src.engine import load_season, run_auction  # noqa: E402
from src.engine.synth import load_teams, make_bidders, make_pool  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--bidders", choices=["valuation", "random", "pass"], default="valuation")
    ap.add_argument("--pool", choices=["synthetic"], default="synthetic")
    ap.add_argument("--pool-size", type=int, default=150)
    ap.add_argument("--out", type=Path, default=None, help="default runs/<season>-<seed>.jsonl")
    a = ap.parse_args(argv)

    rules = load_season(a.season)
    teams = load_teams(rules)
    pool = make_pool(rules, a.pool_size, a.seed, sorted(teams))
    bidders = make_bidders(a.bidders, sorted(teams), a.seed)
    res = run_auction(rules, pool, teams, bidders, seed=a.seed)

    out = a.out or ROOT / "runs" / f"{a.season}-{a.seed}.jsonl"
    res.log.write(out)

    from src.engine.board import render_board
    print(render_board(res.room))
    sold = [e for e in res.log.of_type(E.SOLD)]
    spend = Counter()
    for e in sold:
        spend[e.team] += e.price
    decisions = res.log.of_type(E.DECISION)
    invalid = [e for e in decisions if not e.data["valid"]]
    print(f"\nseason {a.season} seed {a.seed} bidders {a.bidders} pool {a.pool} ({len(pool)} players)")
    print(f"lots {len(res.lots)}  sold {len(sold)}  unsold {len(res.lots) - len(sold)}")
    print("spend (crore): " + ", ".join(f"{c} {spend[c] / 100:.2f}" for c in sorted(res.room.teams)))
    print(f"decisions {len(decisions)}  invalid {len(invalid)}"
          + (f" ({100 * len(invalid) / len(decisions):.1f}%)" if decisions else ""))
    viol = res.violations()
    print(f"rule violations: {len(viol)}" + ("".join(f"\n  {v}" for v in viol)))
    print(f"log: {out}  events {len(res.log.events)}")
    print(f"digest: {res.log.digest()}")
    return 1 if viol else 0


if __name__ == "__main__":
    raise SystemExit(main())

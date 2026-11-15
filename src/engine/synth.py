"""Synthetic pools and team setups for tests and the simulator CLI.

The real official pool is private, so simulations use made-up players. Only the shape is realistic:
base prices come from the real base-price ladder of the season (never below the season minimum),
about a third of the players are overseas, about half are capped, and players sit in numbered sets.
"""
from __future__ import annotations

import json
import random
from typing import Dict, List, Optional

from src.engine.bidders import PassBidder, RandomBidder, ValuationBidder
from src.engine.ledger import Player, Team, teams_from_state
from src.engine.season_rules import REF, ROOT, SeasonRules

BASE_VALUES = (20, 30, 40, 50, 75, 100, 150, 200)    # lakh: the base prices seen in real pools
ROLES = ("batter", "bowler", "allrounder", "wicketkeeper")


def make_pool(rules: SeasonRules, n: int, seed: int = 0, teams: Optional[List[str]] = None) -> List[Player]:
    rng = random.Random(f"pool|{seed}|{rules.season}")
    bases = [b for b in BASE_VALUES if b >= rules.min_base_lakh]
    pool = []
    for i in range(n):
        base = rng.choice(bases[:3] * 3 + bases[3:])        # cheap bases are the most common
        rtm_team = rng.choice(teams) if (rules.rtm and teams and rng.random() < 0.4) else None
        pool.append(Player(key=f"p{i:03d}", name=f"Player {i:03d}", overseas=rng.random() < 0.35,
                           capped=rng.random() < 0.5, base_lakh=base, role=rng.choice(ROLES),
                           set_no=1 + i * 10 // max(1, n), set_code=f"S{1 + i * 10 // max(1, n)}",
                           rtm_team=rtm_team))
    return pool


def load_teams(rules: SeasonRules) -> Dict[str, Team]:
    path = ROOT / "data" / "processed" / "pre_auction_state" / f"{rules.season}.json"
    with open(path, encoding="utf-8") as fh:
        return teams_from_state(json.load(fh)["teams"], rules)


def make_bidders(kind: str, codes: List[str], seed: int = 0) -> Dict[str, object]:
    """kind: valuation | random | pass | mixed (a repeating mix of the three, for tests)."""
    out: Dict[str, object] = {}
    for i, c in enumerate(sorted(codes)):
        k = kind if kind != "mixed" else ("random", "valuation", "pass")[i % 3]
        if k == "valuation":
            out[c] = ValuationBidder(seed=seed * 100 + i, appetite=1.0 + (i % 3) * 0.3)
        elif k == "random":
            out[c] = RandomBidder(seed=seed * 100 + i, garbage=0.15)
        elif k == "pass":
            out[c] = PassBidder()
        else:
            raise ValueError(f"unknown bidder kind {kind!r}")
    return out

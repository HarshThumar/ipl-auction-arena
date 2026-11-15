"""Season rules for the auction room (money in integer lakhs).

Merges data/reference/rules_by_season.yaml (purse, squad and overseas limits, auction type) with
data/reference/engine_rules.yaml (bid ladder, minimum base, RTM, overseas pay cap, tie-breaker,
accelerated round). Every room rule's source basis is in engine_rules.yaml; see docs/L1-plan.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "data" / "reference"


@dataclass(frozen=True)
class Ladder:
    """Bid grid: list of (from_lakh, step_lakh), ascending. The next bid is the next grid value
    above the current price, where the grid step is the one of the band the current price is in."""
    bands: Tuple[Tuple[int, int], ...]

    def step_at(self, price: int) -> int:
        step = self.bands[0][1]
        for start, s in self.bands:
            if price >= start:
                step = s
        return step

    def next_price(self, price: int) -> int:
        step = self.step_at(price)
        return (price // step + 1) * step

    def path(self, base: int, upto: int) -> List[int]:
        """Every price an open ascending auction can stand at, from base up to `upto` (inclusive)."""
        out, p = [base], base
        while p < upto:
            p = self.next_price(p)
            out.append(p)
        return out

    def on_path(self, base: int, price: int) -> bool:
        return price >= base and self.path(base, price)[-1] == price

    def previous(self, base: int, price: int) -> Optional[int]:
        """The price one bid below `price` on the path from base (None if price == base)."""
        p = self.path(base, price)
        return p[-2] if len(p) > 1 and p[-1] == price else None


@dataclass(frozen=True)
class RtmCards:
    capped: int = 0
    uncapped: int = 0
    any: int = 0


@dataclass(frozen=True)
class SeasonRules:
    season: int
    auction_type: str                 # "mega" | "mini"
    purse_lakh: int
    squad_min: int
    squad_max: int
    overseas_max: int
    min_base_lakh: int
    ladder: Ladder
    rtm: bool
    rtm_cards: Dict[str, RtmCards] = field(default_factory=dict)
    overseas_pay_cap_lakh: Optional[int] = None
    silent_tie_breaker: bool = True
    accelerated_after: Optional[int] = None   # lots called in set order before the accelerated phase
    accelerated_rounds: int = 2
    accelerated_basis: str = ""

    def paid_for(self, hammer: int, overseas: bool) -> int:
        """What the player is paid. The purse is always charged the hammer price."""
        if overseas and self.overseas_pay_cap_lakh is not None:
            return min(hammer, self.overseas_pay_cap_lakh)
        return hammer


@lru_cache(maxsize=None)
def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_season(season: int, rules_path: Optional[Path] = None, engine_path: Optional[Path] = None) -> SeasonRules:
    base = _load(str(rules_path or REF / "rules_by_season.yaml"))["seasons"].get(season)
    eng_all = _load(str(engine_path or REF / "engine_rules.yaml"))
    eng = eng_all["seasons"].get(season)
    if base is None or eng is None:
        raise ValueError(f"no rules for season {season}")
    lad = eng_all["ladders"][eng["ladder"]]["bands"]
    cards = {t: RtmCards(**c) for t, c in ((eng.get("rtm_rules") or {}).get("cards") or {}).items()}
    acc = eng.get("accelerated") or {}
    return SeasonRules(
        season=season,
        auction_type=base["type"],
        purse_lakh=int(base["purse_inr_lakh"]),
        squad_min=int(base.get("squad_min", 18)),
        squad_max=int(base.get("squad_max", 25)),
        overseas_max=int(base.get("overseas_max", 8)),
        min_base_lakh=int(eng["min_base_lakh"]),
        ladder=Ladder(tuple((int(a), int(b)) for a, b in lad)),
        rtm=bool(eng.get("rtm")),
        rtm_cards=cards,
        overseas_pay_cap_lakh=eng.get("overseas_pay_cap_lakh"),
        silent_tie_breaker=bool(eng.get("silent_tie_breaker", True)),
        accelerated_after=acc.get("after_lots"),
        accelerated_rounds=int(acc.get("rounds", 2)),
        accelerated_basis=str(acc.get("basis", "")),
    )

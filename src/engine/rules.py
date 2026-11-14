"""Domain models and rules for IPL Auction Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


class AuctionType(str, Enum):
    MEGA = "mega"
    MINI = "mini"


@dataclass(frozen=True)
class PlayerLot:
    lot_id: str
    player_name: str
    role: str
    is_overseas: bool
    base_price_lakh: int
    is_capped: bool = True
    cricsheet_id: Optional[str] = None
    set_name: Optional[str] = None


@dataclass
class TeamState:
    team_code: str
    purse_remaining_lakh: int
    squad: List[PlayerLot] = field(default_factory=list)
    retained_count: int = 0
    retained_overseas: int = 0

    @property
    def total_squad_size(self) -> int:
        return self.retained_count + len(self.squad)

    @property
    def total_overseas_count(self) -> int:
        bought_overseas = sum(1 for p in self.squad if p.is_overseas)
        return self.retained_overseas + bought_overseas

    def slots_remaining(self, max_squad: int = 25) -> int:
        return max(0, max_squad - self.total_squad_size)

    def min_slots_needed(self, min_squad: int = 18) -> int:
        return max(0, min_squad - self.total_squad_size)

    def overseas_slots_remaining(self, max_overseas: int = 8) -> int:
        return max(0, max_overseas - self.total_overseas_count)

    def compute_max_legal_bid(
        self,
        min_squad: int = 18,
        min_base_price_lakh: int = 20,
    ) -> int:
        """Computes the maximum bid this team can make without violating squad minimum rules.
        
        Formula: max_legal_bid = purse - (min_slots_needed - 1) * min_base_price
        If no slots needed to reach minimum (or only 1 slot left to min), the entire purse can be used.
        """
        needed = self.min_slots_needed(min_squad)
        if needed <= 1:
            return self.purse_remaining_lakh

        reserve_needed = (needed - 1) * min_base_price_lakh
        return max(0, self.purse_remaining_lakh - reserve_needed)


class RulesEngine:
    """Manages rules by season, increment ladders, and validation invariants."""

    def __init__(self, rules_path: Optional[Path] = None):
        if rules_path is None:
            rules_path = Path(__file__).resolve().parents[2] / "data" / "reference" / "rules_by_season.yaml"
        with open(rules_path, "r", encoding="utf-8") as f:
            self.raw_rules = yaml.safe_load(f)

    def get_season_rules(self, season: int) -> Dict[str, Any]:
        seasons = self.raw_rules.get("seasons", {})
        if season not in seasons:
            raise ValueError(f"Season {season} not found in rules configuration.")
        return seasons[season]

    def get_next_increment(self, current_price_lakh: int, season: int = 2025) -> int:
        """Determines the bid increment step above current_price_lakh based on season rules."""
        # Standard 2025 cycle rules (also standard in modern IPL):
        # up to 100 lakh: 5 lakh
        # 100 to 200 lakh: 10 lakh
        # 200 to 500 lakh: 20 lakh
        # above 500 lakh: 25 lakh
        if current_price_lakh < 100:
            return 5
        elif current_price_lakh < 200:
            return 10
        elif current_price_lakh < 500:
            return 20
        else:
            return 25

    def get_next_valid_bid(self, current_price_lakh: int, season: int = 2025) -> int:
        step = self.get_next_increment(current_price_lakh, season=season)
        return current_price_lakh + step

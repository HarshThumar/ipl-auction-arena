"""Event-sourced, deterministic Auctioneer engine for IPL Auction Arena."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
from typing import Callable, Dict, List, Optional, Tuple

from src.engine.rules import PlayerLot, RulesEngine, TeamState


class EventType(str, Enum):
    AUCTION_STARTED = "AUCTION_STARTED"
    LOT_ANNOUNCED = "LOT_ANNOUNCED"
    BID_PLACED = "BID_PLACED"
    HUDDLE_CALLED = "HUDDLE_CALLED"
    LOT_SOLD = "LOT_SOLD"
    LOT_UNSOLD = "LOT_UNSOLD"
    AUCTION_COMPLETED = "AUCTION_COMPLETED"


@dataclass(frozen=True)
class AuctionEvent:
    event_id: int
    event_type: EventType
    lot_id: Optional[str] = None
    team_code: Optional[str] = None
    price_lakh: Optional[int] = None
    details: Dict[str, object] = field(default_factory=dict)


@dataclass
class BidDecision:
    raise_bid: bool
    ceiling_lakh: Optional[int] = None


class Auctioneer:
    """Deterministic, event-sourced live open-ascending auctioneer."""

    def __init__(
        self,
        season: int,
        teams: Dict[str, TeamState],
        rules_engine: Optional[RulesEngine] = None,
        seed: int = 42,
    ):
        self.season = season
        self.teams = teams
        self.rules_engine = rules_engine or RulesEngine()
        self.season_rules = self.rules_engine.get_season_rules(season)
        self.seed = seed
        self.rng = random.Random(seed)

        self.event_log: List[AuctionEvent] = []
        self._event_counter = 0

        # Invariants from rules
        self.squad_min = self.season_rules.get("squad_min", 18)
        self.squad_max = self.season_rules.get("squad_max", 25)
        self.overseas_max = self.season_rules.get("overseas_max", 8)

    def _log_event(
        self,
        event_type: EventType,
        lot_id: Optional[str] = None,
        team_code: Optional[str] = None,
        price_lakh: Optional[int] = None,
        details: Optional[Dict[str, object]] = None,
    ) -> AuctionEvent:
        self._event_counter += 1
        event = AuctionEvent(
            event_id=self._event_counter,
            event_type=event_type,
            lot_id=lot_id,
            team_code=team_code,
            price_lakh=price_lakh,
            details=details or {},
        )
        self.event_log.append(event)
        return event

    def can_team_bid(self, team_code: str, lot: PlayerLot, target_price_lakh: int) -> bool:
        team = self.teams.get(team_code)
        if not team:
            return False

        # Squad limit check
        if team.total_squad_size >= self.squad_max:
            return False

        # Overseas limit check
        if lot.is_overseas and team.total_overseas_count >= self.overseas_max:
            return False

        # Max legal bid check (A1 guardrail: purse myopia protection)
        min_base = 30 if self.season >= 2025 else 20
        max_legal = team.compute_max_legal_bid(min_squad=self.squad_min, min_base_price_lakh=min_base)
        if target_price_lakh > max_legal:
            return False

        return True

    def conduct_lot(
        self,
        lot: PlayerLot,
        bidder_policy: Callable[[str, PlayerLot, int, Optional[str]], bool],
    ) -> Tuple[Optional[str], int, int]:
        """Runs live open-ascending bidding for a single lot.
        
        Args:
            lot: The player lot up for auction.
            bidder_policy: Function (team_code, lot, current_price_lakh, current_leader) -> bool.
        
        Returns:
            (winner_team_code or None, hammer_price_lakh, paid_price_lakh)
        """
        self._log_event(
            EventType.LOT_ANNOUNCED,
            lot_id=lot.lot_id,
            price_lakh=lot.base_price_lakh,
            details={"player_name": lot.player_name, "role": lot.role, "is_overseas": lot.is_overseas},
        )

        current_price = lot.base_price_lakh
        current_leader: Optional[str] = None
        has_opening_bid = False

        while True:
            # Determine who wants to bid at current_price
            if not has_opening_bid:
                target_bid = current_price
            else:
                target_bid = self.rules_engine.get_next_valid_bid(current_price, season=self.season)

            eligible_teams = [
                team_code
                for team_code in self.teams.keys()
                if team_code != current_leader and self.can_team_bid(team_code, lot, target_bid)
            ]

            # Ask policy which teams are willing to raise paddle
            willing_teams = [
                t for t in eligible_teams if bidder_policy(t, lot, target_bid, current_leader)
            ]

            if not willing_teams:
                # Nobody willing to bid higher
                break

            # If multiple teams raise paddles simultaneously, seed-pick one (seeded random tiebreak)
            chosen_team = self.rng.choice(willing_teams)
            current_leader = chosen_team
            current_price = target_bid
            has_opening_bid = True

            self._log_event(
                EventType.BID_PLACED,
                lot_id=lot.lot_id,
                team_code=chosen_team,
                price_lakh=current_price,
            )

        if not has_opening_bid or current_leader is None:
            self._log_event(
                EventType.LOT_UNSOLD,
                lot_id=lot.lot_id,
                price_lakh=lot.base_price_lakh,
            )
            return None, 0, 0

        # Calculate paid price vs hammer price (G5: overseas-mini 18cr cap)
        hammer_price = current_price
        paid_price = hammer_price
        if (
            self.season_rules.get("type") == "mini"
            and self.season >= 2025
            and lot.is_overseas
            and hammer_price > 1800
        ):
            paid_price = 1800

        # Settle the lot
        winning_team = self.teams[current_leader]
        winning_team.purse_remaining_lakh -= paid_price
        winning_team.squad.append(lot)

        self._log_event(
            EventType.LOT_SOLD,
            lot_id=lot.lot_id,
            team_code=current_leader,
            price_lakh=hammer_price,
            details={
                "hammer_price_lakh": hammer_price,
                "paid_price_lakh": paid_price,
                "purse_after": winning_team.purse_remaining_lakh,
            },
        )

        return current_leader, hammer_price, paid_price

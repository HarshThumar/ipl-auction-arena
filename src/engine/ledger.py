"""Team state and the Treasurer: every money and slot calculation, in integer lakhs.

The LLM never does arithmetic (failure register A10): bidders receive these numbers ready-made.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.engine.season_rules import RtmCards, SeasonRules


@dataclass(frozen=True)
class Player:
    """One player in the auction pool."""
    key: str                       # stable id: cricsheet id when known, else normalised name
    name: str
    overseas: bool
    capped: bool
    base_lakh: int
    role: str = ""
    set_no: Optional[int] = None
    set_code: str = ""
    rtm_team: Optional[str] = None  # previous team that may use an RTM card (RTM seasons only)


@dataclass
class Team:
    code: str
    purse_lakh: int
    squad: int                     # players already in the squad (retained + bought)
    overseas: int
    rtm: RtmCards = field(default_factory=RtmCards)
    bought: List[str] = field(default_factory=list)   # player keys bought at this auction

    def copy(self) -> "Team":
        return Team(self.code, self.purse_lakh, self.squad, self.overseas, self.rtm, list(self.bought))


class Treasurer:
    """Pure functions of (rules, team, player, price). No state of its own."""

    def __init__(self, rules: SeasonRules):
        self.r = rules

    def players_needed(self, t: Team) -> int:
        return max(0, self.r.squad_min - t.squad)

    def slots_left(self, t: Team) -> int:
        return max(0, self.r.squad_max - t.squad)

    def overseas_slots_left(self, t: Team) -> int:
        return max(0, self.r.overseas_max - t.overseas)

    def max_legal_bid(self, t: Team) -> int:
        """purse - (players still needed to reach the minimum squad - 1) x minimum base price.
        Keeps enough money to fill the squad after buying this player (guardrail A1)."""
        need = self.players_needed(t)
        reserve = max(0, need - 1) * self.r.min_base_lakh
        return max(0, t.purse_lakh - reserve)

    def can_take(self, t: Team, p: Player) -> bool:
        """Room for this player at all (squad and overseas limits)."""
        if self.slots_left(t) <= 0:
            return False
        if p.overseas and self.overseas_slots_left(t) <= 0:
            return False
        return True

    def can_bid(self, t: Team, p: Player, price: int) -> bool:
        return self.can_take(t, p) and price <= self.max_legal_bid(t)

    def max_affordable(self, t: Team, p: Player) -> int:
        """Highest price this team may bid for this player (0 if it cannot take him)."""
        return self.max_legal_bid(t) if self.can_take(t, p) else 0

    def next_price(self, price: int) -> int:
        return self.r.ladder.next_price(price)

    def purse_after(self, t: Team, price: int) -> int:
        return t.purse_lakh - price

    def rtm_card_for(self, t: Team, p: Player) -> Optional[str]:
        """Which RTM card type this team would spend on this player, or None."""
        kind = "capped" if p.capped else "uncapped"
        if getattr(t.rtm, kind) > 0:
            return kind
        if t.rtm.any > 0:
            return "any"
        return None

    def apply_purchase(self, t: Team, p: Player, hammer: int, rtm_card: Optional[str] = None) -> None:
        t.purse_lakh -= hammer            # purse is charged the hammer price (see engine_rules.yaml)
        t.squad += 1
        t.overseas += int(p.overseas)
        t.bought.append(p.key)
        if rtm_card:
            c = t.rtm
            t.rtm = RtmCards(**{**c.__dict__, rtm_card: getattr(c, rtm_card) - 1})

    def violations(self, t: Team, final: bool = False) -> List[str]:
        out = []
        if t.purse_lakh < 0:
            out.append(f"{t.code}: purse {t.purse_lakh} < 0")
        if t.squad > self.r.squad_max:
            out.append(f"{t.code}: squad {t.squad} > {self.r.squad_max}")
        if t.overseas > self.r.overseas_max:
            out.append(f"{t.code}: overseas {t.overseas} > {self.r.overseas_max}")
        if final and t.squad < self.r.squad_min:
            out.append(f"{t.code}: squad {t.squad} < {self.r.squad_min} at the end")
        return out


def teams_from_state(state: Dict[str, dict], rules: SeasonRules) -> Dict[str, Team]:
    """Build teams from a pre_auction_state/<season>.json 'teams' block."""
    out = {}
    for code, s in sorted(state.items()):
        squad = rules.squad_max - int(s["slots_left"])
        overseas = rules.overseas_max - int(s["overseas_slots_left"])
        out[code] = Team(code, int(s["purse_left_lakh"]), squad, overseas, rules.rtm_cards.get(code, RtmCards()))
    return out

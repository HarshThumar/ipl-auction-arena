"""Append-only event log (event sourcing, failure register H3).

Every state change in the room is one event. The final team state can be rebuilt from the log
alone (`rebuild_teams`), and two runs with the same seed and the same decisions give logs with the
same SHA-256 (`EventLog.digest`).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# event types
AUCTION_STARTED = "AUCTION_STARTED"
ROUND_STARTED = "ROUND_STARTED"        # data: {round, phase: "main"|"accelerated", lots}
NOMINATIONS = "NOMINATIONS"            # data: {round, by_team: {team: [keys]}}
LOT_ANNOUNCED = "LOT_ANNOUNCED"        # data: {player, key, base, overseas, capped, set_code, round}
DECISION = "DECISION"                  # team, data: {point, decision, valid, reason}
BID = "BID"                            # team, price
DROPPED = "DROPPED"                    # team, data: {why}
GOING_ONCE = "GOING_ONCE"              # price
TIE_BREAK = "TIE_BREAK"                # data: {teams, amounts, winner}
RTM_USED = "RTM_USED"                  # team, price, data: {card}
RTM_RAISE = "RTM_RAISE"                # team, price
RTM_RESULT = "RTM_RESULT"              # team, price, data: {matched}
SOLD = "SOLD"                          # team, price (hammer), data: {key, paid, purse_after, rtm_card, overseas}
UNSOLD = "UNSOLD"                      # data: {key}
AUCTION_ENDED = "AUCTION_ENDED"


@dataclass(frozen=True)
class Event:
    seq: int
    type: str
    lot_id: Optional[str] = None
    team: Optional[str] = None
    price: Optional[int] = None
    data: Dict[str, Any] = field(default_factory=dict)


class EventLog:
    def __init__(self) -> None:
        self.events: List[Event] = []

    def add(self, type: str, lot_id: Optional[str] = None, team: Optional[str] = None,
            price: Optional[int] = None, **data: Any) -> Event:
        e = Event(len(self.events) + 1, type, lot_id, team, price, data)
        self.events.append(e)
        return e

    def of_type(self, *types: str) -> List[Event]:
        return [e for e in self.events if e.type in types]

    def lines(self) -> Iterable[str]:
        for e in self.events:
            yield json.dumps(asdict(e), sort_keys=True, separators=(",", ":"))

    def digest(self) -> str:
        h = hashlib.sha256()
        for line in self.lines():
            h.update(line.encode("utf-8"))
            h.update(b"\n")
        return h.hexdigest()

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            for line in self.lines():
                fh.write(line + "\n")

    @staticmethod
    def read(path: Path) -> "EventLog":
        log = EventLog()
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                log.events.append(Event(d["seq"], d["type"], d.get("lot_id"), d.get("team"), d.get("price"), d.get("data") or {}))
        return log


def rebuild_teams(events: Iterable[Event], start: Dict[str, "Team"]) -> Dict[str, "Team"]:  # noqa: F821
    """Apply SOLD events to a copy of the starting teams. Must equal the live end state (H3)."""
    from src.engine.season_rules import RtmCards
    teams = {k: v.copy() for k, v in start.items()}
    for e in events:
        if e.type != SOLD:
            continue
        t = teams[e.team]
        t.purse_lakh -= int(e.price)
        t.squad += 1
        t.overseas += int(bool(e.data.get("overseas")))
        t.bought.append(e.data["key"])
        card = e.data.get("rtm_card")
        if card:
            c = t.rtm
            t.rtm = RtmCards(**{**c.__dict__, card: getattr(c, card) - 1})
    return teams

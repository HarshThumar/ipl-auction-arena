"""Auctioneer lines from templates. A generic persona: no real auctioneer's name, no catchphrases.

Deterministic: the same (seed, lot_id, kind, price, team) always gives the same line. Prices are
shown in crore (display only; the engine works in integer lakhs).
"""
from __future__ import annotations

import random
from typing import Dict, List

from src.engine.board import crore

TEMPLATES: Dict[str, List[str]] = {
    "announce": [
        "Next up: {player}, base price {base} crore.",
        "Lot {lot}. {player}, {kind}. We start at {base} crore.",
        "{player} comes into the room. Base price {base} crore.",
    ],
    "price": [
        "{price} crore, from {team}.",
        "{team} bids {price} crore.",
        "We have {price} crore with {team}. Any advance?",
    ],
    "going_once": [
        "{price} crore, going once.",
        "At {price} crore. Going once. Last chance to come in.",
    ],
    "sold": [
        "Sold. {player} goes to {team} for {price} crore.",
        "That is it. {team} take {player} at {price} crore.",
    ],
    "unsold": [
        "No bids. {player} goes unsold.",
        "Nobody comes in. {player} is unsold for now.",
    ],
    "rtm": [
        "{team} hold a right-to-match card for {player} and are thinking.",
        "A right-to-match card is in play: {team} can take {player} at {price} crore.",
    ],
    "tie_break": [
        "{teams} are level at {price} crore. Sealed extra amounts, please.",
        "Both paddles are at their limit at {price} crore ({teams}). We go to the silent tie-breaker.",
    ],
}


def line(kind: str, seed: int = 0, lot_id: str = "", **kw) -> str:
    """One auctioneer line. kw: player, base (lakh), price (lakh), team, teams (list), role."""
    options = TEMPLATES[kind]
    rng = random.Random(f"{seed}|{lot_id}|{kind}|{kw.get('price')}|{kw.get('team')}")
    fmt = dict(kw)
    for k in ("base", "price"):
        if fmt.get(k) is not None:
            fmt[k] = crore(fmt[k])
    if isinstance(fmt.get("teams"), (list, tuple)):
        fmt["teams"] = " and ".join(fmt["teams"])
    fmt.setdefault("kind", fmt.get("role", "player"))
    fmt.setdefault("lot", lot_id)
    for k in ("player", "team", "teams", "price", "base"):
        fmt.setdefault(k, "")
    return rng.choice(options).format(**fmt)


def narrate(events, seed: int = 0) -> List[str]:
    """Turn an event list into a short commentary (one line per event that has a template)."""
    from src.engine import events as E
    out: List[str] = []
    names: Dict[str, str] = {}
    for e in events:
        d = e.data
        if e.type == E.LOT_ANNOUNCED:
            names[e.lot_id] = d["player"]
            out.append(line("announce", seed, e.lot_id, player=d["player"], base=d["base"]))
        elif e.type == E.BID:
            out.append(line("price", seed, e.lot_id, team=e.team, price=e.price))
        elif e.type == E.GOING_ONCE:
            out.append(line("going_once", seed, e.lot_id, price=e.price))
        elif e.type == E.TIE_BREAK:
            out.append(line("tie_break", seed, e.lot_id, teams=d["teams"], price=e.price))
        elif e.type == E.RTM_USED:
            out.append(line("rtm", seed, e.lot_id, team=e.team, player=names.get(e.lot_id, "the player"), price=e.price))
        elif e.type == E.SOLD:
            out.append(line("sold", seed, e.lot_id, team=e.team, player=names.get(e.lot_id, "the player"), price=e.price))
        elif e.type == E.UNSOLD:
            out.append(line("unsold", seed, e.lot_id, player=names.get(e.lot_id, "the player")))
    return out

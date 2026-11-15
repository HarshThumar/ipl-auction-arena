"""Plain-text live board of the auction room (no logos, no broadcast styling)."""
from __future__ import annotations

from typing import Dict, List

from src.engine.lot import Room


def crore(lakh: int) -> str:
    """Integer lakhs to a crore string with 2 decimals (100 lakh = 1 crore). Display only."""
    sign = "-" if lakh < 0 else ""
    lakh = abs(int(lakh))
    return f"{sign}{lakh // 100}.{lakh % 100:02d}"


def render_board(room: Room, last: int = 5) -> str:
    rows = room.board()
    bought: Dict[str, List[str]] = {}
    for h in room.history:
        if h.get("sold"):
            bought.setdefault(h["team"], []).append(f"{h['player']} {crore(h['price_lakh'])}")
    head = f"{'Team':<6}{'Purse(cr)':>10}{'Squad':>7}{'Ovs':>5}{'Left':>6}  Last {last} lots"
    lines: List[str] = [head, "-" * len(head)]
    for r in sorted(rows, key=lambda r: r["team"]):
        recent = bought.get(r["team"], [])[-last:]
        lines.append(f"{r['team']:<6}{crore(r['purse_lakh']):>10}{r['squad']:>7}{r['overseas']:>5}"
                     f"{r['slots_left']:>6}  " + ("; ".join(recent) if recent else "-"))
    return "\n".join(lines)

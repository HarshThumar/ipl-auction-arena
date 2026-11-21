"""Rule #1 in code: refuse to fit or score level N while a High register row owned by an earlier
level is not Closed.

Ownership comes from the "Closes" column of docs/levels.md; severity and status from
docs/failure-register.md. Rows owned by level N itself are reported but don't block (level N is
the work that closes them, e.g. D6 "weak baselines" is closed by building the L2 baselines).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEVELS = ROOT / "docs" / "levels.md"
REGISTER = ROOT / "docs" / "failure-register.md"
ROW_ID = re.compile(r"^[A-H]\d+$")


def _expand(text: str) -> list[str]:
    ids = []
    for a, b in re.findall(r"\b([A-H]\d+)(?:\s*[–-]\s*([A-H]?\d+))?", text):
        if not b:
            ids.append(a)
            continue
        letter, start = a[0], int(a[1:])
        end = int(b[1:] if b[0].isalpha() else b)
        ids += [f"{letter}{i}" for i in range(start, end + 1)]
    return ids


def owners(levels_path: Path = LEVELS) -> dict[str, int]:
    """Register row id -> owning level (the first level whose Closes column names it)."""
    out: dict[str, int] = {}
    for line in levels_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*\*\*L(\d)\*\*\s*\|", line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5:  # only the main goals table (Level | Name | Done when | Closes | Date)
            continue
        closes = re.sub(r"\(.*?\)", "", cells[3])  # drop notes like "(G4, G6 move to L1)"
        for rid in _expand(closes):
            out.setdefault(rid, int(m.group(1)))
    return out


def register(register_path: Path = REGISTER) -> dict[str, tuple[str, str]]:
    """Register row id -> (severity, status word)."""
    out = {}
    for line in register_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not ROW_ID.match(cells[0]):
            continue
        sev = next((c for c in cells[1:] if c in ("H", "M", "L")), "?")
        st = re.match(r"\**\s*(Open|Closed|In progress|Deferred|Won't fix)", cells[-1])
        out[cells[0]] = (sev, st.group(1) if st else cells[-1][:30])
    return out


def check(level: int, levels_path: Path = LEVELS, register_path: Path = REGISTER) -> dict:
    own, reg = owners(levels_path), register(register_path)
    blocking, own_level = [], []
    for rid, lvl in sorted(own.items()):
        sev, st = reg.get(rid, ("?", "missing"))
        if sev != "H" or st in ("Closed", "Deferred", "Won't fix"):
            continue
        (blocking if lvl < level else own_level if lvl == level else []).append(f"{rid} ({st})")
    return {"level": level, "ok": not blocking, "blocking": blocking, "own_level_open": own_level}

"""Contamination guard (failure register D1).

A model cannot have seen an auction that happened after it was released, because its training
data stops before its release. So "release date < auction date" is a guarantee of a clean
backtest. A model's own claim about its cutoff is NOT evidence (models misreport it), and a
refusal to answer is not proof it doesn't know.

Any LLM score on a season that fails this check must carry the flag "possibly_contaminated"
and can never be presented as a clean result (rule #8).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "data" / "reference" / "rules_by_season.yaml"

# Public release dates (first open-weights release). Training data ends on or before these.
MODEL_RELEASES = {
    "qwen2:7b": (dt.date(2024, 6, 7), "https://qwenlm.github.io/blog/qwen2/"),
    "qwen2.5:7b": (dt.date(2024, 9, 19), "https://qwenlm.github.io/blog/qwen2.5/"),
    "llama3.1:8b": (dt.date(2024, 7, 23), "https://ai.meta.com/blog/meta-llama-3-1/"),
}

# Cloud models: banned from every backtest, whatever the date (rule #9, register D1).
BANNED_FOR_BACKTEST_PREFIXES = ("gemini",)


class ContaminationError(RuntimeError):
    pass


def auction_date(season: int) -> dt.date:
    """Day 1 of the auction for an IPL season, from rules_by_season.yaml."""
    with open(RULES, encoding="utf-8") as f:
        rules = yaml.safe_load(f)
    seasons = rules.get("seasons", rules)
    entry = seasons.get(season) or seasons.get(str(season))
    if not entry or "date" not in entry:
        raise ContaminationError(f"no auction date for season {season} in {RULES.name}")
    d = entry["date"]
    return d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))


def status(model: str, season: int) -> str:
    """'clean' or 'possibly_contaminated'. Raises for banned or unknown models."""
    name = model.lower()
    if name.startswith(BANNED_FOR_BACKTEST_PREFIXES):
        raise ContaminationError(f"{model} is banned from backtests (rule #9)")
    if name not in MODEL_RELEASES:
        raise ContaminationError(
            f"{model} has no release date in MODEL_RELEASES; add it with a source URL first"
        )
    released, _ = MODEL_RELEASES[name]
    return "clean" if released < auction_date(season) else "possibly_contaminated"


def require_clean(model: str, season: int) -> None:
    """Call before any LLM run whose score will be reported as clean."""
    s = status(model, season)
    if s != "clean":
        raise ContaminationError(
            f"{model} was released {MODEL_RELEASES[model.lower()][0]}, after the season {season} "
            f"auction ({auction_date(season)}). Report it as possibly_contaminated."
        )

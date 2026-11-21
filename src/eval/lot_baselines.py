"""Lot-level baselines (L2), scored with AuctionIQ's metric set.

For every player called in a mini-auction, each baseline gives:
  p_sold, a point price (lakhs), an 80% price interval, and a ranking of the 10 teams as buyer.

Baselines:
  base_price  price = base price; p_sold = past sold-rate for that base price; buyers ranked by
              purse left at the start of the auction.
  last_price  price = the player's most recent hammer price in an earlier auction (else base);
              p_sold as base_price; his last buyer is ranked first, then by purse.

As-of (register D2): everything used to predict season s comes from seasons < s, plus the
pre-auction state of s itself (purses after retentions are public before the auction).
Prices are hammer prices (what the room paid), not the capped overseas pay.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "processed" / "master" / "all_auctions_master.csv"
STATE_DIR = ROOT / "data" / "processed" / "pre_auction_state"
SOLD_PRIOR_STRENGTH = 10.0
INTERVAL = (0.10, 0.90)


def load_master(path: Path = MASTER) -> pd.DataFrame:
    m = pd.read_csv(path)
    m = m[~m["withdrawn"].astype(bool)].copy()
    m["key"] = m["cricsheet_id"].fillna("name:" + m["player"].str.lower().str.strip())
    m["sold"] = (m["status"] == "sold").astype(int)
    return m


def load_purses(season: int, state_dir: Path = STATE_DIR) -> dict[str, int]:
    with open(state_dir / f"{season}.json", encoding="utf-8") as f:
        return {t: v["purse_left_lakh"] for t, v in json.load(f)["teams"].items()}


def _purse_ranking(purses: dict[str, int]) -> list[str]:
    return sorted(purses, key=lambda t: (-purses[t], t))


def _sold_rate_model(hist: pd.DataFrame):
    p0 = hist["sold"].mean()
    g = hist.groupby("base_lakh")["sold"]
    rate = ((g.sum() + SOLD_PRIOR_STRENGTH * p0) / (g.count() + SOLD_PRIOR_STRENGTH)).to_dict()
    return lambda base: np.array([rate.get(b, p0) for b in base], float)


def _last_price(hist: pd.DataFrame):
    sold = hist[hist["sold"] == 1].sort_values("season")
    last = sold.groupby("key").tail(1).set_index("key")
    return last["hammer_lakh"].to_dict(), last["winner"].to_dict()


def _point(kind: str, lots: pd.DataFrame, hist: pd.DataFrame) -> np.ndarray:
    base = lots["base_lakh"].to_numpy(float)
    if kind == "base_price":
        return base
    price, _ = _last_price(hist)
    return np.array([price.get(k, b) for k, b in zip(lots["key"], base)], float)


def _ratio_quantiles(kind: str, m: pd.DataFrame, season: int) -> tuple[float, float]:
    """Calibrate the 80% interval as quantiles of hammer/point on earlier seasons' sold lots."""
    ratios = []
    for s in sorted(m["season"].unique()):
        if s >= season:
            break
        past, lots = m[m["season"] < s], m[(m["season"] == s) & (m["sold"] == 1)]
        if len(lots):
            ratios.append(lots["hammer_lakh"].to_numpy(float) / _point(kind, lots, past))
    r = np.concatenate(ratios)
    lo, hi = np.quantile(r, INTERVAL)
    return float(lo), float(hi)


def predict(kind: str, m: pd.DataFrame, season: int, purses: dict[str, int]) -> pd.DataFrame:
    assert kind in ("base_price", "last_price")
    hist = m[m["season"] < season]
    lots = m[m["season"] == season].copy()
    point = _point(kind, lots, hist)
    qlo, qhi = _ratio_quantiles(kind, m, season)
    by_purse = _purse_ranking(purses)
    if kind == "last_price":
        _, last_team = _last_price(hist)
        rankings = []
        for k in lots["key"]:
            t = last_team.get(k)
            rankings.append(([t] if t in purses else []) + [x for x in by_purse if x != t])
    else:
        rankings = [by_purse] * len(lots)
    return pd.DataFrame({
        "player": lots["player"].to_numpy(),
        "sold": lots["sold"].to_numpy(),
        "winner": lots["winner"].to_numpy(),
        "hammer_lakh": lots["hammer_lakh"].to_numpy(),
        "p_sold": _sold_rate_model(hist)(lots["base_lakh"].to_numpy()),
        "point": point,
        "lo": point * qlo,
        "hi": point * qhi,
        "ranking": rankings,
    })

"""L2 metrics.

Decision level (the bar the LoRA must beat at L3): log-loss and Brier of P(DROP) on held-out rows.
Lot level (AuctionIQ's set, register D7): sold/unsold AUC, Brier, buyer in top 3, Spearman,
log-price MAE on SOLD lots only, and coverage of the 80% price interval.

Small samples (register D4): every number gets a bootstrap CI that resamples whole LOTS, never
single rows, because rows inside one bidding war are not independent.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

EPS = 1e-6


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y, float)
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def auc(y: np.ndarray, p: np.ndarray) -> float | None:
    y = np.asarray(y)
    if len(np.unique(y)) < 2:
        return None
    return float(roc_auc_score(y, p))


def spearman(pred: np.ndarray, actual: np.ndarray) -> float | None:
    if len(pred) < 3:
        return None
    r = spearmanr(pred, actual).statistic
    return None if np.isnan(r) else float(r)


def log_price_mae(pred_lakhs: np.ndarray, actual_lakhs: np.ndarray) -> float:
    return float(np.mean(np.abs(np.log(np.asarray(pred_lakhs, float)) - np.log(np.asarray(actual_lakhs, float)))))


def coverage(lo: np.ndarray, hi: np.ndarray, actual: np.ndarray) -> float:
    a = np.asarray(actual, float)
    return float(np.mean((a >= np.asarray(lo, float)) & (a <= np.asarray(hi, float))))


def top3_hit(rankings: list[list[str]], winners: list[str]) -> float:
    return float(np.mean([w in r[:3] for r, w in zip(rankings, winners)]))


def bootstrap_ci(groups: np.ndarray, stat, n: int = 1000, seed: int = 0, alpha: float = 0.05):
    """Percentile CI of stat(index_array) resampling whole groups (lots) with replacement.

    stat receives an integer index array into the original rows and returns a float.
    """
    groups = np.asarray(groups)
    uniq = np.unique(groups)
    idx_by_group = {g: np.flatnonzero(groups == g) for g in uniq}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by_group[g] for g in pick])
        v = stat(idx)
        if v is not None and not np.isnan(v):
            vals.append(v)
    if not vals:
        return None
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return [float(lo), float(hi)]

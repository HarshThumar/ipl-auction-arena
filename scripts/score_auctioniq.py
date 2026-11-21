"""Score AuctionIQ (MIT, github.com/FuadAhamed91/auctioniq) on our L2 minis with our metrics.

AuctionIQ's per-player predictions are built from data it took from archived iplt20.com pages, so
they stay in private/auctioniq/ (local only, rule #7). Only aggregate scores are committed.

Inputs (made by running AuctionIQ's own code at commit 487c8b8, out of tree):
  private/auctioniq/auctioniq_value_{2023,2024}.csv   value model alone (out-of-sample)
  private/auctioniq/auctioniq_sim_points_2024.csv     full simulation, from its validation_2024.json
                                                      (TUNING SET: its weights were chosen on 2024)
Two pools per season:
  called  the lots that were actually called (our master): comparable with our baselines
  list    AuctionIQ's whole auction list incl. never-called players (its own published pool)

  python scripts/score_auctioniq.py   -> data/processed/l2/auctioniq_scores.json
"""
from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_decision_dataset import norm_name  # noqa: E402
from src.eval import lot_baselines as lb, metrics as mt  # noqa: E402

PRIV = ROOT / "private" / "auctioniq"
OUT = ROOT / "data" / "processed" / "l2" / "auctioniq_scores.json"
AUCTIONIQ_COMMIT = "487c8b8209f0f6317ad7d043ed5aeaf7da3fc5b6"


def match_names(ours: pd.DataFrame, theirs: pd.DataFrame) -> dict[int, int]:
    """our row index -> their row index. Exact normalised name first; then, among players with the
    same base price, a unique surname match or a close spelling (difflib >= 0.8)."""
    tn = theirs["name"].map(norm_name)
    exact = {n: i for i, n in zip(theirs.index, tn)}
    out, used = {}, set()
    for i, n in zip(ours.index, ours["player"].map(norm_name)):
        if n in exact:
            out[i] = exact[n]
            used.add(exact[n])
    for i, row in ours.drop(index=list(out)).iterrows():
        cand = theirs[(theirs["base_lakh"] == row["base_lakh"]) & ~theirs.index.isin(used)]
        surname = norm_name(row["player"].split()[-1])
        by_surname = cand[cand["name"].map(lambda s: norm_name(s.split()[-1]) == surname)]
        if len(by_surname) == 1:
            j = by_surname.index[0]
        else:
            names = cand["name"].map(norm_name).tolist()
            close = difflib.get_close_matches(norm_name(row["player"]), names, n=1, cutoff=0.8)
            if not close:
                continue
            j = cand.index[names.index(close[0])]
        out[i] = j
        used.add(j)
    return out


def score(pred: pd.DataFrame, sold: np.ndarray, price: np.ndarray, buyer_top3: float | None = None) -> dict:
    s = sold.astype(bool)
    r = lambda x: None if x is None else round(float(x), 4)  # noqa: E731
    return {
        "n_lots": int(len(pred)), "n_sold": int(s.sum()),
        "sold_auc": r(mt.auc(s, pred["p_sold"])),
        "sold_brier": r(mt.brier(s, pred["p_sold"])),
        "buyer_top3": buyer_top3,
        "spearman": r(mt.spearman(pred["median"][s], price[s])),
        "log_price_mae": r(mt.log_price_mae(pred["median"][s], price[s])),
        "interval80_coverage": r(mt.coverage(pred["p10"][s], pred["p90"][s], price[s])),
    }


def main() -> int:
    if not PRIV.exists():
        print(f"{PRIV} missing: run AuctionIQ first (see docstring). Nothing scored.")
        return 1
    m = lb.load_master()
    res = {"auctioniq_commit": AUCTIONIQ_COMMIT, "seasons": {}}
    sim24 = pd.read_csv(PRIV / "auctioniq_sim_points_2024.csv").rename(columns={"pSold": "p_sold"})
    for y in (2023, 2024):
        val = pd.read_csv(PRIV / f"auctioniq_value_{y}.csv")
        ours = m[m["season"] == y]
        mp = match_names(ours, val)
        unmatched = sorted(ours.loc[~ours.index.isin(list(mp)), "player"])
        o = ours.loc[list(mp)]
        p = val.loc[list(mp.values())].reset_index(drop=True)
        entry = {
            "called_lots": int(len(ours)), "matched": int(len(mp)), "unmatched": unmatched,
            "value_model": {
                "called": score(p, o["sold"].to_numpy(), o["hammer_lakh"].to_numpy(float)),
                "list": score(val, val["status"].eq("sold").to_numpy(), val["price_lakh"].to_numpy(float)),
            },
        }
        if y == 2024:
            # validation_2024.json points are in the same order as the value-model list
            assert (sim24["name"].to_numpy() == val["name"].to_numpy()).all()
            ps = sim24.loc[list(mp.values())].reset_index(drop=True)
            entry["simulation_tuning_set"] = {
                "called": score(ps, o["sold"].to_numpy(), o["hammer_lakh"].to_numpy(float)),
                "list": score(sim24, sim24["sold"].to_numpy(bool), sim24["price"].to_numpy(float),
                              buyer_top3=0.38),
                "note": "AuctionIQ chose its weights on 2024; buyer top-3 0.38 is its published "
                        "number on its own pool (buyer probabilities were not in its output).",
            }
        res["seasons"][y] = entry
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

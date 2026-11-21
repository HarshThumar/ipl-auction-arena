"""L2: score the baselines on the 2023-season (Dec 2022) and 2024-season (Dec 2023) minis.

  python scripts/run_l2_baselines.py --dry-run   # load data and show split sizes; fits nothing
  python scripts/run_l2_baselines.py             # fit + score; refuses while the rule #1 gate is red

The 2026-season (Dec 2025) mini is NOT scored here: it is held back and run once at L5 (D5).
Outputs: data/processed/l2/l2_scores.json and docs/L2-baselines.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import decision_baselines as db  # noqa: E402
from src.eval import gate, lot_baselines as lb, metrics as mt  # noqa: E402

DECISIONS = ROOT / "data" / "processed" / "decisions" / "decision_rows.parquet"
OUT_DIR = ROOT / "data" / "processed" / "l2"
REPORT = ROOT / "docs" / "L2-baselines.md"
SCORE_SEASONS = [2023, 2024]  # minis only (register D8); 2026 held back for L5
LABELS = {2023: "2023 season (Dec 2022 mini)", 2024: "2024 season (Dec 2023 mini)"}
N_BOOT = 1000


def _r(x, k=4):
    return None if x is None else round(float(x), k)


def score_decisions(df: pd.DataFrame) -> dict:
    out = {}
    for s in SCORE_SEASONS:
        train, val = db.forward_split(df, s)
        y, lots, war = db.label(val), val["lot_id"].to_numpy(), db.war_mask(val)
        preds = {m.name: m.fit(train).predict(val) for m in db.all_models()}
        base = preds["prior"]
        res = {"train_seasons": sorted(train["season"].unique().tolist()), "n_rows": int(len(val)),
               "n_drop": int(y.sum()), "n_lots": int(len(np.unique(lots))), "n_war_rows": int(war.sum()),
               "models": {}}
        for name, p in preds.items():
            w = np.flatnonzero(war)
            res["models"][name] = {
                "log_loss": _r(mt.log_loss(y, p)),
                "log_loss_ci": [_r(v) for v in mt.bootstrap_ci(lots, lambda i: mt.log_loss(y[i], p[i]), N_BOOT)],
                "delta_vs_prior_ci": [_r(v) for v in mt.bootstrap_ci(
                    lots, lambda i: mt.log_loss(y[i], p[i]) - mt.log_loss(y[i], base[i]), N_BOOT)],
                "brier": _r(mt.brier(y, p)),
                "auc": _r(mt.auc(y, p)),
                "war_log_loss": _r(mt.log_loss(y[w], p[w])) if len(w) else None,
                "war_log_loss_ci": [_r(v) for v in mt.bootstrap_ci(
                    lots[w], lambda i: mt.log_loss(y[w][i], p[w][i]), N_BOOT)] if len(w) else None,
            }
        out[s] = res
    return out


def score_lots(m: pd.DataFrame) -> dict:
    out = {}
    for s in SCORE_SEASONS:
        purses = lb.load_purses(s)
        out[s] = {}
        for kind in ("base_price", "last_price"):
            p = lb.predict(kind, m, s, purses)
            sold = p[p["sold"] == 1]
            out[s][kind] = {
                "n_lots": int(len(p)), "n_sold": int(len(sold)),
                "sold_auc": _r(mt.auc(p["sold"], p["p_sold"])),
                "sold_brier": _r(mt.brier(p["sold"], p["p_sold"])),
                "buyer_top3": _r(mt.top3_hit(list(sold["ranking"]), list(sold["winner"]))),
                "spearman": _r(mt.spearman(sold["point"], sold["hammer_lakh"])),
                "log_price_mae": _r(mt.log_price_mae(sold["point"], sold["hammer_lakh"])),
                "interval80_coverage": _r(mt.coverage(sold["lo"], sold["hi"], sold["hammer_lakh"])),
            }
    return out


AUCTIONIQ = OUT_DIR / "auctioniq_scores.json"
METRIC_COLS = ["n_lots", "n_sold", "sold_auc", "sold_brier", "buyer_top3", "spearman",
               "log_price_mae", "interval80_coverage"]


def auctioniq_section() -> list[str]:
    """AuctionIQ scores from scripts/score_auctioniq.py (its code, run out of tree, MIT)."""
    if not AUCTIONIQ.exists():
        return ["## AuctionIQ", "", "Not scored yet: run `scripts/score_auctioniq.py`.", ""]
    a = json.loads(AUCTIONIQ.read_text(encoding="utf-8"))
    L = ["## AuctionIQ (rule-based, MIT)", "",
         f"Its own code, commit `{a['auctioniq_commit'][:7]}`, run out of tree; its per-player outputs "
         "stay private because its data came from archived iplt20.com pages (rule #7).", "",
         "- **called** = the lots actually called (same pool as the baselines above). "
         "**list** = AuctionIQ's whole auction list, including players never called (its own published pool). "
         "Never-called players are easy 'unsold' calls, so the list AUC is much higher and not comparable.",
         "- **Value model** = its Tobit price model alone, trained on earlier minis: out-of-sample. "
         "Its 80% range is ours (quantiles given a sale); it sits above base price, and about half of real "
         "sales happen at base, so it misses them.",
         "- **Simulation** = its full 10-agent Monte Carlo, taken from its published 2024 back-test. "
         "**Tuning set**: AuctionIQ chose its weights on 2024, so these are in-sample. "
         "2023 has no simulation (AuctionIQ ships no 2023 team file).", ""]
    for s, e in a["seasons"].items():
        L += [f"### {LABELS[int(s)]}", "",
              f"Matched {e['matched']} of {e['called_lots']} called lots by name"
              + (f" (unmatched: {', '.join(e['unmatched'])})" if e["unmatched"] else "") + ".", "",
              "| model | pool | lots | sold | sold AUC | sold Brier | buyer top-3 | Spearman | log-price MAE | 80% coverage |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for name, key in (("value model", "value_model"), ("simulation (tuning set)", "simulation_tuning_set")):
            if key not in e:
                continue
            for pool in ("called", "list"):
                v = e[key][pool]
                L.append(f"| {name} | {pool} | " + " | ".join(str(v[c]) if v[c] is not None else "–"
                                                         for c in METRIC_COLS) + " |")
        L.append("")
    return L


def write_report(scores: dict) -> None:
    L = ["# L2 baselines: scores", "",
         "*Generated by `scripts/run_l2_baselines.py`. Do not edit by hand.*", "",
         "Forward-chaining: each season is scored by models trained only on earlier seasons. "
         "The 2026-season (Dec 2025) mini is held back for one run at L5. 95% CIs resample whole lots.",
         "", "**Small samples (D4):** a few dozen DROP rows per season. Read the CIs, not the point values.", ""]
    L += ["## Decision level: P(DROP) on {state -> RAISE/DROP} rows", "",
          "`war` = contested lots after the opening bid (the hard rows; the opening bid is always RAISE).", ""]
    for s, r in scores["decisions"].items():
        L += [f"### {LABELS[int(s)]}", "",
              f"Train seasons {r['train_seasons']}; {r['n_rows']} rows, {r['n_drop']} DROP, "
              f"{r['n_lots']} lots, {r['n_war_rows']} war rows.", "",
              "| model | log-loss [95% CI] | vs prior [95% CI] | Brier | AUC | war log-loss [95% CI] |",
              "|---|---|---|---|---|---|"]
        for n, v in r["models"].items():
            L.append(f"| {n} | {v['log_loss']} {v['log_loss_ci']} | {v['delta_vs_prior_ci']} | {v['brier']} | "
                     f"{v['auc']} | {v['war_log_loss']} {v['war_log_loss_ci']} |")
        L.append("")
    L += ["## Lot level (AuctionIQ metrics)", "",
          "Price metrics use SOLD lots and hammer prices (D7).", ""]
    for s, r in scores["lots"].items():
        L += [f"### {LABELS[int(s)]}", "",
              "| baseline | lots | sold | sold AUC | sold Brier | buyer top-3 | Spearman | log-price MAE | 80% coverage |",
              "|---|---|---|---|---|---|---|---|---|"]
        for n, v in r.items():
            L.append(f"| {n} | {v['n_lots']} | {v['n_sold']} | {v['sold_auc']} | {v['sold_brier']} | "
                     f"{v['buyer_top3']} | {v['spearman']} | {v['log_price_mae']} | {v['interval80_coverage']} |")
        L.append("")
    L += auctioniq_section()
    L += ["## Not yet scored", "",
          "- **Single-prompt LLM**: `qwen2.5:7b` was released Sep 2024, after both scored auctions, so its "
          "score here must be labelled *possibly contaminated* (`src/eval/contamination.py`).",
          "- **JioStar pundit mock**: covers the Dec 2025 mini only, so it is scored at L5 with the held-back season.", ""]
    REPORT.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    df = pd.read_parquet(DECISIONS)
    m = lb.load_master()
    for s in SCORE_SEASONS:
        tr, va = db.forward_split(df, s)
        print(f"{LABELS[s]}: train {len(tr)} rows {sorted(tr.season.unique())}, val {len(va)} rows "
              f"({int(db.label(va).sum())} DROP), lots {int((m.season == s).sum())}")
    g = gate.check(2)
    print("rule #1 gate:", g)
    if args.dry_run:
        return 0
    if not g["ok"]:
        print("Refusing to fit: close the blocking register rows first (rule #1).")
        return 2
    scores = {"decisions": score_decisions(df), "lots": score_lots(m),
              "config": {"lgbm_params": db.PARAMS, "features": db.FEATURES, "n_boot": N_BOOT}}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "l2_scores.json").write_text(json.dumps(scores, indent=2, default=str), encoding="utf-8")
    write_report(scores)
    print(f"wrote {OUT_DIR / 'l2_scores.json'} and {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

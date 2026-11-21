"""L2 single-prompt LLM baseline on the 2023/2024-season minis (named and anonymised).

  python scripts/run_llm_baseline.py --model qwen2.5:7b              # both seasons, both variants
  python scripts/run_llm_baseline.py --model qwen2:7b --limit 3      # smoke test, scores not saved

Every call is cached (runs/llm_cache/), so a re-run replays exactly and a stopped run resumes.
Per-player answers go to runs/llm_baseline/ (gitignored); scores to data/processed/l2/llm_scores.json.
Scores on these seasons are labelled possibly_contaminated for models released after them (D1).
Refuses to run while the rule #1 gate for L2 is red.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import gate, llm_baseline as lm, lot_baselines as lb, metrics as mt  # noqa: E402
from src.llm.ollama_client import OllamaClient  # noqa: E402

SEASONS = [2023, 2024]
OUT = ROOT / "data" / "processed" / "l2" / "llm_scores.json"
RUNS = ROOT / "runs" / "llm_baseline"
N_BOOT = 1000


def score(df) -> dict:
    s = df["sold"].to_numpy(bool)
    sold = df[s]
    r = lambda x: None if x is None else round(float(x), 4)  # noqa: E731
    return {
        "n_lots": int(len(df)), "n_sold": int(s.sum()),
        "sold_auc": r(mt.auc(s, df["p_sold"])),
        "sold_brier": r(mt.brier(s, df["p_sold"])),
        "buyer_top3": r(mt.top3_hit(list(sold["ranking"]), list(sold["winner"]))),
        "spearman": r(mt.spearman(sold["point"], sold["hammer_lakh"])),
        "log_price_mae": r(mt.log_price_mae(sold["point"], sold["hammer_lakh"])),
        "interval80_coverage": r(mt.coverage(sold["lo"], sold["hi"], sold["hammer_lakh"])),
    }


def named_minus_anon(named, anon) -> dict:
    """Paired bootstrap over sold lots: log-price error and buyer top-3, named minus anon.
    A clearly better named score (lower error / higher top-3) hints at memorised results."""
    s = named["sold"].to_numpy(bool)
    idx = np.flatnonzero(s)
    a_err = np.abs(np.log(named["point"].to_numpy(float)) - np.log(named["hammer_lakh"].to_numpy(float)))
    b_err = np.abs(np.log(anon["point"].to_numpy(float)) - np.log(anon["hammer_lakh"].to_numpy(float)))
    a_hit = np.array([w in r[:3] for r, w in zip(named["ranking"], named["winner"])], float)
    b_hit = np.array([w in r[:3] for r, w in zip(anon["ranking"], anon["winner"])], float)
    groups = idx  # one lot per group
    rnd = lambda v: [round(x, 4) for x in v] if v else None  # noqa: E731
    return {
        "log_price_mae_diff": round(float((a_err[idx] - b_err[idx]).mean()), 4),
        "log_price_mae_diff_ci": rnd(mt.bootstrap_ci(groups, lambda i: float((a_err[i] - b_err[i]).mean()), N_BOOT)),
        "buyer_top3_diff": round(float((a_hit[idx] - b_hit[idx]).mean()), 4),
        "buyer_top3_diff_ci": rnd(mt.bootstrap_ci(groups, lambda i: float((a_hit[i] - b_hit[i]).mean()), N_BOOT)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--host", default=None)
    ap.add_argument("--variants", nargs="+", default=["named", "anon"], choices=["named", "anon"])
    ap.add_argument("--seasons", nargs="+", type=int, default=SEASONS)
    ap.add_argument("--limit", type=int, default=None, help="first N lots only (smoke test; scores not saved)")
    args = ap.parse_args()

    g = gate.check(2)
    if not g["ok"]:
        print("Refusing to run: rule #1 gate is red:", g["blocking"])
        return 2
    client = OllamaClient(model=args.model, host=args.host)
    m = lb.load_master()
    results = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() and not args.limit else {}
    per = {}
    for season in args.seasons:
        state = json.loads((lb.STATE_DIR / f"{season}.json").read_text(encoding="utf-8"))
        mm = m if not args.limit else m[(m["season"] != season) | m.index.isin(m[m["season"] == season].index[: args.limit])]
        for v in args.variants:
            t0 = time.time()
            df, meta = lm.predict(client, mm, season, state, v)
            meta["seconds"] = round(time.time() - t0, 1)
            per[(season, v)] = df
            print(f"{season} {v}: {meta}")
            if args.limit:
                print(df[["player", "p_sold", "point", "lo", "hi", "ranking", "hammer_lakh", "winner"]].to_string())
                continue
            RUNS.mkdir(parents=True, exist_ok=True)
            (RUNS / f"{args.model.replace(':', '_')}_{season}_{v}.csv").write_text(lm.to_jsonable(df), encoding="utf-8")
            results.setdefault(args.model, {}).setdefault(str(season), {})[v] = {**meta, **score(df)}
        if not args.limit and {"named", "anon"} <= set(args.variants):
            results[args.model][str(season)]["named_minus_anon"] = named_minus_anon(
                per[(season, "named")], per[(season, "anon")])
    if not args.limit:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

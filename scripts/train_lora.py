"""L3: Train shared-LoRA decision model predicting P(DROP).

Forward-chaining evaluation matching L2: for each val season s, train on seasons < s,
predict P(DROP) on season s. Refuses if held-out seasons 2025/2026 are included.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import contamination, decision_baselines as db, gate, metrics as mt
from src.lora.serialize import TARGETS, row_to_prompt

HELDOUT_SEASONS = {2025, 2026}
DEFAULT_BASE = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_DATA = "data/processed/decisions/decision_rows.parquet"
DEFAULT_OUT = "runs/lora"
DEFAULT_VAL_SEASONS = [2023, 2024]
N_BOOT = 1000


def check_seasons(train_seasons: list[int] | set[int], val_seasons: list[int] | set[int]) -> None:
    """Hard-refuse (exit 2) if 2025 or 2026 is in train or val (held out for L5/L7)."""
    forbidden = HELDOUT_SEASONS & (set(train_seasons) | set(val_seasons))
    if forbidden:
        print(
            f"Refusing to run: held-out season(s) {sorted(forbidden)} found in train or val (rule #1, held out for L5/L7).",
            file=sys.stderr,
        )
        sys.exit(2)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Train shared-LoRA decision model")
    parser.add_argument("--base", type=str, default=DEFAULT_BASE, help="Base model name or path")
    parser.add_argument("--data", type=str, default=DEFAULT_DATA, help="Path to decision_rows.parquet")
    parser.add_argument("--val-seasons", type=int, nargs="+", default=DEFAULT_VAL_SEASONS, help="Validation seasons")
    parser.add_argument("--epochs", type=int, default=2, help="Number of training epochs")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--max-len", type=int, default=384, help="Max token sequence length")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    parser.add_argument("--out", type=str, default=DEFAULT_OUT, help="Output directory for runs")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of rows for smoke testing")
    parser.add_argument("--pos-weight", type=float, default=1.0, help="DROP class weight in the loss (1.0 = calibrated)")
    parser.add_argument(
        "--zero-identity",
        action="store_true",
        help="Replace team tokens with <OTHER> at train and eval (register F6/L6 ablation)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    # gate check (rule #1 warning print only, do not block)
    g = gate.check(2)
    print("rule #1 gate check (warning only):", g)

    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    if not data_path.exists():
        print(f"Error: Data file {data_path} not found.", file=sys.stderr)
        return 1

    df = pd.read_parquet(data_path)

    # Check forward splits for all val seasons before importing heavy packages
    for s in args.val_seasons:
        train, val = db.forward_split(df, s)
        tr_seasons = sorted(train["season"].unique().tolist())
        va_seasons = sorted(val["season"].unique().tolist())
        check_seasons(tr_seasons, va_seasons)

    # Now import torch, peft, transformers and src.lora.model
    import torch
    from src.lora.model import build, restricted_logprobs, weighted_bce_loss

    # Set seed
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    tag_name = f"{args.base.replace('/', '_')}_{'zero_identity' if args.zero_identity else 'shared'}"
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    run_dir = out_dir / tag_name
    run_dir.mkdir(parents=True, exist_ok=True)

    timings = {}
    metrics_by_season = {}
    contamination_by_season = {}

    for s in args.val_seasons:
        print(f"\n========== Evaluating Season {s} ==========")
        train, val = db.forward_split(df, s)
        if args.limit:
            train = train.head(args.limit)
            val = val.head(args.limit)

        print(f"Season {s}: train rows = {len(train)}, val rows = {len(val)}")

        # Contamination status: unknown or banned models are refused (raises), never labelled "unknown"
        c_status = contamination.status(args.base, s)
        contamination_by_season[str(s)] = c_status
        print(f"Contamination status for {args.base} on {s}: {c_status}")

        # Train fresh LoRA for this season
        t0_train = time.time()
        model, tokenizer, (raise_id, drop_id) = build(
            base_model=args.base,
            r=16,
            alpha=32,
            dropout=0.05,
        )
        model.to(device)

        train_prompts = [row_to_prompt(row, zero_identity=args.zero_identity) for _, row in train.iterrows()]
        train_y = db.label(train)

        # pos_weight 1.0 by default: up-weighting DROP inflates P(DROP) and wrecks log-loss, which is
        # the L3 gate metric (LightGBM is trained unweighted). Change only as a logged new config.
        pos_weight = args.pos_weight

        optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr)

        model.train()
        n_train = len(train_prompts)
        for epoch in range(args.epochs):
            indices = np.random.permutation(n_train)
            epoch_loss = 0.0
            n_batches = 0
            for start_idx in range(0, n_train, args.batch):
                batch_indices = indices[start_idx : start_idx + args.batch]
                b_prompts = [train_prompts[i] for i in batch_indices]
                b_y = torch.tensor(train_y[batch_indices], dtype=torch.float32, device=device)

                enc = tokenizer(
                    b_prompts,
                    padding=True,
                    truncation=True,
                    max_length=args.max_len,
                    return_tensors="pt",
                )
                input_ids = enc["input_ids"].to(device)
                attention_mask = enc["attention_mask"].to(device)

                optimizer.zero_grad()
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                last_idx = attention_mask.sum(dim=1) - 1
                b_idx = torch.arange(input_ids.size(0), device=device)
                last_logits = outputs.logits[b_idx, last_idx, :]

                logp2 = restricted_logprobs(last_logits, raise_id, drop_id)
                loss = weighted_bce_loss(logp2, b_y, pos_weight=pos_weight)
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()
                n_batches += 1

            avg_loss = epoch_loss / max(n_batches, 1)
            print(f"Epoch {epoch + 1}/{args.epochs} - Loss: {avg_loss:.4f}")

        t_train = time.time() - t0_train

        # Save adapter and tokenizer for this season
        adapter_dir = run_dir / f"adapter_{s}"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(adapter_dir)
        tokenizer.save_pretrained(adapter_dir)
        print(f"Saved adapter to {adapter_dir}")

        # Evaluation on val
        t0_eval = time.time()
        model.eval()
        val_prompts = [row_to_prompt(row, zero_identity=args.zero_identity) for _, row in val.iterrows()]
        val_p_drops = []
        with torch.no_grad():
            for start_idx in range(0, len(val_prompts), args.batch):
                b_prompts = val_prompts[start_idx : start_idx + args.batch]
                enc = tokenizer(
                    b_prompts,
                    padding=True,
                    truncation=True,
                    max_length=args.max_len,
                    return_tensors="pt",
                )
                input_ids = enc["input_ids"].to(device)
                attention_mask = enc["attention_mask"].to(device)
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                last_idx = attention_mask.sum(dim=1) - 1
                b_idx = torch.arange(input_ids.size(0), device=device)
                last_logits = outputs.logits[b_idx, last_idx, :]
                logp2 = restricted_logprobs(last_logits, raise_id, drop_id)
                p_drop = torch.exp(logp2[:, 1]).cpu().numpy()
                val_p_drops.extend(p_drop)

        p_lora = np.array(val_p_drops)
        t_eval = time.time() - t0_eval

        # Save preds
        preds_csv = run_dir / f"preds_{s}.csv"
        pd.DataFrame({"index": val.index, "p_drop": p_lora}).to_csv(preds_csv, index=False)
        print(f"Saved predictions to {preds_csv}")

        # Fit LightGBM baseline on the same train rows
        lgbm = db.LGBM(with_identity=True)
        lgbm.fit(train)
        p_lgbm = lgbm.predict(val)

        # Compute metrics
        y_val = db.label(val)
        lots = val["lot_id"].to_numpy()
        war = db.war_mask(val)
        w = np.flatnonzero(war)

        log_loss_val = mt.log_loss(y_val, p_lora)
        log_loss_ci = mt.bootstrap_ci(lots, lambda i: mt.log_loss(y_val[i], p_lora[i]), n=N_BOOT, seed=args.seed)
        brier_val = mt.brier(y_val, p_lora)
        auc_val = mt.auc(y_val, p_lora)

        war_ll = mt.log_loss(y_val[w], p_lora[w]) if len(w) > 0 else None
        war_ll_ci = (
            mt.bootstrap_ci(lots[w], lambda i: mt.log_loss(y_val[w][i], p_lora[w][i]), n=N_BOOT, seed=args.seed)
            if len(w) > 0
            else None
        )

        delta_ci = mt.bootstrap_ci(
            lots,
            lambda i: mt.log_loss(y_val[i], p_lora[i]) - mt.log_loss(y_val[i], p_lgbm[i]),
            n=N_BOOT,
            seed=args.seed,
        )

        timings[str(s)] = {
            "train_seconds": round(t_train, 2),
            "eval_seconds": round(t_eval, 2),
        }

        metrics_by_season[str(s)] = {
            "n_rows": int(len(val)),
            "n_drop": int(y_val.sum()),
            "n_lots": int(len(np.unique(lots))),
            "n_war_rows": int(war.sum()),
            "log_loss": round(float(log_loss_val), 4),
            "log_loss_ci": [round(float(v), 4) for v in log_loss_ci] if log_loss_ci else None,
            "brier": round(float(brier_val), 4),
            "auc": round(float(auc_val), 4) if auc_val is not None else None,
            "war_log_loss": round(float(war_ll), 4) if war_ll is not None else None,
            "war_log_loss_ci": [round(float(v), 4) for v in war_ll_ci] if war_ll_ci else None,
            "delta_vs_lgbm_ci": [round(float(v), 4) for v in delta_ci] if delta_ci else None,
        }

    # Write lora_scores.json
    scores_out = ROOT / "data" / "processed" / "l3" / "lora_scores.json"
    scores_out.parent.mkdir(parents=True, exist_ok=True)
    if args.limit:
        print("--limit smoke run: scores not saved")
        return 0
    all_scores = json.loads(scores_out.read_text(encoding="utf-8")) if scores_out.exists() else {}
    all_scores[tag_name] = {
        "config": {
            "base": args.base,
            "epochs": args.epochs,
            "lr": args.lr,
            "batch": args.batch,
            "max_len": args.max_len,
            "seed": args.seed,
            "zero_identity": args.zero_identity,
            "pos_weight": args.pos_weight,
        },
        "base_model": args.base,
        "contamination": contamination_by_season,
        "timings": timings,
        "metrics": metrics_by_season,
    }
    scores_out.write_text(json.dumps(all_scores, indent=2), encoding="utf-8")
    print(f"Wrote scores to {scores_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

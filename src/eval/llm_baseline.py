"""Single-prompt LLM baseline (L2): one prompt per called player, no agents, no simulation.

The model sees only what was public before the auction: the player's role, overseas flag, capped
flag, base price, last IPL hammer price (earlier auctions only), and each team's purse, open slots
and open overseas slots after retentions. It answers in JSON: P(sold), an 80% price range with a
median, and its three likeliest buyers.

Two variants (register D1, "named vs anonymised"):
  named  the player's real name is in the prompt
  anon   the name is replaced by "Player <n>"
If named clearly beats anon on the same lots, the model is probably recalling the real result.

Contamination: every result carries contamination.status(model, season). For qwen2/qwen2.5 the
2023 and 2024 seasons are "possibly_contaminated"; never report them as clean (rule #8).
Same local model as the arena; never Gemini (rule #9).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.eval import contamination, lot_baselines as lb

TEAMS = ["CSK", "DC", "GT", "KKR", "LSG", "MI", "PBKS", "RCB", "RR", "SRH"]

SCHEMA = {
    "type": "object",
    "properties": {
        "p_sold": {"type": "number"},
        "price_lakh_p10": {"type": "number"},
        "price_lakh_median": {"type": "number"},
        "price_lakh_p90": {"type": "number"},
        "likely_buyers": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["p_sold", "price_lakh_p10", "price_lakh_median", "price_lakh_p90", "likely_buyers"],
}

SYSTEM = ("You are an IPL auction analyst. You predict one player's outcome in a mini-auction using only "
          "the facts given. Money is in lakhs of rupees (100 lakh = 1 crore). Reply with JSON only.")


def team_table(state: dict) -> str:
    rows = ["team | purse left (lakh) | open slots | open overseas slots"]
    for t in TEAMS:
        v = state["teams"][t]
        rows.append(f"{t} | {v['purse_left_lakh']} | {v['slots_left']} | {v['overseas_slots_left']}")
    return "\n".join(rows)


def build_prompt(lot: dict, season: int, teams: str, anon_id: int | None = None) -> str:
    name = f"Player {anon_id}" if anon_id is not None else lot["player"]
    lp = lot.get("last_price")
    last = (f"{int(lp)} lakh (his most recent IPL auction price since 2022)"
            if lp is not None and pd.notna(lp) else "not recorded (records start with the 2022 auction)")
    return (
        f"IPL {season} season mini-auction. Teams after retentions:\n{teams}\n\n"
        f"Player: {name}\n"
        f"Role: {lot['role'] if pd.notna(lot['role']) else 'unknown'}\n"
        f"Overseas: {'yes' if lot['overseas'] else 'no'}\n"
        f"Capped: {'yes' if lot['capped'] else 'no'}\n"
        f"Base price: {int(lot['base_lakh'])} lakh\n"
        f"Last IPL price: {last}\n\n"
        "Predict:\n"
        "- p_sold: probability (0 to 1) that he is sold\n"
        "- price_lakh_p10, price_lakh_median, price_lakh_p90: his hammer price in lakh IF sold "
        "(80% range and median; never below the base price)\n"
        "- likely_buyers: the three team codes most likely to buy him, most likely first\n"
        "Answer as a JSON object with exactly those keys."
    )


def parse(data: dict | None, base: float, purse_rank: list[str]) -> tuple[dict, bool]:
    """Clean one answer. Returns (prediction, valid). Invalid answers fall back to the base-price
    baseline (p_sold 0.5, price = base, buyers by purse) and are counted, never hidden."""
    try:
        p = float(data["p_sold"])
        q = sorted(float(data[k]) for k in ("price_lakh_p10", "price_lakh_median", "price_lakh_p90"))
        buyers = [str(b).strip().upper() for b in data["likely_buyers"]]
        if not (np.isfinite(p) and all(np.isfinite(q))):
            raise ValueError
    except (TypeError, KeyError, ValueError):
        return {"p_sold": 0.5, "point": base, "lo": base, "hi": base, "ranking": purse_rank}, False
    p = min(max(p if p <= 1 else p / 100, 0.01), 0.99)       # "70" -> 0.70
    lo, mid, hi = (max(x, base) for x in q)
    seen, ranking = set(), []
    for b in buyers + purse_rank:                            # valid codes first, then fill by purse
        if b in TEAMS and b not in seen:
            seen.add(b)
            ranking.append(b)
    return {"p_sold": p, "point": mid, "lo": lo, "hi": hi, "ranking": ranking}, True


def lots_for(m: pd.DataFrame, season: int) -> pd.DataFrame:
    """Called lots of one season with their as-of facts (last price from earlier seasons only)."""
    hist = m[(m["season"] < season) & (m["sold"] == 1)].sort_values("season")
    last = hist.groupby("key")["hammer_lakh"].last().to_dict()
    lots = m[m["season"] == season].copy().reset_index(drop=True)
    lots["last_price"] = lots["key"].map(last)
    lots["overseas"] = lots["nationality"].fillna("").str.lower().ne("india")
    lots["capped"] = lots["capped"].astype(str).str.lower().isin(["capped", "true", "1"])
    return lots


def predict(client, m: pd.DataFrame, season: int, state: dict, variant: str, seed: int = 0,
            log=print) -> tuple[pd.DataFrame, dict]:
    assert variant in ("named", "anon")
    status = contamination.status(client.model, season)
    lots = lots_for(m, season)
    teams = team_table(state)
    purses = {t: state["teams"][t]["purse_left_lakh"] for t in TEAMS}
    purse_rank = sorted(purses, key=lambda t: (-purses[t], t))
    rows, invalid = [], 0
    for i, lot in lots.iterrows():
        prompt = build_prompt(lot.to_dict(), season, teams, anon_id=i + 1 if variant == "anon" else None)
        res = client.generate_json(prompt, schema=SCHEMA, seed=seed, num_predict=160, system=SYSTEM)
        pred, ok = parse(res.data, float(lot["base_lakh"]), purse_rank)
        invalid += not ok
        rows.append({"player": lot["player"], "sold": lot["sold"], "winner": lot["winner"],
                     "hammer_lakh": lot["hammer_lakh"], **pred})
        if (i + 1) % 10 == 0:
            log(f"  {season} {variant}: {i + 1}/{len(lots)} (cache hits {client.hits}, calls {client.calls})")
    meta = {"model": client.model, "variant": variant, "season": season, "contamination": status,
            "n_lots": len(lots), "n_invalid": invalid, "seed": seed}
    return pd.DataFrame(rows), meta


def to_jsonable(df: pd.DataFrame) -> str:
    out = df.copy()
    out["ranking"] = out["ranking"].map(json.dumps)
    return out.to_csv(index=False)

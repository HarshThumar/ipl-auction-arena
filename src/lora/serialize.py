"""L3 LoRA prompt serialization.

Converts a decision state row into a fixed, neutral, numeric prompt card.
Deterministic, leak-free, contains team-identity tokens, no player names or forbidden features.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from src.eval.decision_baselines import FEATURES, FORBIDDEN

FRANCHISE_TEAMS = ("CSK", "DC", "GT", "KKR", "LSG", "MI", "PBKS", "RCB", "RR", "SRH")
TEAM_TOKENS: list[str] = [f"<{t}>" for t in FRANCHISE_TEAMS] + ["<OTHER>"]
TARGETS: tuple[str, str] = (" RAISE", " DROP")

MONEY_COLS = {
    "base_price_lakhs",
    "current_price_lakhs",
    "next_increment_lakhs",
    "spend_so_far_lakhs",
    "purse_left_lakhs",
    "rival_purse_left_lakhs",
    "same_role_avg_base",
    "purse_minus_rival_purse",
}


def team_token(franchise_id: Any) -> str:
    """Return franchise token e.g. '<CSK>' or '<OTHER>' for any unlisted franchise/missing."""
    if franchise_id is None or pd.isna(franchise_id):
        return "<OTHER>"
    fid = str(franchise_id).strip().upper()
    if fid in FRANCHISE_TEAMS:
        return f"<{fid}>"
    return "<OTHER>"


def _is_missing(val: Any) -> bool:
    if val is None:
        return True
    if pd.isna(val):
        return True
    s = str(val).strip().lower()
    return s in ("", "none", "nan", "unknown", "<na>")


def _fmt_money(val: Any) -> str:
    if _is_missing(val):
        return "unknown"
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return "unknown"
        return f"{int(round(f))} lakh"
    except (ValueError, TypeError):
        return "unknown"


def _fmt_int(val: Any) -> str:
    if _is_missing(val):
        return "unknown"
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return "unknown"
        return f"{int(round(f))}"
    except (ValueError, TypeError):
        return "unknown"


def _fmt_float(val: Any, decimals: int = 2) -> str:
    if _is_missing(val):
        return "unknown"
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return "unknown"
        return f"{f:.{decimals}f}"
    except (ValueError, TypeError):
        return "unknown"


def _fmt_str(val: Any) -> str:
    if _is_missing(val):
        return "unknown"
    return str(val).strip()


def row_to_prompt(row: dict | pd.Series, zero_identity: bool = False) -> str:
    """Format a decision row as a fixed, neutral, numeric text card.

    Starts with deciding team's token, includes rival's token.
    Money as integer lakhs with the word 'lakh'.
    Missing values written as 'unknown'.
    Ends with 'Decision:'.
    Contains ONLY features from decision_baselines.FEATURES; forbidden columns excluded.
    Deterministic: same row -> same string.
    If zero_identity is True, replaces both team tokens with '<OTHER>'.
    """
    if isinstance(row, pd.Series):
        row = row.to_dict()

    # Team identity tokens
    if zero_identity:
        deciding_token = "<OTHER>"
        rival_token = "<OTHER>"
    else:
        deciding_token = team_token(row.get("franchise_id"))
        rival_token = team_token(row.get("rival_id"))

    curr_p = row.get("current_price_lakhs")
    base_p = row.get("base_price_lakhs")
    purse_p = row.get("purse_left_lakhs")
    rival_p = row.get("rival_purse_left_lakhs")

    # Derived features logic (matches decision_baselines.make_X if not precomputed)
    pob = row.get("price_over_base")
    if _is_missing(pob) and not _is_missing(curr_p) and not _is_missing(base_p):
        try:
            pob = float(curr_p) / max(float(base_p), 1.0)
        except (ValueError, ZeroDivisionError):
            pob = None

    psop = row.get("price_share_of_purse")
    if _is_missing(psop) and not _is_missing(curr_p) and not _is_missing(purse_p):
        try:
            psop = float(curr_p) / max(float(purse_p), 1.0)
        except (ValueError, ZeroDivisionError):
            psop = None

    pmrp = row.get("purse_minus_rival_purse")
    if _is_missing(pmrp) and not _is_missing(purse_p) and not _is_missing(rival_p):
        try:
            pmrp = float(purse_p) - float(rival_p)
        except (ValueError, TypeError):
            pmrp = None

    lines = [
        deciding_token,
        f"Rival: {rival_token}",
        f"Era: {_fmt_str(row.get('era'))}",
        f"Role: {_fmt_str(row.get('role'))}",
        f"Overseas: {_fmt_int(row.get('is_overseas'))}",
        f"Capped: {_fmt_int(row.get('capped'))}",
        f"Base price: {_fmt_money(base_p)}",
        f"Current price: {_fmt_money(curr_p)}",
        f"Next increment: {_fmt_money(row.get('next_increment_lakhs'))}",
        f"Step index: {_fmt_int(row.get('step_index'))}",
        f"Set no: {_fmt_int(row.get('set_no'))}",
        f"Lots done: {_fmt_int(row.get('lots_done'))}",
        f"Spend so far: {_fmt_money(row.get('spend_so_far_lakhs'))}",
        f"Spend pace vs expected: {_fmt_float(row.get('spend_pace_vs_expected'))}",
        f"Purse left: {_fmt_money(purse_p)}",
        f"Slots left: {_fmt_int(row.get('slots_left'))}",
        f"Overseas left: {_fmt_int(row.get('overseas_left'))}",
        f"Role gap: {_fmt_int(row.get('role_gap'))}",
        f"Is final two: {_fmt_int(row.get('is_final_two'))}",
        f"Rival purse left: {_fmt_money(rival_p)}",
        f"Rival slots left: {_fmt_int(row.get('rival_slots_left'))}",
        f"Rival role gap: {_fmt_int(row.get('rival_role_gap'))}",
        f"Active estimate: {_fmt_int(row.get('n_active_estimate'))}",
        f"Same role remaining: {_fmt_int(row.get('same_role_remaining'))}",
        f"Same role avg base: {_fmt_money(row.get('same_role_avg_base'))}",
        f"Price over base: {_fmt_float(pob)}",
        f"Price share of purse: {_fmt_float(psop, decimals=4)}",
        f"Purse minus rival purse: {_fmt_money(pmrp)}",
        "Decision:",
    ]
    return "\n".join(lines)

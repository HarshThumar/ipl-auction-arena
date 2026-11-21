"""Tests for L3 LoRA pipeline (docs/levels.md row L3, docs/L3-decision-dataset-spec.md).

All synthetic, no network, no model download.
Torch tests skip gracefully when torch is missing.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from scripts.train_lora import check_seasons
from src.eval.decision_baselines import FEATURES, FORBIDDEN
from src.lora.serialize import TARGETS, TEAM_TOKENS, row_to_prompt, team_token


def _make_synthetic_row(
    franchise_id="CSK",
    rival_id="MI",
    era="2022-24",
    role="BAT",
    is_overseas=0,
    capped=1,
    base_price_lakhs=200,
    current_price_lakhs=500,
    next_increment_lakhs=20,
    step_index=3,
    set_no=1,
    lots_done=4,
    spend_so_far_lakhs=1200,
    spend_pace_vs_expected=1.05,
    purse_left_lakhs=7500,
    slots_left=15,
    overseas_left=6,
    role_gap=2,
    is_final_two=1,
    rival_purse_left_lakhs=6000,
    rival_slots_left=12,
    rival_role_gap=1,
    n_active_estimate=2,
    same_role_remaining=8,
    same_role_avg_base=150,
    **extra,
) -> dict:
    row = {
        "franchise_id": franchise_id,
        "rival_id": rival_id,
        "era": era,
        "role": role,
        "is_overseas": is_overseas,
        "capped": capped,
        "base_price_lakhs": base_price_lakhs,
        "current_price_lakhs": current_price_lakhs,
        "next_increment_lakhs": next_increment_lakhs,
        "step_index": step_index,
        "set_no": set_no,
        "lots_done": lots_done,
        "spend_so_far_lakhs": spend_so_far_lakhs,
        "spend_pace_vs_expected": spend_pace_vs_expected,
        "purse_left_lakhs": purse_left_lakhs,
        "slots_left": slots_left,
        "overseas_left": overseas_left,
        "role_gap": role_gap,
        "is_final_two": is_final_two,
        "rival_purse_left_lakhs": rival_purse_left_lakhs,
        "rival_slots_left": rival_slots_left,
        "rival_role_gap": rival_role_gap,
        "n_active_estimate": n_active_estimate,
        "same_role_remaining": same_role_remaining,
        "same_role_avg_base": same_role_avg_base,
    }
    row.update(extra)
    return row


# ---------- Serializer tests ----------


def test_team_tokens():
    expected_franchises = ["CSK", "DC", "GT", "KKR", "LSG", "MI", "PBKS", "RCB", "RR", "SRH"]
    for f in expected_franchises:
        assert f"<{f}>" in TEAM_TOKENS
        assert team_token(f) == f"<{f}>"
        assert team_token(f.lower()) == f"<{f}>"

    assert "<OTHER>" in TEAM_TOKENS
    assert team_token("DECCAN") == "<OTHER>"
    assert team_token("KTK") == "<OTHER>"
    assert team_token("UNKNOWN_TEAM") == "<OTHER>"
    assert team_token(None) == "<OTHER>"
    assert team_token(float("nan")) == "<OTHER>"


def test_serializer_no_forbidden_and_deterministic():
    forbidden_sample = {
        "player": "Test Star Player",
        "season": 1993,
        "lot_id": "1993-L99-teststar",
        "action": "SECRET_ACTION",
        "contested": True,
        "confidence": "SECRET_CONFIDENCE",
        "final_price": 9999,
        "winner": "SECRET_WINNER",
        "final_two": ["SEC1", "SEC2"],
        "hammer_lakh": 8888,
        "paid_lakh": 7777,
    }
    row = _make_synthetic_row(**forbidden_sample)

    p1 = row_to_prompt(row)
    p2 = row_to_prompt(row)

    # Deterministic: same row -> same string
    assert p1 == p2

    # Starts with deciding team token, includes rival token, ends with Decision:
    assert p1.startswith("<CSK>")
    assert "Rival: <MI>" in p1
    assert p1.endswith("Decision:")

    # Money formatted as integer lakhs with the word "lakh"
    assert "Base price: 200 lakh" in p1
    assert "Current price: 500 lakh" in p1
    assert "Next increment: 20 lakh" in p1
    assert "Purse left: 7500 lakh" in p1

    # MUST NOT contain: player name, season, lot_id, or anything in FORBIDDEN
    assert "Test Star Player" not in p1
    assert "1993-L99-teststar" not in p1
    assert "1993" not in p1
    assert "SECRET_ACTION" not in p1
    assert "SECRET_CONFIDENCE" not in p1
    assert "SECRET_WINNER" not in p1
    assert "SEC1" not in p1
    assert "SEC2" not in p1
    assert "9999" not in p1
    assert "8888" not in p1
    assert "7777" not in p1

    for forb in FORBIDDEN:
        # Check that the forbidden key label is not in the text card
        assert f"{forb}:" not in p1.lower()


def test_serializer_missing_values_and_zero_identity():
    # Missing numeric values -> written as "unknown"
    row = _make_synthetic_row(
        franchise_id="RCB",
        rival_id=None,
        rival_purse_left_lakhs=None,
        spend_pace_vs_expected=float("nan"),
        role_gap=None,
    )
    prompt = row_to_prompt(row)
    assert prompt.startswith("<RCB>")
    assert "Rival: <OTHER>" in prompt
    assert "Rival purse left: unknown" in prompt
    assert "Spend pace vs expected: unknown" in prompt
    assert "Role gap: unknown" in prompt

    # Ablation: zero_identity replaces both team tokens with <OTHER>
    p_zero = row_to_prompt(row, zero_identity=True)
    assert p_zero.startswith("<OTHER>")
    assert "Rival: <OTHER>" in p_zero


def test_synthetic_dataframe_features():
    """Verify serializer works on synthetic DataFrame using FEATURES columns without reading disk."""
    records = [_make_synthetic_row(franchise_id="GT", rival_id="RR", current_price_lakhs=300 + 10 * i) for i in range(5)]
    df = pd.DataFrame(records)
    for col in FEATURES:
        if col not in df.columns:
            # Derived columns might not be in raw records; make sure df has them or serializer handles them
            pass

    for _, r in df.iterrows():
        p = row_to_prompt(r)
        assert p.startswith("<GT>")
        assert "Rival: <RR>" in p
        assert p.endswith("Decision:")


# ---------- Model functions tests (torch required) ----------


def test_restricted_logprobs():
    torch = pytest.importorskip("torch")
    from src.lora.model import restricted_logprobs

    # Shape [2, 8] logits
    logits = torch.tensor(
        [
            [1.0, 2.0, 10.0, 3.0, 4.0, 5.0, 12.0, 0.0],  # sample 0: raise_id=2 (10), drop_id=6 (12)
            [5.0, 0.0, 8.0, 1.0, 2.0, 3.0, 8.0, 0.0],   # sample 1: raise_id=2 (8), drop_id=6 (8)
        ]
    )
    raise_id = 2
    drop_id = 6

    logp2 = restricted_logprobs(logits, raise_id, drop_id)

    assert logp2.shape == (2, 2)
    # Exponentiated probabilities sum to 1.0 along dim 1
    probs = torch.exp(logp2)
    assert torch.allclose(probs.sum(dim=-1), torch.tensor([1.0, 1.0]), atol=1e-5)

    # Sample 0: logits [10.0, 12.0]
    expected_0_1 = 12.0 - math.log(math.exp(10.0) + math.exp(12.0))
    assert math.isclose(logp2[0, 1].item(), expected_0_1, rel_tol=1e-5)

    # Sample 1: equal logits [8.0, 8.0] -> P(DROP) = 0.5
    assert math.isclose(probs[1, 1].item(), 0.5, rel_tol=1e-5)


def test_weighted_bce_loss():
    torch = pytest.importorskip("torch")
    from src.lora.model import weighted_bce_loss

    # Two samples: sample 0 is RAISE (0), sample 1 is DROP (1)
    p_drop_0 = 0.2
    p_drop_1 = 0.7
    logp2 = torch.tensor(
        [
            [math.log(1 - p_drop_0), math.log(p_drop_0)],
            [math.log(1 - p_drop_1), math.log(p_drop_1)],
        ],
        dtype=torch.float32,
    )
    y = torch.tensor([0, 1], dtype=torch.float32)
    pos_weight = 4.0

    loss = weighted_bce_loss(logp2, y, pos_weight)

    loss_0 = - (0.0 + 1.0 * math.log(1 - p_drop_0))
    loss_1 = - (pos_weight * 1.0 * math.log(p_drop_1) + 0.0)
    expected_loss = (loss_0 + loss_1) / 2.0

    assert math.isclose(loss.item(), expected_loss, rel_tol=1e-5)


# ---------- Split validation tests (no torch needed) ----------


def test_check_seasons_accepts_clean_and_refuses_held_out():
    # Valid forward split
    check_seasons([2018, 2019, 2020, 2021, 2022], [2023, 2024])

    # 2025 in train -> hard refuse (SystemExit 2)
    with pytest.raises(SystemExit) as exc_info:
        check_seasons([2018, 2022, 2025], [2024])
    assert exc_info.value.code == 2

    # 2026 in train -> hard refuse (SystemExit 2)
    with pytest.raises(SystemExit) as exc_info:
        check_seasons([2018, 2026], [2024])
    assert exc_info.value.code == 2

    # 2025 in val -> hard refuse (SystemExit 2)
    with pytest.raises(SystemExit) as exc_info:
        check_seasons([2018, 2022], [2025])
    assert exc_info.value.code == 2

    # 2026 in val -> hard refuse (SystemExit 2)
    with pytest.raises(SystemExit) as exc_info:
        check_seasons([2018, 2022], [2026])
    assert exc_info.value.code == 2

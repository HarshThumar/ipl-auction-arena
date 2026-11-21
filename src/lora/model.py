"""L3 LoRA model architecture and training loss.

All torch, transformers, and peft imports are deferred inside functions so this module
can be imported in environments where ML packages are not installed.
"""
from __future__ import annotations

import inspect
from typing import Any


def restricted_logprobs(logits_last: Any, raise_id: int, drop_id: int) -> Any:
    """Return log-softmax over just the RAISE and DROP token logits (shape [B, 2]).

    Column 0 corresponds to RAISE, Column 1 corresponds to DROP.
    P(DROP) = exp of column 1.
    """
    import torch

    if logits_last.ndim == 1:
        logits_last = logits_last.unsqueeze(0)
    sub_logits = logits_last[:, [raise_id, drop_id]]
    return torch.log_softmax(sub_logits, dim=-1)


def weighted_bce_loss(logp2: Any, y: Any, pos_weight: Any) -> Any:
    """Weighted binary cross entropy loss for class imbalance (~8% DROP).

    logp2: shape [B, 2] (log probabilities of RAISE and DROP)
    y: binary labels (0 for RAISE, 1 for DROP)
    pos_weight: multiplier for positive class (DROP = 1)
    """
    import torch

    y_flat = y.view(-1).float()
    log_p_raise = logp2[:, 0]
    log_p_drop = logp2[:, 1]

    if not isinstance(pos_weight, torch.Tensor):
        pos_weight = torch.tensor(pos_weight, device=logp2.device, dtype=logp2.dtype)

    loss = -(pos_weight * y_flat * log_p_drop + (1.0 - y_flat) * log_p_raise).mean()
    return loss


def build(base_model: str, r: int = 16, alpha: int = 32, dropout: float = 0.05) -> tuple[Any, Any, tuple[int, int]]:
    """Load tokenizer + causal LM, add team tokens as special tokens, resize embeddings,
    wrap with peft LoRA on attention + MLP projections, and make the new team-token
    embedding rows trainable.

    Returns:
        (model, tokenizer, (raise_id, drop_id))
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model
    from src.lora.serialize import TARGETS, TEAM_TOKENS

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    num_added = tokenizer.add_special_tokens({"additional_special_tokens": TEAM_TOKENS})

    model = AutoModelForCausalLM.from_pretrained(base_model, trust_remote_code=True)
    if num_added > 0:
        model.resize_token_embeddings(len(tokenizer))

    # Assert RAISE and DROP each tokenize to a single first token; use the first token id if not
    raise_ids = tokenizer.encode(TARGETS[0], add_special_tokens=False)
    drop_ids = tokenizer.encode(TARGETS[1], add_special_tokens=False)
    assert len(raise_ids) >= 1, f"Empty tokenization for target {TARGETS[0]}"
    assert len(drop_ids) >= 1, f"Empty tokenization for target {TARGETS[1]}"
    raise_id = raise_ids[0]
    drop_id = drop_ids[0]
    assert raise_id != drop_id, "RAISE and DROP share a first token; change TARGETS"

    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

    lora_kwargs = dict(
        r=r,
        lora_alpha=alpha,
        lora_dropout=dropout,
        target_modules=target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )

    team_token_ids = [tokenizer.convert_tokens_to_ids(t) for t in TEAM_TOKENS]
    sig = inspect.signature(LoraConfig.__init__)
    if "trainable_token_indices" in sig.parameters:
        lora_kwargs["trainable_token_indices"] = team_token_ids
    else:
        # Fallback: make embedding layer trainable via modules_to_save
        lora_kwargs["modules_to_save"] = ["embed_tokens"]

    peft_config = LoraConfig(**lora_kwargs)
    peft_model = get_peft_model(model, peft_config)

    return peft_model, tokenizer, (raise_id, drop_id)

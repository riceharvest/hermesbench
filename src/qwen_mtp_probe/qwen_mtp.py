"""HF-native helpers for manually attaching and training Qwen MTP modules.

Stock Transformers Qwen3.5/Qwen3.6 MoE loaders currently ignore checkpoint keys
matching ``mtp.*``. This module reconstructs the one-layer MTP block using the same
Transformers Qwen MoE building blocks and exposes small utilities for loading,
freezing, masking, and computing future-token losses.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import torch
from torch import Tensor, nn


@dataclass(frozen=True)
class MTPForwardInputs:
    """Position/mask tensors needed by the manual MTP decoder layer."""

    position_ids: Tensor
    rope_position_ids: Tensor
    position_embeddings: tuple[Tensor, Tensor]
    causal_mask: Tensor


def has_mtp_component(name: str) -> bool:
    """Return true when ``mtp`` is a dot-path component in a parameter/key name."""

    return "mtp" in name.split(".")


def checkpoint_mtp_weight_map(index: Mapping[str, Any]) -> dict[str, str]:
    """Extract ``mtp.*`` tensor -> shard-file entries from a safetensors index."""

    weight_map = index.get("weight_map", {})
    return {name: shard for name, shard in weight_map.items() if has_mtp_component(name)}


class ManualQwenMTP(nn.Module):
    """One-layer Qwen3.5/Qwen3.6 MoE MTP block reconstructed for HF training.

    The checkpoint exposes keys like ``mtp.pre_fc_norm_embedding.weight``,
    ``mtp.fc.weight``, ``mtp.layers.0.*`` and ``mtp.norm.weight``. This class uses
    matching local names after removing the ``mtp.`` prefix, so ``load_state_dict``
    can load those tensors directly.
    """

    def __init__(self, text_config: Any):
        super().__init__()
        try:
            from transformers.models.qwen3_5_moe.modeling_qwen3_5_moe import (
                Qwen3_5MoeDecoderLayer,
                Qwen3_5MoeRMSNorm,
            )
        except Exception as exc:  # pragma: no cover - depends on installed transformers build
            raise RuntimeError(
                "ManualQwenMTP requires a Transformers build with qwen3_5_moe modeling code"
            ) from exc

        self.config = text_config
        self.pre_fc_norm_embedding = Qwen3_5MoeRMSNorm(
            text_config.hidden_size, eps=text_config.rms_norm_eps
        )
        self.pre_fc_norm_hidden = Qwen3_5MoeRMSNorm(
            text_config.hidden_size, eps=text_config.rms_norm_eps
        )
        self.fc = nn.Linear(text_config.hidden_size * 2, text_config.hidden_size, bias=False)

        mtp_config = copy.deepcopy(text_config)
        mtp_config.num_hidden_layers = 1
        mtp_config.layer_types = ["full_attention"]
        self.layers = nn.ModuleList([Qwen3_5MoeDecoderLayer(mtp_config, 0)])
        self.norm = Qwen3_5MoeRMSNorm(text_config.hidden_size, eps=text_config.rms_norm_eps)

    def forward(
        self,
        input_embeds: Tensor,
        hidden_states: Tensor,
        *,
        position_embeddings: tuple[Tensor, Tensor],
        attention_mask: Tensor,
        position_ids: Tensor,
    ) -> Tensor:
        input_embeds = self.pre_fc_norm_embedding(input_embeds)
        hidden_states = self.pre_fc_norm_hidden(hidden_states)
        hidden_states = torch.cat([input_embeds, hidden_states], dim=-1)
        hidden_states = self.fc(hidden_states)
        hidden_states = self.layers[0](
            hidden_states,
            position_embeddings=position_embeddings,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_values=None,
            use_cache=False,
        )
        return self.norm(hidden_states)


def text_model_from_causal_lm(model: nn.Module) -> nn.Module:
    """Return the inner text model for Qwen causal-LM wrappers."""

    inner = getattr(model, "model", model)
    return getattr(inner, "language_model", inner)


def build_manual_qwen_mtp(model: nn.Module) -> ManualQwenMTP:
    """Construct a manual MTP block on the same device/dtype as a loaded base model."""

    text_model = text_model_from_causal_lm(model)
    first_param = next(model.parameters())
    return ManualQwenMTP(text_model.config).to(first_param.device, dtype=first_param.dtype)


def load_mtp_checkpoint_state(
    mtp: nn.Module,
    *,
    model_name: str,
    mtp_weight_map: Mapping[str, str],
    hf_hub_download: Callable[..., str],
    safetensors_load_file: Callable[..., Mapping[str, Tensor]],
) -> dict[str, Tensor]:
    """Download/load checkpoint MTP tensors that match a manual MTP module.

    ``hf_hub_download`` and ``safetensors_load_file`` are injected so tests can use
    fake shards without importing Hugging Face or safetensors.
    """

    local_keys = set(mtp.state_dict())
    loaded: dict[str, Tensor] = {}
    for shard in sorted(set(mtp_weight_map.values())):
        path = hf_hub_download(model_name, shard)
        shard_tensors = safetensors_load_file(path, device="cpu")
        for ckpt_name, ckpt_shard in mtp_weight_map.items():
            if ckpt_shard != shard:
                continue
            local_name = ckpt_name.removeprefix("mtp.")
            if local_name in local_keys:
                loaded[local_name] = shard_tensors[ckpt_name]
    return loaded


def freeze_base_train_mtp(base_model: nn.Module, mtp: nn.Module) -> list[str]:
    """Freeze base model parameters and leave only manual MTP parameters trainable."""

    for param in base_model.parameters():
        param.requires_grad_(False)
    trainable: list[str] = []
    for name, param in mtp.named_parameters():
        param.requires_grad_(True)
        trainable.append(name)
    return trainable


def build_mtp_forward_inputs(
    text_model: nn.Module,
    input_ids: Tensor,
    hidden_states: Tensor,
    attention_mask: Tensor | None,
) -> MTPForwardInputs:
    """Create text-only Qwen rotary positions and a 4D causal mask for MTP forward."""

    bsz, seq_len = input_ids.shape
    device = hidden_states.device
    position_ids = torch.arange(seq_len, device=device).view(1, -1).expand(bsz, -1)
    # Qwen3.5/3.6 multimodal-safe rotary path expects [3, batch, seq] positions.
    rope_position_ids = position_ids[None, ...].expand(3, bsz, -1)
    position_embeddings = text_model.rotary_emb(hidden_states, rope_position_ids)
    causal_mask = build_4d_causal_mask(
        attention_mask=attention_mask,
        batch_size=bsz,
        seq_len=seq_len,
        dtype=hidden_states.dtype,
        device=device,
    )
    return MTPForwardInputs(position_ids, rope_position_ids, position_embeddings, causal_mask)


def build_4d_causal_mask(
    *,
    attention_mask: Tensor | None,
    batch_size: int,
    seq_len: int,
    dtype: torch.dtype,
    device: torch.device,
) -> Tensor:
    """Build an additive [batch, 1, query, key] causal+padding mask.

    This replaces the earlier ``None`` smoke mask and matches the mask shape used by
    eager HF decoder layers. Masked logits receive the minimum finite value for the
    model dtype.
    """

    min_dtype = torch.finfo(dtype).min
    mask = torch.full((seq_len, seq_len), min_dtype, dtype=dtype, device=device)
    mask = torch.triu(mask, diagonal=1)
    mask = mask[None, None, :, :].expand(batch_size, 1, seq_len, seq_len).clone()

    if attention_mask is not None:
        padding = attention_mask.to(device=device, dtype=torch.bool)
        if padding.shape != (batch_size, seq_len):
            raise ValueError("attention_mask must have shape [batch, seq]")
        mask = mask.masked_fill(~padding[:, None, None, :], min_dtype)
    return mask


def mtp_future_token_loss(
    mtp_logits: Tensor,
    labels: Tensor,
    *,
    depth: int = 2,
    ignore_index: int = -100,
) -> Tensor:
    """Cross entropy where logits at position ``t`` predict label ``t + depth``."""

    if mtp_logits.ndim != 3 or labels.ndim != 2:
        raise ValueError("expected mtp_logits [batch, seq, vocab] and labels [batch, seq]")
    if mtp_logits.shape[:2] != labels.shape:
        raise ValueError("mtp_logits and labels batch/sequence dimensions must match")
    if depth >= mtp_logits.shape[1]:
        raise ValueError("depth must be smaller than sequence length")
    usable_logits = mtp_logits[:, :-depth, :].contiguous()
    target_labels = labels[:, depth:].contiguous()
    return torch.nn.functional.cross_entropy(
        usable_logits.view(-1, usable_logits.shape[-1]),
        target_labels.contiguous().view(-1),
        ignore_index=ignore_index,
    )


def nonzero_grad_norms(module: nn.Module) -> dict[str, float]:
    """Return nonzero gradient norms for a module's parameters."""

    norms: dict[str, float] = {}
    for name, param in module.named_parameters():
        if param.grad is None:
            continue
        norm = float(param.grad.detach().norm().cpu())
        if norm > 0:
            norms[name] = norm
    return norms

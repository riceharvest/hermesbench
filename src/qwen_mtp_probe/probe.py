"""Utilities for probing whether Qwen-style MTP modules can be trained.

The functions in this module are deliberately small and framework-light so they can be
unit-tested on toy modules before being used against a large HF checkpoint.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import torch
import torch.nn.functional as F
from torch import Tensor, nn


@dataclass
class ProbeReport:
    model_name: str
    mtp_parameter_count: int
    mtp_parameters: list[str]
    trainable_mtp_parameters: list[str]
    mtp_gradient_norms: dict[str, float]
    has_nonzero_mtp_gradient: bool


def discover_mtp_parameters(model: nn.Module) -> list[str]:
    """Return parameter names belonging to MTP modules.

    Qwen3.6 exposes its MTP block under names like ``mtp.fc.weight`` and
    ``mtp.layers.0.self_attn.q_proj.weight``. Matching on path components avoids
    accidental matches such as ``attempt``.
    """

    return [name for name, _ in model.named_parameters() if _has_mtp_component(name)]


def set_trainable_mtp_only(model: nn.Module, *, train_lm_head: bool = False) -> list[str]:
    """Freeze all parameters except MTP modules, optionally keeping lm_head trainable."""

    trainable: list[str] = []
    for name, param in model.named_parameters():
        should_train = _has_mtp_component(name) or (train_lm_head and name.startswith("lm_head."))
        param.requires_grad_(should_train)
        if should_train:
            trainable.append(name)
    return trainable


def compute_next_token_loss(logits: Tensor, labels: Tensor, *, ignore_index: int = -100) -> Tensor:
    """Standard causal-LM next-token cross entropy."""

    if logits.ndim != 3 or labels.ndim != 2:
        raise ValueError("expected logits [batch, seq, vocab] and labels [batch, seq]")
    if logits.shape[:2] != labels.shape:
        raise ValueError("logits and labels batch/sequence dimensions must match")
    return _shifted_ce(logits, labels, depth=1, ignore_index=ignore_index)


def compute_mtp_aux_loss(
    mtp_logits: Tensor | Sequence[Tensor],
    labels: Tensor,
    *,
    depth: int | Sequence[int] = 2,
    ignore_index: int = -100,
) -> Tensor:
    """Cross entropy for one or more future-token MTP prediction heads.

    ``depth=2`` means logits at position ``t`` are trained against label ``t+2``.
    For multiple heads, pass matching sequences of logits and depths; their losses
    are averaged, matching common MTP formulations before applying an external
    scaling factor.
    """

    logits_list = _as_list(mtp_logits)
    depths = _normalize_depths(depth, len(logits_list))
    if labels.ndim != 2:
        raise ValueError("expected labels [batch, seq]")

    losses = [
        _shifted_ce(logits, labels, depth=current_depth, ignore_index=ignore_index)
        for logits, current_depth in zip(logits_list, depths, strict=True)
    ]
    return torch.stack(losses).mean()


def combined_loss(
    logits: Tensor,
    labels: Tensor,
    mtp_logits: Tensor | Sequence[Tensor] | None,
    *,
    mtp_depth: int | Sequence[int] = 2,
    mtp_weight: float = 0.1,
    ignore_index: int = -100,
) -> Tensor:
    """Main next-token loss plus optional weighted MTP auxiliary loss."""

    main = compute_next_token_loss(logits, labels, ignore_index=ignore_index)
    if mtp_logits is None or mtp_weight == 0:
        return main
    aux = compute_mtp_aux_loss(mtp_logits, labels, depth=mtp_depth, ignore_index=ignore_index)
    return main + mtp_weight * aux


def collect_gradient_norms(model: nn.Module, names: Iterable[str]) -> dict[str, float]:
    """Collect gradient norms for named parameters that received gradients."""

    wanted = set(names)
    norms: dict[str, float] = {}
    for name, param in model.named_parameters():
        if name in wanted and param.grad is not None:
            norms[name] = float(param.grad.detach().norm().cpu())
    return norms


def summarize_hf_metadata(model: str, config: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    """Summarize whether a Hugging Face checkpoint advertises and stores MTP weights."""

    weight_map = index.get("weight_map", {})
    mtp_weights = sorted(name for name in weight_map if _has_mtp_component(name))
    return {
        "model": model,
        "architectures": config.get("architectures", []),
        "model_type": config.get("model_type"),
        "mtp_num_hidden_layers": config.get("mtp_num_hidden_layers"),
        "unsloth_fixed_mtp": config.get("unsloth_fixed_mtp"),
        "has_mtp_weights": bool(mtp_weights),
        "mtp_weight_count": len(mtp_weights),
        "mtp_weight_examples": mtp_weights[:20],
    }


def fetch_hf_metadata(model: str) -> dict[str, Any]:
    """Fetch lightweight HF config/index metadata without downloading model shards."""

    base = f"https://huggingface.co/{model}/raw/main"
    config = _fetch_json(f"{base}/config.json")
    index = _fetch_json(f"{base}/model.safetensors.index.json")
    return summarize_hf_metadata(model, config, index)


def write_report(report: ProbeReport | dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report) if isinstance(report, ProbeReport) else report
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _has_mtp_component(name: str) -> bool:
    return "mtp" in name.split(".")


def _as_list(value: Tensor | Sequence[Tensor]) -> list[Tensor]:
    if isinstance(value, Tensor):
        return [value]
    return list(value)


def _normalize_depths(depth: int | Sequence[int], count: int) -> list[int]:
    if isinstance(depth, int):
        depths = [depth] * count
    else:
        depths = list(depth)
    if len(depths) != count:
        raise ValueError("number of MTP depths must match number of MTP logits")
    if any(current < 1 for current in depths):
        raise ValueError("MTP depth must be >= 1")
    return depths


def _shifted_ce(logits: Tensor, labels: Tensor, *, depth: int, ignore_index: int) -> Tensor:
    if logits.ndim != 3:
        raise ValueError("expected logits [batch, seq, vocab]")
    if logits.shape[:2] != labels.shape:
        raise ValueError("logits and labels batch/sequence dimensions must match")
    if depth >= logits.shape[1]:
        raise ValueError("depth must be smaller than sequence length")

    usable_logits = logits[:, : -depth, :].contiguous()
    target_labels = labels[:, depth:].contiguous()
    return F.cross_entropy(
        usable_logits.view(-1, usable_logits.shape[-1]),
        target_labels.view(-1),
        ignore_index=ignore_index,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe MTP parameter availability for a HF model.")
    parser.add_argument("--model", default="unsloth/Qwen3.6-35B-A3B")
    parser.add_argument("--output", type=Path, default=Path("reports/mtp_probe.json"))
    parser.add_argument("--metadata-only", action="store_true", help="Only fetch config/index; do not load weights.")
    parser.add_argument("--trust-remote-code", action="store_true")
    args = parser.parse_args()

    if args.metadata_only:
        report = fetch_hf_metadata(args.model)
        write_report(report, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    from transformers import AutoModelForCausalLM  # imported lazily; tests do not need transformers

    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype="auto",
        device_map="cpu",
        trust_remote_code=args.trust_remote_code,
    )
    mtp_names = discover_mtp_parameters(model)
    trainable = set_trainable_mtp_only(model)
    report = ProbeReport(
        model_name=args.model,
        mtp_parameter_count=len(mtp_names),
        mtp_parameters=mtp_names,
        trainable_mtp_parameters=trainable,
        mtp_gradient_norms={},
        has_nonzero_mtp_gradient=False,
    )
    write_report(report, args.output)
    print(json.dumps(asdict(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

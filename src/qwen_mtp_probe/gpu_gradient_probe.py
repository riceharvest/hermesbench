"""Loaded-model MTP gradient probe.

This is the first real gate before any serious Qwen3.6 specialization run. It loads a
HF causal-LM checkpoint, discovers MTP parameters, runs one tiny tokenized batch,
adds an explicit future-token MTP auxiliary loss when possible, backprops, and writes
a JSON report.

It is intentionally conservative: it refuses to load huge checkpoints unless
--allow-large-load is passed, based on lightweight HF metadata.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import torch
from torch import Tensor

from qwen_mtp_probe.probe import (
    collect_gradient_norms,
    compute_mtp_aux_loss,
    discover_mtp_parameters,
    fetch_hf_metadata,
    set_trainable_mtp_only,
    write_report,
)


@dataclass
class GradientProbeReport:
    model: str
    device: str
    dtype: str
    metadata_mtp_weight_count: int | None
    loaded_mtp_param_count: int
    trainable_mtp_param_count: int
    forward_has_logits: bool
    forward_mtp_keys: list[str]
    used_builtin_loss: bool
    used_explicit_mtp_loss: bool
    loss: float | None
    mtp_aux_loss: float | None
    nonzero_mtp_grad_count: int
    mtp_grad_norms: dict[str, float]
    elapsed_seconds: float
    error: str | None = None


def run_gradient_probe(
    *,
    model_name: str,
    prompt: str,
    output: Path,
    allow_large_load: bool,
    mtp_weight: float,
    max_length: int,
    trust_remote_code: bool,
) -> GradientProbeReport:
    started = time.time()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    metadata_count: int | None = None

    try:
        metadata = fetch_hf_metadata(model_name)
        metadata_count = metadata.get("mtp_weight_count")
        if metadata_count and not allow_large_load:
            raise RuntimeError(
                "Refusing to load a large MTP checkpoint without --allow-large-load. "
                f"Metadata shows {metadata_count} MTP tensors. Use this flag only on a GPU box "
                "with enough RAM/VRAM for the HF safetensors checkpoint."
            )

        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=trust_remote_code)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype="auto",
            device_map="auto" if device == "cuda" else "cpu",
            trust_remote_code=trust_remote_code,
        )
        model.train()

        mtp_names = discover_mtp_parameters(model)
        trainable_names = set_trainable_mtp_only(model)

        batch = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=max_length)
        batch = {key: value.to(model.device) for key, value in batch.items()}
        labels = batch["input_ids"].clone()

        outputs = model(**batch, labels=labels, use_cache=False)
        logits = getattr(outputs, "logits", None)
        forward_keys = _output_keys(outputs)
        mtp_logits = _extract_mtp_logits(outputs)
        mtp_aux_loss: Tensor | None = None

        used_builtin_loss = getattr(outputs, "loss", None) is not None
        loss = outputs.loss if used_builtin_loss else None
        if mtp_logits is not None:
            mtp_aux_loss = compute_mtp_aux_loss(mtp_logits, labels, depth=2)
            assert mtp_aux_loss is not None
            base_loss = loss if loss is not None else torch.zeros((), device=labels.device)
            loss = base_loss + mtp_weight * mtp_aux_loss
        elif loss is None and logits is not None:
            # Fallback: proves normal loaded-model backprop works, but not MTP refresh.
            from qwen_mtp_probe.probe import compute_next_token_loss

            loss = compute_next_token_loss(logits, labels)

        if loss is None:
            raise RuntimeError(f"No usable loss/logits found in model output keys: {forward_keys}")

        loss.backward()
        grad_norms = collect_gradient_norms(model, trainable_names)
        nonzero = {name: norm for name, norm in grad_norms.items() if norm > 0}

        report = GradientProbeReport(
            model=model_name,
            device=device,
            dtype=str(next(model.parameters()).dtype),
            metadata_mtp_weight_count=metadata_count,
            loaded_mtp_param_count=len(mtp_names),
            trainable_mtp_param_count=len(trainable_names),
            forward_has_logits=logits is not None,
            forward_mtp_keys=[key for key in forward_keys if "mtp" in key.lower() or "next" in key.lower()],
            used_builtin_loss=used_builtin_loss,
            used_explicit_mtp_loss=mtp_aux_loss is not None,
            loss=float(loss.detach().cpu()),
            mtp_aux_loss=float(mtp_aux_loss.detach().cpu()) if mtp_aux_loss is not None else None,
            nonzero_mtp_grad_count=len(nonzero),
            mtp_grad_norms=nonzero,
            elapsed_seconds=time.time() - started,
        )
    except Exception as exc:
        report = GradientProbeReport(
            model=model_name,
            device=device,
            dtype="unknown",
            metadata_mtp_weight_count=metadata_count,
            loaded_mtp_param_count=0,
            trainable_mtp_param_count=0,
            forward_has_logits=False,
            forward_mtp_keys=[],
            used_builtin_loss=False,
            used_explicit_mtp_loss=False,
            loss=None,
            mtp_aux_loss=None,
            nonzero_mtp_grad_count=0,
            mtp_grad_norms={},
            elapsed_seconds=time.time() - started,
            error=str(exc),
        )

    write_report(asdict(report), output)
    return report


def _output_keys(outputs: Any) -> list[str]:
    if hasattr(outputs, "keys"):
        return list(outputs.keys())
    if hasattr(outputs, "__dict__"):
        return list(outputs.__dict__.keys())
    return []


def _extract_mtp_logits(outputs: Any) -> Tensor | list[Tensor] | None:
    candidates = [
        "mtp_logits",
        "mtp_logit",
        "nextn_logits",
        "next_logits",
        "speculative_logits",
    ]
    for key in candidates:
        value = getattr(outputs, key, None)
        if value is not None:
            return value
        if hasattr(outputs, "get"):
            value = outputs.get(key, None)
            if value is not None:
                return value
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a watched one-batch MTP gradient probe.")
    parser.add_argument("--model", default="unsloth/Qwen3.6-35B-A3B")
    parser.add_argument("--output", type=Path, default=Path("reports/gpu-gradient-probe.json"))
    parser.add_argument("--prompt", default="Return exactly this JSON: {\"ok\": true}")
    parser.add_argument("--max-length", type=int, default=64)
    parser.add_argument("--mtp-weight", type=float, default=0.1)
    parser.add_argument("--allow-large-load", action="store_true")
    parser.add_argument("--trust-remote-code", action="store_true")
    args = parser.parse_args()

    report = run_gradient_probe(
        model_name=args.model,
        prompt=args.prompt,
        output=args.output,
        allow_large_load=args.allow_large_load,
        mtp_weight=args.mtp_weight,
        max_length=args.max_length,
        trust_remote_code=args.trust_remote_code,
    )
    print(json.dumps(asdict(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

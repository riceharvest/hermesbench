"""Run Qwen3.6 MTP gradient probe on Modal.

Usage:
  modal run modal_gradient_probe.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

import modal

APP_NAME = "qwen36-mtp-gradient-probe"
MODEL_NAME = "unsloth/Qwen3.6-35B-A3B"

app = modal.App(APP_NAME)
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
results = modal.Volume.from_name("qwen-mtp-probe-results", create_if_missing=True)

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .apt_install("git")
    .pip_install(
        "torch",
        "accelerate",
        "safetensors",
        "hf_transfer",
        "huggingface_hub[hf_transfer]",
        "transformers>=5.0.0",
    )
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "TOKENIZERS_PARALLELISM": "false",
    })
)


def _fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _has_mtp_component(name: str) -> bool:
    return "mtp" in name.split(".")


def _output_keys(outputs: Any) -> list[str]:
    if hasattr(outputs, "keys"):
        return list(outputs.keys())
    if hasattr(outputs, "__dict__"):
        return list(outputs.__dict__.keys())
    return []


def _extract_mtp_logits(outputs: Any):
    for key in ["mtp_logits", "mtp_logit", "nextn_logits", "next_logits", "speculative_logits"]:
        value = getattr(outputs, key, None)
        if value is not None:
            return value, key
        if hasattr(outputs, "get"):
            value = outputs.get(key, None)
            if value is not None:
                return value, key
    return None, None


def _shifted_ce(torch, F, logits, labels, depth: int):
    usable_logits = logits[:, :-depth, :].contiguous()
    target_labels = labels[:, depth:].contiguous()
    return F.cross_entropy(
        usable_logits.view(-1, usable_logits.shape[-1]),
        target_labels.view(-1),
        ignore_index=-100,
    )


def _as_mtp_list(torch, mtp_logits):
    if mtp_logits is None:
        return []
    if isinstance(mtp_logits, torch.Tensor):
        return [mtp_logits]
    return list(mtp_logits)


@app.function(
    image=image,
    gpu="A100-80GB",
    timeout=1800,
    scaledown_window=10,
    max_containers=1,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/results": results,
    },
)
def remote_probe(model_name: str = MODEL_NAME, max_length: int = 32, mtp_weight: float = 0.1) -> dict[str, Any]:
    started = time.time()
    report: dict[str, Any] = {
        "model": model_name,
        "stage": "start",
        "error": None,
    }

    try:
        import torch
        import torch.nn.functional as F
        from transformers import AutoModelForCausalLM, AutoTokenizer

        print("[probe] torch", torch.__version__, "cuda", torch.version.cuda, flush=True)
        print("[probe] gpu", torch.cuda.get_device_name(0), flush=True)
        print("[probe] fetching metadata", flush=True)

        base = f"https://huggingface.co/{model_name}/raw/main"
        config = _fetch_json(f"{base}/config.json")
        index = _fetch_json(f"{base}/model.safetensors.index.json")
        mtp_weights = sorted(name for name in index.get("weight_map", {}) if _has_mtp_component(name))

        report.update({
            "stage": "metadata",
            "config_model_type": config.get("model_type"),
            "config_architectures": config.get("architectures"),
            "config_mtp_num_hidden_layers": config.get("mtp_num_hidden_layers"),
            "metadata_mtp_weight_count": len(mtp_weights),
            "metadata_mtp_weight_examples": mtp_weights[:20],
        })
        print("[probe] metadata mtp weights", len(mtp_weights), flush=True)

        print("[probe] loading tokenizer", flush=True)
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)

        print("[probe] loading model", flush=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype="auto",
            device_map="auto",
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        model.train()
        torch.cuda.empty_cache()
        print("[probe] loaded", flush=True)

        mtp_param_names = [name for name, _ in model.named_parameters() if _has_mtp_component(name)]
        trainable_names = []
        for name, param in model.named_parameters():
            should_train = _has_mtp_component(name)
            param.requires_grad_(should_train)
            if should_train:
                trainable_names.append(name)

        report.update({
            "stage": "loaded",
            "dtype": str(next(model.parameters()).dtype),
            "loaded_mtp_param_count": len(mtp_param_names),
            "trainable_mtp_param_count": len(trainable_names),
            "loaded_mtp_param_examples": mtp_param_names[:20],
            "cuda_memory_allocated_gb_after_load": torch.cuda.memory_allocated() / 1e9,
            "cuda_memory_reserved_gb_after_load": torch.cuda.memory_reserved() / 1e9,
        })
        print("[probe] loaded mtp params", len(mtp_param_names), flush=True)

        prompt = "Return exactly this JSON: {\"ok\": true}"
        batch = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=max_length)
        device = next(model.parameters()).device
        batch = {key: value.to(device) for key, value in batch.items()}
        labels = batch["input_ids"].clone()

        print("[probe] forward", flush=True)
        outputs = model(**batch, labels=labels, use_cache=False)
        keys = _output_keys(outputs)
        logits = getattr(outputs, "logits", None)
        builtin_loss = getattr(outputs, "loss", None)
        mtp_logits, mtp_key = _extract_mtp_logits(outputs)

        loss = builtin_loss
        mtp_aux_loss = None
        if mtp_logits is not None:
            mtp_losses = []
            for i, head_logits in enumerate(_as_mtp_list(torch, mtp_logits), start=2):
                mtp_losses.append(_shifted_ce(torch, F, head_logits, labels, depth=i))
            mtp_aux_loss = torch.stack(mtp_losses).mean()
            base_loss = loss if loss is not None else torch.zeros((), device=labels.device)
            loss = base_loss + mtp_weight * mtp_aux_loss
        elif loss is None and logits is not None:
            loss = _shifted_ce(torch, F, logits, labels, depth=1)

        report.update({
            "stage": "forward",
            "forward_keys": keys,
            "forward_has_logits": logits is not None,
            "forward_mtp_key": mtp_key,
            "used_builtin_loss": builtin_loss is not None,
            "used_explicit_mtp_loss": mtp_aux_loss is not None,
            "loss_requires_grad": bool(loss is not None and loss.requires_grad),
            "loss": float(loss.detach().cpu()) if loss is not None else None,
            "mtp_aux_loss": float(mtp_aux_loss.detach().cpu()) if mtp_aux_loss is not None else None,
        })
        print("[probe] forward keys", keys, flush=True)
        print("[probe] mtp key", mtp_key, "loss requires grad", report["loss_requires_grad"], flush=True)

        if loss is None:
            raise RuntimeError("No usable loss/logits found")
        if not loss.requires_grad:
            raise RuntimeError("Loss does not require grad; likely MTP path is not used by forward loss")

        print("[probe] backward", flush=True)
        loss.backward()

        grad_norms = {}
        for name, param in model.named_parameters():
            if name in trainable_names and param.grad is not None:
                norm = float(param.grad.detach().norm().cpu())
                if norm > 0:
                    grad_norms[name] = norm

        report.update({
            "stage": "done",
            "nonzero_mtp_grad_count": len(grad_norms),
            "mtp_grad_norms": grad_norms,
            "cuda_memory_allocated_gb_final": torch.cuda.memory_allocated() / 1e9,
            "cuda_memory_reserved_gb_final": torch.cuda.memory_reserved() / 1e9,
            "elapsed_seconds": time.time() - started,
        })
        print("[probe] nonzero mtp grads", len(grad_norms), flush=True)

    except Exception as exc:
        report.update({
            "stage": report.get("stage", "error"),
            "error": repr(exc),
            "elapsed_seconds": time.time() - started,
        })
        print("[probe] ERROR", repr(exc), flush=True)

    path = Path("/results/modal-gradient-probe.json")
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    results.commit()
    return report


@app.local_entrypoint()
def main():
    report = remote_probe.remote()
    print(json.dumps(report, indent=2, sort_keys=True))

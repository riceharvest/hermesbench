"""Modal probe that trains a tiny MTP refresh and exports preserved `mtp.*` tensors.

The exported artifact is intentionally small: a safetensors file containing only the
refreshed MTP tensors plus a manifest. A serving checkpoint can be assembled by
copying/symlinking the original model snapshot and editing `model.safetensors.index.json`
so `mtp.*` keys point at this exported shard.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import modal

APP_NAME = "qwen36-mtp-export-probe"
MODEL_NAME = "unsloth/Qwen3.6-35B-A3B"
EXPORT_DIR = "/results/qwen36-mtp-refresh-export"

app = modal.App(APP_NAME)
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
results = modal.Volume.from_name("qwen-mtp-probe-results", create_if_missing=True)

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .pip_install(
        "torch",
        "accelerate",
        "safetensors",
        "hf_transfer",
        "huggingface_hub[hf_transfer]",
        "transformers>=5.0.0",
    )
    .add_local_dir("src", "/workspace/src", copy=True)
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "HF_XET_HIGH_PERFORMANCE": "1",
        "PYTHONPATH": "/workspace/src",
        "TOKENIZERS_PARALLELISM": "false",
    })
)


def _fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _examples() -> list[str]:
    return [
        'Task: return compact JSON for lead status. Answer: {"status":"qualified","score":0.91}',
        'Task: return compact JSON for lead status. Answer: {"status":"reject","score":0.12}',
        'Task: classify support ticket. Answer: {"queue":"billing","priority":"medium"}',
        'Task: classify support ticket. Answer: {"queue":"security","priority":"high"}',
        'Task: extract car listing. Answer: {"make":"Toyota","model":"Yaris","year":2018}',
        'Task: extract car listing. Answer: {"make":"Mazda","model":"3","year":2020}',
        'Task: write SQL intent. Answer: {"table":"users","op":"select","limit":20}',
        'Task: write SQL intent. Answer: {"table":"orders","op":"count","limit":null}',
        'Task: normalize date. Answer: {"date":"2026-05-25","tz":"Europe/Amsterdam"}',
        'Task: normalize date. Answer: {"date":"2026-06-01","tz":"Europe/Amsterdam"}',
        'Task: route VA task. Answer: {"assignee_type":"research","channel":"whatsapp"}',
        'Task: route VA task. Answer: {"assignee_type":"posting","channel":"whatsapp"}',
        'Task: produce agent action. Answer: {"action":"search","path":"src","pattern":"auth"}',
        'Task: produce agent action. Answer: {"action":"patch","path":"src/app.ts","safe":true}',
        'Task: evaluate answer. Answer: {"valid":true,"reason":"schema matched"}',
        'Task: evaluate answer. Answer: {"valid":false,"reason":"missing field"}',
    ]


@app.function(
    image=image,
    gpu="A100-80GB",
    timeout=3600,
    scaledown_window=10,
    max_containers=1,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/results": results,
    },
)
def remote_export(
    model_name: str = MODEL_NAME,
    steps: int = 24,
    batch_size: int = 2,
    max_length: int = 48,
    lr: float = 3e-5,
) -> dict[str, Any]:
    started = time.time()
    report: dict[str, Any] = {
        "model": model_name,
        "stage": "start",
        "error": None,
        "steps": steps,
        "batch_size": batch_size,
        "max_length": max_length,
        "lr": lr,
    }

    try:
        import torch
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file, save_file
        from transformers import AutoModelForCausalLM, AutoTokenizer

        from qwen_mtp_probe.qwen_mtp import (
            build_manual_qwen_mtp,
            build_mtp_forward_inputs,
            checkpoint_mtp_weight_map,
            freeze_base_train_mtp,
            load_mtp_checkpoint_state,
            mtp_future_token_loss,
            nonzero_grad_norms,
            text_model_from_causal_lm,
        )

        torch.manual_seed(42)
        base = f"https://huggingface.co/{model_name}/raw/main"
        config = _fetch_json(f"{base}/config.json")
        index = _fetch_json(f"{base}/model.safetensors.index.json")
        mtp_weight_map = checkpoint_mtp_weight_map(index)
        report.update({"stage": "metadata", "metadata_mtp_weight_count": len(mtp_weight_map)})

        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype="auto",
            device_map="auto",
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        model.eval()
        text_model = text_model_from_causal_lm(model)
        device = next(model.parameters()).device

        mtp = build_manual_qwen_mtp(model)
        loaded_state = load_mtp_checkpoint_state(
            mtp,
            model_name=model_name,
            mtp_weight_map=mtp_weight_map,
            hf_hub_download=hf_hub_download,
            safetensors_load_file=load_file,
        )
        missing, unexpected = mtp.load_state_dict(loaded_state, strict=False)
        freeze_base_train_mtp(model, mtp)
        mtp.train()
        optimizer = torch.optim.AdamW(mtp.parameters(), lr=lr)
        examples = _examples()

        def batch_loss(texts: list[str], *, backward: bool) -> torch.Tensor:
            batch = tokenizer(
                texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_length,
            )
            batch = {key: value.to(device) for key, value in batch.items()}
            labels = batch["input_ids"].clone()
            labels[batch["attention_mask"] == 0] = -100
            with torch.no_grad():
                outputs = model.model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                    output_hidden_states=False,
                    use_cache=False,
                )
                hidden_states = outputs[0].detach()
                input_embeds = text_model.embed_tokens(batch["input_ids"])
                forward_inputs = build_mtp_forward_inputs(
                    text_model,
                    batch["input_ids"],
                    hidden_states,
                    batch["attention_mask"],
                )
            mtp_hidden = mtp(
                input_embeds,
                hidden_states,
                position_embeddings=forward_inputs.position_embeddings,
                attention_mask=forward_inputs.causal_mask,
                position_ids=forward_inputs.position_ids,
            )
            mtp_logits = model.lm_head(mtp_hidden)
            loss = mtp_future_token_loss(mtp_logits, labels, depth=2)
            if backward:
                loss.backward()
            return loss

        def full_eval_loss() -> float:
            mtp.eval()
            losses: list[float] = []
            with torch.no_grad():
                for start in range(0, len(examples), batch_size):
                    loss = batch_loss(examples[start : start + batch_size], backward=False)
                    losses.append(float(loss.detach().cpu()))
            mtp.train()
            return sum(losses) / len(losses)

        initial_loss = full_eval_loss()
        last_grad_norms: dict[str, float] = {}
        for step in range(steps):
            start_idx = (step * batch_size) % len(examples)
            texts = examples[start_idx : start_idx + batch_size]
            if len(texts) < batch_size:
                texts += examples[: batch_size - len(texts)]
            optimizer.zero_grad(set_to_none=True)
            loss = batch_loss(texts, backward=True)
            last_grad_norms = nonzero_grad_norms(mtp)
            optimizer.step()
            print(f"[mtp-export] step {step + 1}/{steps} loss={float(loss.detach().cpu()):.4f} grads={len(last_grad_norms)}", flush=True)

        final_loss = full_eval_loss()

        # Save refreshed MTP tensors with original checkpoint key names.
        export_dir = Path(EXPORT_DIR)
        export_dir.mkdir(parents=True, exist_ok=True)
        local_state = mtp.state_dict()
        refreshed_state = {
            f"mtp.{name}": tensor.detach().cpu().contiguous()
            for name, tensor in local_state.items()
            if f"mtp.{name}" in mtp_weight_map
        }
        export_shard = export_dir / "mtp-refresh.safetensors"
        save_file(refreshed_state, str(export_shard), metadata={"format": "pt"})

        # Produce an updated index fragment/checkpoint index showing how to point mtp.*
        # keys at the refresh shard while leaving all base weights unchanged.
        refreshed_index = json.loads(json.dumps(index))
        for key in refreshed_state:
            refreshed_index["weight_map"][key] = export_shard.name
        refreshed_index_path = export_dir / "model.safetensors.index.with-mtp-refresh.json"
        refreshed_index_path.write_text(json.dumps(refreshed_index, indent=2, sort_keys=True) + "\n")

        manifest = {
            "model": model_name,
            "source_mtp_weight_count": len(mtp_weight_map),
            "exported_mtp_tensor_count": len(refreshed_state),
            "export_shard": export_shard.name,
            "updated_index": refreshed_index_path.name,
            "config_mtp_num_hidden_layers": config.get("mtp_num_hidden_layers"),
            "config_unsloth_fixed_mtp": config.get("unsloth_fixed_mtp"),
            "initial_eval_loss": initial_loss,
            "final_eval_loss": final_loss,
            "loss_delta": initial_loss - final_loss,
            "last_nonzero_mtp_grad_count": len(last_grad_norms),
            "assembly_note": "Copy or symlink the original model snapshot, copy mtp-refresh.safetensors into it, and replace model.safetensors.index.json with model.safetensors.index.with-mtp-refresh.json.",
        }
        (export_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        # Verify exported shard reloads and exactly matches the trained MTP state.
        reloaded = load_file(str(export_shard), device="cpu")
        max_abs_diffs = {
            key: float((reloaded[key] - refreshed_state[key]).abs().max()) for key in refreshed_state
        }
        max_abs_diff = max(max_abs_diffs.values()) if max_abs_diffs else None

        report.update({
            "stage": "done",
            "loaded_mtp_tensor_count": len(loaded_state),
            "load_missing": list(missing),
            "load_unexpected": list(unexpected),
            "example_count": len(examples),
            "initial_eval_loss": initial_loss,
            "final_eval_loss": final_loss,
            "loss_delta": initial_loss - final_loss,
            "last_nonzero_mtp_grad_count": len(last_grad_norms),
            "export_dir": EXPORT_DIR,
            "export_shard": str(export_shard),
            "exported_mtp_tensor_count": len(refreshed_state),
            "export_reload_max_abs_diff": max_abs_diff,
            "elapsed_seconds": time.time() - started,
        })

    except Exception as exc:
        report.update({
            "stage": report.get("stage", "error"),
            "error": repr(exc),
            "elapsed_seconds": time.time() - started,
        })
        print("[mtp-export] ERROR", repr(exc), flush=True)

    path = Path("/results/modal-mtp-export-probe.json")
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    results.commit()
    return report


@app.local_entrypoint()
def main():
    report = remote_export.remote()
    print(json.dumps(report, indent=2, sort_keys=True))

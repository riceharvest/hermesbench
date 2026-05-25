"""Modal proof for manually attaching Qwen3.6 MTP modules to HF Transformers model.

The previous probe showed stock Transformers ignores `mtp.*` weights via
`_keys_to_ignore_on_load_unexpected = [r"^mtp.*"]`. This script checks whether we
can reconstruct an HF-native MTP module from Qwen3.5 MoE building blocks, load the
checkpoint's `mtp.*` tensors, and get nonzero gradients.
"""

from __future__ import annotations

import copy
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import modal

APP_NAME = "qwen36-mtp-manual-attach-probe"
MODEL_NAME = "unsloth/Qwen3.6-35B-A3B"

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
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "HF_XET_HIGH_PERFORMANCE": "1",
        "TOKENIZERS_PARALLELISM": "false",
    })
)


def _fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _has_mtp_component(name: str) -> bool:
    return "mtp" in name.split(".")


def _tensor_stats(tensor) -> dict[str, Any]:
    return {
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype),
        "mean": float(tensor.float().mean().cpu()),
        "std": float(tensor.float().std().cpu()),
    }


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
def remote_probe(model_name: str = MODEL_NAME, max_length: int = 32) -> dict[str, Any]:
    started = time.time()
    report: dict[str, Any] = {"model": model_name, "stage": "start", "error": None}

    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from transformers.models.qwen3_5_moe.modeling_qwen3_5_moe import (
            Qwen3_5MoeDecoderLayer,
            Qwen3_5MoeRMSNorm,
        )

        class ManualQwenMTP(nn.Module):
            def __init__(self, text_config):
                super().__init__()
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

            def forward(self, input_embeds, hidden_states, position_embeddings, attention_mask, position_ids):
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

        print("[manual-mtp] torch", torch.__version__, "cuda", torch.version.cuda, flush=True)
        print("[manual-mtp] gpu", torch.cuda.get_device_name(0), flush=True)
        base = f"https://huggingface.co/{model_name}/raw/main"
        index = _fetch_json(f"{base}/model.safetensors.index.json")
        mtp_weight_map = {name: file for name, file in index["weight_map"].items() if _has_mtp_component(name)}
        report.update({"stage": "metadata", "metadata_mtp_weight_count": len(mtp_weight_map)})
        print("[manual-mtp] metadata mtp weights", len(mtp_weight_map), flush=True)

        print("[manual-mtp] loading model", flush=True)
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype="auto",
            device_map="auto",
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        model.train()
        text_model = model.model.language_model if hasattr(model.model, "language_model") else model.model
        text_config = text_model.config
        print("[manual-mtp] base loaded", flush=True)

        mtp = ManualQwenMTP(text_config).to(next(model.parameters()).device, dtype=next(model.parameters()).dtype)
        local_state = mtp.state_dict()
        report["manual_mtp_state_keys"] = sorted(local_state.keys())

        # Load only MTP tensors from the relevant safetensor shards.
        shard_names = sorted(set(mtp_weight_map.values()))
        loaded_state = {}
        for shard in shard_names:
            print("[manual-mtp] downloading shard", shard, flush=True)
            path = hf_hub_download(model_name, shard)
            shard_tensors = load_file(path, device="cpu")
            for ckpt_name, ckpt_shard in mtp_weight_map.items():
                if ckpt_shard != shard:
                    continue
                local_name = ckpt_name.removeprefix("mtp.")
                if local_name in local_state:
                    loaded_state[local_name] = shard_tensors[ckpt_name]

        missing, unexpected = mtp.load_state_dict(loaded_state, strict=False)
        report.update({
            "stage": "mtp_loaded",
            "loaded_mtp_tensor_count": len(loaded_state),
            "load_missing": list(missing),
            "load_unexpected": list(unexpected),
            "loaded_tensor_examples": sorted(loaded_state.keys())[:20],
            "fc_stats": _tensor_stats(mtp.fc.weight.detach()),
        })
        print("[manual-mtp] loaded tensors", len(loaded_state), "missing", len(missing), flush=True)

        # Freeze base, train only manual MTP.
        for param in model.parameters():
            param.requires_grad_(False)
        for param in mtp.parameters():
            param.requires_grad_(True)

        prompt = "Return exactly this JSON: {\"ok\": true}"
        batch = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=max_length)
        device = next(model.parameters()).device
        batch = {key: value.to(device) for key, value in batch.items()}
        labels = batch["input_ids"].clone()

        print("[manual-mtp] base forward", flush=True)
        outputs = model.model(
            input_ids=batch["input_ids"],
            attention_mask=batch.get("attention_mask"),
            output_hidden_states=False,
            use_cache=False,
        )
        hidden_states = outputs[0]

        # Recreate the basic text position inputs for a text-only batch.
        bsz, seq_len = batch["input_ids"].shape
        position_ids = torch.arange(seq_len, device=device).view(1, -1).expand(bsz, -1)
        rope_position_ids = position_ids[None, ...].expand(3, bsz, -1)
        position_embeddings = text_model.rotary_emb(hidden_states, rope_position_ids)
        causal_mask = None  # small smoke; full trainer should use create_causal_mask from Transformers.
        input_embeds = text_model.embed_tokens(batch["input_ids"])

        print("[manual-mtp] mtp forward", flush=True)
        mtp_hidden = mtp(input_embeds, hidden_states.detach(), position_embeddings, causal_mask, position_ids)
        mtp_logits = model.lm_head(mtp_hidden)
        # Depth 2 future-token objective: position t predicts token t+2.
        loss = F.cross_entropy(
            mtp_logits[:, :-2, :].contiguous().view(-1, mtp_logits.shape[-1]),
            labels[:, 2:].contiguous().view(-1),
        )
        report.update({
            "stage": "forward",
            "mtp_hidden_shape": list(mtp_hidden.shape),
            "mtp_logits_shape": list(mtp_logits.shape),
            "mtp_loss": float(loss.detach().cpu()),
            "loss_requires_grad": bool(loss.requires_grad),
        })
        print("[manual-mtp] backward", flush=True)
        loss.backward()

        grad_norms = {
            name: float(param.grad.detach().norm().cpu())
            for name, param in mtp.named_parameters()
            if param.grad is not None and float(param.grad.detach().norm().cpu()) > 0
        }
        report.update({
            "stage": "done",
            "nonzero_mtp_grad_count": len(grad_norms),
            "mtp_grad_norms": grad_norms,
            "cuda_memory_allocated_gb_final": torch.cuda.memory_allocated() / 1e9,
            "cuda_memory_reserved_gb_final": torch.cuda.memory_reserved() / 1e9,
            "elapsed_seconds": time.time() - started,
        })
        print("[manual-mtp] done nonzero grads", len(grad_norms), flush=True)

    except Exception as exc:
        report.update({
            "stage": report.get("stage", "error"),
            "error": repr(exc),
            "elapsed_seconds": time.time() - started,
        })
        print("[manual-mtp] ERROR", repr(exc), flush=True)

    path = Path("/results/modal-manual-mtp-probe.json")
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    results.commit()
    return report


@app.local_entrypoint()
def main():
    report = remote_probe.remote()
    print(json.dumps(report, indent=2, sort_keys=True))

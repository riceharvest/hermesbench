"""vLLM benchmark/load probe for the exported Qwen3.6 MTP refresh checkpoint.

Runs two separate Modal functions so GPU memory is clean between modes:
1. normal decode against the assembled refreshed checkpoint
2. speculative MTP decode against the same checkpoint
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import modal

APP_NAME = "qwen36-mtp-vllm-bench"
MODEL_NAME = "unsloth/Qwen3.6-35B-A3B"
EXPORT_DIR = Path("/results/qwen36-mtp-refresh-export")
ASSEMBLED_DIR = Path("/tmp/qwen36-mtp-refresh-checkpoint")

app = modal.App(APP_NAME)
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
results = modal.Volume.from_name("qwen-mtp-probe-results", create_if_missing=True)

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .pip_install("vllm>=0.17.0", "huggingface_hub[hf_transfer]", "hf_transfer")
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "HF_XET_HIGH_PERFORMANCE": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "VLLM_ALLOW_LONG_MAX_MODEL_LEN": "1",
        # Qwen MoE/VL TP startup can hang at shm_broadcast on some multi-GPU nodes.
        # A vLLM issue thread reports this avoids the TP P2P deadlock class.
        "NCCL_P2P_DISABLE": "1",
    })
)


def _assemble_checkpoint(source: Path, export: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    refresh_shard = export / "mtp-refresh.safetensors"
    refreshed_index = export / "model.safetensors.index.with-mtp-refresh.json"
    if not refresh_shard.exists():
        raise FileNotFoundError(refresh_shard)
    if not refreshed_index.exists():
        raise FileNotFoundError(refreshed_index)

    for item in source.iterdir():
        dest = output / item.name
        if dest.exists() or dest.is_symlink():
            continue
        if item.name == "model.safetensors.index.json":
            continue
        os.symlink(item, dest, target_is_directory=item.is_dir())

    shutil.copy2(refresh_shard, output / refresh_shard.name)
    shutil.copy2(refreshed_index, output / "model.safetensors.index.json")


def _prompts() -> list[str]:
    return [
        'Return only compact JSON. Classify: "customer cannot login after password reset"',
        'Return only compact JSON. Extract car listing: 2020 Mazda 3, 84k km, €12950',
        'Return only compact JSON. Route VA task: verify 50 Instagram leads for Nigeria campaign',
        'Return only compact JSON. Produce agent action for finding auth middleware in a repo',
    ]


def _run_bench(speculative: bool) -> dict[str, Any]:
    from huggingface_hub import snapshot_download
    from vllm import LLM, SamplingParams

    source = Path(snapshot_download(MODEL_NAME))
    if ASSEMBLED_DIR.exists():
        shutil.rmtree(ASSEMBLED_DIR)
    _assemble_checkpoint(source, EXPORT_DIR, ASSEMBLED_DIR)

    llm_kwargs: dict[str, Any] = {
        "model": str(ASSEMBLED_DIR),
        "tokenizer": str(ASSEMBLED_DIR),
        "trust_remote_code": True,
        "tensor_parallel_size": 2,
        "max_model_len": 4096,
        "gpu_memory_utilization": 0.90,
        "dtype": "bfloat16",
        "enforce_eager": True,
        "disable_log_stats": False,
        "disable_custom_all_reduce": True,
        "max_num_batched_tokens": 4096,
        "limit_mm_per_prompt": {"image": 0, "video": 0},
        "mm_processor_cache_gb": 0,
        "mm_encoder_tp_mode": "data",
    }
    if speculative:
        llm_kwargs["speculative_config"] = {"method": "mtp", "num_speculative_tokens": 2}

    started_load = time.time()
    llm = LLM(**llm_kwargs)
    load_seconds = time.time() - started_load

    sampling = SamplingParams(temperature=0.0, max_tokens=96)
    prompts = _prompts()
    started = time.time()
    outputs = llm.generate(prompts, sampling)
    wall_seconds = time.time() - started
    generated_tokens = sum(len(out.outputs[0].token_ids) for out in outputs)
    texts = [out.outputs[0].text for out in outputs]

    return {
        "mode": "mtp" if speculative else "normal",
        "model_dir": str(ASSEMBLED_DIR),
        "prompt_count": len(prompts),
        "generated_tokens": generated_tokens,
        "load_seconds": load_seconds,
        "wall_seconds": wall_seconds,
        "tokens_per_second": generated_tokens / wall_seconds if wall_seconds > 0 else None,
        "texts": texts,
    }


@app.function(
    image=image,
    gpu="H100:2",
    timeout=2400,
    scaledown_window=10,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/results": results,
    },
)
def bench_normal() -> dict[str, Any]:
    return _run_bench(speculative=False)


@app.function(
    image=image,
    gpu="H100:2",
    timeout=2400,
    scaledown_window=10,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/results": results,
    },
)
def bench_mtp() -> dict[str, Any]:
    return _run_bench(speculative=True)


@app.local_entrypoint()
def main():
    report: dict[str, Any] = {"model": MODEL_NAME, "error": None}
    try:
        normal = bench_normal.remote()
        mtp = bench_mtp.remote()
        report.update({"normal": normal, "mtp": mtp})
        if normal.get("tokens_per_second") and mtp.get("tokens_per_second"):
            report["speedup"] = mtp["tokens_per_second"] / normal["tokens_per_second"]
    except Exception as exc:
        report["error"] = repr(exc)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/modal-vllm-bench.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))

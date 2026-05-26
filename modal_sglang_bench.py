"""SGLang serving probe for assembled Qwen3.6 MTP-refresh checkpoint.

This is the fallback after vLLM TP=2 on Modal loaded weights but hung in
shared-memory broadcast/post-load profiling. It launches SGLang as a subprocess,
waits for readiness, sends a few OpenAI-compatible requests, and reports tok/s.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import modal

APP_NAME = "qwen36-mtp-sglang-bench"
MODEL_NAME = "unsloth/Qwen3.6-35B-A3B"
EXPORT_DIR = Path("/results/qwen36-mtp-refresh-export")
ASSEMBLED_DIR = Path("/tmp/qwen36-mtp-refresh-checkpoint")
PORT = 30000

app = modal.App(APP_NAME)
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
results = modal.Volume.from_name("qwen-mtp-probe-results", create_if_missing=True)

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .apt_install("libnuma1")
    .pip_install(
        "sglang[all]>=0.5.5",
        "huggingface_hub[hf_transfer]",
        "hf_transfer",
        "openai",
        "requests",
    )
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "HF_XET_HIGH_PERFORMANCE": "1",
        "TOKENIZERS_PARALLELISM": "false",
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


def _tail(lines: list[str], n: int = 160) -> str:
    return "".join(lines[-n:])


def _start_log_reader(proc: subprocess.Popen[str]) -> tuple[list[str], threading.Thread]:
    lines: list[str] = []

    def reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            print(line, end="", flush=True)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    return lines, thread


def _wait_ready(proc: subprocess.Popen[str], logs: list[str], timeout_s: int = 900) -> str:
    import requests

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc.poll() is not None:
            time.sleep(1)
            raise RuntimeError(f"SGLang exited early with {proc.returncode}. Tail:\n{_tail(logs)}")
        try:
            response = requests.get(f"http://127.0.0.1:{PORT}/health", timeout=2)
            if response.status_code == 200:
                return "health"
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"SGLang did not become ready. Tail:\n{_tail(logs)}")


def _run_sglang(
    speculative: bool,
    *,
    minimal: bool = False,
    triton_moe: bool = False,
    tp: int = 2,
    disable_cuda_graph: bool = True,
    mem_fraction_static: float = 0.70,
    max_total_tokens: int = 8192,
    max_running_requests: int = 4,
) -> dict[str, Any]:
    from huggingface_hub import snapshot_download
    from openai import OpenAI

    source = Path(snapshot_download(MODEL_NAME))
    if ASSEMBLED_DIR.exists():
        shutil.rmtree(ASSEMBLED_DIR)
    _assemble_checkpoint(source, EXPORT_DIR, ASSEMBLED_DIR)

    cmd = [
        "python3",
        "-m",
        "sglang.launch_server",
        "--model-path",
        str(ASSEMBLED_DIR),
        "--tp",
        str(tp),
        "--reasoning-parser",
        "qwen3",
        "--dtype",
        "bfloat16",
        "--context-length",
        "4096",
        "--max-total-tokens",
        str(max_total_tokens),
        "--page-size",
        "1",
        "--mem-fraction-static",
        str(mem_fraction_static),
        "--max-running-requests",
        str(max_running_requests),
        "--chunked-prefill-size",
        "2048",
        "--trust-remote-code",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
    ]
    if disable_cuda_graph:
        cmd.append("--disable-cuda-graph")
    if speculative:
        cmd.extend([
            "--speculative-algorithm",
            # SGLang exposes MTP through the EAGLE speculative path. NEXTN is a
            # vLLM-facing name and exits before model load on current SGLang.
            "EAGLE",
            "--speculative-num-steps",
            "1" if minimal else "3",
            "--speculative-eagle-topk",
            "1",
            "--speculative-num-draft-tokens",
            "2" if minimal else "4",
        ])
        # Qwen3.5/Qwen3.6 Mamba-MoE disables overlap scheduling by default with
        # mamba_scheduler_strategy=no_buffer. SGLang rejects speculative decoding
        # in that mode unless SpecV2 and the extra Mamba cache buffer are enabled.
        cmd.extend([
            "--mamba-scheduler-strategy",
            "extra_buffer",
        ])
        if triton_moe:
            cmd.extend([
                "--speculative-moe-runner-backend",
                "triton",
            ])

    env = os.environ.copy()
    if speculative:
        env["SGLANG_ENABLE_SPEC_V2"] = "1"

    started_load = time.time()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    logs, reader_thread = _start_log_reader(proc)
    try:
        ready_signal = _wait_ready(proc, logs)
        load_seconds = time.time() - started_load
        client = OpenAI(base_url=f"http://127.0.0.1:{PORT}/v1", api_key="None")
        generated_tokens = 0
        texts: list[str] = []
        started = time.time()
        for prompt in _prompts():
            response = client.chat.completions.create(
                model="default",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=96,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False},
                    "separate_reasoning": True,
                },
            )
            message = response.choices[0].message
            content = message.content or getattr(message, "reasoning_content", None) or ""
            texts.append(content)
            if response.usage and response.usage.completion_tokens:
                generated_tokens += response.usage.completion_tokens
        wall_seconds = time.time() - started
        return {
            "mode": "nextn" if speculative else "normal",
            "tp": tp,
            "disable_cuda_graph": disable_cuda_graph,
            "mem_fraction_static": mem_fraction_static,
            "max_total_tokens": max_total_tokens,
            "max_running_requests": max_running_requests,
            "speculative_algorithm": "EAGLE" if speculative else None,
            "speculative_minimal": minimal if speculative else None,
            "speculative_moe_runner_backend": "triton" if triton_moe else None,
            "ready_signal": ready_signal,
            "load_seconds": load_seconds,
            "wall_seconds": wall_seconds,
            "generated_tokens": generated_tokens,
            "tokens_per_second": generated_tokens / wall_seconds if wall_seconds > 0 else None,
            "texts": texts,
            "log_tail": _tail(logs, 40),
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        reader_thread.join(timeout=5)


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
    return _run_sglang(speculative=False)


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
def bench_nextn() -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for minimal, triton_moe in [(False, False), (False, True), (True, True), (True, False)]:
        try:
            result = _run_sglang(speculative=True, minimal=minimal, triton_moe=triton_moe)
            result["attempts"] = attempts
            return result
        except Exception as exc:
            attempts.append({
                "minimal": minimal,
                "triton_moe": triton_moe,
                "error": repr(exc),
            })
    raise RuntimeError(json.dumps({"nextn_attempts": attempts}, indent=2))


@app.function(
    image=image,
    gpu="H100",
    timeout=2400,
    scaledown_window=10,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/results": results,
    },
)
def bench_normal_single_h100() -> dict[str, Any]:
    """Single-H100 fit/perf check with CUDA graphs enabled for a less-debuggy baseline."""

    try:
        return _run_sglang(
            speculative=False,
            tp=1,
            disable_cuda_graph=False,
            mem_fraction_static=0.88,
            max_total_tokens=4096,
            max_running_requests=1,
        )
    except Exception as exc:
        return {
            "mode": "normal",
            "tp": 1,
            "disable_cuda_graph": False,
            "mem_fraction_static": 0.88,
            "max_total_tokens": 4096,
            "max_running_requests": 1,
            "error": repr(exc),
            "fallback": _run_sglang(
                speculative=False,
                tp=1,
                disable_cuda_graph=True,
                mem_fraction_static=0.88,
                max_total_tokens=4096,
                max_running_requests=1,
            ),
        }


@app.function(
    image=image,
    gpu="H100",
    timeout=2400,
    scaledown_window=10,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/results": results,
    },
)
def bench_nextn_single_h100() -> dict[str, Any]:
    """Single-H100 speculative check; fall back to disabled CUDA graphs if needed."""

    attempts: list[dict[str, Any]] = []
    for disable_cuda_graph in [False, True]:
        for minimal, triton_moe in [(False, False), (False, True), (True, True), (True, False)]:
            try:
                result = _run_sglang(
                    speculative=True,
                    minimal=minimal,
                    triton_moe=triton_moe,
                    tp=1,
                    disable_cuda_graph=disable_cuda_graph,
                    mem_fraction_static=0.88,
                    max_total_tokens=4096,
                    max_running_requests=1,
                )
                result["attempts"] = attempts
                return result
            except Exception as exc:
                attempts.append({
                    "disable_cuda_graph": disable_cuda_graph,
                    "minimal": minimal,
                    "triton_moe": triton_moe,
                    "error": repr(exc),
                })
    raise RuntimeError(json.dumps({"single_h100_nextn_attempts": attempts}, indent=2))


@app.local_entrypoint()
def main(mode: str = "all"):
    report_path = Path(
        "reports/modal-sglang-single-h100-bench.json"
        if mode == "single-h100"
        else "reports/modal-sglang-bench.json"
    )
    report: dict[str, Any] = {"model": MODEL_NAME, "backend": "sglang", "error": None}

    if mode == "single-h100":
        try:
            normal = bench_normal_single_h100.remote()
            report["normal"] = normal
            Path("reports").mkdir(exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        except Exception as exc:
            report["normal_error"] = repr(exc)
            report["error"] = repr(exc)
            Path("reports").mkdir(exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            print(json.dumps(report, indent=2, sort_keys=True))
            return

        try:
            nextn = bench_nextn_single_h100.remote()
            report["nextn"] = nextn
            normal_tps = normal.get("tokens_per_second") or normal.get("fallback", {}).get(
                "tokens_per_second"
            )
            nextn_tps = nextn.get("tokens_per_second")
            if normal_tps and nextn_tps:
                report["speedup"] = nextn_tps / normal_tps
        except Exception as exc:
            report["nextn_error"] = repr(exc)
            report["error"] = repr(exc)

        Path("reports").mkdir(exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    if mode == "nextn-only" and report_path.exists():
        report.update(json.loads(report_path.read_text()))
        report["error"] = None
    else:
        try:
            normal = bench_normal.remote()
            report["normal"] = normal
            Path("reports").mkdir(exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        except Exception as exc:
            report["normal_error"] = repr(exc)
            report["error"] = repr(exc)
            Path("reports").mkdir(exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            print(json.dumps(report, indent=2, sort_keys=True))
            return

    try:
        nextn = bench_nextn.remote()
        report["nextn"] = nextn
        if report["normal"].get("tokens_per_second") and nextn.get("tokens_per_second"):
            report["speedup"] = nextn["tokens_per_second"] / report["normal"]["tokens_per_second"]
    except Exception as exc:
        report["nextn_error"] = repr(exc)
        report["error"] = repr(exc)

    Path("reports").mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))

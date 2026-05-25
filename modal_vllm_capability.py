from __future__ import annotations

import inspect
import json

import modal

app = modal.App("vllm-capability-probe")
image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .pip_install("vllm>=0.17.0")
)


@app.function(image=image, gpu="H100", timeout=900)
def probe():
    import vllm
    from vllm import LLM

    return {
        "vllm_version": getattr(vllm, "__version__", "unknown"),
        "llm_signature": str(inspect.signature(LLM)),
    }


@app.local_entrypoint()
def main():
    print(json.dumps(probe.remote(), indent=2, sort_keys=True))

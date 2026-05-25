from types import SimpleNamespace

import torch

from qwen_mtp_probe.gpu_gradient_probe import _extract_mtp_logits, _output_keys


def test_extract_mtp_logits_from_attribute():
    logits = torch.randn(1, 3, 5)
    outputs = SimpleNamespace(logits=torch.randn(1, 3, 5), mtp_logits=logits)

    assert _extract_mtp_logits(outputs) is logits


def test_extract_mtp_logits_from_mapping_like_output():
    logits = torch.randn(1, 3, 5)
    outputs = {"logits": torch.randn(1, 3, 5), "nextn_logits": logits}

    assert _extract_mtp_logits(outputs) is logits


def test_output_keys_supports_mapping_and_object():
    assert _output_keys({"logits": 1, "mtp_logits": 2}) == ["logits", "mtp_logits"]

    object_keys = _output_keys(SimpleNamespace(logits=1, mtp_logits=2))

    assert "logits" in object_keys
    assert "mtp_logits" in object_keys

import torch
from torch import nn

from qwen_mtp_probe.qwen_mtp import (
    build_4d_causal_mask,
    checkpoint_mtp_weight_map,
    freeze_base_train_mtp,
    has_mtp_component,
    load_mtp_checkpoint_state,
    mtp_future_token_loss,
    nonzero_grad_norms,
)


def test_has_mtp_component_avoids_substring_false_positive():
    assert has_mtp_component("mtp.fc.weight")
    assert has_mtp_component("model.mtp.layers.0.weight")
    assert not has_mtp_component("attempt.weight")


def test_checkpoint_mtp_weight_map_filters_safetensors_index():
    index = {
        "weight_map": {
            "model.layers.0.weight": "a.safetensors",
            "mtp.fc.weight": "b.safetensors",
            "mtp.layers.0.self_attn.q_proj.weight": "c.safetensors",
        }
    }

    assert checkpoint_mtp_weight_map(index) == {
        "mtp.fc.weight": "b.safetensors",
        "mtp.layers.0.self_attn.q_proj.weight": "c.safetensors",
    }


def test_load_mtp_checkpoint_state_maps_checkpoint_prefix_to_local_keys():
    class TinyMTP(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = nn.Linear(2, 2, bias=False)

    mtp = TinyMTP()
    tensor = torch.ones_like(mtp.fc.weight)

    def fake_download(model_name: str, shard: str) -> str:
        assert model_name == "fake/model"
        assert shard == "one.safetensors"
        return "/fake/one.safetensors"

    def fake_load(path: str, device: str):
        assert path == "/fake/one.safetensors"
        assert device == "cpu"
        return {
            "mtp.fc.weight": tensor,
            "mtp.unknown.weight": torch.zeros(1),
        }

    state = load_mtp_checkpoint_state(
        mtp,
        model_name="fake/model",
        mtp_weight_map={
            "mtp.fc.weight": "one.safetensors",
            "mtp.unknown.weight": "one.safetensors",
        },
        hf_hub_download=fake_download,
        safetensors_load_file=fake_load,
    )

    assert list(state) == ["fc.weight"]
    assert torch.equal(state["fc.weight"], tensor)


def test_build_4d_causal_mask_masks_future_and_padding_tokens():
    attention_mask = torch.tensor([[1, 1, 0]])
    mask = build_4d_causal_mask(
        attention_mask=attention_mask,
        batch_size=1,
        seq_len=3,
        dtype=torch.float32,
        device=torch.device("cpu"),
    )

    assert mask.shape == (1, 1, 3, 3)
    assert mask[0, 0, 0, 0] == 0
    assert mask[0, 0, 0, 1] < -1e20  # future token
    assert mask[0, 0, 2, 2] < -1e20  # padding key


def test_mtp_future_token_loss_uses_depth_shift():
    labels = torch.tensor([[0, 1, 2, 3]])
    logits = torch.full((1, 4, 5), -20.0)
    logits[0, 0, 2] = 20.0
    logits[0, 1, 3] = 20.0

    loss = mtp_future_token_loss(logits, labels, depth=2)

    assert loss.item() < 1e-4


def test_freeze_base_train_mtp_and_nonzero_grad_norms():
    base = nn.Linear(2, 2)
    mtp = nn.Linear(2, 1)

    trainable = freeze_base_train_mtp(base, mtp)
    assert trainable == ["weight", "bias"]
    assert all(not param.requires_grad for param in base.parameters())
    assert all(param.requires_grad for param in mtp.parameters())

    mtp(torch.ones(1, 2)).sum().backward()
    norms = nonzero_grad_norms(mtp)
    assert set(norms) == {"weight", "bias"}

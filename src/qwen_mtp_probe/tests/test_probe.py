import torch
import torch.nn as nn

from qwen_mtp_probe.probe import (
    compute_mtp_aux_loss,
    discover_mtp_parameters,
    summarize_hf_metadata,
    set_trainable_mtp_only,
)


class TinyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = nn.Linear(3, 3)
        self.mtp = nn.Module()
        self.mtp.fc = nn.Linear(3, 3)
        self.mtp.layers = nn.ModuleList([nn.Linear(3, 3)])
        self.lm_head = nn.Linear(3, 5)


def test_discovers_only_mtp_parameters():
    model = TinyModel()

    names = discover_mtp_parameters(model)

    assert names
    assert all("mtp" in name for name in names)
    assert "mtp.fc.weight" in names
    assert "backbone.weight" not in names


def test_set_trainable_mtp_only_freezes_base_model():
    model = TinyModel()

    trainable = set_trainable_mtp_only(model)

    assert trainable == discover_mtp_parameters(model)
    assert all(param.requires_grad for name, param in model.named_parameters() if "mtp" in name)
    assert all(not param.requires_grad for name, param in model.named_parameters() if "mtp" not in name)


def test_mtp_aux_loss_uses_future_token_labels_and_backprops_to_mtp_logits():
    vocab = 7
    batch = 2
    seq = 5
    depth = 2
    logits = torch.randn(batch, seq, vocab, requires_grad=True)
    labels = torch.tensor([
        [0, 1, 2, 3, 4],
        [1, 2, 3, 4, 5],
    ])

    loss = compute_mtp_aux_loss(logits, labels, depth=depth)
    loss.backward()

    assert loss.item() > 0
    assert logits.grad is not None
    assert torch.count_nonzero(logits.grad[:, : seq - depth]).item() > 0
    assert torch.count_nonzero(logits.grad[:, seq - depth :]).item() == 0


def test_mtp_aux_loss_accepts_multiple_prediction_heads():
    vocab = 7
    labels = torch.tensor([[0, 1, 2, 3]])
    head_1 = torch.randn(1, 4, vocab, requires_grad=True)
    head_2 = torch.randn(1, 4, vocab, requires_grad=True)

    loss = compute_mtp_aux_loss([head_1, head_2], labels, depth=[1, 2])
    loss.backward()

    assert head_1.grad is not None
    assert head_2.grad is not None
    assert loss.item() > 0


def test_summarize_hf_metadata_reports_mtp_config_and_weights():
    config = {
        "model_type": "qwen3_5_moe",
        "architectures": ["Qwen3_5MoeForConditionalGeneration"],
        "mtp_num_hidden_layers": 1,
        "unsloth_fixed_mtp": True,
    }
    index = {
        "weight_map": {
            "mtp.fc.weight": "model-00002-of-00002.safetensors",
            "mtp.layers.0.self_attn.q_proj.weight": "model-00002-of-00002.safetensors",
            "lm_head.weight": "model-00002-of-00002.safetensors",
        }
    }

    summary = summarize_hf_metadata("fake/qwen", config, index)

    assert summary["model"] == "fake/qwen"
    assert summary["model_type"] == "qwen3_5_moe"
    assert summary["mtp_num_hidden_layers"] == 1
    assert summary["has_mtp_weights"] is True
    assert summary["mtp_weight_count"] == 2
    assert summary["mtp_weight_examples"] == [
        "mtp.fc.weight",
        "mtp.layers.0.self_attn.q_proj.weight",
    ]

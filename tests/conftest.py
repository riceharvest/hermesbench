from __future__ import annotations

import importlib.util
from pathlib import Path


LEGACY_ML_TESTS = {
    'test_data_alignment.py',
    'test_datasets.py',
    'test_eval_usecase.py',
    'test_gpu_gradient_probe.py',
    'test_modal_smoke_eval.py',
    'test_modal_training_token_filter.py',
    'test_prediction_runner.py',
    'test_probe.py',
    'test_qwen_mtp.py',
    'test_train_sft_config.py',
    'test_ultra_compact_data.py',
}


def pytest_ignore_collect(collection_path: Path, config):
    """Keep HermesBench core CI lightweight when optional ML deps are absent."""
    if importlib.util.find_spec('torch') is not None:
        return False
    return collection_path.name in LEGACY_ML_TESTS

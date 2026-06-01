from pathlib import Path
import importlib.util


def load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "create_fresh_wave.py"
    spec = importlib.util.spec_from_file_location("create_fresh_wave", path)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_create_fresh_wave_starter_files(tmp_path):
    mod = load_module()
    written = mod.create_wave("fresh-2026-07", 2, tmp_path)
    assert tmp_path.joinpath("tasks/fresh-rolling/fresh-2026-07/manifest.yaml").exists()
    assert tmp_path.joinpath("tasks/fresh-rolling/fresh-2026-07/fresh-2026-07-001.md").read_text().startswith("---")
    assert tmp_path.joinpath("fixtures/fresh-2026-07/fresh-2026-07-002/README.md").exists()
    manifest = tmp_path.joinpath("tasks/fresh-rolling/fresh-2026-07/manifest.yaml").read_text()
    assert "minimum_task_count: 2" in manifest
    assert "fresh-2026-07-001" in manifest
    assert written


def test_create_fresh_wave_rejects_bad_wave(tmp_path):
    mod = load_module()
    try:
        mod.create_wave("wave-2026-07", 1, tmp_path)
    except SystemExit as exc:
        assert "fresh-" in str(exc)
    else:
        raise AssertionError("expected SystemExit")

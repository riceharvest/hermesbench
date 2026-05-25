"""Assemble a local checkpoint dir that overrides original `mtp.*` weights.

Input:
- an original HF model snapshot/local dir containing all base shards
- an export dir containing `mtp-refresh.safetensors` and
  `model.safetensors.index.with-mtp-refresh.json`

Output:
- a checkpoint directory with symlinks/copies to original files,
- copied `mtp-refresh.safetensors`,
- `model.safetensors.index.json` replaced so all `mtp.*` keys point to the refresh shard.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def assemble_checkpoint(*, source: Path, export: Path, output: Path, copy_files: bool) -> None:
    source = source.resolve()
    export = export.resolve()
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
        if copy_files:
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        else:
            os.symlink(item, dest, target_is_directory=item.is_dir())

    shutil.copy2(refresh_shard, output / refresh_shard.name)
    shutil.copy2(refreshed_index, output / "model.safetensors.index.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble a Qwen MTP-refresh checkpoint dir.")
    parser.add_argument("--source", type=Path, required=True, help="Original HF snapshot/local model dir")
    parser.add_argument("--export", type=Path, required=True, help="Directory with mtp-refresh.safetensors")
    parser.add_argument("--output", type=Path, required=True, help="Output checkpoint dir")
    parser.add_argument("--copy", action="store_true", help="Copy files instead of symlinking")
    args = parser.parse_args()
    assemble_checkpoint(source=args.source, export=args.export, output=args.output, copy_files=args.copy)
    print(f"assembled {args.output}")


if __name__ == "__main__":
    main()

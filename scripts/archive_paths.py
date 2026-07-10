"""Canonical repository-relative official archive path validation."""
from __future__ import annotations

import re
import sys
from typing import Iterable

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def is_official_archive_source(source: object) -> bool:
    """Accept only canonical `official-runs/<safe-segment>/...` POSIX paths."""
    if not isinstance(source, str) or any(char in source for char in ("%", "?", "#", "\\")):
        return False
    parts = source.split("/")
    return (
        len(parts) >= 3
        and parts[0] == "official-runs"
        and all(part not in {"", ".", ".."} and _SAFE_SEGMENT.fullmatch(part) for part in parts[1:])
    )


def validate_lines(lines: Iterable[str]) -> list[bool]:
    return [is_official_archive_source(line.rstrip("\n")) for line in lines]


if __name__ == "__main__":
    print("\n".join("true" if valid else "false" for valid in validate_lines(sys.stdin)))

"""Root conftest: custom CLI options and shared fixtures for acceptance tests."""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --run-slow to opt into heavyweight release-reproducibility tests."""
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests (fresh-wheel install, sdist rebuild, etc.).",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the 'slow' marker in the config so --strict-markers doesn't barf."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (fresh-wheel install, sdist rebuild, "
        "long-running reproducibility gates). Skipped by default without --run-slow.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip slow tests unless --run-slow was passed."""
    if not config.getoption("--run-slow"):
        skip_slow = pytest.mark.skip(reason="use --run-slow to enable reproducibility tests")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)

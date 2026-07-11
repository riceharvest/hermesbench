"""Root conftest: custom CLI options and shared fixtures for acceptance tests.

Fixture policy:
  - The ``fake_hermes`` fixture (test_hermes_telemetry.py) is deliberately
    module-scoped — it sets up PATH, HOME, monkeypatches, and an executable
    shim that only the telemetry module needs.  No other test module currently
    requires it, so hoisting it here would increase fixture surface without
    reducing real duplication.
  - Module-level helpers (``_fake_task``, ``_temporary_profile_dirs`` in
    test_hermes_telemetry.py) serve the same purpose in the same module.
  - If a second module ever needs ``fake_hermes``, promote it here with a
    ``@pytest.fixture(scope='module')`` and document the cross-module contract.
"""

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

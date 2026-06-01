from pathlib import Path
import tomllib


def test_pytest_is_configured_for_parallel_execution_when_available():
    config = tomllib.loads(Path('pyproject.toml').read_text())

    pytest_options = config['tool']['pytest']['ini_options']
    assert '-n' in pytest_options['addopts'].split()
    assert 'auto' in pytest_options['addopts'].split()


def test_xdist_is_available_in_test_dependency_sets():
    config = tomllib.loads(Path('pyproject.toml').read_text())

    optional_test = config['project']['optional-dependencies']['test']
    optional_dev = config['project']['optional-dependencies']['dev']
    group_dev = config['dependency-groups']['dev']

    assert 'pytest-xdist' in optional_test
    assert 'pytest-xdist' in optional_dev
    assert 'pytest-xdist' in group_dev

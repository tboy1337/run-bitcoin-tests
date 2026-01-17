"""Shared fixtures and configuration for tests."""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_subprocess_run():
    """Mock for subprocess.run that returns a successful result."""
    with pytest.mock.patch("subprocess.run") as mock_run:
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        yield mock_run


@pytest.fixture
def mock_path_exists():
    """Mock for Path that simulates all files existing."""

    def mock_exists(self):
        return True

    with pytest.mock.patch.object(Path, "exists", mock_exists):
        yield


@pytest.fixture
def mock_path_not_exists():
    """Mock for Path that simulates no files existing."""

    def mock_exists(self):
        return False

    with pytest.mock.patch.object(Path, "exists", mock_exists):
        yield


@pytest.fixture
def temp_working_directory(tmp_path):
    """Change to a temporary directory for the test."""
    original_cwd = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        yield tmp_path
    finally:
        os.chdir(original_cwd)


@pytest.fixture(autouse=True)
def reset_modules():
    """Reset imported modules between tests to ensure clean state."""
    modules_to_reset = [
        "run_bitcoin_tests.main",
    ]

    original_modules = {}
    for module in modules_to_reset:
        if module in sys.modules:
            original_modules[module] = sys.modules[module]

    yield

    # Restore original modules
    for module, original in original_modules.items():
        sys.modules[module] = original

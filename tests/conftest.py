"""Shared fixtures and configuration for tests."""

import sys
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_subprocess_run() -> Generator[Mock, None, None]:
    """Mock for subprocess.run that returns a successful result."""
    with patch("subprocess.run") as mock_run:
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        yield mock_run


@pytest.fixture
def mock_path_exists() -> Generator[None, None, None]:
    """Mock for Path that simulates all files existing."""

    def mock_exists(self: Path) -> bool:
        return True

    with patch.object(Path, "exists", mock_exists):
        yield


@pytest.fixture
def mock_path_not_exists() -> Generator[None, None, None]:
    """Mock for Path that simulates no files existing."""

    def mock_exists(self: Path) -> bool:
        return False

    with patch.object(Path, "exists", mock_exists):
        yield


@pytest.fixture
def temp_working_directory(tmp_path: Path) -> Generator[Path, None, None]:
    """Change to a temporary directory for the test."""
    original_cwd = Path.cwd()
    try:
        import os  # isort: skip

        os.chdir(tmp_path)
        yield tmp_path
    finally:
        os.chdir(original_cwd)


@pytest.fixture(autouse=True)
def reset_modules() -> Generator[None, None, None]:
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


@pytest.fixture(autouse=True)
def reset_config() -> Generator[None, None, None]:
    """Reset the global config manager between tests to ensure clean state."""
    # Import here to avoid import-time side effects
    from run_bitcoin_tests import config as config_module  # isort: skip

    # Store original config
    original_config_manager = config_module.config_manager

    # Create a fresh config manager for the test
    config_module.config_manager = config_module.ConfigManager()

    yield

    # Restore original config manager
    config_module.config_manager = original_config_manager

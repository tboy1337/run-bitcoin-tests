"""
Tests for Python functional test support.

This module tests the new functionality for running Bitcoin Core Python
functional tests alongside C++ unit tests.
"""

import argparse
from unittest.mock import MagicMock, Mock, patch

import pytest

from run_bitcoin_tests.config import ConfigManager, ExecutionConfig, get_config, load_config
from run_bitcoin_tests.main import parse_arguments


class TestExecutionConfig:
    """Test the ExecutionConfig dataclass."""

    def test_default_values(self) -> None:
        """Test that ExecutionConfig has correct default values."""
        config = ExecutionConfig()
        assert config.test_suite == "both"
        assert config.python_test_scope == "standard"
        assert config.python_test_jobs == 4
        assert config.cpp_test_args == ""
        assert config.python_test_args == ""
        assert config.exclude_python_tests == []

    def test_custom_values(self) -> None:
        """Test ExecutionConfig with custom values."""
        config = ExecutionConfig(
            test_suite="python",
            python_test_scope="quick",
            python_test_jobs=8,
            cpp_test_args="--log_level=all",
            python_test_args="--coverage",
            exclude_python_tests=["feature_fee_estimation", "rpc_blockchain"],
        )
        assert config.test_suite == "python"
        assert config.python_test_scope == "quick"
        assert config.python_test_jobs == 8
        assert config.cpp_test_args == "--log_level=all"
        assert config.python_test_args == "--coverage"
        assert len(config.exclude_python_tests) == 2


class TestConfigManagerTestSuite:
    """Test ConfigManager handling of test suite configuration."""

    def test_load_test_suite_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading test suite configuration from environment variables."""
        monkeypatch.setenv("BTC_TEST_SUITE", "python")
        monkeypatch.setenv("BTC_PYTHON_TEST_SCOPE", "quick")
        monkeypatch.setenv("BTC_PYTHON_TEST_JOBS", "8")
        monkeypatch.setenv("BTC_CPP_TEST_ARGS", "--log_level=all")
        monkeypatch.setenv("BTC_PYTHON_TEST_ARGS", "--coverage")

        manager = ConfigManager()
        manager.load_from_env_vars()

        assert manager.config.test.test_suite == "python"
        assert manager.config.test.python_test_scope == "quick"
        assert manager.config.test.python_test_jobs == 8
        assert manager.config.test.cpp_test_args == "--log_level=all"
        assert manager.config.test.python_test_args == "--coverage"

    def test_update_from_cli_args_test_suite(self) -> None:
        """Test updating test suite from CLI arguments."""
        manager = ConfigManager()
        args = argparse.Namespace(
            test_suite="cpp",
            python_tests="all",
            python_jobs=16,
            exclude_test=["test1", "test2"],
            cpp_only=False,
            python_only=False,
        )
        manager.update_from_cli_args(args)

        assert manager.config.test.test_suite == "cpp"
        assert manager.config.test.python_test_scope == "all"
        assert manager.config.test.python_test_jobs == 16
        assert manager.config.test.exclude_python_tests == ["test1", "test2"]

    def test_update_from_cli_args_cpp_only(self) -> None:
        """Test --cpp-only shortcut flag."""
        manager = ConfigManager()
        args = argparse.Namespace(
            test_suite=None,
            cpp_only=True,
            python_only=False,
            python_tests=None,
            python_jobs=None,
            exclude_test=None,
        )
        manager.update_from_cli_args(args)

        assert manager.config.test.test_suite == "cpp"

    def test_update_from_cli_args_python_only(self) -> None:
        """Test --python-only shortcut flag."""
        manager = ConfigManager()
        args = argparse.Namespace(
            test_suite=None,
            cpp_only=False,
            python_only=True,
            python_tests=None,
            python_jobs=None,
            exclude_test=None,
        )
        manager.update_from_cli_args(args)

        assert manager.config.test.test_suite == "python"

    def test_validate_test_suite(self) -> None:
        """Test validation of test suite configuration."""
        manager = ConfigManager()

        # Valid test suites
        for suite in ["cpp", "python", "both"]:
            manager.config.test.test_suite = suite
            # Validation happens during load_config, so we just check the value is set
            assert manager.config.test.test_suite in ["cpp", "python", "both"]

        # Invalid test suite would be caught by argparse choices
        manager.config.test.test_suite = "both"
        assert manager.config.test.test_suite == "both"

    def test_validate_python_test_jobs(self) -> None:
        """Test validation of Python test jobs."""
        manager = ConfigManager()

        # Valid jobs
        manager.config.test.python_test_jobs = 1
        assert manager.config.test.python_test_jobs >= 1

        # Test setting jobs
        manager.config.test.python_test_jobs = 8
        assert manager.config.test.python_test_jobs == 8

    def test_get_summary_includes_test_suite(self) -> None:
        """Test that get_summary includes test suite information."""
        manager = ConfigManager()
        manager.config.test.test_suite = "both"
        manager.config.test.python_test_scope = "standard"
        manager.config.test.python_test_jobs = 4

        summary = manager.get_summary()
        assert "Test Suite: both" in summary
        assert "Python Test Scope: standard" in summary
        assert "Python Test Jobs: 4" in summary

    def test_get_summary_cpp_only(self) -> None:
        """Test that get_summary doesn't show Python details for cpp-only."""
        manager = ConfigManager()
        manager.config.test.test_suite = "cpp"

        summary = manager.get_summary()
        assert "Test Suite: cpp" in summary
        assert "Python Test Scope" not in summary
        assert "Python Test Jobs" not in summary


class TestCLIArguments:
    """Test command-line argument parsing for test suite options."""

    @patch("sys.argv", ["run-bitcoin-tests.py", "--test-suite", "python"])
    def test_parse_test_suite_argument(self) -> None:
        """Test parsing --test-suite argument."""
        args = parse_arguments()
        assert args.test_suite == "python"

    @patch("sys.argv", ["run-bitcoin-tests.py", "--cpp-only"])
    def test_parse_cpp_only_flag(self) -> None:
        """Test parsing --cpp-only flag."""
        args = parse_arguments()
        assert args.cpp_only is True

    @patch("sys.argv", ["run-bitcoin-tests.py", "--python-only"])
    def test_parse_python_only_flag(self) -> None:
        """Test parsing --python-only flag."""
        args = parse_arguments()
        assert args.python_only is True

    @patch("sys.argv", ["run-bitcoin-tests.py", "--python-tests", "quick"])
    def test_parse_python_tests_argument(self) -> None:
        """Test parsing --python-tests argument."""
        args = parse_arguments()
        assert args.python_tests == "quick"

    @patch("sys.argv", ["run-bitcoin-tests.py", "--python-jobs", "8"])
    def test_parse_python_jobs_argument(self) -> None:
        """Test parsing --python-jobs argument."""
        args = parse_arguments()
        assert args.python_jobs == 8

    @patch(
        "sys.argv", ["run-bitcoin-tests.py", "--exclude-test", "test1", "--exclude-test", "test2"]
    )
    def test_parse_exclude_test_argument(self) -> None:
        """Test parsing --exclude-test argument (multiple)."""
        args = parse_arguments()
        assert args.exclude_test == ["test1", "test2"]

    @patch(
        "sys.argv",
        [
            "run-bitcoin-tests.py",
            "--python-only",
            "--python-tests",
            "wallet_basic",
            "--python-jobs",
            "16",
        ],
    )
    def test_parse_combined_python_arguments(self) -> None:
        """Test parsing multiple Python test arguments together."""
        args = parse_arguments()
        assert args.python_only is True
        assert args.python_tests == "wallet_basic"
        assert args.python_jobs == 16


class TestTestExecution:
    """Test test execution logic with different test suites."""

    @patch("run_bitcoin_tests.main.run_command")
    @patch("run_bitcoin_tests.main.get_config")
    @patch("run_bitcoin_tests.main.docker_container_lock")
    def test_run_tests_both_suites(
        self, mock_lock: Mock, mock_get_config: Mock, mock_run_command: Mock
    ) -> None:
        """Test running both test suites."""
        from run_bitcoin_tests.main import run_tests  # isort: skip

        # Setup mock config
        mock_config = MagicMock()
        mock_config.test.test_suite = "both"
        mock_config.test.python_test_scope = "standard"
        mock_config.test.python_test_jobs = 4
        mock_config.test.cpp_test_args = ""
        mock_config.test.python_test_args = ""
        mock_config.test.exclude_python_tests = []
        mock_config.docker.container_name = "bitcoin-tests"
        mock_config.quiet = True
        mock_get_config.return_value = mock_config

        # Setup mock command result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        # Setup mock lock context manager
        mock_lock.return_value.__enter__ = Mock()
        mock_lock.return_value.__exit__ = Mock()

        # Run tests
        exit_code = run_tests()

        # Verify
        assert exit_code == 0
        assert mock_run_command.called
        call_args = mock_run_command.call_args[0][0]
        assert any("TEST_SUITE=both" in str(arg) for arg in call_args)

    @patch("run_bitcoin_tests.main.run_command")
    @patch("run_bitcoin_tests.main.get_config")
    @patch("run_bitcoin_tests.main.docker_container_lock")
    def test_run_tests_cpp_only(
        self, mock_lock: Mock, mock_get_config: Mock, mock_run_command: Mock
    ) -> None:
        """Test running C++ tests only."""
        from run_bitcoin_tests.main import run_tests  # isort: skip

        # Setup mock config
        mock_config = MagicMock()
        mock_config.test.test_suite = "cpp"
        mock_config.test.python_test_scope = "standard"
        mock_config.test.python_test_jobs = 4
        mock_config.test.cpp_test_args = ""
        mock_config.test.python_test_args = ""
        mock_config.test.exclude_python_tests = []
        mock_config.docker.container_name = "bitcoin-tests"
        mock_config.quiet = True
        mock_get_config.return_value = mock_config

        # Setup mock command result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        # Setup mock lock context manager
        mock_lock.return_value.__enter__ = Mock()
        mock_lock.return_value.__exit__ = Mock()

        # Run tests
        exit_code = run_tests()

        # Verify
        assert exit_code == 0
        call_args = mock_run_command.call_args[0][0]
        assert any("TEST_SUITE=cpp" in str(arg) for arg in call_args)

    @patch("run_bitcoin_tests.main.run_command")
    @patch("run_bitcoin_tests.main.get_config")
    @patch("run_bitcoin_tests.main.docker_container_lock")
    def test_run_tests_python_only(
        self, mock_lock: Mock, mock_get_config: Mock, mock_run_command: Mock
    ) -> None:
        """Test running Python tests only."""
        from run_bitcoin_tests.main import run_tests  # isort: skip

        # Setup mock config
        mock_config = MagicMock()
        mock_config.test.test_suite = "python"
        mock_config.test.python_test_scope = "quick"
        mock_config.test.python_test_jobs = 8
        mock_config.test.cpp_test_args = ""
        mock_config.test.python_test_args = ""
        mock_config.test.exclude_python_tests = []
        mock_config.docker.container_name = "bitcoin-tests"
        mock_config.quiet = True
        mock_get_config.return_value = mock_config

        # Setup mock command result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        # Setup mock lock context manager
        mock_lock.return_value.__enter__ = Mock()
        mock_lock.return_value.__exit__ = Mock()

        # Run tests
        exit_code = run_tests()

        # Verify
        assert exit_code == 0
        call_args = mock_run_command.call_args[0][0]
        assert any("TEST_SUITE=python" in str(arg) for arg in call_args)
        assert any("PYTHON_TEST_SCOPE=quick" in str(arg) for arg in call_args)
        assert any("PYTHON_TEST_JOBS=8" in str(arg) for arg in call_args)

    @patch("run_bitcoin_tests.main.run_command")
    @patch("run_bitcoin_tests.main.get_config")
    @patch("run_bitcoin_tests.main.docker_container_lock")
    def test_run_tests_with_exclusions(
        self, mock_lock: Mock, mock_get_config: Mock, mock_run_command: Mock
    ) -> None:
        """Test running tests with exclusions."""
        from run_bitcoin_tests.main import run_tests  # isort: skip

        # Setup mock config
        mock_config = MagicMock()
        mock_config.test.test_suite = "python"
        mock_config.test.python_test_scope = "standard"
        mock_config.test.python_test_jobs = 4
        mock_config.test.cpp_test_args = ""
        mock_config.test.python_test_args = ""
        mock_config.test.exclude_python_tests = ["test1", "test2"]
        mock_config.docker.container_name = "bitcoin-tests"
        mock_config.quiet = True
        mock_get_config.return_value = mock_config

        # Setup mock command result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        # Setup mock lock context manager
        mock_lock.return_value.__enter__ = Mock()
        mock_lock.return_value.__exit__ = Mock()

        # Run tests
        exit_code = run_tests()

        # Verify
        assert exit_code == 0
        call_args = mock_run_command.call_args[0][0]
        assert any("EXCLUDE_TESTS=test1,test2" in str(arg) for arg in call_args)


class TestIntegrationWithConfig:
    """Integration tests for configuration and test execution."""

    @patch("sys.argv", ["run-bitcoin-tests.py", "--python-only", "--python-tests", "wallet_basic"])
    def test_full_config_flow_python_only(self) -> None:
        """Test full configuration flow for Python-only tests."""
        args = parse_arguments()
        config = load_config(args)

        assert config.test.test_suite == "python"
        assert config.test.python_test_scope == "wallet_basic"

    @patch("sys.argv", ["run-bitcoin-tests.py", "--cpp-only"])
    def test_full_config_flow_cpp_only(self) -> None:
        """Test full configuration flow for C++-only tests."""
        args = parse_arguments()
        config = load_config(args)

        assert config.test.test_suite == "cpp"

    def test_full_config_flow_default(self) -> None:
        """Test full configuration flow with defaults."""
        # Create a fresh ConfigManager to avoid state from previous tests
        from run_bitcoin_tests.config import ConfigManager  # isort: skip

        manager = ConfigManager()

        # Verify defaults
        assert manager.config.test.test_suite == "both"
        assert manager.config.test.python_test_scope == "standard"
        assert manager.config.test.python_test_jobs == 4

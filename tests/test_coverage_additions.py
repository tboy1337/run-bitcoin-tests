"""
Additional tests to increase code coverage to >90%.

This module focuses on covering edge cases and error paths that are
not covered by existing tests.
"""

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from run_bitcoin_tests.main import (
    clone_bitcoin_repo,
    main,
    parse_arguments,
    print_colored,
)


class TestCloneBitcoinRepoErrorPaths:
    """Test error paths in clone_bitcoin_repo function."""

    @patch("run_bitcoin_tests.main.clone_bitcoin_repo_enhanced")
    @patch("run_bitcoin_tests.main.get_config")
    def test_clone_repo_network_error(self, mock_get_config: Mock, mock_clone: Mock) -> None:
        """Test handling of NetworkError during cloning."""
        from run_bitcoin_tests.network_utils import NetworkError

        mock_config = MagicMock()
        mock_config.network.use_git_cache = False
        mock_config.quiet = True
        mock_get_config.return_value = mock_config

        mock_clone.side_effect = NetworkError("Network connection failed")

        with pytest.raises(NetworkError):
            clone_bitcoin_repo("https://github.com/bitcoin/bitcoin", "master")

    @patch("run_bitcoin_tests.main.get_performance_monitor")
    @patch("run_bitcoin_tests.main.clone_bitcoin_repo_enhanced")
    @patch("run_bitcoin_tests.main.get_config")
    def test_clone_repo_generic_exception(
        self, mock_get_config: Mock, mock_clone: Mock, mock_monitor: Mock
    ) -> None:
        """Test handling of generic exceptions during cloning."""
        mock_config = MagicMock()
        mock_config.network.use_git_cache = False
        mock_config.quiet = False
        mock_get_config.return_value = mock_config

        # Mock performance monitor
        mock_perf_monitor = MagicMock()
        mock_perf_monitor.stop_monitoring.return_value = []
        mock_monitor.return_value = mock_perf_monitor

        mock_clone.side_effect = RuntimeError("Unexpected error")

        # Test that the exception is raised (error handling path is covered)
        with pytest.raises(RuntimeError, match="Unexpected error"):
            clone_bitcoin_repo("https://github.com/bitcoin/bitcoin", "master")


class TestParseArgumentsEdgeCases:
    """Test edge cases in argument parsing."""

    @patch("sys.argv", ["run-bitcoin-tests.py", "--config", ".env.test"])
    @patch("run_bitcoin_tests.config.config_manager")
    def test_parse_args_with_config_file(self, mock_config_manager: Mock) -> None:
        """Test parsing with --config option."""
        args = parse_arguments()
        assert args.config == ".env.test"
        mock_config_manager.load_from_env_file.assert_called_once_with(".env.test")

    @patch("sys.argv", ["run-bitcoin-tests.py", "--show-config"])
    @patch("run_bitcoin_tests.main.load_config")
    @patch("run_bitcoin_tests.config.config_manager")
    def test_parse_args_show_config_success(
        self, mock_config_manager: Mock, mock_load_config: Mock
    ) -> None:
        """Test --show-config option."""
        mock_config_manager.get_summary.return_value = "Test Config"

        with pytest.raises(SystemExit) as exc_info:
            parse_arguments()

        assert exc_info.value.code == 0
        mock_config_manager.get_summary.assert_called_once()

    @patch("sys.argv", ["run-bitcoin-tests.py", "--show-config"])
    @patch("run_bitcoin_tests.main.load_config")
    def test_parse_args_show_config_error(
        self, mock_load_config: Mock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test --show-config with configuration error."""
        mock_load_config.side_effect = ValueError("Invalid config")

        with pytest.raises(SystemExit) as exc_info:
            parse_arguments()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[CONFIG ERROR]" in captured.out

    @patch("sys.argv", ["run-bitcoin-tests.py", "--save-config", "test.env"])
    @patch("run_bitcoin_tests.main.load_config")
    @patch("run_bitcoin_tests.config.config_manager")
    def test_parse_args_save_config_success(
        self, mock_config_manager: Mock, mock_load_config: Mock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test --save-config option."""
        with pytest.raises(SystemExit) as exc_info:
            parse_arguments()

        assert exc_info.value.code == 0
        mock_config_manager.save_to_env_file.assert_called_once_with("test.env")
        captured = capsys.readouterr()
        assert "Configuration saved" in captured.out

    @patch("sys.argv", ["run-bitcoin-tests.py", "--save-config", "test.env"])
    @patch("run_bitcoin_tests.main.load_config")
    @patch("run_bitcoin_tests.config.config_manager")
    def test_parse_args_save_config_error(
        self, mock_config_manager: Mock, mock_load_config: Mock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test --save-config with error."""
        mock_config_manager.save_to_env_file.side_effect = IOError("Cannot write file")

        with pytest.raises(SystemExit) as exc_info:
            parse_arguments()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[ERROR] Failed to save configuration" in captured.out


class TestMainFunctionEdgeCases:
    """Test edge cases in main function."""

    @patch("sys.argv", ["run-bitcoin-tests.py"])
    @patch("run_bitcoin_tests.main.load_config")
    def test_main_config_error(
        self, mock_load_config: Mock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test main function with configuration error."""
        mock_load_config.side_effect = ValueError("Invalid configuration")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[CONFIG ERROR]" in captured.out

    @patch("sys.argv", ["run-bitcoin-tests.py", "--dry-run"])
    @patch("run_bitcoin_tests.main.load_config")
    @patch("run_bitcoin_tests.main.initialize_thread_safety")
    @patch("run_bitcoin_tests.main.optimize_system_resources")
    @patch("run_bitcoin_tests.main.setup_logging")
    def test_main_dry_run(
        self,
        mock_setup_logging: Mock,
        mock_optimize: Mock,
        mock_init_thread: Mock,
        mock_load_config: Mock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test main function with --dry-run flag."""
        mock_config = MagicMock()
        mock_config.dry_run = True
        mock_config.quiet = False
        mock_config.verbose = False
        mock_config.logging.level = "INFO"
        mock_config.logging.file = None
        mock_config.repository.url = "https://github.com/bitcoin/bitcoin"
        mock_config.repository.branch = "master"
        mock_config.build.type = "RelWithDebInfo"
        mock_config.test.timeout = 3600
        mock_load_config.return_value = mock_config

        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out
        assert "Clone repository" in captured.out


class TestPrintColoredEdgeCases:
    """Test print_colored function variations."""

    def test_print_colored_default(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test print_colored with default parameters."""
        from colorama import Fore, Style

        print_colored("Test message")
        captured = capsys.readouterr()
        assert "Test message" in captured.out

    def test_print_colored_with_color(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test print_colored with specific color."""
        from colorama import Fore, Style

        print_colored("Red message", Fore.RED)
        captured = capsys.readouterr()
        assert "Red message" in captured.out

    def test_print_colored_with_bright(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test print_colored with bright option."""
        from colorama import Fore, Style

        print_colored("Bright message", Fore.GREEN, bright=True)
        captured = capsys.readouterr()
        assert "Bright message" in captured.out


class TestNetworkErrorHandling:
    """Test network error handling in various functions."""

    @patch("run_bitcoin_tests.main.check_prerequisites")
    @patch("run_bitcoin_tests.main.build_docker_image")
    @patch("run_bitcoin_tests.main.run_tests")
    @patch("run_bitcoin_tests.main.cleanup_containers")
    @patch("run_bitcoin_tests.main.load_config")
    @patch("run_bitcoin_tests.main.initialize_thread_safety")
    @patch("run_bitcoin_tests.main.optimize_system_resources")
    @patch("run_bitcoin_tests.main.setup_logging")
    @patch("sys.argv", ["run-bitcoin-tests.py"])
    def test_main_network_error(
        self,
        mock_setup_logging: Mock,
        mock_optimize: Mock,
        mock_init_thread: Mock,
        mock_load_config: Mock,
        mock_cleanup: Mock,
        mock_run_tests: Mock,
        mock_build: Mock,
        mock_check: Mock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test main function handling network errors."""
        from run_bitcoin_tests.network_utils import NetworkError

        mock_config = MagicMock()
        mock_config.dry_run = False
        mock_config.quiet = False
        mock_config.verbose = False
        mock_config.logging.level = "INFO"
        mock_config.logging.file = None
        mock_config.docker.keep_containers = False
        mock_load_config.return_value = mock_config

        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger

        mock_check.side_effect = NetworkError("Network connection failed")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[NETWORK ERROR]" in captured.out

    @patch("run_bitcoin_tests.main.check_prerequisites")
    @patch("run_bitcoin_tests.main.build_docker_image")
    @patch("run_bitcoin_tests.main.run_tests")
    @patch("run_bitcoin_tests.main.cleanup_containers")
    @patch("run_bitcoin_tests.main.load_config")
    @patch("run_bitcoin_tests.main.initialize_thread_safety")
    @patch("run_bitcoin_tests.main.optimize_system_resources")
    @patch("run_bitcoin_tests.main.setup_logging")
    @patch("sys.argv", ["run-bitcoin-tests.py"])
    def test_main_repository_error(
        self,
        mock_setup_logging: Mock,
        mock_optimize: Mock,
        mock_init_thread: Mock,
        mock_load_config: Mock,
        mock_cleanup: Mock,
        mock_run_tests: Mock,
        mock_build: Mock,
        mock_check: Mock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test main function handling repository errors."""
        from run_bitcoin_tests.network_utils import RepositoryError

        mock_config = MagicMock()
        mock_config.dry_run = False
        mock_config.quiet = False
        mock_config.verbose = False
        mock_config.logging.level = "INFO"
        mock_config.logging.file = None
        mock_config.docker.keep_containers = False
        mock_load_config.return_value = mock_config

        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger

        mock_check.side_effect = RuntimeError("Repository not found")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[REPO ERROR]" in captured.out


class TestConfigLoadingEdgeCases:
    """Test configuration loading edge cases."""

    @patch("sys.argv", ["run-bitcoin-tests.py", "--test-suite", "invalid"])
    def test_parse_args_invalid_test_suite(self) -> None:
        """Test that invalid test suite is caught by argparse."""
        with pytest.raises(SystemExit):
            parse_arguments()

    @patch("sys.argv", ["run-bitcoin-tests.py", "--build-type", "InvalidType"])
    def test_parse_args_invalid_build_type(self) -> None:
        """Test that invalid build type is caught by argparse."""
        with pytest.raises(SystemExit):
            parse_arguments()

    @patch("sys.argv", ["run-bitcoin-tests.py", "--log-level", "INVALID"])
    def test_parse_args_invalid_log_level(self) -> None:
        """Test that invalid log level is caught by argparse."""
        with pytest.raises(SystemExit):
            parse_arguments()

"""Integration tests for the run-bitcoin-tests package."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from run_bitcoin_tests.main import main


class TestIntegration:
    """Integration tests for the full workflow."""

    @patch("run_bitcoin_tests.main.parse_arguments")
    @patch("run_bitcoin_tests.main.check_prerequisites")
    @patch("run_bitcoin_tests.main.build_docker_image")
    @patch("run_bitcoin_tests.main.run_tests")
    @patch("run_bitcoin_tests.main.cleanup_containers")
    @patch("sys.exit")
    def test_full_workflow_success(self, mock_exit, mock_cleanup, mock_run_tests,
                                  mock_build, mock_check_prereqs, mock_parse_args, capsys):
        """Test the complete workflow with all functions succeeding."""
        # Setup mocks for successful execution
        mock_args = Mock()
        mock_args.repo_url = "https://github.com/bitcoin/bitcoin"
        mock_args.branch = "master"
        mock_args.verbose = False
        mock_args.quiet = False
        mock_args.log_level = "INFO"
        mock_args.log_file = None
        mock_args.no_cache = False
        mock_args.performance_monitor = False
        mock_args.dry_run = False
        mock_parse_args.return_value = mock_args

        mock_run_tests.return_value = 0

        # Run main function
        main()

        # Verify the workflow
        output = capsys.readouterr().out
        assert "Bitcoin Core C++ Tests Runner" in output

        # Verify all steps were called
        mock_check_prereqs.assert_called_once()
        mock_build.assert_called_once()
        mock_run_tests.assert_called_once()
        mock_cleanup.assert_called_once()
        mock_exit.assert_called_once_with(0)

    @patch("run_bitcoin_tests.main.parse_arguments")
    @patch("run_bitcoin_tests.main.check_prerequisites")
    @patch("run_bitcoin_tests.main.build_docker_image")
    @patch("run_bitcoin_tests.main.run_tests")
    @patch("run_bitcoin_tests.main.cleanup_containers")
    @patch("sys.exit")
    def test_full_workflow_with_custom_args(self, mock_exit, mock_cleanup, mock_run_tests,
                                          mock_build, mock_check_prereqs, mock_parse_args, capsys):
        """Test the complete workflow with custom repository arguments."""
        # Setup mocks for custom repo
        mock_args = Mock()
        mock_args.repo_url = "https://github.com/myfork/bitcoin"
        mock_args.branch = "feature-branch"
        mock_args.verbose = False
        mock_args.quiet = False
        mock_args.log_level = "INFO"
        mock_args.log_file = None
        mock_args.no_cache = False
        mock_args.performance_monitor = False
        mock_args.dry_run = False
        mock_parse_args.return_value = mock_args

        mock_run_tests.return_value = 0

        # Run main function
        main()

        # Verify custom repo info is displayed
        output = capsys.readouterr().out
        assert "Repository: https://github.com/myfork/bitcoin (branch: feature-branch)" in output

        mock_check_prereqs.assert_called_once()
        mock_exit.assert_called_once_with(0)


class TestCommandLineInterface:
    """Test the command line interface."""

    def test_script_execution_help(self):
        """Test that the script can display help."""
        result = subprocess.run(
            [sys.executable, "run-bitcoin-tests.py", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        assert result.returncode == 0
        assert "Run Bitcoin Core C++ unit tests in Docker" in result.stdout
        assert "--repo-url" in result.stdout
        assert "--branch" in result.stdout

    def test_module_execution_help(self):
        """Test that the module can be executed with help."""
        result = subprocess.run(
            [sys.executable, "-m", "run_bitcoin_tests", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        assert result.returncode == 0
        assert "Run Bitcoin Core C++ unit tests in Docker" in result.stdout


class TestErrorScenarios:
    """Test various error scenarios."""

    @patch("run_bitcoin_tests.main.get_config")
    @patch("run_bitcoin_tests.main.Path")
    def test_prerequisites_failure_calls_cleanup_indirectly(self, mock_path, mock_get_config):
        """Test that prerequisites failure would trigger cleanup (integration test)."""
        # This is a conceptual test - in real usage, sys.exit() calls from individual
        # functions would exit the program. Here we test that the functions work as expected.
        from run_bitcoin_tests.main import check_prerequisites

        # Mock config
        mock_config = Mock()
        mock_config.quiet = True
        mock_config.docker.compose_file = "docker-compose.yml"
        mock_get_config.return_value = mock_config

        with pytest.raises(SystemExit):
            # Setup mocks to simulate missing files
            def path_side_effect(path_str):
                mock_file = Mock()
                mock_file.exists.return_value = False  # Files don't exist
                return mock_file

            mock_path.side_effect = path_side_effect

            check_prerequisites()

    def test_build_failure_calls_cleanup_indirectly(self):
        """Test that build failure would trigger cleanup (integration test)."""
        # Similar to above - testing the function behavior directly
        from run_bitcoin_tests.main import build_docker_image

        with patch("run_bitcoin_tests.main.run_command") as mock_run, \
             pytest.raises(SystemExit):
            mock_result = Mock()
            mock_result.returncode = 1  # Simulate build failure
            mock_run.return_value = mock_result

            build_docker_image()
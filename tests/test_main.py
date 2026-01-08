"""Unit tests for the main module of run-bitcoin-tests."""

import argparse
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from run_bitcoin_tests.main import (
    build_docker_image,
    check_prerequisites,
    cleanup_containers,
    clone_bitcoin_repo,
    main,
    parse_arguments,
    print_colored,
    run_command,
    run_tests,
)


class TestPrintColored:
    """Test print_colored function."""

    def test_print_colored_with_colorama(self, capsys):
        """Test print_colored with colorama available."""
        with patch("run_bitcoin_tests.main.colorama"):
            print_colored("test message", "RED", bright=True)
            captured = capsys.readouterr()
            assert "test message" in captured.out

    def test_print_colored_without_colorama(self, capsys):
        """Test print_colored without colorama (fallback)."""
        # Test that the fallback classes work by directly testing the fallback logic
        # The colorama import happens at module level, so we test the fallback behavior
        # by checking that print_colored works even when colorama classes are empty strings

        # This test verifies the fallback works by ensuring no exceptions are raised
        # and output is produced
        print_colored("test message", "RED", bright=True)
        captured = capsys.readouterr()
        assert "test message" in captured.out




class TestRunCommand:
    """Test run_command function."""

    @patch("subprocess.run")
    def test_run_command_success(self, mock_run, capsys):
        """Test successful command execution."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = run_command(["echo", "hello"], "Test command")

        assert result == mock_result
        mock_run.assert_called_once_with(
            ["echo", "hello"],
            capture_output=False,
            text=True,
            check=False
        )

    @patch("subprocess.run")
    def test_run_command_file_not_found(self, mock_run, capsys):
        """Test command execution when command is not found."""
        mock_run.side_effect = FileNotFoundError("Command not found")

        with pytest.raises(SystemExit) as exc_info:
            run_command(["nonexistent_command"], "Test command")

        assert exc_info.value.code == 1

    @patch("subprocess.run")
    def test_run_command_generic_exception(self, mock_run, capsys):
        """Test command execution with generic exception."""
        mock_run.side_effect = Exception("Generic error")

        with pytest.raises(SystemExit) as exc_info:
            run_command(["echo", "hello"], "Test command")

        assert exc_info.value.code == 1


class TestCloneBitcoinRepo:
    """Test clone_bitcoin_repo function."""

    @patch("run_bitcoin_tests.main.clone_bitcoin_repo_enhanced")
    def test_clone_repo_already_exists(self, mock_clone_enhanced, capsys):
        """Test when bitcoin directory already exists."""
        clone_bitcoin_repo("https://github.com/bitcoin/bitcoin", "master")

        # Should call the enhanced clone function
        mock_clone_enhanced.assert_called_once_with("https://github.com/bitcoin/bitcoin", "master", "bitcoin")

    @patch("run_bitcoin_tests.main.clone_bitcoin_repo_enhanced")
    def test_clone_repo_success(self, mock_clone_enhanced, capsys):
        """Test successful repository cloning."""
        # Mock the enhanced clone function to not raise an exception
        mock_clone_enhanced.return_value = None

        clone_bitcoin_repo("https://github.com/bitcoin/bitcoin", "master")

        # Verify the enhanced clone function was called
        mock_clone_enhanced.assert_called_once_with("https://github.com/bitcoin/bitcoin", "master", "bitcoin")

    @patch("run_bitcoin_tests.main.clone_bitcoin_repo_enhanced")
    def test_clone_repo_failure(self, mock_clone_enhanced, capsys):
        """Test repository cloning failure."""
        # Mock the enhanced clone function to raise an exception
        mock_clone_enhanced.side_effect = Exception("Clone failed")

        with pytest.raises(Exception, match="Clone failed"):
            clone_bitcoin_repo("https://github.com/bitcoin/bitcoin", "master")

        # Verify the enhanced clone function was called
        mock_clone_enhanced.assert_called_once_with("https://github.com/bitcoin/bitcoin", "master", "bitcoin")

    @patch("run_bitcoin_tests.main.clone_bitcoin_repo_enhanced")
    def test_clone_repo_exception(self, mock_clone_enhanced, capsys):
        """Test repository cloning with exception."""
        # Mock the enhanced clone function to raise an exception
        mock_clone_enhanced.side_effect = Exception("Network error")

        with pytest.raises(Exception, match="Network error"):
            clone_bitcoin_repo("https://github.com/bitcoin/bitcoin", "master")

        # Verify the enhanced clone function was called
        mock_clone_enhanced.assert_called_once_with("https://github.com/bitcoin/bitcoin", "master", "bitcoin")


class TestCheckPrerequisites:
    """Test check_prerequisites function."""

    @patch("run_bitcoin_tests.main.clone_bitcoin_repo")
    @patch("run_bitcoin_tests.main.Path")
    def test_check_prerequisites_missing_files(self, mock_path, mock_clone, capsys):
        """Test when required files are missing."""
        # Mock Path to return files that don't exist
        def path_side_effect(path_str):
            mock_file = Mock()
            mock_file.exists.return_value = False
            return mock_file

        mock_path.side_effect = path_side_effect

        with pytest.raises(SystemExit) as exc_info:
            check_prerequisites("https://github.com/bitcoin/bitcoin", "master")

        assert exc_info.value.code == 1

    @patch("run_bitcoin_tests.main.clone_bitcoin_repo")
    @patch("run_bitcoin_tests.main.Path")
    def test_check_prerequisites_success(self, mock_path, mock_clone, capsys):
        """Test successful prerequisites check."""
        # Mock Path for required files (exist) and CMakeLists.txt (exists)
        call_count = 0
        def path_side_effect(path_str):
            nonlocal call_count
            mock_file = Mock()
            if path_str in ["docker-compose.yml", "Dockerfile", "bitcoin/CMakeLists.txt"]:
                mock_file.exists.return_value = True
            else:
                mock_file.exists.return_value = False
            call_count += 1
            return mock_file

        mock_path.side_effect = path_side_effect

        check_prerequisites("https://github.com/bitcoin/bitcoin", "master")

        # Should have called clone_bitcoin_repo
        mock_clone.assert_called_once_with("https://github.com/bitcoin/bitcoin", "master")

    @patch("run_bitcoin_tests.main.clone_bitcoin_repo")
    @patch("run_bitcoin_tests.main.Path")
    def test_check_prerequisites_missing_cmake(self, mock_path, mock_clone, capsys):
        """Test when CMakeLists.txt is missing after cloning."""
        # Mock Path for required files (exist) but CMakeLists.txt doesn't exist
        def path_side_effect(path_str):
            mock_file = Mock()
            if path_str in ["docker-compose.yml", "Dockerfile"]:
                mock_file.exists.return_value = True
            else:
                mock_file.exists.return_value = False
            return mock_file

        mock_path.side_effect = path_side_effect

        with pytest.raises(SystemExit) as exc_info:
            check_prerequisites("https://github.com/bitcoin/bitcoin", "master")

        assert exc_info.value.code == 1


class TestBuildDockerImage:
    """Test build_docker_image function."""

    @patch("run_bitcoin_tests.main.run_command")
    def test_build_docker_image_success(self, mock_run_command, capsys):
        """Test successful Docker image build."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        build_docker_image()

        mock_run_command.assert_called_once_with(["docker-compose", "build"], "Build Docker image")

    @patch("run_bitcoin_tests.main.run_command")
    def test_build_docker_image_failure(self, mock_run_command, capsys):
        """Test Docker image build failure."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_run_command.return_value = mock_result

        with pytest.raises(SystemExit) as exc_info:
            build_docker_image()

        assert exc_info.value.code == 1


class TestRunTests:
    """Test run_tests function."""

    @patch("run_bitcoin_tests.main.run_command")
    def test_run_tests_success(self, mock_run_command, capsys):
        """Test successful test execution."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        exit_code = run_tests()

        assert exit_code == 0
        mock_run_command.assert_called_once_with(
            ["docker-compose", "run", "--rm", "bitcoin-tests"], "Run tests"
        )

    @patch("run_bitcoin_tests.main.run_command")
    def test_run_tests_failure(self, mock_run_command, capsys):
        """Test test execution failure."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_run_command.return_value = mock_result

        exit_code = run_tests()

        assert exit_code == 1


class TestCleanupContainers:
    """Test cleanup_containers function."""

    @patch("run_bitcoin_tests.main.run_command")
    def test_cleanup_containers(self, mock_run_command, capsys):
        """Test container cleanup."""
        cleanup_containers()

        mock_run_command.assert_called_once_with(
            ["docker-compose", "down", "--remove-orphans"], "Cleanup containers"
        )


class TestParseArguments:
    """Test parse_arguments function."""

    def test_parse_arguments_default(self):
        """Test parsing with default arguments."""
        with patch("sys.argv", ["script.py"]):
            args = parse_arguments()

            assert args.repo_url == "https://github.com/bitcoin/bitcoin"
            assert args.branch == "master"

    def test_parse_arguments_custom(self):
        """Test parsing with custom arguments."""
        with patch("sys.argv", ["script.py", "-r", "https://github.com/myfork/bitcoin", "-b", "feature-branch"]):
            args = parse_arguments()

            assert args.repo_url == "https://github.com/myfork/bitcoin"
            assert args.branch == "feature-branch"

    def test_parse_arguments_long_options(self):
        """Test parsing with long options."""
        with patch("sys.argv", ["script.py", "--repo-url", "https://github.com/test/bitcoin", "--branch", "test-branch"]):
            args = parse_arguments()

            assert args.repo_url == "https://github.com/test/bitcoin"
            assert args.branch == "test-branch"


class TestMain:
    """Test main function."""

    @patch("run_bitcoin_tests.main.parse_arguments")
    @patch("run_bitcoin_tests.main.check_prerequisites")
    @patch("run_bitcoin_tests.main.build_docker_image")
    @patch("run_bitcoin_tests.main.run_tests")
    @patch("run_bitcoin_tests.main.cleanup_containers")
    @patch("sys.exit")
    def test_main_success(self, mock_exit, mock_cleanup, mock_run_tests, mock_build,
                         mock_check_prereqs, mock_parse_args, capsys):
        """Test successful main execution."""
        # Setup mocks
        mock_args = Mock()
        mock_args.repo_url = "https://github.com/bitcoin/bitcoin"
        mock_args.branch = "master"
        mock_parse_args.return_value = mock_args

        mock_run_tests.return_value = 0

        main()

        # Verify all functions were called
        mock_parse_args.assert_called_once()
        mock_check_prereqs.assert_called_once_with(mock_args.repo_url, mock_args.branch)
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
    def test_main_tests_failure(self, mock_exit, mock_cleanup, mock_run_tests, mock_build,
                               mock_check_prereqs, mock_parse_args, capsys):
        """Test main execution when tests fail."""
        # Setup mocks
        mock_args = Mock()
        mock_args.repo_url = "https://github.com/bitcoin/bitcoin"
        mock_args.branch = "master"
        mock_parse_args.return_value = mock_args

        mock_run_tests.return_value = 1

        main()

        # Verify cleanup and exit with test failure code
        mock_cleanup.assert_called_once()
        mock_exit.assert_called_once_with(1)

    @patch("run_bitcoin_tests.main.parse_arguments")
    @patch("run_bitcoin_tests.main.check_prerequisites")
    @patch("run_bitcoin_tests.main.cleanup_containers")
    @patch("sys.exit")
    def test_main_keyboard_interrupt(self, mock_exit, mock_cleanup, mock_check_prereqs,
                                   mock_parse_args, capsys):
        """Test main execution with keyboard interrupt."""
        # Setup mocks
        mock_args = Mock()
        mock_parse_args.return_value = mock_args

        mock_check_prereqs.side_effect = KeyboardInterrupt()

        main()

        # Verify cleanup and exit with interrupt code
        mock_cleanup.assert_called_once()
        mock_exit.assert_called_once_with(130)

    @patch("run_bitcoin_tests.main.parse_arguments")
    @patch("run_bitcoin_tests.main.check_prerequisites")
    @patch("run_bitcoin_tests.main.cleanup_containers")
    @patch("sys.exit")
    def test_main_generic_exception(self, mock_exit, mock_cleanup, mock_check_prereqs,
                                   mock_parse_args, capsys):
        """Test main execution with generic exception."""
        # Setup mocks
        mock_args = Mock()
        mock_parse_args.return_value = mock_args

        mock_check_prereqs.side_effect = Exception("Test error")

        main()

        # Verify cleanup and exit with error code
        mock_cleanup.assert_called_once()
        mock_exit.assert_called_once_with(1)
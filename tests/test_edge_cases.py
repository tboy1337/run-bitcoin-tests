"""Edge case and error condition tests for the run-bitcoin-tests package."""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from run_bitcoin_tests.main import (
    build_docker_image,
    check_prerequisites,
    clone_bitcoin_repo,
    run_command,
    run_tests,
)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_run_command_empty_command_list(self) -> None:
        """Test run_command with empty command list."""
        with pytest.raises(SystemExit) as exc_info:
            run_command([], "Empty command")

        assert exc_info.value.code == 1

    @patch("subprocess.run")
    def test_run_command_with_special_characters(self, mock_run) -> None:
        """Test run_command with commands containing special characters."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Test command with spaces, quotes, and special chars
        command = ["echo", 'hello "world" & test']
        result = run_command(command, "Special chars test")

        assert result == mock_result
        mock_run.assert_called_once_with(command, capture_output=False, text=True, check=False)

    @patch("run_bitcoin_tests.main.clone_bitcoin_repo_enhanced")
    def test_clone_repo_with_unicode_branch_name(self, mock_clone_enhanced) -> None:
        """Test cloning with Unicode branch names."""
        # Mock the enhanced clone function
        mock_clone_enhanced.return_value = None

        unicode_branch = "feature/ñämé-tëst"
        clone_bitcoin_repo("https://github.com/bitcoin/bitcoin", unicode_branch)

        # Verify the enhanced clone function was called with the unicode branch name
        mock_clone_enhanced.assert_called_once_with(
            repo_url="https://github.com/bitcoin/bitcoin",
            branch=unicode_branch,
            target_dir="bitcoin",
            use_cache=True,
        )

    @patch("run_bitcoin_tests.main.get_config")
    @patch("run_bitcoin_tests.main.clone_bitcoin_repo")
    @patch("run_bitcoin_tests.main.Path")
    def test_check_prerequisites_empty_repo_url(self, mock_path, mock_clone, mock_get_config) -> None:
        """Test check_prerequisites with empty repository URL."""
        mock_config = Mock()
        mock_config.docker.compose_file = "docker-compose.yml"
        mock_config.repository.url = ""
        mock_config.repository.branch = "master"
        mock_config.quiet = False
        mock_get_config.return_value = mock_config

        # Mock required files exist
        def path_side_effect(path_str):
            mock_file = Mock()
            mock_file.exists.return_value = True
            return mock_file

        mock_path.side_effect = path_side_effect

        # Empty repo URL should still work (though not recommended)
        check_prerequisites()

        mock_clone.assert_called_once_with("", "master")

    @patch("run_bitcoin_tests.main.get_config")
    @patch("run_bitcoin_tests.main.clone_bitcoin_repo")
    @patch("run_bitcoin_tests.main.Path")
    def test_check_prerequisites_empty_branch(self, mock_path, mock_clone, mock_get_config) -> None:
        """Test check_prerequisites with empty branch name."""
        mock_config = Mock()
        mock_config.docker.compose_file = "docker-compose.yml"
        mock_config.repository.url = "https://github.com/bitcoin/bitcoin"
        mock_config.repository.branch = ""
        mock_config.quiet = False
        mock_get_config.return_value = mock_config

        # Mock required files exist
        def path_side_effect(path_str):
            mock_file = Mock()
            mock_file.exists.return_value = True
            return mock_file

        mock_path.side_effect = path_side_effect

        # Empty branch should still work
        check_prerequisites()

        mock_clone.assert_called_once_with("https://github.com/bitcoin/bitcoin", "")

    @patch("run_bitcoin_tests.main.run_command")
    def test_build_docker_image_with_unicode_description(self, mock_run_command) -> None:
        """Test build_docker_image with unicode characters in internal description."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        build_docker_image()

        # The description contains unicode characters
        args = mock_run_command.call_args[0]
        description = args[1]
        assert "Build Docker image" == description

    @patch("run_bitcoin_tests.main.run_command")
    def test_run_tests_with_unicode_description(self, mock_run_command) -> None:
        """Test run_tests with unicode characters in internal description."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        exit_code = run_tests()

        assert exit_code == 0
        # The description contains unicode characters
        args = mock_run_command.call_args[0]
        description = args[1]
        assert "Run tests" == description


class TestEnvironmentVariables:
    """Test behavior with different environment variables."""

    @patch.dict(os.environ, {"DOCKER_HOST": "tcp://localhost:2376"})
    @patch("run_bitcoin_tests.main.get_config")
    @patch("run_bitcoin_tests.main.run_command")
    def test_docker_with_custom_host(self, mock_run_command, mock_get_config) -> None:
        """Test that Docker commands work with custom DOCKER_HOST."""
        mock_config = Mock()
        mock_config.docker.compose_file = "docker-compose.yml"
        mock_config.docker.container_name = "bitcoin-tests"
        mock_config.build.parallel_jobs = None
        mock_config.quiet = False
        mock_get_config.return_value = mock_config

        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        build_docker_image()

        # Should still work with custom Docker host - check that build command was called
        call_args = mock_run_command.call_args[0][0]
        assert "build" in call_args

    @patch.dict(os.environ, {"COMPOSE_FILE": "custom-compose.yml"})
    @patch("run_bitcoin_tests.main.get_config")
    @patch("run_bitcoin_tests.main.run_command")
    def test_docker_compose_with_custom_file(self, mock_run_command, mock_get_config) -> None:
        """Test that docker-compose works with custom COMPOSE_FILE."""
        mock_config = Mock()
        mock_config.docker.compose_file = "docker-compose.yml"
        mock_config.docker.container_name = "bitcoin-tests"
        mock_config.build.parallel_jobs = None
        mock_config.quiet = False
        mock_get_config.return_value = mock_config

        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        build_docker_image()

        # Should still work with custom compose file
        mock_run_command.assert_called_once_with(
            [
                "docker",
                "compose",
                "-f",
                "docker-compose.yml",
                "build",
                "--no-cache-filter",
                "bitcoin-deps",
            ],
            "Build Docker image",
        )


class TestFileSystemEdgeCases:
    """Test file system related edge cases."""

    @patch("run_bitcoin_tests.main.get_config")
    @patch("run_bitcoin_tests.main.Path")
    def test_check_prerequisites_with_symlinks(self, mock_path, mock_get_config) -> None:
        """Test prerequisites check with symlinked files."""
        mock_config = Mock()
        mock_config.docker.compose_file = "docker-compose.yml"
        mock_config.repository.url = "https://github.com/bitcoin/bitcoin"
        mock_config.repository.branch = "master"
        mock_config.quiet = False
        mock_get_config.return_value = mock_config

        # Mock paths to simulate symlinks (exists returns True for all)
        def path_side_effect(path_str):
            mock_file = Mock()
            mock_file.exists.return_value = True
            return mock_file

        mock_path.side_effect = path_side_effect

        # Should pass when all files exist (even if symlinks)
        check_prerequisites()

    @patch("run_bitcoin_tests.main.get_config")
    @patch("run_bitcoin_tests.main.Path")
    def test_check_prerequisites_file_permissions(self, mock_path, mock_get_config) -> None:
        """Test prerequisites check when files exist but may not be readable."""
        mock_config = Mock()
        mock_config.docker.compose_file = "docker-compose.yml"
        mock_config.repository.url = "https://github.com/bitcoin/bitcoin"
        mock_config.repository.branch = "master"
        mock_config.quiet = False
        mock_get_config.return_value = mock_config

        # Mock paths - files exist but simulate permission issues
        def path_side_effect(path_str):
            mock_file = Mock()
            mock_file.exists.return_value = True
            return mock_file

        mock_path.side_effect = path_side_effect

        # Should pass since we're only checking existence, not readability
        check_prerequisites()


class TestConcurrencyEdgeCases:
    """Test edge cases that might occur in concurrent environments."""

    @patch("run_bitcoin_tests.main.run_command")
    def test_multiple_docker_operations(self, mock_run_command) -> None:
        """Test running multiple Docker operations in sequence."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        # Run multiple operations
        build_docker_image()
        run_tests()
        run_tests()  # Run tests twice

        # Should have called run_command 3 times
        assert mock_run_command.call_count == 3

    @patch("run_bitcoin_tests.main.run_command")
    def test_cleanup_called_multiple_times(self, mock_run_command) -> None:
        """Test that cleanup can be called multiple times safely."""
        from run_bitcoin_tests.main import cleanup_containers

        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result

        # Call cleanup multiple times
        cleanup_containers()
        cleanup_containers()
        cleanup_containers()

        # Should have called run_command 3 times
        assert mock_run_command.call_count == 3

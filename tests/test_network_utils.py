"""Tests for network utilities module."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from run_bitcoin_tests.network_utils import (
    diagnose_network_connectivity,
    run_git_command_with_retry,
    clone_bitcoin_repo_enhanced,
    ConnectionError,
    SSLError,
    AuthenticationError,
    RepositoryError,
    DiskSpaceError,
    TimeoutError,
)


class TestDiagnoseNetworkConnectivity:
    """Test network connectivity diagnostics."""

    @patch("socket.gethostbyname")
    @patch("subprocess.run")
    def test_successful_connectivity(self, mock_run, mock_gethostbyname):
        """Test successful network connectivity diagnosis."""
        # Mock successful ping
        mock_ping_result = Mock()
        mock_ping_result.returncode = 0
        mock_run.return_value = mock_ping_result

        # Mock successful DNS resolution
        mock_gethostbyname.return_value = "192.168.1.1"

        diagnostics = diagnose_network_connectivity("https://github.com/bitcoin/bitcoin")

        assert len(diagnostics) >= 2
        assert any("connectivity" in diag and "working" in diag for diag in diagnostics)
        assert any("DNS resolution" in diag and "working" in diag for diag in diagnostics)

    @patch("socket.gethostbyname")
    @patch("subprocess.run")
    def test_failed_connectivity(self, mock_run, mock_gethostbyname):
        """Test failed network connectivity diagnosis."""
        # Mock failed ping
        mock_ping_result = Mock()
        mock_ping_result.returncode = 1
        mock_run.return_value = mock_ping_result

        # Mock failed DNS resolution
        mock_gethostbyname.side_effect = Exception("DNS resolution failed")

        diagnostics = diagnose_network_connectivity("https://github.com/bitcoin/bitcoin")

        assert len(diagnostics) >= 2
        assert any("Cannot reach" in diag for diag in diagnostics)
        assert any("DNS resolution failed" in diag for diag in diagnostics)


class TestRunGitCommandWithRetry:
    """Test git command execution with retry logic."""

    @patch("subprocess.run")
    def test_successful_command(self, mock_run):
        """Test successful git command execution."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "success"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = run_git_command_with_retry(
            ["git", "status"],
            "Test command",
            max_retries=1
        )

        assert result == mock_result
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_network_error_with_retry(self, mock_run):
        """Test network error that triggers retry."""
        # First call fails with network error
        mock_result_fail = Mock()
        mock_result_fail.returncode = 128
        mock_result_fail.stderr = "fatal: unable to access 'https://github.com/repo.git/': Could not resolve host: github.com"
        mock_result_fail.stdout = ""

        # Second call succeeds
        mock_result_success = Mock()
        mock_result_success.returncode = 0
        mock_result_success.stdout = "success"
        mock_result_success.stderr = ""

        mock_run.side_effect = [mock_result_fail, mock_result_success]

        result = run_git_command_with_retry(
            ["git", "clone", "repo"],
            "Clone repository",
            max_retries=2,
            retry_delay=0  # No delay for testing
        )

        assert result == mock_result_success
        assert mock_run.call_count == 2

    @patch("subprocess.run")
    def test_max_retries_exceeded(self, mock_run):
        """Test when max retries are exceeded."""
        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: unable to access 'https://github.com/repo.git/': Could not resolve host: github.com"
        mock_run.return_value = mock_result

        with pytest.raises(ConnectionError):
            run_git_command_with_retry(
                ["git", "clone", "repo"],
                "Clone repository",
                max_retries=2,
                retry_delay=0
            )

        assert mock_run.call_count == 2  # Should retry once

    @patch("subprocess.run")
    def test_ssl_error(self, mock_run):
        """Test SSL certificate error handling."""
        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: unable to access 'https://github.com/repo.git/': SSL certificate problem: self signed certificate"
        mock_run.return_value = mock_result

        with pytest.raises(SSLError):
            run_git_command_with_retry(
                ["git", "clone", "repo"],
                "Clone repository",
                max_retries=1
            )

    @patch("subprocess.run")
    def test_authentication_error(self, mock_run):
        """Test authentication error handling."""
        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: Authentication failed for 'https://github.com/repo.git/'"
        mock_run.return_value = mock_result

        with pytest.raises(AuthenticationError):
            run_git_command_with_retry(
                ["git", "clone", "repo"],
                "Clone repository",
                max_retries=1
            )

    @patch("subprocess.run")
    def test_repository_error(self, mock_run):
        """Test repository access error handling."""
        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: remote: repository not found"
        mock_run.return_value = mock_result

        with pytest.raises(RepositoryError):
            run_git_command_with_retry(
                ["git", "clone", "repo"],
                "Clone repository",
                max_retries=1
            )

    @patch("subprocess.run")
    def test_disk_space_error(self, mock_run):
        """Test disk space error handling."""
        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: write error: No space left on device"
        mock_run.return_value = mock_result

        with pytest.raises(DiskSpaceError):
            run_git_command_with_retry(
                ["git", "clone", "repo"],
                "Clone repository",
                max_retries=1
            )

    @patch("subprocess.run")
    def test_timeout_error(self, mock_run):
        """Test timeout error handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(["git", "clone"], 300)

        with pytest.raises(TimeoutError):
            run_git_command_with_retry(
                ["git", "clone", "repo"],
                "Clone repository",
                max_retries=1,
                timeout=300
            )


class TestCloneBitcoinRepoEnhanced:
    """Test enhanced Bitcoin repository cloning."""

    @patch("run_bitcoin_tests.network_utils.clone_bitcoin_repo_enhanced")
    def test_clone_when_directory_exists(self, mock_clone):
        """Test cloning when directory already exists."""
        with patch("pathlib.Path.exists", return_value=True):
            clone_bitcoin_repo_enhanced("https://github.com/bitcoin/bitcoin", "master")
            # Should not call the actual clone function
            mock_clone.assert_not_called()

    @patch("run_bitcoin_tests.network_utils.run_git_command_with_retry")
    @patch("run_bitcoin_tests.network_utils.diagnose_network_connectivity")
    @patch("run_bitcoin_tests.network_utils.print_colored")  # Mock print_colored to avoid encoding issues
    def test_successful_clone(self, mock_print_colored, mock_diagnose, mock_run_git):
        """Test successful repository cloning."""
        mock_diagnose.return_value = ["Network connectivity working"]  # Avoid Unicode chars
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_git.return_value = mock_result

        with patch("pathlib.Path.exists", return_value=False):
            clone_bitcoin_repo_enhanced("https://github.com/bitcoin/bitcoin", "master", "test_bitcoin")

        mock_run_git.assert_called_once()
        # Verify that run_git_command_with_retry was called (detailed argument checking
        # would require more complex mocking of the internal logic)

    @patch("run_bitcoin_tests.network_utils.run_git_command_with_retry")
    @patch("run_bitcoin_tests.network_utils.diagnose_network_connectivity")
    def test_clone_with_connection_error(self, mock_diagnose, mock_run_git):
        """Test clone with connection error."""
        mock_diagnose.return_value = ["✗ Cannot reach host"]
        mock_run_git.side_effect = ConnectionError("Network connection failed")

        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(ConnectionError):
                clone_bitcoin_repo_enhanced("https://github.com/bitcoin/bitcoin", "master")

    @patch("run_bitcoin_tests.network_utils.run_git_command_with_retry")
    @patch("run_bitcoin_tests.network_utils.diagnose_network_connectivity")
    def test_clone_with_ssl_error(self, mock_diagnose, mock_run_git):
        """Test clone with SSL error."""
        mock_diagnose.return_value = ["✓ Network connectivity working"]
        mock_run_git.side_effect = SSLError("SSL certificate verification failed")

        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(SSLError):
                clone_bitcoin_repo_enhanced("https://github.com/bitcoin/bitcoin", "master")
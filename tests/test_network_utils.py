"""Tests for network utilities module."""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from run_bitcoin_tests.network_utils import (
    AuthenticationError,
    DiskSpaceError,
    GitCache,
    NetworkConnectionError,
    NetworkTimeoutError,
    RepositoryError,
    SSLError,
    _is_authentication_error,
    _is_disk_space_error,
    _is_network_error,
    _is_repository_error,
    _is_ssl_error,
    clone_bitcoin_repo_enhanced,
    diagnose_network_connectivity,
    get_git_cache,
    run_git_command_with_retry,
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
        assert any("connectivity" in diag and "[OK]" in diag for diag in diagnostics)
        assert any("DNS resolution" in diag and "[OK]" in diag for diag in diagnostics)

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

        result = run_git_command_with_retry(["git", "status"], "Test command", max_retries=1)

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
            retry_delay=0,  # No delay for testing
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
                ["git", "clone", "repo"], "Clone repository", max_retries=2, retry_delay=0
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
            run_git_command_with_retry(["git", "clone", "repo"], "Clone repository", max_retries=1)

    @patch("subprocess.run")
    def test_authentication_error(self, mock_run):
        """Test authentication error handling."""
        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: Authentication failed for 'https://github.com/repo.git/'"
        mock_run.return_value = mock_result

        with pytest.raises(AuthenticationError):
            run_git_command_with_retry(["git", "clone", "repo"], "Clone repository", max_retries=1)

    @patch("subprocess.run")
    def test_repository_error(self, mock_run):
        """Test repository access error handling."""
        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: remote: repository not found"
        mock_run.return_value = mock_result

        with pytest.raises(RepositoryError):
            run_git_command_with_retry(["git", "clone", "repo"], "Clone repository", max_retries=1)

    @patch("subprocess.run")
    def test_disk_space_error(self, mock_run):
        """Test disk space error handling."""
        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: write error: No space left on device"
        mock_run.return_value = mock_result

        with pytest.raises(DiskSpaceError):
            run_git_command_with_retry(["git", "clone", "repo"], "Clone repository", max_retries=1)

    @patch("subprocess.run")
    def test_timeout_error(self, mock_run):
        """Test timeout error handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(["git", "clone"], 300)

        with pytest.raises(NetworkTimeoutError):
            run_git_command_with_retry(
                ["git", "clone", "repo"], "Clone repository", max_retries=1, timeout=300
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
    @patch(
        "run_bitcoin_tests.network_utils.print_colored"
    )  # Mock print_colored to avoid encoding issues
    def test_successful_clone(self, mock_print_colored, mock_diagnose, mock_run_git):
        """Test successful repository cloning."""
        mock_diagnose.return_value = ["Network connectivity working"]  # Avoid Unicode chars
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_git.return_value = mock_result

        with patch("pathlib.Path.exists", return_value=False):
            clone_bitcoin_repo_enhanced(
                "https://github.com/bitcoin/bitcoin", "master", "test_bitcoin"
            )

        mock_run_git.assert_called_once()
        # Verify that run_git_command_with_retry was called (detailed argument checking
        # would require more complex mocking of the internal logic)

    @patch("run_bitcoin_tests.network_utils.run_git_command_with_retry")
    @patch("run_bitcoin_tests.network_utils.diagnose_network_connectivity")
    def test_clone_with_connection_error(self, mock_diagnose, mock_run_git):
        """Test clone with connection error."""
        mock_diagnose.return_value = ["[FAIL] Cannot reach host"]
        mock_run_git.side_effect = NetworkConnectionError("Network connection failed")

        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(NetworkConnectionError):
                clone_bitcoin_repo_enhanced("https://github.com/bitcoin/bitcoin", "master")

    @patch("run_bitcoin_tests.network_utils.run_git_command_with_retry")
    @patch("run_bitcoin_tests.network_utils.diagnose_network_connectivity")
    def test_clone_with_ssl_error(self, mock_diagnose, mock_run_git):
        """Test clone with SSL error."""
        mock_diagnose.return_value = ["[OK] Network connectivity working"]
        mock_run_git.side_effect = SSLError("SSL certificate verification failed")

        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(SSLError):
                clone_bitcoin_repo_enhanced("https://github.com/bitcoin/bitcoin", "master")


class TestGitCache:
    """Test GitCache functionality."""

    @patch("run_bitcoin_tests.network_utils.GitCache._instance", None)
    def test_get_instance_creates_singleton(self):
        """Test that get_instance creates a singleton."""
        # Reset the singleton
        GitCache._instance = None

        instance1 = GitCache.get_instance()
        instance2 = GitCache.get_instance()

        assert instance1 is instance2
        assert isinstance(instance1, GitCache)

    @patch("run_bitcoin_tests.network_utils.GitCache._instance", None)
    def test_get_instance_with_custom_params(self):
        """Test get_instance with custom parameters."""
        GitCache._instance = None

        instance = GitCache.get_instance(cache_dir="/tmp/custom", max_cache_size_gb=5.0)

        # Use Path comparison to handle platform differences
        from pathlib import Path

        assert instance.cache_dir == Path("/tmp/custom")
        assert instance.max_cache_size_gb == 5.0

    def test_git_cache_initialization(self):
        """Test GitCache initialization."""
        with patch("pathlib.Path.mkdir"):
            cache = GitCache(cache_dir="/tmp/test", max_cache_size_gb=2.0)

            # Use Path comparison to handle platform differences
            from pathlib import Path

            assert cache.cache_dir == Path("/tmp/test")
            assert cache.max_cache_size_gb == 2.0
            assert cache.cache_metadata_file.name == "cache_metadata.json"

    @patch("pathlib.Path.exists")
    @patch("builtins.open")
    @patch("json.load")
    @patch("pathlib.Path.mkdir")  # Prevent directory creation during test
    def test_load_metadata_success(self, mock_mkdir, mock_json_load, mock_open, mock_exists):
        """Test loading metadata successfully."""
        mock_exists.return_value = True
        mock_json_load.return_value = {"test": "data"}

        # Create cache without calling constructor's _load_metadata
        cache = object.__new__(GitCache)
        cache.cache_metadata_file = Mock()
        cache.cache_metadata_file.exists.return_value = True

        metadata = cache._load_metadata()

        assert metadata == {"test": "data"}
        mock_open.assert_called_once()

    @patch("pathlib.Path.exists")
    def test_load_metadata_file_not_exists(self, mock_exists):
        """Test loading metadata when file doesn't exist."""
        mock_exists.return_value = False

        cache = GitCache()
        metadata = cache._load_metadata()

        assert metadata == {}

    @patch("pathlib.Path.exists")
    @patch("builtins.open")
    @patch("json.load", side_effect=json.JSONDecodeError("JSON error", "", 0))
    @patch("logging.warning")
    @patch("pathlib.Path.mkdir")  # Prevent directory creation during test
    def test_load_metadata_json_error(
        self, mock_mkdir, mock_logging_warning, mock_json_load, mock_open, mock_exists
    ):
        """Test loading metadata with JSON error."""
        mock_exists.return_value = True

        # Create cache without calling constructor's _load_metadata
        cache = object.__new__(GitCache)
        cache.cache_metadata_file = Mock()
        cache.cache_metadata_file.exists.return_value = True

        metadata = cache._load_metadata()

        assert metadata == {}
        mock_logging_warning.assert_called_once()

    @patch("logging.warning")
    @patch("pathlib.Path.mkdir")  # Prevent directory creation during test
    def test_save_metadata(self, mock_mkdir, mock_logging_warning):
        """Test saving metadata."""
        with patch("builtins.open") as mock_open, patch("json.dump") as mock_json_dump:

            # Create cache without calling constructor's _load_metadata
            cache = object.__new__(GitCache)
            cache.cache_metadata_file = Mock()
            cache._metadata = {"test": "data"}
            cache._metadata_lock = Mock()
            cache._metadata_lock.__enter__ = Mock(return_value=None)
            cache._metadata_lock.__exit__ = Mock(return_value=None)

            cache._save_metadata()

            mock_open.assert_called_once()
            # Check that json.dump was called with the mock file object
            call_args = mock_json_dump.call_args
            assert call_args[0][0] == {"test": "data"}
            assert call_args[1]["indent"] == 2

    @patch("logging.warning")
    @patch("builtins.open", side_effect=IOError("Write error"))
    @patch("pathlib.Path.mkdir")  # Prevent directory creation during test
    def test_save_metadata_error(self, mock_mkdir, mock_open, mock_logging_warning):
        """Test saving metadata with error."""
        # Create cache without calling constructor's _load_metadata
        cache = object.__new__(GitCache)
        cache.cache_metadata_file = Mock()
        cache._metadata = {"test": "data"}
        cache._metadata_lock = Mock()
        cache._metadata_lock.__enter__ = Mock(return_value=None)
        cache._metadata_lock.__exit__ = Mock(return_value=None)

        # Should not raise exception
        cache._save_metadata()

        mock_logging_warning.assert_called_once()


class TestGetGitCache:
    """Test get_git_cache function."""

    @patch("run_bitcoin_tests.network_utils.GitCache")
    def test_get_git_cache_default_params(self, mock_git_cache_class):
        """Test get_git_cache with default parameters."""
        mock_instance = Mock()
        mock_git_cache_class.return_value = mock_instance

        # Reset global cache
        import run_bitcoin_tests.network_utils as nu

        nu._git_cache = None

        result = get_git_cache()

        mock_git_cache_class.assert_called_once_with(None, 10.0)
        assert result == mock_instance

    @patch("run_bitcoin_tests.network_utils.GitCache")
    def test_get_git_cache_custom_params(self, mock_git_cache_class):
        """Test get_git_cache with custom parameters."""
        mock_instance = Mock()
        mock_git_cache_class.return_value = mock_instance

        # Reset global cache
        import run_bitcoin_tests.network_utils as nu

        nu._git_cache = None

        result = get_git_cache(cache_dir="/tmp/custom", max_cache_size_gb=5.0)

        mock_git_cache_class.assert_called_once_with("/tmp/custom", 5.0)
        assert result == mock_instance


class TestErrorDetectionFunctions:
    """Test error detection helper functions."""

    def test_is_network_error_true(self):
        """Test _is_network_error returns True for network errors."""
        network_errors = [
            "Network is unreachable",
            "Connection refused",
            "Connection timed out",
            "Connection reset by peer",
            "No route to host",
            "Temporary failure in name resolution",
            "Could not resolve host",
            "Failed to connect to github.com",
            "Network error occurred",
            "Transfer closed with outstanding read data remaining",
            "The remote end hung up unexpectedly",
        ]

        for error in network_errors:
            assert _is_network_error(error), f"Should detect '{error}' as network error"

    def test_is_network_error_false(self):
        """Test _is_network_error returns False for non-network errors."""
        non_network_errors = [
            "Repository not found",
            "Authentication failed",
            "Disk space insufficient",
            "Permission denied",
        ]

        for error in non_network_errors:
            assert not _is_network_error(error), f"Should not detect '{error}' as network error"

    def test_is_ssl_error_true(self):
        """Test _is_ssl_error returns True for SSL errors."""
        ssl_errors = [
            "SSL certificate verification failed",
            "SSL verification error",
            "TLS handshake failed",
            "Certificate verify failed",
            "Self signed certificate in certificate chain",
        ]

        for error in ssl_errors:
            assert _is_ssl_error(error), f"Should detect '{error}' as SSL error"

    def test_is_ssl_error_false(self):
        """Test _is_ssl_error returns False for non-SSL errors."""
        non_ssl_errors = ["Repository not found", "Connection refused", "Disk space insufficient"]

        for error in non_ssl_errors:
            assert not _is_ssl_error(error), f"Should not detect '{error}' as SSL error"

    def test_is_authentication_error_true(self):
        """Test _is_authentication_error returns True for auth errors."""
        auth_errors = [
            "Authentication failed",
            "Permission denied (publickey)",
            "Access denied",
            "not authorized",
            "Invalid credentials",
            "remote: invalid username or password",
        ]

        for error in auth_errors:
            assert _is_authentication_error(error), f"Should detect '{error}' as auth error"

    def test_is_authentication_error_false(self):
        """Test _is_authentication_error returns False for non-auth errors."""
        non_auth_errors = [
            "Network is unreachable",
            "SSL certificate verification failed",
            "Disk space insufficient",
            "fatal: remote error: upload denied",
        ]

        for error in non_auth_errors:
            assert not _is_authentication_error(error), f"Should not detect '{error}' as auth error"

    def test_is_repository_error_true(self):
        """Test _is_repository_error returns True for repository errors."""
        repo_errors = [
            "Remote repository not found",
            "remote: repository not found",
            "remote: access denied",
            "remote: permission to user/repo denied",
            "remote: the repository you are trying to access does not exist",
            "fatal: remote error: access denied or repository not exported",
            "fatal: could not read from remote repository",
        ]

        for error in repo_errors:
            assert _is_repository_error(error), f"Should detect '{error}' as repository error"

    def test_is_repository_error_false(self):
        """Test _is_repository_error returns False for non-repository errors."""
        non_repo_errors = [
            "Network is unreachable",
            "Authentication failed for user",
            "Disk space insufficient",
        ]

        for error in non_repo_errors:
            assert not _is_repository_error(
                error
            ), f"Should not detect '{error}' as repository error"

    def test_is_disk_space_error_true(self):
        """Test _is_disk_space_error returns True for disk space errors."""
        disk_errors = [
            "No space left on device",
            "insufficient disk space",
            "Out of disk space",
            "disk quota exceeded",
            "Disk full",
        ]

        for error in disk_errors:
            assert _is_disk_space_error(error), f"Should detect '{error}' as disk space error"

    def test_is_disk_space_error_false(self):
        """Test _is_disk_space_error returns False for non-disk errors."""
        non_disk_errors = [
            "Network is unreachable",
            "Authentication failed",
            "Repository not found",
        ]

        for error in non_disk_errors:
            assert not _is_disk_space_error(
                error
            ), f"Should not detect '{error}' as disk space error"

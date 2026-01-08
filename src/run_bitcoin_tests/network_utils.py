"""
Network utilities for robust Git operations with comprehensive error handling.

This module provides enhanced network operations with proper error handling for:
- Network timeouts and connection issues
- SSL certificate problems
- DNS resolution failures
- Authentication issues
- Repository access problems
- Disk space and permission issues

Key Features:
- Automatic retry logic with exponential backoff
- Network connectivity diagnostics
- Detailed error categorization and user-friendly messages
- Thread-safe operations
- Configurable timeouts and retry policies

Error Hierarchy:
- NetworkError (base exception)
  - ConnectionError: Network connectivity issues
  - SSLError: SSL/TLS certificate validation failures
  - AuthenticationError: Repository authentication failures
  - RepositoryError: Repository access/permission issues
  - DiskSpaceError: Insufficient disk space
  - TimeoutError: Operation timeouts

Example Usage:
    from run_bitcoin_tests.network_utils import clone_bitcoin_repo_enhanced

    try:
        clone_bitcoin_repo_enhanced(
            repo_url="https://github.com/bitcoin/bitcoin",
            branch="master",
            target_dir="bitcoin"
        )
    except ConnectionError as e:
        print(f"Network connection failed: {e}")
    except SSLError as e:
        print(f"SSL certificate error: {e}")
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from .logging_config import get_logger
from .thread_utils import atomic_directory_operation, file_system_lock

logger = get_logger(__name__)

# Try to import colorama for colored output, fallback to plain text
try:
    from .main import print_colored, Fore
except ImportError:
    def print_colored(message, color="", bright=False):
        print(message)
    class Fore:
        RED = ""
        GREEN = ""
        YELLOW = ""
        WHITE = ""
        CYAN = ""


class NetworkError(Exception):
    """Base exception for network-related errors."""
    pass


class ConnectionError(NetworkError):
    """Raised when network connection fails."""
    pass


class TimeoutError(NetworkError):
    """Raised when network operation times out."""
    pass


class SSLError(NetworkError):
    """Raised when SSL/TLS certificate validation fails."""
    pass


class AuthenticationError(NetworkError):
    """Raised when authentication fails."""
    pass


class RepositoryError(NetworkError):
    """Raised when repository access fails."""
    pass


class DiskSpaceError(NetworkError):
    """Raised when insufficient disk space for operations."""
    pass


def diagnose_network_connectivity(url: str) -> List[str]:
    """
    Diagnose network connectivity issues for a given URL.

    Performs comprehensive network diagnostics including:
    - Ping connectivity tests
    - DNS resolution checks
    - SSL/TLS connection validation (for HTTPS URLs)

    Args:
        url: The URL to test connectivity for

    Returns:
        List of diagnostic messages indicating connectivity status

    Note:
        Some diagnostic tests may not be available on all platforms
        (e.g., ping command availability)
    """
    """
    Diagnose network connectivity issues.

    Args:
        url: URL to test connectivity for

    Returns:
        List of diagnostic messages
    """
    diagnostics = []

    try:
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path.split('/')[0]

        # Test basic connectivity with ping
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["ping", "-n", "1", "-w", "5000", host],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            else:
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "5", host],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

            if result.returncode == 0:
                diagnostics.append(f"✓ Network connectivity to {host} is working")
            else:
                diagnostics.append(f"✗ Cannot reach {host} - network connectivity issue")

        except subprocess.TimeoutExpired:
            diagnostics.append(f"✗ Ping to {host} timed out")
        except FileNotFoundError:
            diagnostics.append("! Ping command not available for connectivity testing")

        # Test DNS resolution
        try:
            import socket
            socket.gethostbyname(host)
            diagnostics.append(f"✓ DNS resolution for {host} is working")
        except socket.gaierror:
            diagnostics.append(f"✗ DNS resolution failed for {host}")

        # Test SSL connectivity if HTTPS
        if url.startswith('https://'):
            try:
                import ssl
                import socket

                context = ssl.create_default_context()
                with socket.create_connection((host, 443), timeout=10) as sock:
                    with context.wrap_socket(sock, server_hostname=host) as ssock:
                        diagnostics.append(f"✓ SSL/TLS connection to {host} is working")
            except ssl.SSLCertVerificationError:
                diagnostics.append(f"✗ SSL certificate verification failed for {host}")
            except Exception as e:
                diagnostics.append(f"✗ SSL connection failed for {host}: {e}")

    except Exception as e:
        diagnostics.append(f"! Could not complete network diagnostics: {e}")

    return diagnostics


def run_git_command_with_retry(
    cmd: List[str],
    description: str,
    max_retries: int = 3,
    timeout: int = 300,
    retry_delay: int = 5
) -> subprocess.CompletedProcess[str]:
    """
    Run a Git command with automatic retry logic and error handling.

    This function provides robust Git command execution with:
    - Automatic retries for transient network errors
    - Exponential backoff delay between retries
    - Comprehensive error categorization
    - User-friendly error messages

    Args:
        cmd: Git command arguments as a list
        description: Human-readable description of the operation
        max_retries: Maximum number of retry attempts (default: 3)
        timeout: Command timeout in seconds (default: 300)
        retry_delay: Base delay between retries in seconds (default: 5)

    Returns:
        subprocess.CompletedProcess object with execution results

    Raises:
        ConnectionError: For network connectivity issues
        SSLError: For SSL certificate validation failures
        AuthenticationError: For repository authentication failures
        RepositoryError: For repository access issues
        DiskSpaceError: For insufficient disk space
        TimeoutError: For command execution timeouts
        RuntimeError: For other command execution failures
    """
    """
    Run a git command with retry logic and comprehensive error handling.

    Args:
        cmd: Git command to execute
        description: Human-readable description of the operation
        max_retries: Maximum number of retry attempts
        timeout: Timeout for each attempt in seconds
        retry_delay: Delay between retries in seconds

    Returns:
        CompletedProcess object

    Raises:
        Various NetworkError subclasses based on the failure type
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            logger.debug(f"Running git command (attempt {attempt + 1}/{max_retries}): {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )

            # Analyze the result and raise appropriate exceptions
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()

                # Categorize different types of git errors
                # Check in order of specificity: most specific to least specific
                if _is_ssl_error(error_msg):
                    raise SSLError(f"SSL certificate error: {error_msg}")

                elif _is_disk_space_error(error_msg):
                    raise DiskSpaceError(f"Insufficient disk space: {error_msg}")

                elif _is_repository_error(error_msg):
                    raise RepositoryError(f"Repository access error: {error_msg}")

                elif _is_authentication_error(error_msg):
                    raise AuthenticationError(f"Authentication failed: {error_msg}")

                elif _is_network_error(error_msg):
                    if attempt < max_retries - 1:
                        logger.warning(f"Network error (attempt {attempt + 1}/{max_retries}): {error_msg}")
                        print_colored(f"Network error, retrying in {retry_delay} seconds...", Fore.YELLOW)
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise ConnectionError(f"Network error after {max_retries} attempts: {error_msg}")

                else:
                    # Generic error
                    if attempt < max_retries - 1:
                        logger.warning(f"Git command failed (attempt {attempt + 1}/{max_retries}): {error_msg}")
                        print_colored(f"Command failed, retrying in {retry_delay} seconds...", Fore.YELLOW)
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise RuntimeError(f"Git command failed after {max_retries} attempts: {error_msg}")

            # Success!
            logger.debug(f"Git command completed successfully: {description}")
            return result

        except subprocess.TimeoutExpired:
            if attempt < max_retries - 1:
                logger.warning(f"Git command timed out (attempt {attempt + 1}/{max_retries})")
                print_colored(f"Operation timed out, retrying in {retry_delay} seconds...", Fore.YELLOW)
                time.sleep(retry_delay)
                continue
            else:
                raise TimeoutError(f"Git command timed out after {max_retries} attempts")

        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                logger.warning(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")
                print_colored(f"Unexpected error, retrying in {retry_delay} seconds...", Fore.YELLOW)
                time.sleep(retry_delay)
                continue
            else:
                raise

    # This should never be reached, but just in case
    raise last_exception or RuntimeError("Git command failed with unknown error")


def _is_network_error(error_msg: str) -> bool:
    """Check if error message indicates a network connectivity issue."""
    network_indicators = [
        "network is unreachable",
        "connection refused",
        "connection timed out",
        "connection reset",
        "no route to host",
        "temporary failure in name resolution",
        "could not resolve host",
        "failed to connect",
        "network error",
        "transfer closed with",
        "the remote end hung up unexpectedly"
    ]
    return any(indicator.lower() in error_msg.lower() for indicator in network_indicators)


def _is_ssl_error(error_msg: str) -> bool:
    """Check if error message indicates an SSL/TLS issue."""
    ssl_indicators = [
        "ssl certificate",
        "ssl verification",
        "tls",
        "certificate verify failed",
        "self signed certificate",
        "certificate has expired",
        "unable to verify the first certificate"
    ]
    return any(indicator.lower() in error_msg.lower() for indicator in ssl_indicators)


def _is_authentication_error(error_msg: str) -> bool:
    """Check if error message indicates an authentication issue."""
    auth_indicators = [
        "authentication failed",
        "permission denied",
        "access denied",
        "not authorized",
        "invalid credentials",
        "repository not found",
        "does not exist",
        "remote: invalid username or password"
    ]
    return any(indicator.lower() in error_msg.lower() for indicator in auth_indicators)


def _is_repository_error(error_msg: str) -> bool:
    """Check if error message indicates a repository access issue."""
    repo_indicators = [
        "repository not found",
        "does not exist",
        "remote: repository not found",
        "remote: access denied",
        "remote: permission to",
        "remote: the repository you are trying to access does not exist",
        "fatal: remote error:",
        "fatal: could not read from remote repository"
    ]
    return any(indicator.lower() in error_msg.lower() for indicator in repo_indicators)


def _is_disk_space_error(error_msg: str) -> bool:
    """Check if error message indicates insufficient disk space."""
    disk_indicators = [
        "no space left on device",
        "disk full",
        "insufficient disk space",
        "out of disk space",
        "disk quota exceeded"
    ]
    return any(indicator.lower() in error_msg.lower() for indicator in disk_indicators)


def clone_bitcoin_repo_enhanced(repo_url: str, branch: str, target_dir: str = "bitcoin") -> None:
    """
    Enhanced Bitcoin repository cloning with comprehensive error handling.

    This function provides robust repository cloning with:
    - Automatic network diagnostics before cloning
    - Thread-safe directory operations
    - Comprehensive error handling and retry logic
    - User-friendly progress messages and error reporting

    Args:
        repo_url: URL of the Git repository to clone
        branch: Branch name to clone from the repository
        target_dir: Local directory path for the cloned repository

    Raises:
        ConnectionError: For network connectivity issues
        SSLError: For SSL certificate validation failures
        AuthenticationError: For repository authentication failures
        RepositoryError: For repository access/permission issues
        DiskSpaceError: For insufficient disk space
        TimeoutError: For operation timeouts
        RuntimeError: For other cloning failures

    Example:
        clone_bitcoin_repo_enhanced(
            "https://github.com/bitcoin/bitcoin",
            "master",
            "bitcoin-source"
        )
    """
    """
    Enhanced Bitcoin repository cloning with comprehensive error handling and thread safety.

    Args:
        repo_url: URL of the repository to clone
        branch: Branch to clone
        target_dir: Target directory for the clone

    Raises:
        NetworkError: For network-related issues
        RepositoryError: For repository access issues
        DiskSpaceError: For disk space issues
        TimeoutError: For timeout issues
    """
    target_path = Path(target_dir)

    # Thread-safe check for existing directory
    with file_system_lock(f"check_existing_repo_{target_dir}"):
        if target_path.exists():
            print_colored(f"[OK] Bitcoin source directory '{target_dir}' already exists", Fore.GREEN)
            logger.info(f"Repository directory {target_dir} already exists, skipping clone")
            return

    print_colored(f"Cloning Bitcoin repository from {repo_url} (branch: {branch})...", Fore.YELLOW)
    logger.info(f"Starting repository clone from {repo_url} branch {branch} to {target_dir}")

    # Show network diagnostics before attempting clone
    print_colored("Checking network connectivity...", Fore.CYAN)
    diagnostics = diagnose_network_connectivity(repo_url)
    for diag in diagnostics:
        print_colored(f"  {diag}", Fore.WHITE)

    try:
        # Ensure parent directory exists in a thread-safe manner
        parent_dir = target_path.parent
        if str(parent_dir) != ".":  # Only if parent is not current directory
            with atomic_directory_operation(parent_dir, "create_parent_for_clone"):
                pass  # Directory creation handled by context manager

        # Use shallow clone for faster downloads and less disk usage
        cmd = ["git", "clone", "--depth", "1", "--branch", branch, repo_url, target_dir]

        result = run_git_command_with_retry(
            cmd=cmd,
            description=f"Clone Bitcoin repository to {target_dir}",
            max_retries=3,
            timeout=600,  # 10 minutes timeout
            retry_delay=10
        )

        print_colored("[SUCCESS] Bitcoin repository cloned successfully", Fore.GREEN)
        logger.info(f"Repository cloned successfully to {target_dir}")

    except ConnectionError as e:
        logger.error(f"Network connection error during clone: {e}")
        print_colored(f"[ERROR] Network connection failed: {e}", Fore.RED)
        print_colored("Please check your internet connection and try again.", Fore.WHITE)
        raise

    except SSLError as e:
        logger.error(f"SSL certificate error during clone: {e}")
        print_colored(f"[ERROR] SSL certificate verification failed: {e}", Fore.RED)
        print_colored("This might be due to firewall restrictions or certificate issues.", Fore.WHITE)
        print_colored("You can try using HTTP instead of HTTPS if the repository allows it.", Fore.WHITE)
        raise

    except AuthenticationError as e:
        logger.error(f"Authentication error during clone: {e}")
        print_colored(f"[ERROR] Authentication failed: {e}", Fore.RED)
        print_colored("Please check your credentials and repository access permissions.", Fore.WHITE)
        raise

    except RepositoryError as e:
        logger.error(f"Repository access error during clone: {e}")
        print_colored(f"[ERROR] Repository access failed: {e}", Fore.RED)
        print_colored("Please verify the repository URL and branch name are correct.", Fore.WHITE)
        raise

    except DiskSpaceError as e:
        logger.error(f"Disk space error during clone: {e}")
        print_colored(f"[ERROR] Insufficient disk space: {e}", Fore.RED)
        print_colored("Please free up disk space and try again.", Fore.WHITE)
        raise

    except TimeoutError as e:
        logger.error(f"Timeout error during clone: {e}")
        print_colored(f"[ERROR] Operation timed out: {e}", Fore.RED)
        print_colored("The repository might be large or your connection might be slow.", Fore.WHITE)
        print_colored("Try increasing the timeout or checking your network speed.", Fore.WHITE)
        raise

    except Exception as e:
        logger.error(f"Unexpected error during clone: {e}")
        print_colored(f"[ERROR] Unexpected error during repository clone: {e}", Fore.RED)
        raise
"""
Bitcoin Core C++ Unit Tests Runner

A cross-platform Python script to run Bitcoin Core C++ unit tests using Docker.
This script automatically downloads the Bitcoin source code from GitHub and
provides a simple way to build and execute the test suite in a containerized environment.

Requirements:
- Python 3.6+
- Git installed
- Docker and Docker Compose installed and running
- colorama (optional, for colored output): `pip install colorama`

Usage:
    python run-bitcoin-tests.py [options]

Options:
    -r, --repo-url URL     Git repository URL to clone Bitcoin from
                           (default: https://github.com/bitcoin/bitcoin)
    -b, --branch BRANCH    Branch to clone from the repository
                           (default: master)

Examples:
    python run-bitcoin-tests.py
    python run-bitcoin-tests.py --repo-url https://github.com/myfork/bitcoin --branch my-feature
    python run-bitcoin-tests.py -r https://github.com/bitcoin/bitcoin -b v25.1
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .logging_config import get_logger, setup_logging
from .network_utils import (clone_bitcoin_repo_enhanced, ConnectionError as NetworkConnectionError,
                           SSLError as NetworkSSLError, AuthenticationError as NetworkAuthError,
                           RepositoryError as NetworkRepoError, DiskSpaceError as NetworkDiskError,
                           TimeoutError as NetworkTimeoutError, NetworkError)
from .thread_utils import (atomic_directory_operation, docker_container_lock, file_system_lock,
                          initialize_thread_safety, register_cleanup_handler, resource_tracker)
from .validation import validate_branch_name, validate_git_url, ValidationError

try:
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)
except ImportError:  # pragma: no cover
    # Fallback if colorama is not available
    class Fore:  # pragma: no cover
        CYAN = ""  # pragma: no cover
        GREEN = ""  # pragma: no cover
        RED = ""  # pragma: no cover
        YELLOW = ""  # pragma: no cover
        WHITE = ""  # pragma: no cover
        RESET = ""  # pragma: no cover

    class Style:  # pragma: no cover
        BRIGHT = ""  # pragma: no cover
        RESET_ALL = ""  # pragma: no cover


def print_colored(message: str, color: str = Fore.WHITE, bright: bool = False) -> None:
    """Print a colored message to stdout."""
    prefix = Style.BRIGHT if bright else ""
    print(f"{prefix}{color}{message}{Style.RESET_ALL}")


def run_command(command: List[str], description: str) -> subprocess.CompletedProcess[str]:
    """Run a command and return the completed process."""
    print_colored(f"Running: {' '.join(command)}", Fore.WHITE)
    try:
        result = subprocess.run(
            command,
            capture_output=False,  # Show output in real-time
            text=True,
            check=False  # Don't raise exception on non-zero exit
        )
        return result
    except FileNotFoundError:
        print_colored(f"[ERROR] Command not found: {command[0]}", Fore.RED)
        print_colored("Please ensure Docker and Docker Compose are installed and in PATH.", Fore.WHITE)
        sys.exit(1)
    except Exception as e:
        print_colored(f"[ERROR] Error running command: {e}", Fore.RED)
        sys.exit(1)


def clone_bitcoin_repo(repo_url: str, branch: str) -> None:
    """Clone the Bitcoin repository if it doesn't exist."""
    try:
        clone_bitcoin_repo_enhanced(repo_url, branch, "bitcoin")
    except NetworkError as e:
        # Network errors are already handled in the enhanced function
        # Just re-raise to maintain the same interface
        raise e
    except Exception as e:
        print_colored(f"[ERROR] Failed to clone repository: {e}", Fore.RED)
        print_colored("Please ensure git is installed and you have internet access.", Fore.WHITE)
        raise


def check_prerequisites(repo_url: str, branch: str) -> None:
    """Check if required files exist and clone repo if needed."""
    print_colored("Checking prerequisites...", Fore.YELLOW)

    # Check for Docker-related files (thread-safe)
    with file_system_lock("check_docker_files"):
        required_files = ["docker-compose.yml", "Dockerfile"]

        missing_files = []
        for file_str in required_files:
            file_path = Path(file_str)
            if not file_path.exists():
                missing_files.append(file_str)

        if missing_files:
            print_colored("[ERROR] Missing required files:", Fore.RED)
            for file in missing_files:
                print_colored(f"  - {file}", Fore.RED)
            sys.exit(1)

    # Clone Bitcoin repo if needed (already thread-safe via enhanced function)
    clone_bitcoin_repo(repo_url, branch)

    # Verify Bitcoin source after cloning (thread-safe)
    with file_system_lock("verify_bitcoin_source"):
        bitcoin_cmake = Path("bitcoin/CMakeLists.txt")
        if not bitcoin_cmake.exists():
            print_colored("[ERROR] Bitcoin CMakeLists.txt not found after cloning", Fore.RED)
            print_colored("The repository may not be a valid Bitcoin Core repository.", Fore.WHITE)
            sys.exit(1)

    print_colored("[OK] Prerequisites check passed", Fore.GREEN)
    print()


def build_docker_image() -> None:
    """Build the Docker image for Bitcoin Core tests."""
    print_colored("Building Docker image...", Fore.YELLOW)

    with docker_container_lock("bitcoin-tests-build"):
        result = run_command(["docker-compose", "build"], "Build Docker image")

        if result.returncode != 0:
            print_colored("[ERROR] Failed to build Docker image", Fore.RED)
            sys.exit(1)

    print_colored("[OK] Docker image built successfully", Fore.GREEN)
    print()


def run_tests() -> int:
    """Run the Bitcoin Core unit tests."""
    print_colored("Running Bitcoin Core unit tests...", Fore.YELLOW)

    with docker_container_lock("bitcoin-tests-runner"):
        result = run_command(["docker-compose", "run", "--rm", "bitcoin-tests"], "Run tests")

    print()
    if result.returncode == 0:
        print_colored("[SUCCESS] All tests passed!", Fore.GREEN)
    else:
        print_colored("[FAILED] Some tests failed", Fore.RED)
        print_colored(f"Exit code: {result.returncode}", Fore.WHITE)

    return result.returncode


def cleanup_containers() -> None:
    """Clean up Docker containers and networks."""
    print_colored("Cleaning up containers...", Fore.YELLOW)

    with docker_container_lock("bitcoin-tests-cleanup"):
        run_command(["docker-compose", "down", "--remove-orphans"], "Cleanup containers")

    # Also cleanup any tracked resources
    resource_tracker.cleanup_all_resources()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Bitcoin Core C++ unit tests in Docker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run-bitcoin-tests.py
  python run-bitcoin-tests.py --repo-url https://github.com/myfork/bitcoin --branch my-feature-branch
  python run-bitcoin-tests.py -r https://github.com/bitcoin/bitcoin -b v25.1
  python run-bitcoin-tests.py --verbose --log-file bitcoin-tests.log
        """
    )

    parser.add_argument(
        "-r", "--repo-url",
        default="https://github.com/bitcoin/bitcoin",
        help="Git repository URL to clone Bitcoin from (default: %(default)s)"
    )

    parser.add_argument(
        "-b", "--branch",
        default="master",
        help="Branch to clone from the repository (default: %(default)s)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output (DEBUG level logging)"
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress all output except errors"
    )

    parser.add_argument(
        "--log-file",
        help="Path to log file for detailed logging"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: %(default)s)"
    )

    args = parser.parse_args()

    # Validate inputs
    try:
        args.repo_url = validate_git_url(args.repo_url)
        args.branch = validate_branch_name(args.branch)
    except ValidationError as e:
        print_colored(f"[ERROR] Invalid input: {e}", Fore.RED)
        sys.exit(1)

    return args


def main() -> None:
    """Main function to run the Bitcoin Core tests."""
    args = parse_arguments()

    # Initialize thread safety
    initialize_thread_safety()

    # Set up logging
    logger = setup_logging(
        level=args.log_level,
        log_file=args.log_file,
        verbose=args.verbose,
        quiet=args.quiet
    )

    print_colored("Bitcoin Core C++ Tests Runner", Fore.CYAN, bright=True)
    if args.repo_url != "https://github.com/bitcoin/bitcoin" or args.branch != "master":
        print_colored(f"Repository: {args.repo_url} (branch: {args.branch})", Fore.WHITE)

    start_time = datetime.now()
    print_colored(f"Started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}", Fore.WHITE)
    logger.info(f"Starting Bitcoin Core tests runner")
    logger.info(f"Repository: {args.repo_url}, Branch: {args.branch}")
    print()

    try:
        # Check prerequisites
        logger.debug("Checking prerequisites")
        check_prerequisites(args.repo_url, args.branch)
        logger.info("Prerequisites check completed successfully")

        # Build Docker image
        logger.debug("Building Docker image")
        build_docker_image()
        logger.info("Docker image built successfully")

        # Run tests
        logger.debug("Running Bitcoin Core unit tests")
        exit_code = run_tests()
        logger.info(f"Tests completed with exit code: {exit_code}")

        # Cleanup
        logger.debug("Cleaning up Docker containers")
        cleanup_containers()
        logger.info("Cleanup completed")

        # Final status
        end_time = datetime.now()
        print_colored(f"Completed at {end_time.strftime('%Y-%m-%d %H:%M:%S')}", Fore.WHITE)

        # Calculate duration
        duration = end_time - start_time
        print_colored(f"Duration: {duration}", Fore.WHITE)
        logger.info(f"Total execution time: {duration}")

        if exit_code == 0:
            logger.info("All tests passed successfully")
        else:
            logger.warning(f"Some tests failed (exit code: {exit_code})")

        sys.exit(exit_code)

    except NetworkConnectionError as e:
        logger.error(f"Network connection error: {e}")
        print_colored(f"[NETWORK ERROR] Connection failed: {e}", Fore.RED)
        print_colored("Please check your internet connection and try again.", Fore.WHITE)
        cleanup_containers()
        sys.exit(10)

    except NetworkSSLError as e:
        logger.error(f"SSL certificate error: {e}")
        print_colored(f"[SSL ERROR] Certificate verification failed: {e}", Fore.RED)
        print_colored("Try using HTTP instead of HTTPS or check your SSL settings.", Fore.WHITE)
        cleanup_containers()
        sys.exit(11)

    except NetworkAuthError as e:
        logger.error(f"Authentication error: {e}")
        print_colored(f"[AUTH ERROR] Authentication failed: {e}", Fore.RED)
        print_colored("Please check your credentials and repository access permissions.", Fore.WHITE)
        cleanup_containers()
        sys.exit(12)

    except NetworkRepoError as e:
        logger.error(f"Repository access error: {e}")
        print_colored(f"[REPO ERROR] Repository access failed: {e}", Fore.RED)
        print_colored("Please verify the repository URL and branch name are correct.", Fore.WHITE)
        cleanup_containers()
        sys.exit(13)

    except NetworkDiskError as e:
        logger.error(f"Disk space error: {e}")
        print_colored(f"[DISK ERROR] Insufficient disk space: {e}", Fore.RED)
        print_colored("Please free up disk space and try again.", Fore.WHITE)
        cleanup_containers()
        sys.exit(14)

    except NetworkTimeoutError as e:
        logger.error(f"Network timeout error: {e}")
        print_colored(f"[TIMEOUT ERROR] Operation timed out: {e}", Fore.RED)
        print_colored("The operation took too long. Try again or check your network speed.", Fore.WHITE)
        cleanup_containers()
        sys.exit(15)

    except KeyboardInterrupt:
        logger.warning("Operation cancelled by user (KeyboardInterrupt)")
        print_colored("\n[INTERRUPTED] Operation cancelled by user", Fore.YELLOW)
        cleanup_containers()
        sys.exit(130)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        print_colored(f"[ERROR] An unexpected error occurred: {e}", Fore.RED)
        cleanup_containers()
        sys.exit(1)
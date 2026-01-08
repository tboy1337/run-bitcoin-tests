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

from .config import get_config, load_config
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
    config = get_config()

    try:
        # Use configuration values for clone parameters
        clone_bitcoin_repo_enhanced(
            repo_url=repo_url,
            branch=branch,
            target_dir="bitcoin"
        )
    except NetworkError as e:
        # Network errors are already handled in the enhanced function
        # Just re-raise to maintain the same interface
        raise e
    except Exception as e:
        print_colored(f"[ERROR] Failed to clone repository: {e}", Fore.RED)
        print_colored("Please ensure git is installed and you have internet access.", Fore.WHITE)
        raise


def check_prerequisites() -> None:
    """Check if required files exist and clone repo if needed."""
    config = get_config()

    if not config.quiet:
        print_colored("Checking prerequisites...", Fore.YELLOW)

    # Check for Docker-related files (thread-safe)
    with file_system_lock("check_docker_files"):
        required_files = [config.docker.compose_file, "Dockerfile"]

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
    clone_bitcoin_repo(config.repository.url, config.repository.branch)

    # Verify Bitcoin source after cloning (thread-safe)
    with file_system_lock("verify_bitcoin_source"):
        bitcoin_cmake = Path("bitcoin/CMakeLists.txt")
        if not bitcoin_cmake.exists():
            print_colored("[ERROR] Bitcoin CMakeLists.txt not found after cloning", Fore.RED)
            print_colored("The repository may not be a valid Bitcoin Core repository.", Fore.WHITE)
            sys.exit(1)

    if not config.quiet:
        print_colored("[OK] Prerequisites check passed", Fore.GREEN)
        print()


def build_docker_image() -> None:
    """Build the Docker image for Bitcoin Core tests."""
    config = get_config()

    if not config.quiet:
        print_colored("Building Docker image...", Fore.YELLOW)

    container_name = f"{config.docker.container_name}-build"
    with docker_container_lock(container_name):
        cmd = ["docker-compose", "-f", config.docker.compose_file, "build"]
        if config.build.parallel_jobs and config.build.parallel_jobs > 1:
            # Add build arguments for parallel jobs
            cmd.extend(["--build-arg", f"CMAKE_BUILD_PARALLEL_LEVEL={config.build.parallel_jobs}"])

        result = run_command(cmd, "Build Docker image")

        if result.returncode != 0:
            print_colored("[ERROR] Failed to build Docker image", Fore.RED)
            sys.exit(1)

    if not config.quiet:
        print_colored("[OK] Docker image built successfully", Fore.GREEN)
        print()


def run_tests() -> int:
    """Run the Bitcoin Core unit tests."""
    config = get_config()

    if not config.quiet:
        print_colored("Running Bitcoin Core unit tests...", Fore.YELLOW)

    container_name = f"{config.docker.container_name}-runner"
    with docker_container_lock(container_name):
        cmd = ["docker-compose", "run", "--rm", config.docker.container_name]
        result = run_command(cmd, "Run tests")

    if not config.quiet:
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
  python run-bitcoin-tests.py --config .env.production
  python run-bitcoin-tests.py --dry-run

Configuration:
  Settings can be configured via command line arguments, environment variables,
  or .env files. Precedence: CLI args > env vars > .env files > defaults.

  Common .env file settings:
    BTC_REPO_URL=https://github.com/bitcoin/bitcoin
    BTC_REPO_BRANCH=master
    BTC_BUILD_TYPE=RelWithDebInfo
    BTC_LOG_LEVEL=INFO
    BTC_TEST_TIMEOUT=3600
        """
    )

    # Repository options
    parser.add_argument(
        "-r", "--repo-url",
        help="Git repository URL to clone Bitcoin from"
    )

    parser.add_argument(
        "-b", "--branch",
        help="Branch to clone from the repository"
    )

    # Build options
    parser.add_argument(
        "--build-type",
        choices=["Debug", "Release", "RelWithDebInfo", "MinSizeRel"],
        help="CMake build type"
    )

    parser.add_argument(
        "--build-jobs",
        type=int,
        help="Number of parallel build jobs (0 = auto-detect)"
    )

    # Docker options
    parser.add_argument(
        "--keep-containers",
        action="store_true",
        help="Keep Docker containers after execution"
    )

    # Logging options
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
        help="Set logging level"
    )

    # Configuration options
    parser.add_argument(
        "--config",
        help="Path to .env configuration file to load"
    )

    parser.add_argument(
        "--save-config",
        help="Save current configuration to .env file"
    )

    # Application options
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be executed without running operations"
    )

    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Show current configuration and exit"
    )

    args = parser.parse_args()

    # Handle special cases
    if args.config:
        from .config import config_manager
        config_manager.load_from_env_file(args.config)

    if args.show_config:
        try:
            config = load_config(args)
            print(config.get_summary())
            sys.exit(0)
        except ValueError as e:
            print_colored(f"[CONFIG ERROR] {e}", Fore.RED)
            sys.exit(1)

    if args.save_config:
        try:
            config = load_config(args)
            from .config import config_manager
            config_manager.save_to_env_file(args.save_config)
            print_colored(f"Configuration saved to {args.save_config}", Fore.GREEN)
            sys.exit(0)
        except Exception as e:
            print_colored(f"[ERROR] Failed to save configuration: {e}", Fore.RED)
            sys.exit(1)

    return args


def main() -> None:
    """Main function to run the Bitcoin Core tests."""
    args = parse_arguments()

    # Load configuration (this will load from .env files, env vars, and CLI args)
    try:
        config = load_config(args)
    except ValueError as e:
        print_colored(f"[CONFIG ERROR] {e}", Fore.RED)
        sys.exit(1)

    # Initialize thread safety
    initialize_thread_safety()

    # Set up logging using configuration
    logger = setup_logging(
        level=config.logging.level,
        log_file=config.logging.file,
        verbose=config.verbose,
        quiet=config.quiet
    )

    print_colored("Bitcoin Core C++ Tests Runner", Fore.CYAN, bright=True)
    if not config.quiet:
        print_colored(config.get_summary(), Fore.WHITE)
        print()

    start_time = datetime.now()
    if not config.quiet:
        print_colored(f"Started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}", Fore.WHITE)
    logger.info("Starting Bitcoin Core tests runner")
    logger.info(f"Configuration: {config.get_summary().replace(chr(10), ' | ')}")
    if not config.quiet:
        print()

    if config.dry_run:
        print_colored("[DRY RUN] Would execute the following operations:", Fore.YELLOW)
        print_colored(f"  - Clone repository: {config.repository.url} (branch: {config.repository.branch})", Fore.WHITE)
        print_colored(f"  - Build type: {config.build.type}", Fore.WHITE)
        print_colored(f"  - Run tests with timeout: {config.test.timeout}s", Fore.WHITE)
        print_colored("[DRY RUN] Exiting without executing operations", Fore.YELLOW)
        logger.info("Dry run completed, exiting")
        sys.exit(0)

    try:
        # Check prerequisites
        logger.debug("Checking prerequisites")
        check_prerequisites()
        logger.info("Prerequisites check completed successfully")

        # Build Docker image
        logger.debug("Building Docker image")
        build_docker_image()
        logger.info("Docker image built successfully")

        # Run tests
        logger.debug("Running Bitcoin Core unit tests")
        exit_code = run_tests()
        logger.info(f"Tests completed with exit code: {exit_code}")

        # Cleanup (unless configured to keep containers)
        if not config.docker.keep_containers:
            logger.debug("Cleaning up Docker containers")
            cleanup_containers()
            logger.info("Cleanup completed")
        else:
            logger.info("Keeping containers as requested")

        # Final status
        end_time = datetime.now()
        if not config.quiet:
            print_colored(f"Completed at {end_time.strftime('%Y-%m-%d %H:%M:%S')}", Fore.WHITE)

        # Calculate duration
        duration = end_time - start_time
        if not config.quiet:
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
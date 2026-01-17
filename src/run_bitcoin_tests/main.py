"""
Bitcoin Core C++ Unit Tests Runner

A cross-platform Python package to run Bitcoin Core C++ unit tests using Docker.
This package automatically downloads the Bitcoin source code from GitHub and
provides a simple way to build and execute the test suite in a containerized environment.

Features:
- Automatic repository cloning with retry logic
- Docker-based build and test execution
- Comprehensive error handling and diagnostics
- Configurable via CLI, environment variables, or .env files
- Thread-safe operations with proper resource cleanup
- Cross-platform compatibility (Windows, macOS, Linux)

Requirements:
- Python 3.10+
- Git installed and available in PATH
- Docker and Docker Compose installed and running
- colorama (optional, for colored output)

Configuration:
Settings can be configured via:
1. Command line arguments (highest precedence)
2. Environment variables (e.g., BTC_REPO_URL)
3. .env files (lowest precedence)
4. Default values

Example usage:
    # Basic usage with defaults
    python -m run_bitcoin_tests

    # Custom repository and branch
    python -m run_bitcoin_tests --repo-url https://github.com/myfork/bitcoin --branch feature-branch

    # Show configuration
    python -m run_bitcoin_tests --show-config

    # Dry run to see what would be executed
    python -m run_bitcoin_tests --dry-run
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List

from .config import get_config, load_config
from .logging_config import setup_logging
from .network_utils import NetworkError, clone_bitcoin_repo_enhanced
from .performance_utils import get_performance_monitor, optimize_system_resources
from .thread_utils import (
    docker_container_lock,
    file_system_lock,
    initialize_thread_safety,
    resource_tracker,
)

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
    """
    Print a colored message to stdout.

    Args:
        message: The message to print
        color: ANSI color code (e.g., Fore.RED, Fore.GREEN)
        bright: Whether to use bright/bold text
    """
    prefix = Style.BRIGHT if bright else ""
    print(f"{prefix}{color}{message}{Style.RESET_ALL}")


def run_command(
    command: List[str], description: str  # pylint: disable=unused-argument
) -> subprocess.CompletedProcess[str]:
    """
    Run a shell command and return the completed process.

    This function executes commands with real-time output display and proper
    error handling for common failure scenarios.

    Args:
        command: List of command arguments to execute
        description: Human-readable description of the command for logging

    Returns:
        CompletedProcess object containing execution results

    Raises:
        SystemExit: If command execution fails due to missing binaries or other errors
    """
    print_colored(f"Running: {' '.join(command)}", Fore.WHITE)
    try:
        result = subprocess.run(
            command,
            capture_output=False,  # Show output in real-time
            text=True,
            check=False,  # Don't raise exception on non-zero exit
        )
        return result
    except FileNotFoundError:
        print_colored(f"[ERROR] Command not found: {command[0]}", Fore.RED)
        print_colored(
            "Please ensure Docker and Docker Compose are installed and in PATH.", Fore.WHITE
        )
        sys.exit(1)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print_colored(f"[ERROR] Error running command: {exc}", Fore.RED)
        sys.exit(1)


def clone_bitcoin_repo(repo_url: str, branch: str) -> None:
    """
    Clone the Bitcoin repository to the local filesystem.

    This function serves as a wrapper around the enhanced cloning functionality,
    providing a simple interface while leveraging the robust error handling and
    retry logic of the underlying implementation.

    Args:
        repo_url: URL of the Git repository to clone
        branch: Branch name to clone from the repository

    Raises:
        NetworkError: For network connectivity issues
        RepositoryError: For repository access problems
        AuthenticationError: For authentication failures
        SSLError: For SSL certificate issues
        DiskSpaceError: For insufficient disk space
        TimeoutError: For operation timeouts
        RuntimeError: For other cloning failures
    """
    config = get_config()

    # Start performance monitoring for cloning operation
    monitor = get_performance_monitor()
    monitor.start_monitoring()

    try:
        # Use configuration values for clone parameters
        clone_bitcoin_repo_enhanced(
            repo_url=repo_url,
            branch=branch,
            target_dir="bitcoin",
            use_cache=config.network.use_git_cache,
        )

        # Log performance metrics
        metrics = monitor.stop_monitoring()
        if metrics and not config.quiet:
            # Performance metrics collected
            # avg_cpu = sum(m.get('cpu_percent', 0) for m in metrics) / len(metrics)
            # avg_memory = sum(m.get('memory_percent', 0) for m in metrics) / len(metrics)
            pass

    except NetworkError as exc:
        # Network errors are already handled in the enhanced function
        # Just re-raise to maintain the same interface
        monitor.stop_monitoring()
        raise exc
    except Exception as exc:
        print_colored(f"[ERROR] Failed to clone repository: {exc}", Fore.RED)
        print_colored("Please ensure git is installed and you have internet access.", Fore.WHITE)
        raise


def check_prerequisites() -> None:
    """
    Check system prerequisites and prepare the Bitcoin repository.

    This function performs the following checks and operations:
    1. Verifies required Docker configuration files exist
    2. Clones the Bitcoin repository if not already present
    3. Validates the cloned repository structure

    The function uses thread-safe file operations to prevent race conditions
    when multiple processes might be checking prerequisites simultaneously.

    Performance monitoring is enabled during repository operations to track
    resource usage and identify optimization opportunities.

    Raises:
        SystemExit: If required files are missing or repository validation fails
    """
    config = get_config()

    if not config.quiet:
        print_colored("Checking prerequisites...", Fore.YELLOW)

    # Check for Docker-related files (thread-safe)
    with file_system_lock("check_docker_files"):
        required_files = [config.docker.compose_file, "Dockerfile"]

        missing_files: List[str] = []
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
    """
    Build the Docker image for Bitcoin Core compilation and testing.

    This function builds a Docker image containing all necessary dependencies
    for compiling and running Bitcoin Core unit tests. It uses thread-safe
    Docker operations to prevent conflicts when multiple builds might run
    concurrently.

    The build process can be configured to use parallel compilation jobs
    for faster builds on multi-core systems.

    Raises:
        SystemExit: If the Docker build process fails
    """
    config = get_config()

    if not config.quiet:
        print_colored("Building Docker image...", Fore.YELLOW)

    container_name = f"{config.docker.container_name}-build"
    with docker_container_lock(container_name):
        # Import here to avoid circular import
        from .cross_platform_utils import (  # pylint: disable=import-outside-toplevel
            get_cross_platform_command,
        )

        cmd_utils = get_cross_platform_command()
        docker_compose_cmd = cmd_utils.get_docker_compose_command()

        cmd: List[str] = docker_compose_cmd + ["-f", config.docker.compose_file, "build"]

        # Performance optimizations for Docker builds
        if config.build.parallel_jobs and config.build.parallel_jobs > 1:
            # Add build arguments for parallel jobs
            cmd.extend(["--build-arg", f"CMAKE_BUILD_PARALLEL_LEVEL={config.build.parallel_jobs}"])

        # Add the service name to build
        cmd.append(config.docker.container_name)

        # Enable buildkit for better caching and performance
        import os  # pylint: disable=import-outside-toplevel

        old_docker_buildkit = os.environ.get("DOCKER_BUILDKIT")
        os.environ["DOCKER_BUILDKIT"] = "1"

        try:
            result = run_command(cmd, "Build Docker image")
        finally:
            # Restore original DOCKER_BUILDKIT setting
            if old_docker_buildkit is not None:
                os.environ["DOCKER_BUILDKIT"] = old_docker_buildkit
            else:
                os.environ.pop("DOCKER_BUILDKIT", None)

        if result.returncode != 0:
            print_colored("[ERROR] Failed to build Docker image", Fore.RED)
            sys.exit(1)

    if not config.quiet:
        print_colored("[OK] Docker image built successfully", Fore.GREEN)
        print()


def run_tests() -> int:
    """
    Run the Bitcoin Core tests in the Docker container.

    This function executes the selected test suite(s) (C++, Python, or both)
    within a Docker container based on the configuration.

    Returns:
        int: Exit code from the test execution (0 for success, non-zero for failure)

    Note:
        The function uses thread-safe Docker operations to prevent conflicts
        with other concurrent container operations.
    """
    config = get_config()

    test_suite = config.test.test_suite
    if not config.quiet:
        suite_name = {
            "cpp": "C++ unit tests",
            "python": "Python functional tests",
            "both": "C++ unit tests and Python functional tests",
        }.get(test_suite, "tests")
        print_colored(f"Running Bitcoin Core {suite_name}...", Fore.YELLOW)

    container_name = f"{config.docker.container_name}-runner"
    with docker_container_lock(container_name):
        # Import here to avoid circular import
        from .cross_platform_utils import (  # pylint: disable=import-outside-toplevel
            get_cross_platform_command,
        )

        cmd_utils = get_cross_platform_command()
        docker_compose_cmd = cmd_utils.get_docker_compose_command()

        cmd: List[str] = docker_compose_cmd + ["run", "--rm"]

        # Set environment variables for test configuration
        cmd.extend(["-e", f"TEST_SUITE={config.test.test_suite}"])
        cmd.extend(["-e", f"PYTHON_TEST_SCOPE={config.test.python_test_scope}"])
        cmd.extend(["-e", f"PYTHON_TEST_JOBS={config.test.python_test_jobs}"])

        if config.test.cpp_test_args:
            cmd.extend(["-e", f"CPP_TEST_ARGS={config.test.cpp_test_args}"])

        if config.test.python_test_args:
            cmd.extend(["-e", f"PYTHON_TEST_ARGS={config.test.python_test_args}"])

        if config.test.exclude_python_tests and len(config.test.exclude_python_tests) > 0:
            exclude_tests = ",".join(config.test.exclude_python_tests)
            cmd.extend(["-e", f"EXCLUDE_TESTS={exclude_tests}"])

        # Add the service name to run
        cmd.append(config.docker.container_name)
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
    """
    Clean up Docker containers, networks, and tracked resources.

    This function performs comprehensive cleanup of Docker resources created
    during the testing process, including:
    - Stopping and removing containers
    - Removing networks
    - Cleaning up orphaned resources
    - Releasing tracked system resources

    The function uses thread-safe operations to prevent conflicts during
    concurrent cleanup operations.
    """
    config = get_config()

    if not config.quiet:
        print_colored("Cleaning up containers...", Fore.YELLOW)

    with docker_container_lock("bitcoin-tests-cleanup"):
        run_command(["docker-compose", "down", "--remove-orphans"], "Cleanup containers")

    # Also cleanup any tracked resources
    resource_tracker.cleanup_all_resources()


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments with comprehensive configuration options.

    This function sets up an argument parser with support for all major
    configuration categories including repository settings, build options,
    Docker configuration, logging, and application behavior.

    The parsed arguments are processed and validated before being returned.
    Special actions like --show-config and --save-config are handled directly.

    Returns:
        argparse.Namespace: Parsed and validated command line arguments

    Raises:
        SystemExit: For configuration errors or when special actions complete
    """
    parser = argparse.ArgumentParser(
        description="Run Bitcoin Core tests (C++ unit tests and Python functional tests) in Docker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests (C++ and Python)
  python run-bitcoin-tests.py

  # Run only C++ tests
  python run-bitcoin-tests.py --cpp-only

  # Run only Python functional tests (standard suite)
  python run-bitcoin-tests.py --python-only

  # Run quick Python tests
  python run-bitcoin-tests.py --python-only --python-tests quick

  # Run specific Python test
  python run-bitcoin-tests.py --python-only --python-tests wallet_basic

  # Custom repository and branch
  python run-bitcoin-tests.py --repo-url https://github.com/myfork/bitcoin --branch my-feature-branch

  # Verbose output with log file
  python run-bitcoin-tests.py --verbose --log-file bitcoin-tests.log

Configuration:
  Settings can be configured via command line arguments, environment variables,
  or .env files. Precedence: CLI args > env vars > .env files > defaults.

  Common .env file settings:
    BTC_REPO_URL=https://github.com/bitcoin/bitcoin
    BTC_REPO_BRANCH=master
    BTC_BUILD_TYPE=RelWithDebInfo
    BTC_TEST_SUITE=both
    BTC_PYTHON_TEST_SCOPE=standard
    BTC_LOG_LEVEL=INFO
        """,
    )

    # Repository options
    parser.add_argument("-r", "--repo-url", help="Git repository URL to clone Bitcoin from")

    parser.add_argument("-b", "--branch", help="Branch to clone from the repository")

    # Build options
    parser.add_argument(
        "--build-type",
        choices=["Debug", "Release", "RelWithDebInfo", "MinSizeRel"],
        help="CMake build type",
    )

    parser.add_argument(
        "--build-jobs", type=int, help="Number of parallel build jobs (0 = auto-detect)"
    )

    # Test suite options
    parser.add_argument(
        "--test-suite",
        choices=["cpp", "python", "both"],
        default="both",
        help="Which test suite(s) to run (default: both)",
    )

    parser.add_argument(
        "--cpp-only",
        action="store_true",
        help="Run only C++ unit tests (shortcut for --test-suite cpp)",
    )

    parser.add_argument(
        "--python-only",
        action="store_true",
        help="Run only Python functional tests (shortcut for --test-suite python)",
    )

    parser.add_argument(
        "--python-tests",
        help="Python test scope: 'all', 'standard', 'quick', or specific test name(s)",
    )

    parser.add_argument(
        "--python-jobs", type=int, help="Number of parallel jobs for Python tests (default: 4)"
    )

    parser.add_argument(
        "--exclude-test",
        action="append",
        dest="exclude_test",
        help="Exclude specific Python test(s) (can be used multiple times)",
    )

    # Docker options
    parser.add_argument(
        "--keep-containers", action="store_true", help="Keep Docker containers after execution"
    )

    # Logging options
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output (DEBUG level logging)"
    )

    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress all output except errors"
    )

    parser.add_argument("--log-file", help="Path to log file for detailed logging")

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    # Configuration options
    parser.add_argument("--config", help="Path to .env configuration file to load")

    parser.add_argument("--save-config", help="Save current configuration to .env file")

    # Application options
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be executed without running operations",
    )

    parser.add_argument(
        "--show-config", action="store_true", help="Show current configuration and exit"
    )

    # Performance options
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable Git repository caching for cloning operations",
    )

    parser.add_argument(
        "--performance-monitor",
        action="store_true",
        help="Enable detailed performance monitoring during operations",
    )

    args = parser.parse_args()

    # Handle special cases
    if args.config:
        # Import here since config_manager is only needed for special cases
        from .config import config_manager  # pylint: disable=import-outside-toplevel

        config_manager.load_from_env_file(args.config)

    if args.show_config:
        try:
            load_config(args)
            # Import here since config_manager is only needed for special cases
            from .config import config_manager  # pylint: disable=import-outside-toplevel

            print(config_manager.get_summary())
            sys.exit(0)
        except ValueError as exc:
            print_colored(f"[CONFIG ERROR] {exc}", Fore.RED)
            sys.exit(1)

    if args.save_config:
        try:
            load_config(args)
            # Import here since config_manager is only needed for special cases
            from .config import config_manager  # pylint: disable=import-outside-toplevel

            config_manager.save_to_env_file(args.save_config)
            print_colored(f"Configuration saved to {args.save_config}", Fore.GREEN)
            sys.exit(0)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print_colored(f"[ERROR] Failed to save configuration: {exc}", Fore.RED)
            sys.exit(1)

    return args


def main() -> None:
    """
    Main entry point for the Bitcoin Core tests runner.

    This function orchestrates the complete testing workflow:
    1. Parse command line arguments
    2. Load configuration from multiple sources
    3. Initialize thread safety mechanisms
    4. Set up logging system
    5. Execute prerequisite checks
    6. Build Docker image
    7. Run tests
    8. Clean up resources
    9. Report results

    The function handles various error conditions gracefully and ensures
    proper cleanup even when errors occur.

    Raises:
        SystemExit: With appropriate exit codes for different error conditions
    """
    args = parse_arguments()

    # Load configuration (this will load from .env files, env vars, and CLI args)
    try:
        config = load_config(args)
    except ValueError as exc:
        print_colored(f"[CONFIG ERROR] {exc}", Fore.RED)
        sys.exit(1)

    # Initialize thread safety
    initialize_thread_safety()

    # Optimize system resources for better performance
    optimize_system_resources()

    # Set up logging using configuration
    logger = setup_logging(
        level=config.logging.level,
        log_file=config.logging.file,
        verbose=config.verbose,
        quiet=config.quiet,
    )

    print_colored("Bitcoin Core C++ Tests Runner", Fore.CYAN, bright=True)

    # Import config_manager for summary display
    from .config import config_manager  # pylint: disable=import-outside-toplevel

    if not config.quiet:
        print_colored(config_manager.get_summary(), Fore.WHITE)
        print()

    start_time = datetime.now()
    if not config.quiet:
        print_colored(f"Started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}", Fore.WHITE)
    logger.info("Starting Bitcoin Core tests runner")
    logger.info("Configuration: %s", config_manager.get_summary().replace(chr(10), " | "))
    if not config.quiet:
        print()

    if config.dry_run:
        print_colored("[DRY RUN] Would execute the following operations:", Fore.YELLOW)
        print_colored(
            f"  - Clone repository: {config.repository.url} (branch: {config.repository.branch})",
            Fore.WHITE,
        )
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
        logger.info("Tests completed with exit code: %s", exit_code)

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
        logger.info("Total execution time: %s", duration)

        if exit_code == 0:
            logger.info("All tests passed successfully")
        else:
            logger.warning("Some tests failed (exit code: %s)", exit_code)

        sys.exit(exit_code)

    except KeyboardInterrupt:
        logger.warning("Operation cancelled by user (KeyboardInterrupt)")
        print_colored("\n[INTERRUPTED] Operation cancelled by user", Fore.YELLOW)
        cleanup_containers()
        sys.exit(130)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Handle network and other errors generically since we're not using the complex security module
        if "network" in str(exc).lower() or "connection" in str(exc).lower():
            logger.error("Network error: %s", exc)
            print_colored(f"[NETWORK ERROR] {exc}", Fore.RED)
            print_colored("Please check your internet connection and try again.", Fore.WHITE)
        elif "repository" in str(exc).lower() or "not found" in str(exc).lower():
            logger.error("Repository error: %s", exc)
            print_colored(f"[REPO ERROR] {exc}", Fore.RED)
            print_colored(
                "Please verify the repository URL and branch name are correct.", Fore.WHITE
            )
        else:
            logger.error("Unexpected error: %s", exc, exc_info=True)
            print_colored(f"[ERROR] {exc}", Fore.RED)

        cleanup_containers()
        sys.exit(1)

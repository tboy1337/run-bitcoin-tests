#!/usr/bin/env python3
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

try:
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)
except ImportError:
    # Fallback if colorama is not available
    class Fore:
        CYAN = ""
        GREEN = ""
        RED = ""
        YELLOW = ""
        WHITE = ""
        RESET = ""

    class Style:
        BRIGHT = ""
        RESET_ALL = ""

def print_colored(message: str, color: str = Fore.WHITE, bright: bool = False) -> None:
    """Print a colored message to stdout."""
    prefix = Style.BRIGHT if bright else ""
    print(f"{prefix}{color}{message}{Style.RESET_ALL}")

def run_command(command: list, description: str) -> subprocess.CompletedProcess:
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
    bitcoin_path = Path("bitcoin")

    if bitcoin_path.exists():
        print_colored("[OK] Bitcoin source directory already exists", Fore.GREEN)
        return

    print_colored(f"Cloning Bitcoin repository from {repo_url} (branch: {branch})...", Fore.YELLOW)

    try:
        # Clone the repository
        cmd = ["git", "clone", "--depth", "1", "--branch", branch, repo_url, "bitcoin"]
        result = run_command(cmd, "Clone Bitcoin repository")

        if result.returncode != 0:
            print_colored("[ERROR] Failed to clone Bitcoin repository", Fore.RED)
            sys.exit(1)

        print_colored("[OK] Bitcoin repository cloned successfully", Fore.GREEN)

    except Exception as e:
        print_colored(f"[ERROR] Failed to clone repository: {e}", Fore.RED)
        print_colored("Please ensure git is installed and you have internet access.", Fore.WHITE)
        sys.exit(1)

def check_prerequisites(repo_url: str, branch: str) -> None:
    """Check if required files exist and clone repo if needed."""
    print_colored("Checking prerequisites...", Fore.YELLOW)

    # Check for Docker-related files
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

    # Clone Bitcoin repo if needed
    clone_bitcoin_repo(repo_url, branch)

    # Verify Bitcoin source after cloning
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

    result = run_command(["docker-compose", "build"], "Build Docker image")

    if result.returncode != 0:
        print_colored("[ERROR] Failed to build Docker image", Fore.RED)
        sys.exit(1)

    print_colored("[OK] Docker image built successfully", Fore.GREEN)
    print()

def run_tests() -> int:
    """Run the Bitcoin Core unit tests."""
    print_colored("Running Bitcoin Core unit tests...", Fore.YELLOW)

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
    run_command(["docker-compose", "down", "--remove-orphans"], "Cleanup containers")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Bitcoin Core C++ unit tests in Docker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run-bitcoin-tests.py
  python run-bitcoin-tests.py --repo-url https://github.com/myfork/bitcoin --branch my-feature-branch
  python run-bitcoin-tests.py -r https://github.com/bitcoin/bitcoin -b v25.1
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

    return parser.parse_args()

def main() -> None:
    """Main function to run the Bitcoin Core tests."""
    args = parse_arguments()

    print_colored("Bitcoin Core C++ Tests Runner", Fore.CYAN, bright=True)
    if args.repo_url != "https://github.com/bitcoin/bitcoin" or args.branch != "master":
        print_colored(f"Repository: {args.repo_url} (branch: {args.branch})", Fore.WHITE)

    start_time = datetime.now()
    print_colored(f"Started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}", Fore.WHITE)
    print()

    try:
        # Check prerequisites
        check_prerequisites(args.repo_url, args.branch)

        # Build Docker image
        build_docker_image()

        # Run tests
        exit_code = run_tests()

        # Cleanup
        cleanup_containers()

        # Final status
        end_time = datetime.now()
        print_colored(f"Completed at {end_time.strftime('%Y-%m-%d %H:%M:%S')}", Fore.WHITE)

        # Calculate duration
        duration = end_time - start_time
        print_colored(f"Duration: {duration}", Fore.WHITE)

        sys.exit(exit_code)

    except KeyboardInterrupt:
        print_colored("\n[INTERRUPTED] Operation cancelled by user", Fore.YELLOW)
        cleanup_containers()
        sys.exit(130)
    except Exception as e:
        print_colored(f"[ERROR] An unexpected error occurred: {e}", Fore.RED)
        cleanup_containers()
        sys.exit(1)

if __name__ == "__main__":
    main()
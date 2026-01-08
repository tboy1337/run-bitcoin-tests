#!/usr/bin/env python3
"""
Bitcoin Core C++ Unit Tests Runner

A cross-platform Python script to run Bitcoin Core C++ unit tests using Docker.
This script automatically downloads the Bitcoin source code from GitHub and
provides a simple way to build and execute the test suite in a containerized environment.

Requirements:
- Python 3.10+
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

# Import and run the main function from the package
import sys
from pathlib import Path

# Add src directory to Python path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from run_bitcoin_tests.main import main

if __name__ == "__main__":
    main()
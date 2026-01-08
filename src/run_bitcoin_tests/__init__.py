"""
Bitcoin Core C++ Unit Tests Runner

A cross-platform Python package to run Bitcoin Core C++ unit tests using Docker.
This package automatically downloads the Bitcoin source code from GitHub and
provides a simple way to build and execute the test suite in a containerized environment.

Requirements:
- Python 3.10+
- Git installed
- Docker and Docker Compose installed and running
- colorama (optional, for colored output)
"""

__version__ = "1.0.0"
__author__ = "tboy1337"
__license__ = "MIT"

from .main import main

__all__ = ["main"]
# Bitcoin Core Tests Runner

Docker-based solution to run Bitcoin Core C++ unit tests and Python functional tests with flexible configuration.

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Git
- Docker and Docker Compose (running)

### Installation

```bash
# Install from PyPI (recommended)
pip install run-bitcoin-tests

# Or install from source
git clone https://github.com/tboy1337/run-bitcoin-tests
cd run-bitcoin-tests
pip install -e .
```

### Basic Usage

```bash
# Run all tests (automatically clones Bitcoin Core)
python run-bitcoin-tests.py

# Run only C++ unit tests
python run-bitcoin-tests.py --cpp-only

# Run only Python functional tests
python run-bitcoin-tests.py --python-only

# Run quick Python tests
python run-bitcoin-tests.py --python-only --python-tests quick

# Test specific branch or fork
python run-bitcoin-tests.py -r https://github.com/bitcoin/bitcoin -b v25.1
```

## 📦 Programmatic Usage

```python
from run_bitcoin_tests import main

# Run with custom configuration
import sys
sys.argv = ['run-bitcoin-tests', '--python-only', '--python-tests', 'quick']
exit_code = main()
```

## ✨ Features

- Automatic Bitcoin Core repository cloning
- Custom fork and branch support
- Both C++ (686+) and Python (300+) test suites
- Flexible test selection and filtering
- Parallel test execution
- Cross-platform (Windows, macOS, Linux)
- Docker-based isolation
- Colored output and progress tracking

## 🛠️ How It Works

1. Clones Bitcoin Core repository (configurable fork/branch)
2. Builds Ubuntu 22.04 Docker container with all dependencies
3. Compiles Bitcoin Core with CMake
4. Runs selected test suites (C++, Python, or both)
5. Reports results with colored output and duration tracking

## 📋 Configuration

Create `.env` file from template (optional):

```bash
cp .env.example .env
```

Key environment variables:

```bash
BUILD_TYPE=RelWithDebInfo          # Debug, Release, RelWithDebInfo, MinSizeRel
TEST_SUITE=both                    # cpp, python, or both
PYTHON_TEST_SCOPE=standard         # all, standard, quick, or test name
PYTHON_TEST_JOBS=4                 # Parallel jobs
CPP_TEST_ARGS=                     # Additional C++ test arguments
EXCLUDE_TESTS=                     # Comma-separated tests to skip
VERBOSE=0                          # 1 for verbose output
```

## 🧪 Test Examples

```bash
# Custom repository and branch
python run-bitcoin-tests.py -r https://github.com/myfork/bitcoin -b feature-branch

# Specific Python tests
python run-bitcoin-tests.py --python-only --python-tests wallet_basic
python run-bitcoin-tests.py --python-only --python-tests "wallet_basic.py mempool_accept.py"

# Exclude tests
python run-bitcoin-tests.py --python-only --exclude-test feature_fee_estimation

# More parallel jobs
python run-bitcoin-tests.py --python-only --python-jobs 8

# Verbose output
python run-bitcoin-tests.py --verbose
```

## 🔧 Advanced Usage

### Custom Test Arguments (.env)

```bash
# C++ specific test suite
CPP_TEST_ARGS=--run_test=getarg_tests --log_level=all

# Python specific configuration
PYTHON_TEST_SCOPE=wallet_basic.py
EXCLUDE_TESTS=feature_fee_estimation,rpc_blockchain
PYTHON_TEST_JOBS=8
```

### Manual Docker Commands

```bash
docker-compose build                               # Build image
docker-compose run --rm bitcoin-tests              # Run tests
docker-compose run --rm bitcoin-tests /bin/bash    # Debug shell
docker-compose logs bitcoin-tests                  # View logs
```

### Performance Optimization

Edit `docker-compose.yml` for faster builds:

```yaml
services:
  bitcoin-tests:
    build:
      args:
        CMAKE_BUILD_PARALLEL_LEVEL: 8  # Match CPU cores
```

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Docker not running | Start Docker Desktop |
| Build failures | Clear cache: `docker system prune -a`<br>Ensure 4GB+ RAM available |
| Test failures | Use `--verbose` for details<br>Run failing test alone: `--python-tests test_name` |
| Test timeouts | Use `--python-tests quick`<br>Increase `--python-jobs 8`<br>Exclude slow tests |

## 🧑‍💻 Development

### Run Project Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run test suite
pytest

# Run with coverage
pytest --cov=src/run_bitcoin_tests --cov-report=html

# Type checking
mypy src/

# Linting
pylint src/
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linters
5. Submit a pull request

## 📚 Reference

**C++ Test Commands** (Boost.Test framework):
- `--list_content` - List all tests
- `--run_test=<suite>` - Run specific suite
- `--log_level=all` - Verbose logging

**Python Test Commands**:
- `--jobs=N` - Parallel execution
- `--extended` - Include extended tests
- `--exclude test_name` - Skip specific test

See [Bitcoin Core C++ Tests](https://github.com/bitcoin/bitcoin/blob/master/src/test/README.md) and [Python Functional Tests](https://github.com/bitcoin/bitcoin/blob/master/test/README.md) for details.

## 📄 License

This setup is provided as-is for testing Bitcoin Core. The Bitcoin Core source code is licensed under the MIT License.

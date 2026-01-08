# Bitcoin Core C++ Unit Tests Runner

A one-click Docker-based solution to run Bitcoin Core C++ unit tests.

## 🚀 Quick Start

### Prerequisites

1. **Python 3.6+** installed
2. **Git** installed
3. **Docker and Docker Compose** installed and running
4. **colorama** (optional, for colored output): `pip install -r requirements.txt`

### One-Click Execution

```bash
# Run all tests (cross-platform)
python run-bitcoin-tests.py
# or make executable: chmod +x run-bitcoin-tests.py && ./run-bitcoin-tests.py
```

# Note: The bitcoin/ directory will be created automatically when running the script

## 🛠️ How It Works

### Architecture

1. **Repository Cloning**: Automatically downloads Bitcoin source from GitHub (customizable)
2. **Dockerfile**: Creates Ubuntu 22.04 container with all Bitcoin Core build dependencies
3. **docker-compose.yml**: Orchestrates build and test execution
4. **Python Script**: Cross-platform interface with Git cloning and prerequisite checks
5. **Environment Config**: Allows customization via `.env` file

### Build Process

```mermaid
graph TD
    A[Python Script] --> B[Check Prerequisites]
    B --> C[Clone Bitcoin Repo]
    C --> D[Docker Running?]
    D --> E[Build Docker Image]
    E --> F[Run Tests in Container]
    F --> G[Output Results]
```

## 📋 Configuration

### Environment Variables (.env)

```bash
# Build type: Debug, Release, RelWithDebInfo, MinSizeRel
BUILD_TYPE=RelWithDebInfo

# Test arguments (see bitcoin/src/test/README.md)
TEST_ARGS=

# Verbose output
VERBOSE=0
```

### Python Script Features

The Python script provides:
- **Cross-platform compatibility** (Windows, macOS, Linux)
- **Colored output** for better readability
- **Proper error handling** and cleanup
- **Duration tracking** for performance monitoring
- **Prerequisites checking** before execution

## 🧪 Test Execution Examples

### Run All Tests
```bash
# Run tests with default Bitcoin Core repository (master branch)
python run-bitcoin-tests.py

# Run tests with custom repository and branch
python run-bitcoin-tests.py --repo-url https://github.com/myfork/bitcoin --branch my-feature-branch

# Short options
python run-bitcoin-tests.py -r https://github.com/bitcoin/bitcoin -b v25.1

# Make executable and run directly (Linux/macOS)
chmod +x run-bitcoin-tests.py && ./run-bitcoin-tests.py
```

### Features
- **Automatic repository cloning** - downloads Bitcoin source code from GitHub
- **Custom repository support** - use your own fork and branch
- **Prerequisites checking** - verifies Git, Docker, and required files
- **Clean build process** - builds Docker image with optimized Bitcoin Core compilation
- **Comprehensive test execution** - runs all 686+ unit tests
- **Success/failure reporting** - clear colored output with test results
- **Automatic cleanup** - removes containers and networks after completion
- **Duration tracking** - shows total execution time

## 🔧 Advanced Usage

### Custom Test Arguments

Edit `.env` file for complex test configurations:

```bash
# Run with debug logging
TEST_ARGS=--log_level=all --run_test=getarg_tests

# Run with console output
TEST_ARGS=--run_test=getarg_tests -- -printtoconsole=1

# Custom test data directory
TEST_ARGS=--run_test=getarg_tests -- -testdatadir=/tmp/custom
```

### Manual Docker Commands

```bash
# Build image manually
docker-compose build

# Run tests manually
docker-compose run --rm bitcoin-tests

# Debug in container
docker-compose run --rm bitcoin-tests /bin/bash

# View logs
docker-compose logs bitcoin-tests
```

### Performance Optimization

For faster builds on powerful machines:

1. Edit `docker-compose.yml` and add build args:
```yaml
services:
  bitcoin-tests:
    build:
      args:
        CMAKE_BUILD_PARALLEL_LEVEL: 8  # Adjust based on your CPU cores
```

2. Use more parallel jobs in PowerShell script

## 🐛 Troubleshooting

### Common Issues

#### Docker Not Running
```
✗ Docker is not running
```
**Solution**: Start Docker Desktop and wait for it to be ready.

#### Bitcoin Source Missing
```
✗ Bitcoin source directory not found at ./bitcoin
```
**Solution**: Ensure Bitcoin Core source code is cloned into `bitcoin/` directory.

#### Build Failures
```
✗ Failed to build Docker image
```
**Solutions**:
- Run with `-CleanBuild` flag
- Check Docker Desktop has sufficient resources (4GB+ RAM recommended)
- Clear Docker cache: `docker system prune -a`

#### Test Failures
```
✗ Some tests failed (exit code: X)
```
**Solutions**:
- Use `-Verbose` flag for detailed output
- Use `-KeepContainer` to inspect container
- Check test logs: `docker-compose logs bitcoin-tests`

## 📚 Reference

### Bitcoin Core Test Documentation

This setup follows the official [Unit Tests README](bitcoin/src/test/README.md):

- **Build Command**: `cmake -B build -DBUILD_TESTS=ON`
- **Compile**: `cmake --build build -j$(nproc)`
- **Run Tests**: `build/bin/test_bitcoin`
- **Test Arguments**: Follow Boost.Test framework conventions

### Key Test Commands

| Command | Description |
|---------|-------------|
| `--list_content` | List all available tests |
| `--run_test=<suite>` | Run specific test suite |
| `--run_test=<suite>/<test>` | Run specific test |
| `--log_level=all` | Verbose logging |
| `-- -printtoconsole=1` | Debug output to console |

## 🤖 AI Model Usage

### Automated Testing Workflow

```bash
# 1. Initial setup and full test run (clones Bitcoin Core master)
python run-bitcoin-tests.py

# 2. Test with specific branch or fork
python run-bitcoin-tests.py --repo-url https://github.com/bitcoin/bitcoin --branch v25.1

# 3. Test your own fork and feature branch
python run-bitcoin-tests.py --repo-url https://github.com/myfork/bitcoin --branch my-feature-branch

# 4. CI/CD integration - always fresh clone
python run-bitcoin-tests.py -r https://github.com/bitcoin/bitcoin -b master
```

### CI/CD Integration

This setup is designed for automated testing environments:

- **Idempotent**: Safe to run multiple times
- **Isolated**: No host system pollution
- **Configurable**: Environment-based customization
- **Observable**: Clear success/failure reporting

### Error Pattern Recognition

When tests fail, look for:

1. **Build Errors**: Check Dockerfile dependencies
2. **Test Failures**: Review test output for specific assertions
3. **Environment Issues**: Verify Docker and host system state
4. **Configuration Problems**: Check `.env` file settings

## 📄 License

This setup is provided as-is for testing Bitcoin Core. The Bitcoin Core source code is licensed under the MIT License.
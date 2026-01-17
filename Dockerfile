# Bitcoin Core Tests Docker Environment
# Based on Bitcoin Core build requirements from doc/build-unix.md

FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install basic build tools and dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    pkgconf \
    python3 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Bitcoin Core specific dependencies
RUN apt-get update && apt-get install -y \
    libevent-dev \
    libboost-dev \
    libsqlite3-dev \
    libcapnp-dev \
    capnproto \
    libzmq3-dev \
    systemtap-sdt-dev \
    libdb-dev \
    libdb++-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for functional tests
RUN pip3 install --no-cache-dir \
    pyzmq \
    requests

# Set working directory
WORKDIR /bitcoin

# Copy the bitcoin source code
COPY bitcoin/ .

# Create build directory
RUN mkdir -p build

# Configure the build with CMake
# Enable tests, wallet, and other features needed for functional tests
RUN cd build && \
    cmake .. \
    -DBUILD_TESTS=ON \
    -DBUILD_GUI=OFF \
    -DBUILD_CLI=ON \
    -DBUILD_WALLET=ON \
    -DBUILD_DAEMON=ON \
    -DBUILD_UTIL=ON \
    -DWITH_ZMQ=ON \
    -DWITH_SQLITE=ON \
    -DENABLE_IPC=OFF \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo

# Build the project (including tests)
# Use parallel jobs for faster compilation
RUN cd build && \
    cmake --build . -j$(nproc)

# Create script to run C++ tests
RUN echo '#!/bin/bash\n\
set -e\n\
echo "=========================================="\n\
echo "Running Bitcoin Core C++ Unit Tests"\n\
echo "=========================================="\n\
cd /bitcoin/build\n\
if [ -n "$CPP_TEST_ARGS" ]; then\n\
    echo "Running with args: $CPP_TEST_ARGS"\n\
    ./bin/test_bitcoin $CPP_TEST_ARGS\n\
else\n\
    echo "Running all C++ unit tests..."\n\
    ./bin/test_bitcoin\n\
fi\n\
echo "=========================================="\n\
echo "C++ tests completed successfully"\n\
echo "=========================================="\n\
' > /run_cpp_tests.sh && chmod +x /run_cpp_tests.sh

# Create script to run Python functional tests
RUN echo '#!/bin/bash\n\
set -e\n\
echo "=========================================="\n\
echo "Running Bitcoin Core Python Functional Tests"\n\
echo "=========================================="\n\
cd /bitcoin\n\
\n\
# Determine test scope\n\
TEST_ARGS=""\n\
if [ "$PYTHON_TEST_SCOPE" = "quick" ]; then\n\
    echo "Running quick test suite..."\n\
    # Run a minimal subset of fast tests\n\
    TEST_ARGS="wallet_basic.py mempool_accept.py p2p_invalid_messages.py"\n\
elif [ "$PYTHON_TEST_SCOPE" = "standard" ]; then\n\
    echo "Running standard test suite (excluding extended tests)..."\n\
    TEST_ARGS="--extended"\n\
elif [ "$PYTHON_TEST_SCOPE" = "all" ]; then\n\
    echo "Running all functional tests (including extended)..."\n\
    TEST_ARGS="--extended --extended-only"\n\
elif [ -n "$PYTHON_TEST_SCOPE" ]; then\n\
    echo "Running specific test(s): $PYTHON_TEST_SCOPE"\n\
    TEST_ARGS="$PYTHON_TEST_SCOPE"\n\
else\n\
    echo "Running standard test suite..."\n\
    TEST_ARGS=""\n\
fi\n\
\n\
# Add parallel jobs\n\
JOBS="${PYTHON_TEST_JOBS:-4}"\n\
echo "Using $JOBS parallel jobs"\n\
\n\
# Add additional args\n\
if [ -n "$PYTHON_TEST_ARGS" ]; then\n\
    TEST_ARGS="$TEST_ARGS $PYTHON_TEST_ARGS"\n\
fi\n\
\n\
# Exclude specified tests\n\
if [ -n "$EXCLUDE_TESTS" ]; then\n\
    echo "Excluding tests: $EXCLUDE_TESTS"\n\
    for test in ${EXCLUDE_TESTS//,/ }; do\n\
        TEST_ARGS="$TEST_ARGS --exclude $test"\n\
    done\n\
fi\n\
\n\
# Run the functional test suite\n\
echo "Command: test/functional/test_runner.py --jobs=$JOBS $TEST_ARGS"\n\
python3 test/functional/test_runner.py --jobs=$JOBS $TEST_ARGS\n\
\n\
echo "=========================================="\n\
echo "Python functional tests completed successfully"\n\
echo "=========================================="\n\
' > /run_python_tests.sh && chmod +x /run_python_tests.sh

# Create unified script to run all tests
RUN echo '#!/bin/bash\n\
EXIT_CODE=0\n\
\n\
# Determine which test suite to run\n\
TEST_SUITE="${TEST_SUITE:-both}"\n\
\n\
echo "=========================================="\n\
echo "Bitcoin Core Test Runner"\n\
echo "Test Suite: $TEST_SUITE"\n\
echo "=========================================="\n\
echo ""\n\
\n\
# Run C++ tests\n\
if [ "$TEST_SUITE" = "cpp" ] || [ "$TEST_SUITE" = "both" ]; then\n\
    /run_cpp_tests.sh\n\
    CPP_EXIT=$?\n\
    if [ $CPP_EXIT -ne 0 ]; then\n\
        echo "ERROR: C++ tests failed with exit code $CPP_EXIT"\n\
        EXIT_CODE=$CPP_EXIT\n\
    fi\n\
    echo ""\n\
fi\n\
\n\
# Run Python tests\n\
if [ "$TEST_SUITE" = "python" ] || [ "$TEST_SUITE" = "both" ]; then\n\
    /run_python_tests.sh\n\
    PYTHON_EXIT=$?\n\
    if [ $PYTHON_EXIT -ne 0 ]; then\n\
        echo "ERROR: Python tests failed with exit code $PYTHON_EXIT"\n\
        EXIT_CODE=$PYTHON_EXIT\n\
    fi\n\
    echo ""\n\
fi\n\
\n\
# Report final status\n\
echo "=========================================="\n\
if [ $EXIT_CODE -eq 0 ]; then\n\
    echo "All tests passed successfully!"\n\
else\n\
    echo "Some tests failed (exit code: $EXIT_CODE)"\n\
fi\n\
echo "=========================================="\n\
\n\
exit $EXIT_CODE\n\
' > /run_all_tests.sh && chmod +x /run_all_tests.sh

# Default command runs all tests
CMD ["/run_all_tests.sh"]
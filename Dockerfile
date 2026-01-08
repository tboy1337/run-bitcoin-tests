# Bitcoin Core C++ Unit Tests Docker Environment
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
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /bitcoin

# Copy the bitcoin source code
COPY bitcoin/ .

# Create build directory
RUN mkdir -p build

# Configure the build with CMake
# Enable tests, disable GUI, wallet, and IPC for faster compilation focused on unit tests
RUN cd build && \
    cmake .. \
    -DBUILD_TESTS=ON \
    -DBUILD_GUI=OFF \
    -DBUILD_CLI=ON \
    -DENABLE_IPC=OFF \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo

# Build the project (including tests)
# Use parallel jobs for faster compilation
RUN cd build && \
    cmake --build . -j$(nproc)

# Create a script to run the tests
RUN echo '#!/bin/bash\n\
echo "=========================================="\n\
echo "Running Bitcoin Core C++ Unit Tests"\n\
echo "=========================================="\n\
cd /bitcoin/build\n\
echo "Listing available tests..."\n\
./bin/test_bitcoin --list_content\n\
echo "=========================================="\n\
echo "Running all unit tests..."\n\
echo "=========================================="\n\
./bin/test_bitcoin\n\
echo "=========================================="\n\
echo "Test execution completed"\n\
echo "=========================================="\n\
' > /run_tests.sh && chmod +x /run_tests.sh

# Default command runs the tests
CMD ["/run_tests.sh"]
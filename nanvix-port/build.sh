#!/bin/bash
# Build script for CPython 3.12 on NanVix.
# Run inside Docker: nanvix/toolchain:v0.12.x-minimal
#
# Usage:
#   docker run --rm -v "${PWD}:/mnt" -w /mnt nanvix/toolchain:v0.12.x-minimal \
#     bash src/ports/cpython-nanvix/build.sh

set -e

export PATH=/opt/nanvix/bin:$PATH
NANVIX_ROOT=/mnt
PORT_DIR=$NANVIX_ROOT/src/ports/cpython-nanvix
CPYTHON_DIR=$NANVIX_ROOT/src/contrib/cpython
BUILD_DIR=$NANVIX_ROOT/src/contrib/cpython/build-nanvix

# Cross-compiler settings
export CC=i686-nanvix-gcc
export CXX=i686-nanvix-g++
export AR=i686-nanvix-ar
export RANLIB=i686-nanvix-ranlib
export READELF=i686-nanvix-readelf
export STRIP=i686-nanvix-strip

# Compiler/linker flags
export CFLAGS="-m32 -march=pentiumpro -Os -fdata-sections -ffunction-sections"
export CPPFLAGS="-I/opt/nanvix/i686-nanvix/include"
export LDFLAGS="-T $NANVIX_ROOT/build/user/linker/x86/user.ld -Wl,--gc-sections -static"
export LIBS="-L$NANVIX_ROOT/lib -lposix -L/opt/nanvix/i686-nanvix/lib -lc -lm"

# Step 1: Compile stubs
echo "=== Compiling NanVix stubs ==="
$CC $CFLAGS -c $PORT_DIR/stubs.c -o $PORT_DIR/stubs.o

# Step 2: Configure CPython
echo "=== Configuring CPython ==="
cd $CPYTHON_DIR
mkdir -p $BUILD_DIR
cd $BUILD_DIR

CONFIG_SITE=$PORT_DIR/config.site \
$CPYTHON_DIR/configure \
  --host=i686-nanvix \
  --build=x86_64-linux-gnu \
  --disable-shared \
  --without-pymalloc \
  --disable-ipv6 \
  --without-ensurepip \
  --without-openssl \
  --without-readline \
  --with-system-ffi=no \
  --with-system-expat=no \
  --disable-test-modules \
  2>&1

# Step 3: Build (will likely fail — iterate from here)
echo "=== Building CPython ==="
make -j$(nproc) 2>&1 || echo "Build failed — this is expected on first attempt. Check errors above."

echo "=== Done ==="

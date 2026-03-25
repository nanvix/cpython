#!/bin/bash
# install-missing-deps.sh — Download and install missing NanVix deps
set -uo pipefail

NH="/tmp/cpython-build/.nanvix/extracted/nanvix"
GH_TOKEN=$(gh auth token 2>/dev/null || true)

echo "Sysroot: $NH"

# Download bzip2 (no hyperlight variant — use microvm)
echo "Downloading bzip2..."
curl -fsSL -H "Authorization: Bearer $GH_TOKEN" \
  "https://github.com/nanvix/bzip2/releases/latest/download/bzip2-microvm-multi-process-128mb.tar.bz2" \
  -o /tmp/bzip2.tar.bz2
mkdir -p /tmp/bzip2-x && tar -xjf /tmp/bzip2.tar.bz2 -C /tmp/bzip2-x
find /tmp/bzip2-x -name "*.a" -exec cp -v {} "$NH/lib/" \;
find /tmp/bzip2-x -name "bzlib.h" -exec cp -v {} "$NH/include/" \;

# Download libffi
echo "Downloading libffi..."
curl -fsSL -H "Authorization: Bearer $GH_TOKEN" \
  "https://github.com/nanvix/libffi/releases/latest/download/libffi-hyperlight-multi-process-128mb.tar.bz2" \
  -o /tmp/libffi.tar.bz2
mkdir -p /tmp/libffi-x && tar -xjf /tmp/libffi.tar.bz2 -C /tmp/libffi-x
find /tmp/libffi-x -name "*.a" -exec cp -v {} "$NH/lib/" \;
find /tmp/libffi-x -name "ffi.h" -exec cp -v {} "$NH/include/" \;
find /tmp/libffi-x -name "ffitarget.h" -exec cp -v {} "$NH/include/" \;

# Download openssl
echo "Downloading openssl..."
curl -fsSL -H "Authorization: Bearer $GH_TOKEN" \
  "https://github.com/nanvix/openssl/releases/latest/download/openssl-hyperlight-multi-process-128mb.tar.bz2" \
  -o /tmp/openssl.tar.bz2
mkdir -p /tmp/openssl-x && tar -xjf /tmp/openssl.tar.bz2 -C /tmp/openssl-x
find /tmp/openssl-x -name "*.a" -exec cp -v {} "$NH/lib/" \;
mkdir -p "$NH/include/openssl"
find /tmp/openssl-x -path "*/include/openssl/*.h" -exec cp {} "$NH/include/openssl/" \;

echo "=== Final sysroot ==="
ls "$NH/lib/"*.a | sort
echo "Header dirs:"
ls -d "$NH/include/"*/ 2>/dev/null

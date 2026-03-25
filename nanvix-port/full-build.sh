#!/bin/bash
set -uo pipefail

echo "=== Step 1: Copy repo ==="
rm -rf /tmp/cpython-build
cp -a /mnt/a/Repos/NanVix-CPython /tmp/cpython-build
cd /tmp/cpython-build

echo "=== Step 2: Fix CRLF ==="
find . -maxdepth 1 \( -name "configure" -o -name "config.*" -o -name "install-sh" -o -name "aclocal.m4" -o -name "z" -o -name "pyconfig.h.in" -o -name "Makefile.pre.in" \) -exec sed -i 's/\r$//' {} \;
find Modules \( -name "Setup*" -o -name "makesetup" \) -exec sed -i 's/\r$//' {} \;
sed -i 's/\r$//' nanvix-port/build-pptx-deps.sh nanvix-port/stubs.c nanvix-port/config.site
rm -f pyconfig.h .nanvix-configured

echo "=== Step 3: z setup ==="
export GH_TOKEN=$(gh auth token 2>/dev/null || true)
./z setup || echo "WARNING: z setup had errors (some deps may have failed to download)"

echo "=== Step 4: Build pptx C libs (Docker) ==="
NH=/tmp/cpython-build/.nanvix/extracted/nanvix
DU=$(id -u)
DG=$(id -g)
docker run --rm --user "$DU:$DG" \
  -v /tmp/cpython-build:/mnt/workspace \
  -v "$NH":/mnt/sysroot \
  -w /mnt/workspace \
  -e HOME=/tmp \
  -e NANVIX_HOME=/mnt/sysroot \
  -e NANVIX_TOOLCHAIN=/opt/nanvix \
  nanvix/toolchain:latest-minimal \
  bash nanvix-port/build-pptx-deps.sh 2>&1 | tail -30 || echo "pptx-deps partial"

echo "=== Step 5: z build ==="
./z build 2>&1 | tail -30 || echo "BUILD FAILED - check errors above"

echo "=== BUILD PIPELINE COMPLETE ==="

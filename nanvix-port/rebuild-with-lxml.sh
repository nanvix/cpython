#!/bin/bash
set -uo pipefail
cd /tmp/cpython-build
NH=/tmp/cpython-build/.nanvix/extracted/nanvix
DU=$(id -u)
DG=$(id -g)

echo "=== Rebuilding libxml2 (with schemas) + lxml + CPython ==="

# Step 1: Rebuild pptx deps (libxml2 + lxml)
docker run --rm --user "$DU:$DG" \
  -v /tmp/cpython-build:/mnt/workspace \
  -v "$NH":/mnt/sysroot \
  -w /mnt/workspace \
  -e HOME=/tmp \
  -e NANVIX_HOME=/mnt/sysroot \
  -e NANVIX_TOOLCHAIN=/opt/nanvix \
  nanvix/toolchain:latest-minimal \
  bash nanvix-port/build-pptx-deps.sh 2>&1 | tail -25

echo ""
echo "=== Rebuilding CPython ==="
rm -f .nanvix-configured
# Fix Setup.local paths
sed -i 's|Modules/lxml_etree_builtin.c|lxml_etree_builtin.c|g' Modules/Setup.local
sed -i 's|Modules/lxml_elementpath_builtin.c|lxml_elementpath_builtin.c|g' Modules/Setup.local
./z build 2>&1 | tail -10

echo ""
echo "=== Result ==="
if [ -f python ] || [ -f python.elf ]; then
  echo "BUILD SUCCEEDED!"
  ls -la python python.elf 2>/dev/null
else
  echo "BUILD FAILED"
fi

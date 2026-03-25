#!/bin/bash
# continue-build.sh — Rebuild CPython with lxml modules, then build ramfs
set -euo pipefail

cd /tmp/cpython-build

echo "=== Step 1: Fix Setup.local paths (no Modules/ prefix) ==="
sed -i 's|Modules/lxml_etree_builtin.c|lxml_etree_builtin.c|g' Modules/Setup.local
sed -i 's|Modules/lxml_elementpath_builtin.c|lxml_elementpath_builtin.c|g' Modules/Setup.local
echo "Setup.local:"
grep -E '^_lxml|^_imaging' Modules/Setup.local || echo "(no active entries?)"

echo ""
echo "=== Step 2: Remove stale configure artifacts ==="
rm -f .nanvix-configured

echo ""
echo "=== Step 3: Sync updated build-pptx-deps.sh from Windows ==="
cp /mnt/a/Repos/NanVix-CPython/nanvix-port/build-pptx-deps.sh nanvix-port/build-pptx-deps.sh
sed -i 's/\r$//' nanvix-port/build-pptx-deps.sh

echo ""
echo "=== Step 4: Build CPython with lxml ==="
export GH_TOKEN=$(gh auth token 2>/dev/null || true)
./z build 2>&1

echo ""
echo "=== Step 5: Source env and build ramfs ==="
source .nanvix/env.sh
make -f Makefile.nanvix CONFIG_NANVIX=y NANVIX_HOME="$NANVIX_HOME" ramfs 2>&1

echo ""
echo "=== Step 6: Copy artifacts ==="
if [ -f python.elf ]; then
  cp python.elf /mnt/a/Repos/NanVix/bin/python-pptx.elf
  echo "python.elf -> NanVix/bin/python-pptx.elf"
fi
if [ -f cpython-ramfs.img ]; then
  cp cpython-ramfs.img /mnt/a/Repos/NanVix/bin/cpython-pptx-ramfs.img
  echo "cpython-ramfs.img -> NanVix/bin/cpython-pptx-ramfs.img"
fi

echo ""
echo "=== Artifacts ==="
ls -lh /mnt/a/Repos/NanVix/bin/python-pptx.elf 2>/dev/null || echo "python-pptx.elf MISSING"
ls -lh /mnt/a/Repos/NanVix/bin/cpython-pptx-ramfs.img 2>/dev/null || echo "cpython-pptx-ramfs.img MISSING"
echo ""
echo "=== DONE ==="

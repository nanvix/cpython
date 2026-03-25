#!/bin/bash
set -euo pipefail

cd /tmp/cpython-build

echo "=== Rebuilding CPython with fixed TLS linker script ==="

# Force re-link by removing the old binary
rm -f python python.elf

# Rebuild (just the link step — sources are already compiled)
export GH_TOKEN=$(gh auth token 2>/dev/null || true)
./z build 2>&1 | tail -20

echo ""
echo "=== Checking ELF segments ==="
readelf -l python 2>/dev/null | head -20

echo ""
echo "=== TLS sections ==="
readelf -S python 2>/dev/null | grep -i "tls\|tbss\|tdata"

echo ""
echo "=== Copy to NanVix bin ==="
cp python /mnt/a/Repos/NanVix/bin/python-pptx.elf
ls -lh /mnt/a/Repos/NanVix/bin/python-pptx.elf

echo "=== DONE ==="

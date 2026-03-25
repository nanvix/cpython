#!/bin/bash
# run-pptx-build.sh — Sync fixes from Windows and run pptx-deps build in Docker
set -euo pipefail

SRC="/mnt/a/Repos/NanVix-CPython"
DST="/tmp/cpython-build"

echo "=== Syncing updated files from Windows ==="
cp "$SRC/nanvix-port/build-pptx-deps.sh" "$DST/nanvix-port/build-pptx-deps.sh"
cp "$SRC/nanvix-port/clean-xml-libs.sh" "$DST/nanvix-port/clean-xml-libs.sh"
# Fix CRLF from Windows checkout
sed -i 's/\r$//' "$DST/nanvix-port/build-pptx-deps.sh"
sed -i 's/\r$//' "$DST/nanvix-port/clean-xml-libs.sh"

echo "=== Removing stale lxml .a so Phase 4 re-runs ==="
NH="$DST/.nanvix/extracted/nanvix"
rm -f "$NH/lib/liblxml_etree.a" "$NH/lib/liblxml_elementpath.a"
rm -f "$DST/.nanvix/pptx-deps/build/lxml/lxml_etree.o"
rm -f "$DST/.nanvix/pptx-deps/build/lxml/lxml_elementpath.o"

echo "=== Running build-pptx-deps.sh in Docker ==="
DU=$(id -u)
DG=$(id -g)
docker run --rm --user "$DU:$DG" \
  -v "$DST":/mnt/workspace \
  -v "$NH":/mnt/sysroot \
  -w /mnt/workspace \
  -e HOME=/tmp \
  -e NANVIX_HOME=/mnt/sysroot \
  -e NANVIX_TOOLCHAIN=/opt/nanvix \
  nanvix/toolchain:latest-minimal \
  bash nanvix-port/build-pptx-deps.sh

echo "=== Verifying results ==="
echo "lxml libraries:"
ls -la "$NH/lib/liblxml"* 2>/dev/null || echo "  MISSING!"
echo "Schema macro:"
grep "LIBXML_SCHEMAS_ENABLED" "$NH/include/libxml2/libxml/xmlversion.h" 2>/dev/null || echo "  NOT FOUND!"
echo ""
echo "=== Done ==="

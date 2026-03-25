#!/bin/bash
# build-ramfs-direct.sh — Build ramfs image directly, bypassing Makefile dependencies
# Run this from WSL2 host (not inside Docker) — it orchestrates Docker as needed.
set -euo pipefail

cd /tmp/cpython-build

export NANVIX_HOME="/tmp/cpython-build/.nanvix/extracted/nanvix"
STAGING="/tmp/cpython-build/.nanvix/_ramfs_staging"
SYSROOT="${STAGING}/sysroot"
MKRAMFS="${NANVIX_HOME}/bin/mkramfs.elf"
SITE_PACKAGES="/tmp/cpython-build/.nanvix/pptx-deps/site-packages"
DU=$(id -u)
DG=$(id -g)

echo "=== Step 1: Clean staging and install via Docker ==="
rm -rf "${STAGING}"
docker run --rm --user "${DU}:${DG}" \
  -v /tmp/cpython-build:/mnt/workspace \
  -v "${NANVIX_HOME}":/mnt/sysroot \
  -w /mnt/workspace \
  -e HOME=/tmp \
  -e NANVIX_HOME=/mnt/sysroot \
  -e NANVIX_TOOLCHAIN=/opt/nanvix \
  nanvix/toolchain:latest-minimal \
  make install DESTDIR="/mnt/workspace/.nanvix/_ramfs_staging"

echo ""
echo "=== Step 2: Strip debug symbols via Docker ==="
docker run --rm --user "${DU}:${DG}" \
  -v /tmp/cpython-build:/mnt/workspace \
  -w /mnt/workspace \
  -e HOME=/tmp \
  nanvix/toolchain:latest-minimal \
  bash -c 'find /mnt/workspace/.nanvix/_ramfs_staging/sysroot -name "python3.*" -type f -executable \
    -exec /opt/nanvix/bin/i686-nanvix-strip --strip-debug {} \; 2>/dev/null || true'
echo "  Stripped"

echo ""
echo "=== Step 3: Aggressive stdlib trim ==="
find "${SYSROOT}" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "${SYSROOT}" -type d -name 'test' -path '*/python3.12/*' -exec rm -rf {} + 2>/dev/null || true
find "${SYSROOT}" -type d -name 'tests' -path '*/python3.12/*' -exec rm -rf {} + 2>/dev/null || true
rm -rf "${SYSROOT}/lib/python3.12/idlelib" 2>/dev/null || true
rm -rf "${SYSROOT}/lib/python3.12/tkinter" 2>/dev/null || true
rm -rf "${SYSROOT}/lib/python3.12/ensurepip" 2>/dev/null || true
rm -rf "${SYSROOT}/lib/python3.12/lib2to3" 2>/dev/null || true
rm -rf "${SYSROOT}/lib/python3.12/distutils" 2>/dev/null || true
rm -rf "${SYSROOT}/lib/python3.12/unittest" 2>/dev/null || true
rm -rf "${SYSROOT}/lib/python3.12/turtledemo" 2>/dev/null || true
rm -rf "${SYSROOT}/lib/python3.12/pydoc_data" 2>/dev/null || true
rm -rf "${SYSROOT}/lib/python3.12/lib-dynload" 2>/dev/null || true
find "${SYSROOT}" -type d -name 'config-3.12-*' -exec rm -rf {} + 2>/dev/null || true
find "${SYSROOT}" -name '*.pyc' -delete 2>/dev/null || true
find "${SYSROOT}" -name '*.pyo' -delete 2>/dev/null || true
find "${SYSROOT}" -name '*.so' -delete 2>/dev/null || true
rm -rf "${SYSROOT}/share" 2>/dev/null || true
rm -rf "${SYSROOT}/lib/pkgconfig" 2>/dev/null || true
rm -rf "${SYSROOT}/bin" 2>/dev/null || true
rm -f "${SYSROOT}/lib/libpython3.12.a" 2>/dev/null || true
file_count=$(find "${SYSROOT}" -type f | wc -l)
dir_size=$(du -sh "${SYSROOT}" 2>/dev/null | cut -f1)
echo "  Trimmed: ${file_count} files, ${dir_size}"

echo ""
echo "=== Step 4: Add site-packages (lxml, pptx, PIL) ==="
DEST="${SYSROOT}/lib/python3.12/site-packages"
mkdir -p "${DEST}"
cp -r "${SITE_PACKAGES}/lxml" "${DEST}/" && echo "  lxml: $(find "${DEST}/lxml" -name '*.py' | wc -l) files"
cp -r "${SITE_PACKAGES}/pptx" "${DEST}/" && echo "  pptx: $(find "${DEST}/pptx" -name '*.py' | wc -l) files"
cp -r "${SITE_PACKAGES}/PIL" "${DEST}/" && echo "  PIL: $(find "${DEST}/PIL" -name '*.py' | wc -l) files"

echo ""
echo "=== Step 5: Final stats ==="
total_files=$(find "${SYSROOT}" -type f | wc -l)
total_size=$(du -sh "${SYSROOT}" 2>/dev/null | cut -f1)
echo "  Total: ${total_files} files, ${total_size}"

echo ""
echo "=== Step 6: Strip python.elf ==="
docker run --rm --user "${DU}:${DG}" \
  -v /tmp/cpython-build:/mnt/workspace \
  -w /mnt/workspace \
  -e HOME=/tmp \
  nanvix/toolchain:latest-minimal \
  /opt/nanvix/bin/i686-nanvix-strip --strip-debug python.elf
ls -lh python.elf

echo ""
echo "=== Step 7: Create FAT32 image ==="
"${MKRAMFS}" -o /tmp/cpython-build/cpython-ramfs.img "${SYSROOT}"
ls -lh /tmp/cpython-build/cpython-ramfs.img

echo ""
echo "=== Step 8: Copy artifacts to NanVix bin ==="
cp /tmp/cpython-build/python.elf /mnt/a/Repos/NanVix/bin/python-pptx.elf
cp /tmp/cpython-build/cpython-ramfs.img /mnt/a/Repos/NanVix/bin/cpython-pptx-ramfs.img
ls -lh /mnt/a/Repos/NanVix/bin/python-pptx.elf /mnt/a/Repos/NanVix/bin/cpython-pptx-ramfs.img

echo ""
echo "=== DONE ==="

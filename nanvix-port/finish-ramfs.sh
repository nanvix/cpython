#!/bin/bash
set -euo pipefail
cd /tmp/cpython-build

STAGING="/tmp/cpython-build/.nanvix/_ramfs_staging"
SYSROOT="${STAGING}/sysroot"
MKRAMFS="/tmp/cpython-build/.nanvix/extracted/nanvix/bin/mkramfs.elf"
SITE_PACKAGES="/tmp/cpython-build/.nanvix/pptx-deps/site-packages"

echo "=== Before trim ==="
find "${SYSROOT}" -type f | wc -l
du -sh "${SYSROOT}"

echo "=== Trimming ==="
find "${SYSROOT}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "${SYSROOT}" -type d -name "test" -path "*/python3.12/*" -exec rm -rf {} + 2>/dev/null || true
find "${SYSROOT}" -type d -name "tests" -path "*/python3.12/*" -exec rm -rf {} + 2>/dev/null || true
for d in idlelib tkinter ensurepip lib2to3 distutils unittest turtledemo pydoc_data lib-dynload; do
  rm -rf "${SYSROOT}/lib/python3.12/${d}" 2>/dev/null || true
done
find "${SYSROOT}" -type d -name "config-3.12-*" -exec rm -rf {} + 2>/dev/null || true
find "${SYSROOT}" -name "*.pyc" -delete 2>/dev/null || true
find "${SYSROOT}" -name "*.pyo" -delete 2>/dev/null || true
find "${SYSROOT}" -name "*.so" -delete 2>/dev/null || true
rm -rf "${SYSROOT}/share" "${SYSROOT}/lib/pkgconfig" "${SYSROOT}/bin" 2>/dev/null || true
rm -f "${SYSROOT}/lib/libpython3.12.a" 2>/dev/null || true

echo "=== After trim ==="
find "${SYSROOT}" -type f | wc -l
du -sh "${SYSROOT}"

echo "=== Adding site-packages ==="
DEST="${SYSROOT}/lib/python3.12/site-packages"
mkdir -p "${DEST}"
cp -r "${SITE_PACKAGES}/lxml" "${DEST}/"
cp -r "${SITE_PACKAGES}/pptx" "${DEST}/"
cp -r "${SITE_PACKAGES}/PIL" "${DEST}/"
echo "lxml: $(find "${DEST}/lxml" -name "*.py" | wc -l) files"
echo "pptx: $(find "${DEST}/pptx" -name "*.py" | wc -l) files"
echo "PIL: $(find "${DEST}/PIL" -name "*.py" | wc -l) files"

echo "=== Final stats ==="
find "${SYSROOT}" -type f | wc -l
du -sh "${SYSROOT}"

echo "=== Creating FAT32 image ==="
"${MKRAMFS}" -o /tmp/cpython-build/cpython-ramfs.img "${SYSROOT}"
ls -lh /tmp/cpython-build/cpython-ramfs.img

echo "=== Copying artifacts ==="
cp /tmp/cpython-build/python.elf /mnt/a/Repos/NanVix/bin/python-pptx.elf
cp /tmp/cpython-build/cpython-ramfs.img /mnt/a/Repos/NanVix/bin/cpython-pptx-ramfs.img
ls -lh /mnt/a/Repos/NanVix/bin/python-pptx.elf /mnt/a/Repos/NanVix/bin/cpython-pptx-ramfs.img
echo "=== DONE ==="

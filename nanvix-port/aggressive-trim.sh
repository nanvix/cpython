#!/bin/bash
# aggressive-trim.sh — Trim ramfs staging to fit under 128MB VM memory
set -euo pipefail

SYSROOT="/tmp/cpython-build/.nanvix/_ramfs_staging/sysroot"
PYLIB="${SYSROOT}/lib/python3.12"

echo "=== Before aggressive trim ==="
du -sh "${SYSROOT}"
find "${SYSROOT}" -type f | wc -l

# The big one: config-3.12/ is 47MB of build config files — totally unnecessary at runtime
rm -rf "${PYLIB}/config-3.12"
find "${SYSROOT}" -type d -name 'config-3.12-*' -exec rm -rf {} + 2>/dev/null || true

# Modules not needed for python-pptx on NanVix
rm -rf "${PYLIB}/asyncio"         # async — not used by pptx
rm -rf "${PYLIB}/multiprocessing" # no multiprocessing on NanVix
rm -rf "${PYLIB}/concurrent"      # concurrent futures — not needed
rm -rf "${PYLIB}/email"           # email — not needed
rm -rf "${PYLIB}/http"            # http — no networking
rm -rf "${PYLIB}/urllib"          # urllib — no networking
rm -rf "${PYLIB}/xmlrpc"          # xmlrpc — no networking
rm -rf "${PYLIB}/wsgiref"         # WSGI — no web server
rm -rf "${PYLIB}/ctypes"          # dynamic loading — not available
rm -rf "${PYLIB}/curses"          # terminal UI — no terminal
rm -rf "${PYLIB}/venv"            # virtual envs — not needed
rm -rf "${PYLIB}/dbm"             # database — not needed
rm -rf "${PYLIB}/sqlite3"         # sqlite — not needed
rm -rf "${PYLIB}/zoneinfo"        # timezone data — not needed

# Large standalone files not needed for pptx
rm -f "${PYLIB}/turtle.py"        # turtle graphics
rm -f "${PYLIB}/pydoc.py"         # documentation browser
rm -f "${PYLIB}/doctest.py"       # doctest framework
rm -f "${PYLIB}/pickletools.py"   # pickle debugging
rm -f "${PYLIB}/tarfile.py"       # tar archives — not needed
rm -f "${PYLIB}/_pyio.py"         # pure-Python I/O fallback
rm -f "${PYLIB}/_pydecimal.py"    # pure-Python decimal fallback (C version is built-in)

# Remove .h and .a files (shouldn't be in ramfs)
find "${SYSROOT}" -name '*.h' -delete 2>/dev/null || true
find "${SYSROOT}" -name '*.a' -delete 2>/dev/null || true

# Remove bin/ (python binary loaded separately)
rm -rf "${SYSROOT}/bin" 2>/dev/null || true
# Remove share/ (man pages)
rm -rf "${SYSROOT}/share" 2>/dev/null || true
# Remove pkgconfig
rm -rf "${SYSROOT}/lib/pkgconfig" 2>/dev/null || true
# Remove include/ if any
rm -rf "${SYSROOT}/include" 2>/dev/null || true

# Remove lxml sub-packages not needed by python-pptx
# pptx only uses lxml.etree — not html, isoschematron
rm -rf "${PYLIB}/site-packages/lxml/html" 2>/dev/null || true
rm -rf "${PYLIB}/site-packages/lxml/isoschematron" 2>/dev/null || true
rm -rf "${PYLIB}/site-packages/lxml/includes" 2>/dev/null || true

# PIL: remove large modules python-pptx doesn't use
# pptx uses PIL.Image for image handling — keep core but remove extras
for f in ImageDraw ImageFont ImageFilter ImageEnhance ImageChops ImageOps \
         ImageStat ImageSequence ImagePath ImageMorph ImageMath ImageGrab \
         ImageFile2 PSDraw PcfFontFile BdfFontFile FontFile MspImagePlugin \
         QoiImagePlugin SpiderImagePlugin SunImagePlugin TgaImagePlugin \
         WalImageFile XVThumbImagePlugin XpmImagePlugin; do
  rm -f "${PYLIB}/site-packages/PIL/${f}.py" 2>/dev/null || true
done

echo "=== After aggressive trim ==="
du -sh "${SYSROOT}"
find "${SYSROOT}" -type f | wc -l

echo ""
echo "=== Remaining directories ==="
du -sh "${PYLIB}"/*/ 2>/dev/null | sort -rh | head -15
echo ""
echo "=== Site packages ==="
du -sh "${PYLIB}/site-packages"/*/ 2>/dev/null | sort -rh

echo ""
echo "=== Rebuild FAT32 image ==="
MKRAMFS="/tmp/cpython-build/.nanvix/extracted/nanvix/bin/mkramfs.elf"
"${MKRAMFS}" -o /tmp/cpython-build/cpython-ramfs.img "${SYSROOT}"
ls -lh /tmp/cpython-build/cpython-ramfs.img

echo ""
echo "=== Copy artifacts ==="
cp /tmp/cpython-build/cpython-ramfs.img /mnt/a/Repos/NanVix/bin/cpython-pptx-ramfs.img
cp /tmp/cpython-build/python.elf /mnt/a/Repos/NanVix/bin/python-pptx.elf
ls -lh /mnt/a/Repos/NanVix/bin/python-pptx.elf /mnt/a/Repos/NanVix/bin/cpython-pptx-ramfs.img
echo ""
echo "=== DONE ==="

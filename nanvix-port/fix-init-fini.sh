#!/bin/bash
set -euo pipefail

cd /tmp/cpython-build

# Sync updated stubs.c
cp /mnt/a/Repos/NanVix-CPython/nanvix-port/stubs.c nanvix-port/stubs.c
sed -i 's/\r$//' nanvix-port/stubs.c

NH="/tmp/cpython-build/.nanvix/extracted/nanvix"
DU=$(id -u)
DG=$(id -g)

echo "=== Step 1: Rebuild stubs in Docker ==="
docker run --rm --user "${DU}:${DG}" \
  -v /tmp/cpython-build:/mnt/workspace \
  -v "${NH}":/mnt/sysroot \
  -w /mnt/workspace \
  -e HOME=/tmp \
  -e NANVIX_HOME=/mnt/sysroot \
  -e NANVIX_TOOLCHAIN=/opt/nanvix \
  nanvix/toolchain:latest-minimal \
  bash -c '
    CC=/opt/nanvix/bin/i686-nanvix-gcc
    AR=/opt/nanvix/bin/i686-nanvix-ar
    RANLIB=/opt/nanvix/bin/i686-nanvix-ranlib
    CFLAGS="-m32 -march=pentiumpro -Os -fdata-sections -ffunction-sections -I/mnt/sysroot/include"

    echo "Compiling stubs.c..."
    ${CC} ${CFLAGS} -c /mnt/workspace/nanvix-port/stubs.c -o /tmp/stubs.o
    ${AR} rcs /mnt/sysroot/lib/libnanvix_stubs.a /tmp/stubs.o
    ${RANLIB} /mnt/sysroot/lib/libnanvix_stubs.a

    echo "Checking .init/.fini content in stubs..."
    /opt/nanvix/bin/i686-nanvix-objdump -d /tmp/stubs.o | grep -A2 ".init\|.fini"
    echo "Done"
  '

echo ""
echo "=== Step 2: Re-link CPython ==="
rm -f python python.elf
./z build 2>&1 | tail -5

echo ""
echo "=== Step 3: Verify .init/.fini in new binary ==="
docker run --rm --user "${DU}:${DG}" \
  -v /tmp/cpython-build:/mnt/workspace \
  -w /mnt/workspace \
  -e HOME=/tmp \
  nanvix/toolchain:latest-minimal \
  bash -c '
    echo "Sections:"
    /opt/nanvix/bin/i686-nanvix-readelf -S /mnt/workspace/python.elf | grep -E "\.init|\.fini"
    echo ""
    echo "Disasm at _init/_fini:"
    /opt/nanvix/bin/i686-nanvix-objdump -d /mnt/workspace/python.elf --start-address=0x4081c1eb --stop-address=0x4081c200 2>/dev/null || true
  '

echo ""
echo "=== Step 4: Copy to NanVix bin ==="
cp python.elf /mnt/a/Repos/NanVix/bin/python-pptx.elf
ls -lh /mnt/a/Repos/NanVix/bin/python-pptx.elf
echo "=== DONE ==="

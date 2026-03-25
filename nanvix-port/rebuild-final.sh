#!/bin/bash
set -euo pipefail
cd /tmp/cpython-build

NH="/tmp/cpython-build/.nanvix/extracted/nanvix"

# 1. Sync stubs (no .init/.fini asm)
cp /mnt/a/Repos/NanVix-CPython/nanvix-port/stubs.c nanvix-port/stubs.c
sed -i 's/\r$//' nanvix-port/stubs.c

# 2. Rebuild stubs
docker run --rm --user "$(id -u):$(id -g)" \
  -v /tmp/cpython-build:/mnt/workspace \
  -v "${NH}":/mnt/sysroot \
  -w /mnt/workspace \
  -e HOME=/tmp -e NANVIX_HOME=/mnt/sysroot -e NANVIX_TOOLCHAIN=/opt/nanvix \
  nanvix/toolchain:latest-minimal \
  bash -c '
    /opt/nanvix/bin/i686-nanvix-gcc -m32 -march=pentiumpro -Os -fdata-sections -ffunction-sections -I/mnt/sysroot/include \
      -c /mnt/workspace/nanvix-port/stubs.c -o /tmp/stubs.o
    /opt/nanvix/bin/i686-nanvix-ar rcs /mnt/sysroot/lib/libnanvix_stubs.a /tmp/stubs.o
    /opt/nanvix/bin/i686-nanvix-ranlib /mnt/sysroot/lib/libnanvix_stubs.a
    echo "stubs rebuilt (no .init/.fini asm)"
  '

# 3. Re-link
rm -f python python.elf
./z build 2>&1 | tail -3

# 4. Strip
docker run --rm --user "$(id -u):$(id -g)" \
  -v /tmp/cpython-build:/mnt/workspace -w /mnt/workspace -e HOME=/tmp \
  nanvix/toolchain:latest-minimal \
  /opt/nanvix/bin/i686-nanvix-strip --strip-debug /mnt/workspace/python.elf 2>&1

# 5. Verify _init
echo "=== _init disasm ==="
docker run --rm -v /tmp/cpython-build:/mnt/workspace -w /mnt/workspace -e HOME=/tmp \
  nanvix/toolchain:latest-minimal \
  /opt/nanvix/bin/i686-nanvix-objdump -d /mnt/workspace/python.elf --start-address=0x4000000b --stop-address=0x40000030 2>/dev/null

# 6. Copy
cp python.elf /mnt/a/Repos/NanVix/bin/python-pptx.elf
ls -lh /mnt/a/Repos/NanVix/bin/python-pptx.elf
echo "=== DONE ==="

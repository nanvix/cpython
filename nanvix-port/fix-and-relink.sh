#!/bin/bash
# fix-and-relink.sh — Apply council-recommended fixes and re-link CPython.
#
# Fixes applied:
# 1. Add __register_frame_info/__deregister_frame_info stubs (makes CRT .init safe)
# 2. Restore normal CRT .init/.fini (remove BYTE(0xc3) stubs + .init DISCARD)
# 3. Add .init_array/.fini_array to /DISCARD/ (safety)
# 4. Re-link python.elf
set -euo pipefail

cd /tmp/cpython-build

echo "=== Step 1: Copy updated stubs.c from repo ==="
cp /mnt/a/Repos/NanVix-CPython/nanvix-port/stubs.c nanvix-port/stubs.c
sed -i 's/\r$//' nanvix-port/stubs.c

NH="/tmp/cpython-build/.nanvix/extracted/nanvix"
DU=$(id -u)
DG=$(id -g)

echo "=== Step 2: Rebuild stubs + fix linker script + re-link ==="
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
    READELF=/opt/nanvix/bin/i686-nanvix-readelf
    OBJDUMP=/opt/nanvix/bin/i686-nanvix-objdump
    CFLAGS="-m32 -march=pentiumpro -Os -fdata-sections -ffunction-sections -I/mnt/sysroot/include"

    LDSCRIPT="/mnt/sysroot/lib/user.ld"

    echo "--- 2a: Recompile stubs.c ---"
    ${CC} ${CFLAGS} -c /mnt/workspace/nanvix-port/stubs.c -o /tmp/stubs.o
    ${AR} rcs /mnt/sysroot/lib/libnanvix_stubs.a /tmp/stubs.o
    ${RANLIB} /mnt/sysroot/lib/libnanvix_stubs.a
    echo "  Symbols in stubs:"
    /opt/nanvix/bin/i686-nanvix-nm /tmp/stubs.o | grep -E "register_frame|BeforeFork"

    echo ""
    echo "--- 2b: Fix user.ld — restore CRT .init/.fini ---"
    echo "  Before fix:"
    grep -nE "init|fini|DISCARD" ${LDSCRIPT}

    # Write a fresh user.ld with CRT .init/.fini restored
    cat > ${LDSCRIPT} << "LDEOF"
/*
 * Copyright(c) 2011-2024 The Maintainers of Nanvix.
 * Licensed under the MIT License.
 */

OUTPUT_FORMAT("elf32-i386")
ENTRY(_do_start)

PAGE_SIZE = 0x1000;
BASE_ADDR = 0x40000000;

SECTIONS
{
    . = BASE_ADDR;

    /* Text section. */
    .text : ALIGN(PAGE_SIZE)
    {
        *(.crt0*)
        *(.text*)
    }

    /* CRT .init/.fini — kept for safe CRT startup code.
     * __register_frame_info/__deregister_frame_info are stubbed in
     * libnanvix_stubs.a, so frame_dummy calls are safe (no-op). */
    .init : ALIGN(4)
    {
        KEEP(*(.init))
    }

    .fini : ALIGN(4)
    {
        KEEP(*(.fini))
    }

    /* Initialized data section. */
    .data : ALIGN(PAGE_SIZE)
    {
        *(.data*)
    }

    /* Uninitialized data section. */
    .bss :
    {
        *(.bss*)
    }

    /* Read-only data section. */
    .rodata : ALIGN(PAGE_SIZE)
    {
        *(.rodata*)
    }

    /* Dynamic symbol table. */
    .dynsym : ALIGN(4)
    {
        PROVIDE(__dynsym_start = .);
        *(.dynsym)
        PROVIDE(__dynsym_end = .);
    }

    .dynstr : ALIGN(4)
    {
        PROVIDE(__dynstr_start = .);
        *(.dynstr)
        PROVIDE(__dynstr_end = .);
    }

    .hash : ALIGN(4)
    {
        *(.hash)
        *(.gnu.hash)
    }

    .eh_frame_hdr : ALIGN(4)
    {
        PROVIDE(__eh_frame_hdr_start = .);
        KEEP(*(.eh_frame_hdr))
        PROVIDE(__eh_frame_hdr_end = .);
    }

    .eh_frame : ALIGN(4)
    {
        PROVIDE(__eh_frame_start = .);
        KEEP(*(.eh_frame))
        PROVIDE(__eh_frame_end = .);
    }

    /*
     * Thread-local storage.
     */
    .tls : ALIGN(PAGE_SIZE)
    {
        __TLS_START = .;
        *(.tdata .tdata.*)
        *(.tbss .tbss.*)
        __TLS_END = .;
    }

    .tls_init ADDR(.tls) : AT(ADDR(.tls))
    {
        FILL(0x00000000);
        . = __TLS_END;
    }

    /* Discard: .ctors/.dtors (empty sentinels only), .init_array/.fini_array
     * (modern GCC constructors — not needed on NanVix, c_trampoline handles
     * _init/_fini), and metadata sections. */
    /DISCARD/ :
    {
        *(.ctors)
        *(.dtors)
        *(.init_array*)
        *(.fini_array*)
        *(.comment)
        *(.note)
    }
}
LDEOF

    echo "  After fix:"
    grep -nE "init|fini|DISCARD" ${LDSCRIPT}

    echo ""
    echo "--- 2c: Verify .init/.fini in object files ---"
    echo "  crti.o:"
    ${READELF} -S /opt/nanvix/i686-nanvix/lib/crti.o 2>/dev/null | grep -E "init|fini" || echo "  (none)"
    echo "  crtn.o:"
    ${READELF} -S /opt/nanvix/i686-nanvix/lib/crtn.o 2>/dev/null | grep -E "init|fini" || echo "  (none)"
    echo "  crtbegin.o:"
    ${READELF} -S /opt/nanvix/lib/gcc/i686-nanvix/12.2.0/crtbegin.o 2>/dev/null | grep -E "init|fini" || echo "  (none)"
  '

echo ""
echo "=== Step 3: Re-link CPython ==="
rm -f python python.elf
./z build 2>&1 | tail -30 || echo "BUILD MIGHT HAVE ISSUES"

echo ""
echo "=== Step 4: Verify new binary ==="
docker run --rm --user "${DU}:${DG}" \
  -v /tmp/cpython-build:/mnt/workspace:ro \
  -e HOME=/tmp \
  nanvix/toolchain:latest-minimal \
  bash -c '
    echo "--- Section headers ---"
    /opt/nanvix/bin/i686-nanvix-readelf -S /mnt/workspace/python.elf 2>/dev/null | grep -E "\.init|\.fini|\.ctors|\.dtors|init_arr|fini_arr|\.text|\.data|\.bss|\.tls"
    echo ""
    echo "--- .init disassembly ---"
    /opt/nanvix/bin/i686-nanvix-objdump -d -j .init /mnt/workspace/python.elf 2>/dev/null
    echo ""
    echo "--- Program headers ---"
    /opt/nanvix/bin/i686-nanvix-readelf -l /mnt/workspace/python.elf 2>/dev/null
    echo ""
    echo "--- Binary size ---"
    ls -lh /mnt/workspace/python.elf
    echo ""
    echo "--- Module count ---"
    /opt/nanvix/bin/i686-nanvix-nm /mnt/workspace/python.elf 2>/dev/null | grep "T PyInit_" | wc -l
  '

echo ""
echo "=== Step 5: Copy to NanVix bin ==="
cp python.elf /mnt/a/Repos/NanVix/bin/python-pptx.elf 2>/dev/null || echo "Copy to NanVix/bin failed (not critical)"
ls -lh /mnt/a/Repos/NanVix/bin/python-pptx.elf 2>/dev/null || true

echo "=== DONE ==="

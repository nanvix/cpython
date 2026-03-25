#!/bin/bash
# write-fixed-ld.sh — Write the council-recommended linker script
set -euo pipefail

LDSCRIPT="/tmp/cpython-build/.nanvix/extracted/nanvix/lib/user.ld"

cat > "${LDSCRIPT}" << 'LDEOF'
/*
 * Copyright(c) 2011-2024 The Maintainers of Nanvix.
 * Licensed under the MIT License.
 */

OUTPUT_FORMAT("elf32-i386")
ENTRY(_do_start)

/*
 * Page Size (4 KB)
 */
PAGE_SIZE = 0x1000;

/*
 * Base Address
 */
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

    /*
     * _init / _fini safe stubs.
     *
     * The NanVix CRT c_trampoline calls _init() before main() and _fini() after.
     * With --gc-sections, the CRT .init/.fini input sections may be discarded,
     * leaving _init/_fini pointing to empty addresses that fall through into .data.
     *
     * We define _init and _fini as explicit symbols pointing to a single ret (0xC3)
     * instruction. All CRT .init/.fini input sections are discarded below so that
     * crtbegin.o's frame_dummy / __do_global_ctors_aux (which call NULL function
     * pointers on NanVix) are never included.
     */
    .init : { _init = .; BYTE(0xc3); }
    .fini : { _fini = .; BYTE(0xc3); }

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

    /* Dynamic symbol table (populated by --export-dynamic). */
    .dynsym : ALIGN(4)
    {
        PROVIDE(__dynsym_start = .);
        *(.dynsym)
        PROVIDE(__dynsym_end = .);
    }

    /* Dynamic string table (symbol names for .dynsym). */
    .dynstr : ALIGN(4)
    {
        PROVIDE(__dynstr_start = .);
        *(.dynstr)
        PROVIDE(__dynstr_end = .);
    }

    /* Symbol hash table. */
    .hash : ALIGN(4)
    {
        *(.hash)
        *(.gnu.hash)
    }

    /* Exception handling frame header */
    .eh_frame_hdr : ALIGN(4)
    {
        PROVIDE(__eh_frame_hdr_start = .);
        KEEP(*(.eh_frame_hdr))
        PROVIDE(__eh_frame_hdr_end = .);
    }

    /* Exception handling frames */
    .eh_frame : ALIGN(4)
    {
        PROVIDE(__eh_frame_start = .);
        KEEP(*(.eh_frame))
        PROVIDE(__eh_frame_end = .);
    }

    /*
     * Thread-local storage.
     *
     * Must appear after all PROGBITS sections (.eh_frame, etc.) so that the NOBITS .tbss
     * sub-section does not cause virtual-address (VMA) overlap with subsequent PROGBITS sections.
     */
    .tls : ALIGN(PAGE_SIZE)
    {
        __TLS_START = .;
        *(.tdata .tdata.*)
        *(.tbss .tbss.*)
        __TLS_END = .;
    }

    /*
     * PROGBITS companion for .tls.
     *
     * Because .tbss is NOBITS it does not produce a LOAD segment.  The TDA allocator (tda.rs)
     * copies __TLS_START..__TLS_END into each new thread, so the kernel must have allocated and
     * zero-filled the pages backing that range.  This zero-filled PROGBITS section creates a LOAD
     * segment that covers the .tbss region, causing the ELF loader to map and clear those pages.
     */
    .tls_init ADDR(.tls) : AT(ADDR(.tls))
    {
        FILL(0x00000000);
        . = __TLS_END;
    }

    /* Discarded — CRT .init/.fini (replaced by stubs above), comments, notes. */
    /DISCARD/ :
    {
        *(.init)
        *(.fini)
        *(.ctors)
        *(.dtors)
        *(.comment)
        *(.note)
    }
}
LDEOF

echo "=== Linker script written ==="
echo "Key sections:"
grep -n "init\|fini\|DISCARD\|tdata\|tbss\|tls" "${LDSCRIPT}" | head -20

#!/bin/bash
# write-fixed-ld-v2.sh — Place _init/_fini inside .text to preserve segment separation
set -euo pipefail

LDSCRIPT="/tmp/cpython-build/.nanvix/extracted/nanvix/lib/user.ld"

cat > "${LDSCRIPT}" << 'LDEOF'
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

        /*
         * _init/_fini stubs at end of .text.
         *
         * c_trampoline calls _init before main and _fini after. CRT input
         * .init/.fini sections are discarded (they contain frame_dummy and
         * __do_global_ctors_aux which call NULL function pointers on NanVix).
         * These single-byte ret instructions ensure safe return.
         *
         * Placed inside .text (not as separate sections) to preserve the
         * text/data LOAD segment boundary — separate sections would merge
         * .text and .data into one RWE segment.
         */
        _init = .;
        BYTE(0xc3);
        _fini = .;
        BYTE(0xc3);
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

    /* Discard CRT .init/.fini (replaced by stubs above), constructors, notes. */
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

echo "Written. Verifying key layout:"
grep -n "_init\|_fini\|\.data\|\.text\|DISCARD\|\.tls" "${LDSCRIPT}" | head -15

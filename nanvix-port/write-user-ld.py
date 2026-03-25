#!/usr/bin/env python3
"""Write fixed user.ld for the NanVix CPython build."""
import sys

ld = r"""OUTPUT_FORMAT("elf32-i386")
ENTRY(_do_start)
PAGE_SIZE = 0x1000;
BASE_ADDR = 0x40000000;
SECTIONS
{
    . = BASE_ADDR;
    .text : ALIGN(PAGE_SIZE) { *(.crt0*) *(.text*) }
    .init : ALIGN(4) { KEEP(*(.init)) }
    .fini : ALIGN(4) { KEEP(*(.fini)) }
    .data : ALIGN(PAGE_SIZE) { *(.data*) }
    .got.plt : { *(.got.plt) }
    .ctors : ALIGN(4) { KEEP(*(.ctors)) }
    .dtors : ALIGN(4) { KEEP(*(.dtors)) }
    .bss : { *(.bss*) }
    .rodata : ALIGN(PAGE_SIZE) { *(.rodata*) }
    .dynsym : ALIGN(4) { PROVIDE(__dynsym_start = .); *(.dynsym) PROVIDE(__dynsym_end = .); }
    .dynstr : ALIGN(4) { PROVIDE(__dynstr_start = .); *(.dynstr) PROVIDE(__dynstr_end = .); }
    .hash : ALIGN(4) { *(.hash) *(.gnu.hash) }
    .eh_frame_hdr : ALIGN(4) { PROVIDE(__eh_frame_hdr_start = .); KEEP(*(.eh_frame_hdr)) PROVIDE(__eh_frame_hdr_end = .); }
    .eh_frame : ALIGN(4) { PROVIDE(__eh_frame_start = .); KEEP(*(.eh_frame)) PROVIDE(__eh_frame_end = .); }
    .tls : ALIGN(PAGE_SIZE) { __TLS_START = .; *(.tdata .tdata.*) *(.tbss .tbss.*) __TLS_END = .; }
    .tls_init ADDR(.tls) : AT(ADDR(.tls)) { FILL(0x00000000); . = __TLS_END; }
    /DISCARD/ : { *(.init_array*) *(.fini_array*) *(.comment) *(.note) }
}
"""

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/cpython-build/.nanvix/extracted/nanvix/lib/user.ld"
with open(path, 'w') as f:
    f.write(ld)
print(f"Wrote {len(ld)} bytes to {path}")

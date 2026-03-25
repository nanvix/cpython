#!/bin/bash
set -euo pipefail

ELF="/mnt/workspace/python.elf"
TOOL="/opt/nanvix/bin/i686-nanvix"

echo "=== Relocations ==="
${TOOL}-readelf -r "$ELF" 2>/dev/null | head -20

echo ""
echo "=== .ctors / .init_array sections ==="
${TOOL}-readelf -S "$ELF" 2>/dev/null | grep -iE "ctors|dtors|init_array|fini_array"

echo ""
echo "=== Hex dump at 0x4081d000 (first 64 bytes of .data) ==="
${TOOL}-objdump -s --start-address=0x4081d000 --stop-address=0x4081d040 "$ELF" 2>/dev/null

echo ""
echo "=== c_trampoline disassembly ==="
${TOOL}-objdump -d "$ELF" --start-address=0x40217a20 --stop-address=0x40217b80 2>/dev/null | head -40

echo ""
echo "=== relocate_pie_binary disassembly ==="
${TOOL}-objdump -d "$ELF" --start-address=0x40217e30 --stop-address=0x40218190 2>/dev/null | head -60

echo ""
echo "=== Symbols at exact 0x4081d000 ==="
${TOOL}-nm "$ELF" 2>/dev/null | grep "^4081d00[0-9a-f] "

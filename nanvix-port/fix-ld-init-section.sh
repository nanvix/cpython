#!/bin/bash
set -euo pipefail

LDSCRIPT="/tmp/cpython-build/.nanvix/extracted/nanvix/lib/user.ld"

# Remove previous attempts
sed -i '/BYTE(0xc3)/d' "${LDSCRIPT}"
sed -i '/KEEP(\*(.init))/d' "${LDSCRIPT}"
sed -i '/KEEP(\*(.fini))/d' "${LDSCRIPT}"

# Strategy: place .init and .fini as SEPARATE output sections after .text,
# each with BYTE(0xc3) as fallback content. The KEEP ensures they survive GC.
# The CRT's crti.o/crtn.o content goes first, then our ret as safety net.

# Find the line with .data : ALIGN and insert .init/.fini before it
sed -i '/^\.data : ALIGN/i\/* CRT .init/.fini sections — safety ret prevents fall-through to .data */\n.init : { KEEP(*(.init)) BYTE(0xc3) }\n.fini : { KEEP(*(.fini)) BYTE(0xc3) }' "${LDSCRIPT}"

echo "=== Result ==="
cat "${LDSCRIPT}" | head -45

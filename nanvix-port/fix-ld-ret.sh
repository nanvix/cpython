#!/bin/bash
set -euo pipefail

LDSCRIPT="/tmp/cpython-build/.nanvix/extracted/nanvix/lib/user.ld"

# Remove any KEEP(.init/.fini) we added
sed -i '/KEEP(\*(.init))/d' "${LDSCRIPT}"
sed -i '/KEEP(\*(.fini))/d' "${LDSCRIPT}"
# Remove any BYTE(0xc3) we might have added before
sed -i '/BYTE(0xc3)/d' "${LDSCRIPT}"

# Add safety ret byte after *(.text*) — prevents fall-through to .data
# if _init/_fini are GC'd (empty). When c_trampoline calls the empty
# _init symbol (which points to end of .text), it hits this ret.
sed -i 's|^\t\t\*(.text\*)|\t\t*(.text*)\n\t\tBYTE(0xc3) /* ret safety net for empty _init/_fini */|' "${LDSCRIPT}"

echo "=== .text section ==="
sed -n '/^\.text/,/^}/p' "${LDSCRIPT}"

#!/bin/bash
set -euo pipefail

LDSCRIPT="/tmp/cpython-build/.nanvix/extracted/nanvix/lib/user.ld"

echo "=== Current .text block ==="
sed -n '/^\.text/,/^}/p' "${LDSCRIPT}"

# Remove existing KEEP lines
sed -i '/KEEP(\*(.init))/d' "${LDSCRIPT}"
sed -i '/KEEP(\*(.fini))/d' "${LDSCRIPT}"

# Add KEEP(.init) and KEEP(.fini) AFTER *(.text*) — so they're at end of text,
# not before main. This way fall-through from empty init hits .fini's ret, not .data.
sed -i 's|^\t\t\*(.text\*)|\t\t*(.text*)\n\t\tKEEP(*(.init))\n\t\tKEEP(*(.fini))|' "${LDSCRIPT}"

echo "=== After fix ==="
sed -n '/^\.text/,/^}/p' "${LDSCRIPT}"

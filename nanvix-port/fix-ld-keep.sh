#!/bin/bash
set -euo pipefail

LDSCRIPT="/tmp/cpython-build/.nanvix/extracted/nanvix/lib/user.ld"

echo "=== Before ==="
grep -n "crt0\|\.text\|init\|fini" "${LDSCRIPT}" | head -10

# Replace the .text section to include KEEP(.init) and KEEP(.fini)
sed -i '/\*(.crt0\*)/a\\t\tKEEP(*(.init))' "${LDSCRIPT}"
sed -i '/\*(.text\*)/a\\t\tKEEP(*(.fini))' "${LDSCRIPT}"

echo ""
echo "=== After ==="
grep -n "crt0\|\.text\|init\|fini\|KEEP" "${LDSCRIPT}" | head -15

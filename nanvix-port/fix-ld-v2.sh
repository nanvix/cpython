#!/bin/bash
set -euo pipefail

LDSCRIPT="/tmp/cpython-build/.nanvix/extracted/nanvix/lib/user.ld"

# Insert .init and .fini output sections before .data
# Line 31 is ".data : ALIGN(PAGE_SIZE)" — insert before it
sed -i '31i\/* CRT init/fini — BYTE(0xc3) is a safety ret if sections are empty */\n.init : { KEEP(*(.init)) BYTE(0xc3) }\n.fini : { KEEP(*(.fini)) BYTE(0xc3) }' "${LDSCRIPT}"

echo "=== Lines 25-40 ==="
sed -n '25,40p' "${LDSCRIPT}"

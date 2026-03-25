#!/bin/bash
set -euo pipefail

LDSCRIPT="/tmp/cpython-build/.nanvix/extracted/nanvix/lib/user.ld"

echo "=== Before fix ==="
grep -n "tdata\|tbss" "$LDSCRIPT"
echo ""

# Fix: match subsections too
sed -i 's/\*(.tdata)/*(.tdata .tdata.*)/' "$LDSCRIPT"
sed -i 's/\*(.tbss)/*(.tbss .tbss.*)/' "$LDSCRIPT"

echo "=== After fix ==="
grep -n "tdata\|tbss" "$LDSCRIPT"

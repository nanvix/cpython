#!/bin/bash
# fix-init-discard.sh — Council-recommended fix: discard CRT .init/.fini,
# define _init/_fini as simple ret instructions in linker script.
set -euo pipefail

LDSCRIPT="/tmp/cpython-build/.nanvix/extracted/nanvix/lib/user.ld"

echo "=== Applying council fix to user.ld ==="

# Remove any previous attempts (KEEP, BYTE in .text, etc.)
sed -i '/KEEP(\*(.init))/d' "${LDSCRIPT}"
sed -i '/KEEP(\*(.fini))/d' "${LDSCRIPT}"
sed -i '/BYTE(0xc3)/d' "${LDSCRIPT}"
# Remove any previous .init/.fini output sections we added
sed -i '/^\.init : {/d' "${LDSCRIPT}"
sed -i '/^\.fini : {/d' "${LDSCRIPT}"
sed -i '/CRT init\/fini/d' "${LDSCRIPT}"
sed -i '/safety ret/d' "${LDSCRIPT}"

# Strategy: Add .init/.fini output sections with explicit _init/_fini symbols
# and a ret byte. Then DISCARD input .init/.fini from CRT objects.
# Place these between .text and .data.

# Insert before .data line
sed -i '/^\.data : ALIGN/i\/* _init/_fini: safe ret stubs — discards CRT crtbegin.o contributions */\n.init : { _init = .; BYTE(0xc3); }\n.fini : { _fini = .; BYTE(0xc3); }' "${LDSCRIPT}"

# Add /DISCARD/ for CRT .init/.fini input sections (append before closing brace)
# First check if /DISCARD/ already exists
if grep -q '/DISCARD/' "${LDSCRIPT}"; then
  # Add .init/.fini to existing discard
  sed -i 's|\*/DISCARD/|/DISCARD/|' "${LDSCRIPT}"
  # Just append to the existing block
  sed -i '/\/DISCARD\//s|{|{ *(.init) *(.fini) *(.ctors) *(.dtors)|' "${LDSCRIPT}"
else
  # Add new /DISCARD/ section before the closing brace of SECTIONS
  sed -i '/\/DISCARD\//,/}/d' "${LDSCRIPT}"
  # The existing DISCARD block handles .comment and .note — replace it
  echo "" >> "${LDSCRIPT}"
fi

echo "=== Result ==="
cat "${LDSCRIPT}"

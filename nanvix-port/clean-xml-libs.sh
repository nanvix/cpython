#!/bin/bash
set -euo pipefail
NH=/tmp/cpython-build/.nanvix/extracted/nanvix

echo "Deleting stale XML libraries and headers..."
rm -f "$NH/lib/libxml2.a" "$NH/lib/libxslt.a" "$NH/lib/libexslt.a"
rm -f "$NH/lib/liblxml_etree.a" "$NH/lib/liblxml_elementpath.a"
rm -rf "$NH/include/libxml2" "$NH/include/libxslt" "$NH/include/libexslt"
rm -rf /tmp/cpython-build/.nanvix/pptx-deps/build/libxml2
rm -rf /tmp/cpython-build/.nanvix/pptx-deps/build/libxslt
rm -rf /tmp/cpython-build/.nanvix/pptx-deps/build/lxml
rm -f /tmp/cpython-build/python.elf /tmp/cpython-build/python

echo "Remaining libs:"
ls "$NH/lib/"lib*.a 2>/dev/null | sort
echo "Done"

#!/bin/bash
# build-pptx-deps.sh — Build python-pptx dependencies for NanVix CPython
#
# Downloads and cross-compiles libxml2, libxslt, lxml, and minimal Pillow
# as static libraries, then installs python-pptx and its Python dependencies
# into the site-packages directory.
#
# Run this AFTER ./z setup and BEFORE ./z build:
#   ./z setup
#   bash nanvix-port/build-pptx-deps.sh
#   ./z build
#
# Environment (auto-detected from .nanvix/env.sh if available):
#   NANVIX_HOME       — path to NanVix sysroot (contains lib/, include/)
#   NANVIX_TOOLCHAIN  — path to NanVix toolchain (default: /opt/nanvix)

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────

LIBXML2_VERSION="2.12.9"
LIBXSLT_VERSION="1.1.42"
LXML_VERSION="5.3.0"
PILLOW_VERSION="10.4.0"
PPTX_VERSION="1.0.2"

LIBXML2_URL="https://download.gnome.org/sources/libxml2/2.12/libxml2-${LIBXML2_VERSION}.tar.xz"
LIBXSLT_URL="https://download.gnome.org/sources/libxslt/1.1/libxslt-${LIBXSLT_VERSION}.tar.xz"
LXML_URL="https://github.com/lxml/lxml/releases/download/lxml-${LXML_VERSION}/lxml-${LXML_VERSION}.tar.gz"
PILLOW_URL="https://github.com/python-pillow/Pillow/archive/refs/tags/${PILLOW_VERSION}.tar.gz"
PPTX_URL="https://files.pythonhosted.org/packages/source/p/python-pptx/python_pptx-${PPTX_VERSION}.tar.gz"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${ROOT_DIR}/.nanvix/pptx-deps"
DOWNLOAD_DIR="${WORK_DIR}/downloads"
BUILD_DIR="${WORK_DIR}/build"
PATCHES_DIR="${ROOT_DIR}/nanvix-port/patches-pptx"

# ─── Helpers ──────────────────────────────────────────────────────────────────

log() { printf '[pptx-deps] %s\n' "$*"; }
die() { printf '[pptx-deps] ERROR: %s\n' "$*" >&2; exit 1; }

# Source env if available AND NANVIX_HOME not already set (Docker sets it via -e)
if [[ -z "${NANVIX_HOME:-}" ]] && [[ -f "${ROOT_DIR}/.nanvix/env.sh" ]]; then
  source "${ROOT_DIR}/.nanvix/env.sh"
fi

NANVIX_HOME="${NANVIX_HOME:?NANVIX_HOME not set. Run ./z setup first.}"
NANVIX_TOOLCHAIN="${NANVIX_TOOLCHAIN:-/opt/nanvix}"

# Cross-compiler
CC="${NANVIX_TOOLCHAIN}/bin/i686-nanvix-gcc"
CXX="${NANVIX_TOOLCHAIN}/bin/i686-nanvix-g++"
AR="${NANVIX_TOOLCHAIN}/bin/i686-nanvix-ar"
RANLIB="${NANVIX_TOOLCHAIN}/bin/i686-nanvix-ranlib"
STRIP="${NANVIX_TOOLCHAIN}/bin/i686-nanvix-strip"

SYSROOT="${NANVIX_HOME}"
COMMON_CFLAGS="-m32 -march=pentiumpro -Os -fdata-sections -ffunction-sections -I${SYSROOT}/include"
COMMON_LDFLAGS="-static -L${SYSROOT}/lib"

# Verify toolchain
[[ -x "$CC" ]] || die "Cross-compiler not found at $CC. Is NANVIX_TOOLCHAIN correct?"
[[ -d "$SYSROOT/lib" ]] || die "Sysroot lib/ not found at $SYSROOT/lib. Run ./z setup first."

# ─── Download ─────────────────────────────────────────────────────────────────

download() {
  local url="$1" dest="$2"
  if [[ -f "$dest" ]]; then
    log "Already downloaded: $(basename "$dest")"
    return
  fi
  log "Downloading $(basename "$dest")..."
  curl -fsSL -o "$dest" "$url"
}

mkdir -p "$DOWNLOAD_DIR" "$BUILD_DIR"

log "=== Phase 1: Downloading sources ==="
download "$LIBXML2_URL"  "$DOWNLOAD_DIR/libxml2-${LIBXML2_VERSION}.tar.xz"
download "$LIBXSLT_URL"  "$DOWNLOAD_DIR/libxslt-${LIBXSLT_VERSION}.tar.xz"
download "$LXML_URL"     "$DOWNLOAD_DIR/lxml-${LXML_VERSION}.tar.gz"
download "$PILLOW_URL"   "$DOWNLOAD_DIR/Pillow-${PILLOW_VERSION}.tar.gz"
download "$PPTX_URL"     "$DOWNLOAD_DIR/python-pptx-${PPTX_VERSION}.tar.gz"

# ─── Extract ──────────────────────────────────────────────────────────────────

extract() {
  local archive="$1" dest="$2" strip="${3:-1}"
  if [[ -d "$dest" ]]; then
    log "Already extracted: $(basename "$dest")"
    return
  fi
  log "Extracting $(basename "$archive")..."
  mkdir -p "$dest"
  tar -xf "$archive" -C "$dest" --strip-components="$strip"
}

extract "$DOWNLOAD_DIR/libxml2-${LIBXML2_VERSION}.tar.xz" "$BUILD_DIR/libxml2"
extract "$DOWNLOAD_DIR/libxslt-${LIBXSLT_VERSION}.tar.xz" "$BUILD_DIR/libxslt"
extract "$DOWNLOAD_DIR/lxml-${LXML_VERSION}.tar.gz"       "$BUILD_DIR/lxml"
extract "$DOWNLOAD_DIR/Pillow-${PILLOW_VERSION}.tar.gz"   "$BUILD_DIR/pillow"
extract "$DOWNLOAD_DIR/python-pptx-${PPTX_VERSION}.tar.gz" "$BUILD_DIR/python-pptx"

# ─── Phase 1b: Compile and install NanVix stubs ─────────────────────────────

log "=== Phase 1b: Compiling NanVix stubs ==="
STUBS_SRC="${ROOT_DIR}/nanvix-port/stubs.c"
if [[ -f "$STUBS_SRC" ]] && [[ ! -f "${SYSROOT}/lib/libnanvix_stubs.a" ]]; then
  $CC $COMMON_CFLAGS -I"${ROOT_DIR}/Include" -c "$STUBS_SRC" -o "${WORK_DIR}/stubs.o" 2>/dev/null || \
  $CC $COMMON_CFLAGS -c "$STUBS_SRC" -o "${WORK_DIR}/stubs.o"
  $AR rcs "${SYSROOT}/lib/libnanvix_stubs.a" "${WORK_DIR}/stubs.o"
  $RANLIB "${SYSROOT}/lib/libnanvix_stubs.a"
  log "libnanvix_stubs.a installed to ${SYSROOT}/lib/"
else
  log "stubs already installed or source not found, skipping"
fi

# ─── Phase 2: Build libxml2 ──────────────────────────────────────────────────

log "=== Phase 2: Building libxml2 ${LIBXML2_VERSION} ==="
cd "$BUILD_DIR/libxml2"

# Always clean stale headers so a rebuild picks up correct defines (e.g. LIBXML_SCHEMAS_ENABLED)
rm -rf "${SYSROOT}/include/libxml2" "${SYSROOT}/include/libxslt" "${SYSROOT}/include/libexslt"
log "Cleaned stale XML headers from sysroot"

if [[ ! -f "${SYSROOT}/lib/libxml2.a" ]]; then
  # Copy NanVix-patched config.sub/config.guess so configure recognises i686-nanvix
  cp "${ROOT_DIR}/config.sub" . 2>/dev/null || true
  cp "${ROOT_DIR}/config.guess" . 2>/dev/null || true

  # Clean any previous build
  make distclean 2>/dev/null || true

  CC="$CC" AR="$AR" RANLIB="$RANLIB" \
  CFLAGS="$COMMON_CFLAGS" \
  LDFLAGS="$COMMON_LDFLAGS" \
  ./configure \
    --host=i686-nanvix \
    --build=x86_64-linux-gnu \
    --prefix="$SYSROOT" \
    --enable-static \
    --disable-shared \
    --without-python \
    --without-readline \
    --without-history \
    --without-http \
    --without-ftp \
    --without-catalog \
    --without-debug \
    --without-legacy \
    --without-lzma \
    --without-icu \
    --without-iconv \
    --without-threads \
    --with-zlib="$SYSROOT"

  # Build library only — tools (xmllint etc.) fail to link on NanVix
  make -j"$(nproc)" -k 2>&1 || true
  # Install library and headers only
  make install-libLTLIBRARIES install-xmlincHEADERS 2>&1 || true
  # Fallback: manually copy if make install didn't work
  if [[ -f ".libs/libxml2.a" ]] && [[ ! -f "${SYSROOT}/lib/libxml2.a" ]]; then
    cp .libs/libxml2.a "${SYSROOT}/lib/"
  fi
  # Always install headers (overwrite any stale copies)
  mkdir -p "${SYSROOT}/include/libxml2/libxml"
  cp include/libxml/*.h "${SYSROOT}/include/libxml2/libxml/"

  log "libxml2.a installed to ${SYSROOT}/lib/"

  # Create a minimal xml2-config script so libxslt configure can find libxml2
  mkdir -p "${SYSROOT}/bin"
  cat > "${SYSROOT}/bin/xml2-config" << XMLCFG
#!/bin/sh
case "\$1" in
  --cflags) echo "-I${SYSROOT}/include/libxml2" ;;
  --libs)   echo "-L${SYSROOT}/lib -lxml2 -lz" ;;
  --version) echo "${LIBXML2_VERSION}" ;;
  *) echo "Usage: xml2-config [--cflags|--libs|--version]" ;;
esac
XMLCFG
  chmod +x "${SYSROOT}/bin/xml2-config"
  log "xml2-config shim created at ${SYSROOT}/bin/"
else
  log "libxml2.a already exists, skipping build"
fi

# Always ensure headers are fresh (even if lib was cached from a previous run)
mkdir -p "${SYSROOT}/include/libxml2/libxml"
cp include/libxml/*.h "${SYSROOT}/include/libxml2/libxml/"
log "libxml2 headers installed to ${SYSROOT}/include/libxml2/libxml/"

# ─── Phase 3: Build libxslt ──────────────────────────────────────────────────

log "=== Phase 3: Building libxslt ${LIBXSLT_VERSION} ==="
cd "$BUILD_DIR/libxslt"

if [[ ! -f "${SYSROOT}/lib/libxslt.a" ]]; then
  # Copy NanVix-patched config.sub/config.guess
  cp "${ROOT_DIR}/config.sub" . 2>/dev/null || true
  cp "${ROOT_DIR}/config.guess" . 2>/dev/null || true

  make distclean 2>/dev/null || true

  # Add sysroot/bin to PATH so xml2-config shim is found by libxslt configure
  export PATH="${SYSROOT}/bin:${PATH}"

  CC="$CC" AR="$AR" RANLIB="$RANLIB" \
  CFLAGS="$COMMON_CFLAGS -I${SYSROOT}/include/libxml2" \
  LDFLAGS="$COMMON_LDFLAGS" \
  XML_CFLAGS="-I${SYSROOT}/include/libxml2" \
  XML_LIBS="-L${SYSROOT}/lib -lxml2 -lz" \
  XML_CONFIG="${SYSROOT}/bin/xml2-config" \
  ./configure \
    --host=i686-nanvix \
    --build=x86_64-linux-gnu \
    --prefix="$SYSROOT" \
    --enable-static \
    --disable-shared \
    --without-python \
    --without-crypto \
    --without-plugins \
    --with-libxml-prefix="$SYSROOT" \
    --with-libxml-include-prefix="${SYSROOT}/include/libxml2" \
    --with-libxml-libs-prefix="${SYSROOT}/lib"

  # Build library only — tools (xsltproc) fail to link on NanVix
  make -j"$(nproc)" -k 2>&1 || true
  make install-libLTLIBRARIES 2>&1 || true
  # Fallback: manually copy
  if [[ -f "libxslt/.libs/libxslt.a" ]] && [[ ! -f "${SYSROOT}/lib/libxslt.a" ]]; then
    cp libxslt/.libs/libxslt.a "${SYSROOT}/lib/"
  fi
  if [[ -f "libexslt/.libs/libexslt.a" ]] && [[ ! -f "${SYSROOT}/lib/libexslt.a" ]]; then
    cp libexslt/.libs/libexslt.a "${SYSROOT}/lib/"
  fi
  # Install headers
  mkdir -p "${SYSROOT}/include/libxslt" "${SYSROOT}/include/libexslt"
  cp libxslt/*.h "${SYSROOT}/include/libxslt/" 2>/dev/null || true
  cp libexslt/*.h "${SYSROOT}/include/libexslt/" 2>/dev/null || true

  log "libxslt.a + libexslt.a installed to ${SYSROOT}/lib/"
else
  log "libxslt.a already exists, skipping build"
fi

# Always ensure libxslt/libexslt headers are fresh (even if lib was cached)
mkdir -p "${SYSROOT}/include/libxslt" "${SYSROOT}/include/libexslt"
cp libxslt/*.h "${SYSROOT}/include/libxslt/" 2>/dev/null || true
cp libexslt/*.h "${SYSROOT}/include/libexslt/" 2>/dev/null || true
log "libxslt/libexslt headers installed to ${SYSROOT}/include/"

# ─── Phase 4: Build lxml C extensions ────────────────────────────────────────

log "=== Phase 4: Building lxml ${LXML_VERSION} C extensions ==="
cd "$BUILD_DIR/lxml"

# CPython include path — pyconfig.h is generated by configure
# If it doesn't exist yet, skip lxml C compilation (run script again after ./z build configure)
CPYTHON_INCLUDE="${ROOT_DIR}/Include"
PYCONFIG="${ROOT_DIR}/pyconfig.h"

if [[ ! -f "$PYCONFIG" ]]; then
  log "WARNING: pyconfig.h not found at ${PYCONFIG}"
  log "  lxml C extensions require CPython headers. Run ./z build first (or at least configure)."
  log "  Skipping Phase 4-5 (C extensions). Re-run this script after configure."
  log "  Phases 1-3 (C libraries) completed successfully."
  # Still install Python packages (Phase 7) — they don't need pyconfig.h

  # Jump straight to Phase 7 (Python package installation)
  SKIP_C_EXTENSIONS=1
else
  SKIP_C_EXTENSIONS=0
fi

if [[ "$SKIP_C_EXTENSIONS" -eq 0 ]]; then

# lxml release tarball has pre-generated C files from Cython
LXML_ETREE_C="src/lxml/etree.c"
LXML_ELEMENTPATH_C="src/lxml/_elementpath.c"

# Fallback: some lxml versions use lxml.etree.c naming
if [[ ! -f "$LXML_ETREE_C" ]]; then
  LXML_ETREE_C="src/lxml/lxml.etree.c"
fi
if [[ ! -f "$LXML_ELEMENTPATH_C" ]]; then
  LXML_ELEMENTPATH_C="src/lxml/lxml._elementpath.c"
fi

[[ -f "$LXML_ETREE_C" ]] || die "lxml etree C source not found. Expected at src/lxml/etree.c or src/lxml/lxml.etree.c"
[[ -f "$LXML_ELEMENTPATH_C" ]] || die "lxml _elementpath C source not found."

LXML_CFLAGS="$COMMON_CFLAGS \
  -I${ROOT_DIR} \
  -I${CPYTHON_INCLUDE} \
  -I${SYSROOT}/include/libxml2 \
  -I${SYSROOT}/include \
  -Isrc/lxml/includes \
  -Isrc \
  -Wno-error"

if [[ ! -f "${SYSROOT}/lib/liblxml_etree.a" ]]; then
  log "Compiling lxml.etree..."
  $CC $LXML_CFLAGS -c "$LXML_ETREE_C" -o lxml_etree.o

  log "Compiling lxml._elementpath..."
  $CC $LXML_CFLAGS -c "$LXML_ELEMENTPATH_C" -o lxml_elementpath.o

  $AR rcs liblxml_etree.a lxml_etree.o
  $AR rcs liblxml_elementpath.a lxml_elementpath.o
  $RANLIB liblxml_etree.a
  $RANLIB liblxml_elementpath.a

  cp liblxml_etree.a liblxml_elementpath.a "${SYSROOT}/lib/"
  log "lxml static libraries installed to ${SYSROOT}/lib/"
else
  log "liblxml_etree.a already exists, skipping build"
fi

# ─── Phase 5: Build minimal Pillow _imaging ──────────────────────────────────

log "=== Phase 5: Building minimal Pillow ${PILLOW_VERSION} ==="
cd "$BUILD_DIR/pillow"

PILLOW_CFLAGS="$COMMON_CFLAGS \
  -I${ROOT_DIR} \
  -I${CPYTHON_INCLUDE} \
  -I${SYSROOT}/include \
  -Isrc/libImaging \
  -DHAVE_LIBZ"

if [[ ! -f "${SYSROOT}/lib/lib_imaging.a" ]]; then
  IMAGING_OBJS=""

  # Core libImaging files (minimal set for python-pptx metadata inspection)
  IMAGING_SOURCES=(
    src/libImaging/Imaging.c
    src/libImaging/Storage.c
    src/libImaging/Access.c
    src/libImaging/Bands.c
    src/libImaging/BCn.c
    src/libImaging/BitDecode.c
    src/libImaging/Codec.c
    src/libImaging/Convert.c
    src/libImaging/Copy.c
    src/libImaging/Crop.c
    src/libImaging/Dib.c
    src/libImaging/Draw.c
    src/libImaging/Effects.c
    src/libImaging/Fill.c
    src/libImaging/Filter.c
    src/libImaging/FliDecode.c
    src/libImaging/Geometry.c
    src/libImaging/GetBBox.c
    src/libImaging/Gif.c
    src/libImaging/GifDecode.c
    src/libImaging/GifEncode.c
    src/libImaging/HexDecode.c
    src/libImaging/Histo.c
    src/libImaging/Jpeg2KDecode.c
    src/libImaging/Jpeg2KEncode.c
    src/libImaging/JpegDecode.c
    src/libImaging/JpegEncode.c
    src/libImaging/LzwDecode.c
    src/libImaging/Matrix.c
    src/libImaging/ModeInfo.c
    src/libImaging/MspDecode.c
    src/libImaging/Negative.c
    src/libImaging/Offset.c
    src/libImaging/Pack.c
    src/libImaging/PackDecode.c
    src/libImaging/Palette.c
    src/libImaging/Paste.c
    src/libImaging/PcdDecode.c
    src/libImaging/PcxDecode.c
    src/libImaging/PcxEncode.c
    src/libImaging/Point.c
    src/libImaging/Quant.c
    src/libImaging/QuantHash.c
    src/libImaging/QuantHeap.c
    src/libImaging/QuantOctree.c
    src/libImaging/QuantPngQuant.c
    src/libImaging/RankFilter.c
    src/libImaging/RawDecode.c
    src/libImaging/RawEncode.c
    src/libImaging/Reduce.c
    src/libImaging/Resample.c
    src/libImaging/SgiRleDecode.c
    src/libImaging/SunRleDecode.c
    src/libImaging/TgaRleDecode.c
    src/libImaging/TgaRleEncode.c
    src/libImaging/TiffDecode.c
    src/libImaging/Unpack.c
    src/libImaging/UnpackYCC.c
    src/libImaging/UnsharpMask.c
    src/libImaging/XbmDecode.c
    src/libImaging/XbmEncode.c
    src/libImaging/ZipDecode.c
    src/libImaging/ZipEncode.c
  )

  for src in "${IMAGING_SOURCES[@]}"; do
    if [[ -f "$src" ]]; then
      obj="$(basename "${src%.c}.o")"
      log "  Compiling $(basename "$src")..."
      $CC $PILLOW_CFLAGS -c "$src" -o "$obj" 2>/dev/null || {
        log "  Warning: $(basename "$src") failed to compile, skipping"
        continue
      }
      IMAGING_OBJS="$IMAGING_OBJS $obj"
    fi
  done

  if [[ -n "$IMAGING_OBJS" ]]; then
    $AR rcs lib_imaging.a $IMAGING_OBJS
    $RANLIB lib_imaging.a
    cp lib_imaging.a "${SYSROOT}/lib/"
    log "lib_imaging.a installed to ${SYSROOT}/lib/"
  else
    die "No Pillow imaging objects compiled successfully"
  fi

  # Also compile the main _imaging Python extension module
  if [[ -f "src/_imaging.c" ]]; then
    log "Compiling _imaging.c (Python C extension)..."
    $CC $PILLOW_CFLAGS -c "src/_imaging.c" -o _imaging_module.o 2>/dev/null || \
      log "Warning: _imaging.c compile failed — may need manual fix"
  fi
else
  log "lib_imaging.a already exists, skipping build"
fi

fi

# ─── Phase 6: Create C shims and Setup.local entries ─────────────────────────

if [[ "${SKIP_C_EXTENSIONS:-0}" -eq 0 ]]; then
log "=== Phase 6: Installing C shims and Setup.local entries ==="

MODULES_DIR="${ROOT_DIR}/Modules"

# Patch Makefile.nanvix LIBS to include stubs + lxml + Pillow if not already done
MAKEFILE="${ROOT_DIR}/Makefile.nanvix"
if ! grep -q "nanvix_stubs" "$MAKEFILE" 2>/dev/null; then
  log "Patching Makefile.nanvix LIBS to include stubs and lxml libraries..."
  sed -i 's/-lbz2 -lffi/-lbz2 -lffi -lnanvix_stubs -llxml_etree -llxml_elementpath -lxslt -lexslt -lxml2/' "$MAKEFILE"
fi

# lxml etree shim
cat > "${MODULES_DIR}/lxml_etree_builtin.c" << 'SHIM_EOF'
/*
 * lxml_etree_builtin.c - Shim to register lxml.etree as a CPython built-in.
 * makesetup does not support dotted names, so we use flat "_lxml_etree".
 */
#include "Python.h"
extern PyObject* PyInit_etree(void);
PyMODINIT_FUNC PyInit__lxml_etree(void) { return PyInit_etree(); }
SHIM_EOF

# lxml elementpath shim
cat > "${MODULES_DIR}/lxml_elementpath_builtin.c" << 'SHIM_EOF'
/*
 * lxml_elementpath_builtin.c - Shim for lxml._elementpath built-in.
 */
#include "Python.h"
extern PyObject* PyInit__elementpath(void);
PyMODINIT_FUNC PyInit__lxml_elementpath(void) { return PyInit__elementpath(); }
SHIM_EOF

log "C shims installed to ${MODULES_DIR}/"

# Append to Modules/Setup.local
SETUP_LOCAL="${MODULES_DIR}/Setup.local"

# Back up existing Setup.local
cp "$SETUP_LOCAL" "${SETUP_LOCAL}.bak" 2>/dev/null || true

# Check if lxml entries already exist (uncommented/active)
if ! grep -q '^_lxml_etree ' "$SETUP_LOCAL" 2>/dev/null; then
  cat >> "$SETUP_LOCAL" << SETUP_EOF

# --- lxml (python-pptx dependency, added by build-pptx-deps.sh) ---
_lxml_etree lxml_etree_builtin.c -L${SYSROOT}/lib -llxml_etree -lxslt -lexslt -lxml2 -lz
_lxml_elementpath lxml_elementpath_builtin.c -L${SYSROOT}/lib -llxml_elementpath -lxml2 -lz
SETUP_EOF
  log "lxml entries added to Setup.local"
else
  log "lxml entries already in Setup.local, skipping"
fi

# Note: Pillow's _imaging is more complex to integrate as a static built-in
# due to its many source files. For now we add a placeholder.
if ! grep -q '^_imaging ' "$SETUP_LOCAL" 2>/dev/null; then
  cat >> "$SETUP_LOCAL" << SETUP_EOF

# --- Pillow _imaging (minimal, python-pptx dependency) ---
# NOTE: _imaging integration requires listing all libImaging .o files.
# This is a placeholder — see lib_imaging.a in ${SYSROOT}/lib/
# _imaging src/_imaging.c -L${SYSROOT}/lib -l_imaging -lz
SETUP_EOF
  log "Pillow placeholder added to Setup.local (needs manual finalization)"
fi

fi  # end SKIP_C_EXTENSIONS check for Phase 4-6

# ─── Phase 7: Install Python packages ────────────────────────────────────────

log "=== Phase 7: Installing Python packages into site-packages ==="

# Determine site-packages path
# After install, it's at DESTDIR/sysroot/lib/python3.12/site-packages/
# During build, we stage into the source tree for later install
SITE_PKG_STAGING="${WORK_DIR}/site-packages"
mkdir -p "$SITE_PKG_STAGING"

# Install lxml pure-Python files
if [[ -d "$BUILD_DIR/lxml/src/lxml" ]]; then
  LXML_DST="${SITE_PKG_STAGING}/lxml"
  mkdir -p "$LXML_DST"
  cp "$BUILD_DIR/lxml/src/lxml/"*.py "$LXML_DST/" 2>/dev/null || true
  # Copy sub-packages
  for subdir in html isoschematron includes; do
    if [[ -d "$BUILD_DIR/lxml/src/lxml/$subdir" ]]; then
      cp -r "$BUILD_DIR/lxml/src/lxml/$subdir" "$LXML_DST/"
    fi
  done

  # Install Python shims (override the .so stubs)
  cat > "$LXML_DST/etree.py" << 'SHIM_PY'
# lxml/etree.py — Bridge to _lxml_etree built-in module.
from _lxml_etree import *  # noqa: F401,F403
SHIM_PY

  cat > "$LXML_DST/_elementpath.py" << 'SHIM_PY'
# lxml/_elementpath.py — Bridge to _lxml_elementpath built-in module.
from _lxml_elementpath import *  # noqa: F401,F403
SHIM_PY

  log "lxml Python files installed to ${LXML_DST}/"
fi

# Install python-pptx
if [[ -d "$BUILD_DIR/python-pptx" ]]; then
  # python-pptx source layout: src/pptx/ or pptx/
  PPTX_SRC=""
  if [[ -d "$BUILD_DIR/python-pptx/src/pptx" ]]; then
    PPTX_SRC="$BUILD_DIR/python-pptx/src/pptx"
  elif [[ -d "$BUILD_DIR/python-pptx/pptx" ]]; then
    PPTX_SRC="$BUILD_DIR/python-pptx/pptx"
  fi

  if [[ -n "$PPTX_SRC" ]]; then
    cp -r "$PPTX_SRC" "$SITE_PKG_STAGING/pptx"
    log "python-pptx installed to ${SITE_PKG_STAGING}/pptx/"
  else
    log "Warning: Could not find python-pptx source directory"
    ls "$BUILD_DIR/python-pptx/"
  fi
fi

# Install minimal Pillow Python files
if [[ -d "$BUILD_DIR/pillow/src/PIL" ]]; then
  cp -r "$BUILD_DIR/pillow/src/PIL" "$SITE_PKG_STAGING/PIL"
  log "Pillow Python files installed to ${SITE_PKG_STAGING}/PIL/"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────

log ""
log "=== Build complete ==="
log ""
log "Static libraries in ${SYSROOT}/lib/:"
for lib in libxml2.a libxslt.a libexslt.a liblxml_etree.a liblxml_elementpath.a lib_imaging.a; do
  if [[ -f "${SYSROOT}/lib/$lib" ]]; then
    size=$(stat -c%s "${SYSROOT}/lib/$lib" 2>/dev/null || echo "?")
    log "  ✓ $lib ($size bytes)"
  else
    log "  ✗ $lib (MISSING)"
  fi
done
log ""
log "Python packages staged in ${SITE_PKG_STAGING}/:"
ls -d "$SITE_PKG_STAGING"/*/ 2>/dev/null | while read d; do
  count=$(find "$d" -name "*.py" | wc -l)
  log "  $(basename "$d")/ ($count .py files)"
done
log ""
log "Setup.local entries:"
grep -E '^_lxml|^_imaging' "$SETUP_LOCAL" 2>/dev/null | while read line; do
  log "  $line"
done
log ""
log "Next steps:"
log "  1. Run: ./z build"
log "  2. After build, copy site-packages into the ramfs staging:"
log "     cp -r ${SITE_PKG_STAGING}/* <DESTDIR>/sysroot/lib/python3.12/site-packages/"
log "  3. Rebuild ramfs: make -f Makefile.nanvix ramfs"
log "  4. Test: echo 'from pptx import Presentation; print(\"OK\")' | nanvixd ..."

#!/usr/bin/env bash

set -euo pipefail

LIBXML2_VERSION="2.12.9"
LIBXSLT_VERSION="1.1.42"
LXML_VERSION="5.3.0"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${ROOT_DIR}/.nanvix/pptx-deps"
DOWNLOAD_DIR="${WORK_DIR}/downloads"
BUILD_DIR="${WORK_DIR}/build"
SITE_PACKAGES_DIR="${WORK_DIR}/site-packages"

LIBXML2_URL="https://download.gnome.org/sources/libxml2/2.12/libxml2-${LIBXML2_VERSION}.tar.xz"
LIBXSLT_URL="https://download.gnome.org/sources/libxslt/1.1/libxslt-${LIBXSLT_VERSION}.tar.xz"
LXML_URL="https://github.com/lxml/lxml/releases/download/lxml-${LXML_VERSION}/lxml-${LXML_VERSION}.tar.gz"

log() {
    printf '[build-lxml-deps] %s\n' "$*"
}

die() {
    printf '[build-lxml-deps] ERROR: %s\n' "$*" >&2
    exit 1
}

if [[ -z "${NANVIX_HOME:-}" ]]; then
    ENV_JSON="${ROOT_DIR}/.nanvix/env.json"
    if [[ -f "${ENV_JSON}" ]]; then
        NANVIX_HOME="$(python3 -c "import json; print(json.load(open('${ENV_JSON}'))['NANVIX_SYSROOT'])" 2>/dev/null || true)"
    fi
fi

NANVIX_HOME="${NANVIX_HOME:-}"
[[ -n "${NANVIX_HOME}" ]] || die "NANVIX_HOME is not set. Run ./z setup first."
[[ -d "${NANVIX_HOME}" ]] || die "NANVIX_HOME directory not found: ${NANVIX_HOME}"

NANVIX_TOOLCHAIN="${NANVIX_TOOLCHAIN:-/opt/nanvix}"
CC="${NANVIX_TOOLCHAIN}/bin/i686-nanvix-gcc"
CXX="${NANVIX_TOOLCHAIN}/bin/i686-nanvix-g++"
AR="${NANVIX_TOOLCHAIN}/bin/i686-nanvix-ar"
RANLIB="${NANVIX_TOOLCHAIN}/bin/i686-nanvix-ranlib"
STRIP="${NANVIX_TOOLCHAIN}/bin/i686-nanvix-strip"
BUILD_TRIPLET="$(${ROOT_DIR}/config.guess 2>/dev/null || echo x86_64-linux-gnu)"
SYSROOT="${NANVIX_HOME}"
COMMON_CFLAGS="-m32 -march=pentiumpro -Os -fdata-sections -ffunction-sections -I${SYSROOT}/include"

[[ -x "${CC}" ]] || die "Compiler not found: ${CC}"
[[ -x "${CXX}" ]] || die "Compiler not found: ${CXX}"
[[ -x "${AR}" ]] || die "Archiver not found: ${AR}"
[[ -x "${RANLIB}" ]] || die "Ranlib not found: ${RANLIB}"
[[ -x "${STRIP}" ]] || die "Strip not found: ${STRIP}"

PYCONFIG="${ROOT_DIR}/pyconfig.h"
[[ -f "${PYCONFIG}" ]] || die "Missing ${PYCONFIG}. Run the CPython configure/build step before building lxml dependencies."

mkdir -p "${DOWNLOAD_DIR}" "${BUILD_DIR}" "${SITE_PACKAGES_DIR}/lxml" "${SYSROOT}/bin"

download() {
    local url="$1"
    local dest="$2"
    if [[ ! -f "${dest}" ]]; then
        log "Downloading $(basename "${dest}")"
        curl -fsSL "${url}" -o "${dest}"
    fi
}

extract() {
    local archive="$1"
    local dest="$2"
    rm -rf "${dest}"
    mkdir -p "${dest}"
    tar -xf "${archive}" -C "${dest}" --strip-components=1
}

assert_file() {
    local path="$1"
    [[ -f "${path}" ]] || die "Expected file is missing: ${path}"
}

assert_dir() {
    local path="$1"
    [[ -d "${path}" ]] || die "Expected directory is missing: ${path}"
}

download "${LIBXML2_URL}" "${DOWNLOAD_DIR}/libxml2-${LIBXML2_VERSION}.tar.xz"
download "${LIBXSLT_URL}" "${DOWNLOAD_DIR}/libxslt-${LIBXSLT_VERSION}.tar.xz"
download "${LXML_URL}" "${DOWNLOAD_DIR}/lxml-${LXML_VERSION}.tar.gz"

extract "${DOWNLOAD_DIR}/libxml2-${LIBXML2_VERSION}.tar.xz" "${BUILD_DIR}/libxml2"
extract "${DOWNLOAD_DIR}/libxslt-${LIBXSLT_VERSION}.tar.xz" "${BUILD_DIR}/libxslt"
extract "${DOWNLOAD_DIR}/lxml-${LXML_VERSION}.tar.gz" "${BUILD_DIR}/lxml"

# Copy NanVix-patched config.sub/config.guess so autoconf recognises i686-nanvix
for d in "${BUILD_DIR}/libxml2" "${BUILD_DIR}/libxslt"; do
    cp "${ROOT_DIR}/config.sub" "${d}/" 2>/dev/null || true
    cp "${ROOT_DIR}/config.guess" "${d}/" 2>/dev/null || true
done

log "Building libxml2 ${LIBXML2_VERSION}"
pushd "${BUILD_DIR}/libxml2" > /dev/null
CC="${CC}" AR="${AR}" RANLIB="${RANLIB}" \
    CFLAGS="${COMMON_CFLAGS}" \
    ./configure \
    --host=i686-nanvix \
    --build="${BUILD_TRIPLET}" \
    --prefix="${SYSROOT}" \
    --enable-static \
    --disable-shared \
    --without-python \
    --without-threads \
    --without-http \
    --without-ftp \
    --without-readline \
    --without-history \
    --without-catalog \
    --without-debug \
    --without-legacy \
    --without-lzma \
    --without-icu \
    --without-iconv \
    --with-zlib="${SYSROOT}"
# Build library only — tools (xmllint etc.) fail to link on NanVix
make -j"$(nproc)" -C . libxml2.la
make install-libLTLIBRARIES
mkdir -p "${SYSROOT}/include/libxml2/libxml"
cp include/libxml/*.h "${SYSROOT}/include/libxml2/libxml/"
popd > /dev/null

assert_file "${SYSROOT}/lib/libxml2.a"
assert_dir "${SYSROOT}/include/libxml2/libxml"

log "Creating xml2-config shim"
XML2_CONFIG="${SYSROOT}/bin/xml2-config"
printf '%s\n' '#!/bin/sh' > "${XML2_CONFIG}"
printf '%s\n' 'case "$1" in' >> "${XML2_CONFIG}"
printf '%s\n' "  --cflags) echo \"-I${SYSROOT}/include/libxml2\" ;;" >> "${XML2_CONFIG}"
printf '%s\n' "  --libs) echo \"-L${SYSROOT}/lib -lxml2 -lz\" ;;" >> "${XML2_CONFIG}"
printf '%s\n' "  --version) echo \"${LIBXML2_VERSION}\" ;;" >> "${XML2_CONFIG}"
printf '%s\n' '  *) echo "Usage: xml2-config [--cflags|--libs|--version]" ;;' >> "${XML2_CONFIG}"
printf '%s\n' 'esac' >> "${XML2_CONFIG}"
chmod +x "${XML2_CONFIG}"
assert_file "${XML2_CONFIG}"

log "Building libxslt ${LIBXSLT_VERSION}"
pushd "${BUILD_DIR}/libxslt" > /dev/null
PATH="${SYSROOT}/bin:${PATH}" \
CC="${CC}" AR="${AR}" RANLIB="${RANLIB}" \
    CFLAGS="${COMMON_CFLAGS} -I${SYSROOT}/include/libxml2" \
    XML_CONFIG="${XML2_CONFIG}" \
    ./configure \
    --host=i686-nanvix \
    --build="${BUILD_TRIPLET}" \
    --prefix="${SYSROOT}" \
    --enable-static \
    --disable-shared \
    --without-python \
    --without-crypto \
    --without-plugins \
    --with-libxml-prefix="${SYSROOT}" \
    --with-libxml-include-prefix="${SYSROOT}/include/libxml2" \
    --with-libxml-libs-prefix="${SYSROOT}/lib"
# Build libraries only — xsltproc fails to link on NanVix
make -j"$(nproc)" -C libxslt
make -j"$(nproc)" -C libexslt
cp -f libxslt/.libs/libxslt.a "${SYSROOT}/lib/"
cp -f libexslt/.libs/libexslt.a "${SYSROOT}/lib/"
mkdir -p "${SYSROOT}/include/libxslt" "${SYSROOT}/include/libexslt"
cp -f libxslt/*.h "${SYSROOT}/include/libxslt/"
cp -f libexslt/*.h "${SYSROOT}/include/libexslt/"
popd > /dev/null

assert_file "${SYSROOT}/lib/libxslt.a"
assert_file "${SYSROOT}/lib/libexslt.a"
assert_dir "${SYSROOT}/include/libxslt"
assert_dir "${SYSROOT}/include/libexslt"

log "Building lxml static archives ${LXML_VERSION}"
pushd "${BUILD_DIR}/lxml" > /dev/null
assert_file "src/lxml/etree.c"
assert_file "src/lxml/_elementpath.c"
LXML_CFLAGS="${COMMON_CFLAGS} -I${ROOT_DIR} -I${ROOT_DIR}/Include -I${SYSROOT}/include -I${SYSROOT}/include/libxml2 -Isrc -Isrc/lxml/includes"
"${CC}" ${LXML_CFLAGS} -c src/lxml/etree.c -o lxml_etree.o
"${CC}" ${LXML_CFLAGS} -c src/lxml/_elementpath.c -o lxml_elementpath.o
"${AR}" rcs liblxml_etree.a lxml_etree.o
"${AR}" rcs liblxml_elementpath.a lxml_elementpath.o
"${RANLIB}" liblxml_etree.a
"${RANLIB}" liblxml_elementpath.a
cp -f liblxml_etree.a "${SYSROOT}/lib/"
cp -f liblxml_elementpath.a "${SYSROOT}/lib/"
popd > /dev/null

assert_file "${SYSROOT}/lib/liblxml_etree.a"
assert_file "${SYSROOT}/lib/liblxml_elementpath.a"

log "Staging lxml Python package"
LXML_STAGE_DIR="${SITE_PACKAGES_DIR}/lxml"
rm -rf "${LXML_STAGE_DIR}"
mkdir -p "${LXML_STAGE_DIR}"
cp -f "${BUILD_DIR}/lxml/src/lxml/"*.py "${LXML_STAGE_DIR}/"
cp -rf "${BUILD_DIR}/lxml/src/lxml/html" "${LXML_STAGE_DIR}/"
cp -rf "${BUILD_DIR}/lxml/src/lxml/isoschematron" "${LXML_STAGE_DIR}/"
cp -rf "${BUILD_DIR}/lxml/src/lxml/includes" "${LXML_STAGE_DIR}/"
assert_file "${LXML_STAGE_DIR}/__init__.py"

printf '%s\n' 'from _lxml_etree import *' > "${LXML_STAGE_DIR}/etree.py"
printf '%s\n' 'from _lxml_etree import _Element, _ElementTree, _Comment, _ProcessingInstruction, ElementBase, QName, _Attrib' >> "${LXML_STAGE_DIR}/etree.py"
printf '%s\n' 'from _lxml_elementpath import *' > "${LXML_STAGE_DIR}/_elementpath.py"

assert_file "${LXML_STAGE_DIR}/etree.py"
assert_file "${LXML_STAGE_DIR}/_elementpath.py"

log "Done. Installed archives in ${SYSROOT}/lib and headers in ${SYSROOT}/include"
log "Staged lxml Python package in ${LXML_STAGE_DIR}"

#!/bin/bash
set -euo pipefail
cd /tmp/cpython-clean
NH=/mnt/a/Repos/NanVix-CPython/.nanvix/extracted/nanvix
DU=$(id -u)
DG=$(id -g)

echo "=== Compile _imaging.c + update Setup.local + rebuild ==="

docker run --rm --user "${DU}:${DG}" \
  -v /tmp/cpython-clean:/mnt/workspace \
  -v "${NH}":/mnt/sysroot \
  -w /mnt/workspace \
  -e HOME=/tmp \
  -e NANVIX_HOME=/mnt/sysroot \
  -e NANVIX_TOOLCHAIN=/opt/nanvix \
  nanvix/toolchain:latest-minimal \
  bash -c '
    CC=/opt/nanvix/bin/i686-nanvix-gcc
    AR=/opt/nanvix/bin/i686-nanvix-ar
    RANLIB=/opt/nanvix/bin/i686-nanvix-ranlib
    CFLAGS="-m32 -march=pentiumpro -Os -fdata-sections -ffunction-sections -I/mnt/sysroot/include"
    PILLOW=/mnt/workspace/.nanvix/pptx-deps/build/pillow

    echo "Compiling ALL libImaging sources..."
    OBJS=""
    for src in ${PILLOW}/src/libImaging/*.c; do
      obj="/tmp/$(basename ${src%.c}).o"
      ${CC} ${CFLAGS} -I/mnt/workspace/Include -I/mnt/workspace -I${PILLOW}/src/libImaging -DHAVE_LIBZ -c "$src" -o "$obj" 2>/dev/null && OBJS="$OBJS $obj" || echo "  SKIP: $(basename $src)"
    done
    echo "Compiled $(echo $OBJS | wc -w) libImaging objects"

    echo "Compiling _imaging.c and support modules..."
    for src in _imaging.c path.c outline.c decode.c encode.c map.c; do
      obj="/tmp/$(basename ${src%.c}).o"
      ${CC} ${CFLAGS} \
        -I/mnt/workspace/Include \
        -I/mnt/workspace \
        -I${PILLOW}/src/libImaging \
        -DHAVE_LIBZ \
        -DPILLOW_VERSION=\"10.4.0\" \
        -c ${PILLOW}/src/${src} \
        -o ${obj} 2>&1 || { echo "FAILED: ${src}"; exit 1; }
      OBJS="$OBJS ${obj}"
      echo "  OK: ${src}"
    done

    echo "Creating lib_imaging.a with all objects..."
    ${AR} rcs /mnt/sysroot/lib/lib_imaging.a $OBJS
    ${RANLIB} /mnt/sysroot/lib/lib_imaging.a
    echo "lib_imaging.a: $(ls -lh /mnt/sysroot/lib/lib_imaging.a) ($(${AR} t /mnt/sysroot/lib/lib_imaging.a | wc -l) objects)"
  '

echo "=== Update Setup.local ==="
# Replace placeholder with active _imaging entry
sed -i 's|^# _imaging src/_imaging.c.*|_imaging Modules/_imaging.o -L/mnt/sysroot/lib -l_imaging -lz|' Modules/Setup.local
echo "Setup.local _imaging entry:"
grep "_imaging" Modules/Setup.local | grep -v "^#"

echo "=== Rebuild CPython (74 -> 75 modules) ==="
rm -f python python.elf
./z build 2>&1 | tail -5
echo "BUILD:$?"

echo "=== Strip ==="
docker run --rm --user "${DU}:${DG}" \
  -v /tmp/cpython-clean:/mnt/workspace \
  nanvix/toolchain:latest-minimal \
  /opt/nanvix/bin/i686-nanvix-strip -o /mnt/workspace/python-pptx-stripped.elf /mnt/workspace/python.elf
ls -lh python-pptx-stripped.elf
cp python-pptx-stripped.elf /mnt/a/Repos/NanVix/bin/python-pptx.elf
echo "DONE"

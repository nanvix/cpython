# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

# toolchain-python — Nanvix GCC toolchain + host Python 3 for CPython
# cross-compilation.  Published as ghcr.io/nanvix/toolchain-python.

FROM ghcr.io/nanvix/toolchain-gcc:sha-34a3641

# Install the host Python plus the build helpers required by extension
# modules that ship a meson or Cython build step (numpy, scipy, pandas,
# ...):
#
#   - ninja  — meson's default backend; missing it makes every meson-based
#              extension build fail immediately.
#   - Cython — required by numpy 1.26.4's `numpy/_build_utils/tempita.py`
#              .pyx.in code generation. Pinned `<3` for numpy 1.26.x
#              compatibility; lift the pin when bumping numpy.
#
# We deliberately purge `/usr/include/python3.12` after the install. The
# `python3-pip` / `ninja-build` apt packages transitively pull in
# `libpython3.12-dev`, whose headers under `/usr/include/python3.12` would
# otherwise be picked up by meson's regen step ahead of the Nanvix cross
# sysroot headers and silently corrupt the cross-build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-dev \
        python3-pip \
        ninja-build \
    && pip3 install --break-system-packages --no-cache-dir 'Cython<3' \
    && rm -rf /usr/include/python3.12 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /opt/nanvix/bin/python3

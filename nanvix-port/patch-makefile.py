#!/usr/bin/env python3
"""Patch Makefile.nanvix with NanVix cross-compilation fixes."""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "Makefile.nanvix"

with open(path, "r") as f:
    c = f.read()

# Fix 1: CONFIG_SITE in Docker configure
c = c.replace(
    "sh -c '$(CONFIGURE_ENV) ./configure $(CONFIGURE_OPTS)'",
    "sh -c 'CONFIG_SITE=$(DOCKER_WORKSPACE_PATH)/nanvix-port/config.site $(CONFIGURE_ENV) ./configure $(CONFIGURE_OPTS)'"
)

# Fix 2: CONFIG_SITE in native configure
c = c.replace(
    "\t$(CONFIGURE_ENV) ./configure $(CONFIGURE_OPTS)",
    "\tCONFIG_SITE=$(abspath $(CURDIR))/nanvix-port/config.site $(CONFIGURE_ENV) ./configure $(CONFIGURE_OPTS)"
)

# Fix 3: CFLAGS
c = c.replace(
    'CFLAGS="-L$(SYSROOT_PATH)/lib -I$(SYSROOT_PATH)/include"',
    'CFLAGS="-m32 -march=pentiumpro -Os -fdata-sections -ffunction-sections -I$(SYSROOT_PATH)/include -I$(SYSROOT_PATH)/include/libxml2" \\\n\tCPPFLAGS="-I$(TOOLCHAIN_PREFIX)/i686-nanvix/include -I$(SYSROOT_PATH)/include -I$(SYSROOT_PATH)/include/libxml2"'
)

# Fix 4: LDFLAGS
c = c.replace(
    'LDFLAGS="-static -T$(SYSROOT_PATH)/lib/user.ld -Wl,--allow-multiple-definition"',
    'LDFLAGS="-static -T$(SYSROOT_PATH)/lib/user.ld -L$(SYSROOT_PATH)/lib -Wl,--gc-sections -Wl,--allow-multiple-definition"'
)

with open(path, "w") as f:
    f.write(c)

print("Makefile.nanvix patched successfully")

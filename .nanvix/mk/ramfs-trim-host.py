#!/usr/bin/env python3
# ramfs-trim-host.py - Trim a staged sysroot for ramfs (native, cross-platform).
#
# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.
#
# Usage: ramfs-trim-host.py <sysroot-path>
#
# Equivalent to the ramfs-trim Make target in ramfs.mk, but runs natively
# on Windows (no shell/find/rm required).

import glob
import os
import shutil
import sys


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <sysroot-path>", file=sys.stderr)
        sys.exit(1)

    sysroot = sys.argv[1]
    if not os.path.isdir(sysroot):
        print(f"Error: {sysroot} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Trimming sysroot for ramfs: {sysroot}")

    # Remove heavyweight stdlib packages not needed at runtime.
    for subdir in (
        "lib/python3.12/config-3.12",
        "lib/python3.12/idlelib",
        "lib/python3.12/tkinter",
        "lib/python3.12/turtledemo",
        "lib/python3.12/lib2to3",
        "lib/python3.12/ensurepip",
        "lib/python3.12/pydoc_data",
        "lib/python3.12/venv",
        "lib/python3.12/site-packages",
        "lib/python3.12/__phello__",
        "lib/python3.12/test",
        "include",
        "share",
        "lib/pkgconfig",
    ):
        p = os.path.join(sysroot, subdir)
        if os.path.isdir(p):
            shutil.rmtree(p)

    # Remove static library.
    for f in ("lib/libpython3.12.a",):
        p = os.path.join(sysroot, f)
        if os.path.isfile(p):
            os.remove(p)

    # Remove dev/admin scripts from bin/.
    bin_dir = os.path.join(sysroot, "bin")
    if os.path.isdir(bin_dir):
        for pattern in (
            "2to3*", "idle3*", "pydoc3*",
            "python3-config", "python3.12-config", "python3",
            "*.elf", "*.exe",
        ):
            for f in glob.glob(os.path.join(bin_dir, pattern)):
                if os.path.isfile(f):
                    os.remove(f)
        # Remove bin/ if empty.
        try:
            os.rmdir(bin_dir)
        except OSError:
            pass

    # Remove __pycache__ directories.
    for root, dirs, _files in os.walk(sysroot, topdown=False):
        for d in dirs:
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)


if __name__ == "__main__":
    main()

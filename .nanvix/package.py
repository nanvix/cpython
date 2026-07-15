# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Release staging for Nanvix CPython.

Stages the runtime tree under ``regular_out()`` (packaged into the
regular archive by ``nanvix-zutil release``) and the buildroot tree
under ``dev_out()`` (packaged into the ``-dev`` archive). Also inserts
the built ``python.elf`` and prepares the ramfs image inputs.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import config
import ramfs as ramfs_mod
from nanvix_zutil import paths


def sysroot_pkg() -> Path:
    """Staging tree for the runtime archive (packaged verbatim)."""
    return paths.regular_out()


def buildroot_pkg() -> Path:
    """Staging tree for the ``-dev`` (buildroot) archive (packaged verbatim)."""
    return paths.dev_out()


def stage() -> None:
    """Stage the two archive trees under ``regular_out()`` and ``dev_out()``.

    Must run after ``build_mod.build(args)`` has populated
    :func:`sysroot_pkg`. Buildroot is curated *before* the sysroot
    install tree is trimmed in-place.
    """
    # --- Buildroot tarball staging (must come before trim_sysroot) ---
    if buildroot_pkg().is_dir():
        shutil.rmtree(buildroot_pkg())
    br = buildroot_pkg()
    (br / "lib").mkdir(parents=True)
    (br / "bin").mkdir(parents=True)

    # Copy include directory.
    inc_src = sysroot_pkg() / "include"
    if inc_src.is_dir():
        shutil.copytree(inc_src, br / "include")

    # Copy static libraries.
    lib_src = sysroot_pkg() / "lib"
    if lib_src.is_dir():
        for lib_file in lib_src.glob("*.a"):
            shutil.copy2(lib_file, br / "lib" / lib_file.name)
        # Copy pkgconfig.
        pkgconfig = lib_src / "pkgconfig"
        if pkgconfig.is_dir():
            shutil.copytree(pkgconfig, br / "lib" / "pkgconfig")
        # Copy config-3.12.
        config_dir = lib_src / config.PYTHON_LIB_DIR / f"config-{config.PYTHON_VERSION}"
        if config_dir.is_dir():
            dest = (
                br / "lib" / config.PYTHON_LIB_DIR / f"config-{config.PYTHON_VERSION}"
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(config_dir, dest)

    # Cross ``make install`` does not reliably stage the static interpreter
    # archive, so copy the just-built SDK archive directly.
    python_archive = paths.repo_root() / f"libpython{config.PYTHON_VERSION}.a"
    if python_archive.is_file():
        shutil.copy2(python_archive, br / "lib" / python_archive.name)

    # Copy dev binaries.
    for f in [
        "python3-config",
        f"python{config.PYTHON_VERSION}-config",
        "2to3",
        f"2to3-{config.PYTHON_VERSION}",
        "idle3",
        f"idle{config.PYTHON_VERSION}",
        "pydoc3",
        f"pydoc{config.PYTHON_VERSION}",
    ]:
        src = sysroot_pkg() / "bin" / f
        if src.is_file():
            shutil.copy2(src, br / "bin" / f)

    # Copy share directory.
    share_src = sysroot_pkg() / "share"
    if share_src.is_dir():
        shutil.copytree(share_src, br / "share")

    # --- Sysroot tarball staging: trim install tree in-place ---
    ramfs_mod.trim_sysroot(sysroot_pkg())

    # --- Include python.elf binary ---
    python_elf = paths.repo_root() / f"python{config.EXE}"
    if python_elf.is_file():
        bin_dst = sysroot_pkg() / "bin"
        bin_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(python_elf, bin_dst / "python.elf")
        size = (bin_dst / "python.elf").stat().st_size
        print(f"Included bin/python.elf ({size // 1024}K)")
    else:
        print("Warning: python.elf not found — binary will not be included in release")

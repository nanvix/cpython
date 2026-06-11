# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Release packaging and verification for Nanvix CPython.

Replaces package-common.mk and verify-package.mk. Handles sysroot/buildroot
tarball creation, ramfs image inclusion, and tarball verification.
"""

from __future__ import annotations

import shutil
import tarfile
import build as build_mod
import config
import lxml as lxml_mod
import ramfs as ramfs_mod
from nanvix_zutil import paths


def package(
    args: build_mod.MakeArgs,
) -> None:
    """Package CPython release tarballs.

    Creates two tarballs in ``nanvix_zutil.paths.dist_dir()``:
    - ``cpython-<platform>-<mode>-<memory>.tar.gz`` — runtime sysroot + binary + ramfs
    - ``cpython-<platform>-<mode>-<memory>-buildroot.tar.gz`` — build dependencies
    """
    release_staging = paths.release_dir()
    dist_dir = paths.dist_dir()
    artifact = args.asset_prefix()

    print("Packaging CPython release...")

    sysroot_installed = release_staging / "sysroot"
    if not sysroot_installed.is_dir():
        raise FileNotFoundError(
            f"Release install tree not found at {sysroot_installed}. "
            "Run `./z build` first to populate it."
        )

    # Clean previous packaging scratch (but NEVER the installed sysroot,
    # which is produced by `./z build` and is the input to this step).
    for scratch in (
        release_staging / "buildroot-pkg",
        release_staging / "sysroot-pkg-wrap",
        release_staging / "bin",
        release_staging / "cpython-ramfs.img",
    ):
        if scratch.is_dir():
            shutil.rmtree(scratch)
        elif scratch.is_file():
            scratch.unlink()

    # Stage lxml Python package into the installed sysroot.
    lxml_mod.stage_lxml_runtime(sysroot_installed)

    # --- Buildroot: build dependencies ---
    buildroot_pkg = release_staging / "buildroot-pkg"
    buildroot_pkg.mkdir(parents=True)
    (buildroot_pkg / "lib").mkdir()
    (buildroot_pkg / "bin").mkdir()

    # Copy include directory.
    inc_src = sysroot_installed / "include"
    if inc_src.is_dir():
        shutil.copytree(inc_src, buildroot_pkg / "include")

    # Copy static libraries.
    lib_src = sysroot_installed / "lib"
    if lib_src.is_dir():
        for lib_file in lib_src.glob("*.a"):
            shutil.copy2(lib_file, buildroot_pkg / "lib" / lib_file.name)
        # Copy pkgconfig.
        pkgconfig = lib_src / "pkgconfig"
        if pkgconfig.is_dir():
            shutil.copytree(pkgconfig, buildroot_pkg / "lib" / "pkgconfig")
        # Copy config-3.12.
        config_dir = lib_src / config.PYTHON_LIB_DIR / f"config-{config.PYTHON_VERSION}"
        if config_dir.is_dir():
            dest = (
                buildroot_pkg
                / "lib"
                / config.PYTHON_LIB_DIR
                / f"config-{config.PYTHON_VERSION}"
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(config_dir, dest)

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
        src = sysroot_installed / "bin" / f
        if src.is_file():
            shutil.copy2(src, buildroot_pkg / "bin" / f)

    # Copy share directory.
    share_src = sysroot_installed / "share"
    if share_src.is_dir():
        shutil.copytree(share_src, buildroot_pkg / "share")

    # --- Sysroot: runtime stdlib (trimmed) ---
    ramfs_staging = release_staging / "sysroot-pkg-wrap"
    ramfs_sysroot = ramfs_staging / "sysroot" / "lib"
    ramfs_sysroot.mkdir(parents=True)

    py_lib = sysroot_installed / "lib" / config.PYTHON_LIB_DIR
    if py_lib.is_dir():
        shutil.copytree(py_lib, ramfs_sysroot / config.PYTHON_LIB_DIR)

    ramfs_mod.trim_sysroot(ramfs_staging)

    # --- Include python.elf binary ---
    bin_dir = release_staging / "bin"
    python_elf = paths.repo_root() / f"python{config.EXE}"
    if python_elf.is_file():
        bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(python_elf, bin_dir / "python.elf")
        size = (bin_dir / "python.elf").stat().st_size
        print(f"Included bin/python.elf ({size // 1024}K)")
    else:
        print("Warning: python.elf not found — binary will not be included in release")

    # --- Build ramfs image ---
    ramfs_img = release_staging / "cpython-ramfs.img"
    ramfs_mod.build_image(ramfs_staging, args.sysroot, ramfs_img)

    # --- Create release tarballs ---
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Sysroot tarball.
    sysroot_tar = dist_dir / f"{artifact}.tar.gz"
    sysroot_runtime = ramfs_staging / "sysroot"
    with tarfile.open(str(sysroot_tar), "w:gz") as tf:
        tf.add(str(sysroot_runtime), arcname="sysroot")
        if bin_dir.is_dir():
            tf.add(str(bin_dir), arcname="bin")
        if ramfs_img.is_file():
            tf.add(str(ramfs_img), arcname="cpython-ramfs.img")

    # Buildroot tarball.
    buildroot_tar = dist_dir / f"{artifact}-buildroot.tar.gz"
    with tarfile.open(str(buildroot_tar), "w:gz") as tf:
        tf.add(str(buildroot_pkg), arcname="sysroot")

    print("Release tarballs created in dist/")
    for f in sorted(dist_dir.glob(f"{artifact}*.tar.gz")):
        size = f.stat().st_size
        print(f"  {f.name} ({size // 1024}K)")


def verify(args: build_mod.MakeArgs) -> None:
    """Verify release tarballs.

    Checks that tarballs exist, are not corrupt, and contain the
    expected contents.
    """
    artifact = args.asset_prefix()
    dist_dir = paths.dist_dir()

    print("Verifying release tarballs...")

    sysroot_tar = dist_dir / f"{artifact}.tar.gz"
    buildroot_tar = dist_dir / f"{artifact}-buildroot.tar.gz"

    if not sysroot_tar.is_file():
        raise FileNotFoundError(f"Sysroot tarball not found: {sysroot_tar}")
    if not buildroot_tar.is_file():
        raise FileNotFoundError(f"Buildroot tarball not found: {buildroot_tar}")

    # Verify integrity.
    with tarfile.open(str(sysroot_tar), "r:gz") as tf:
        members = tf.getnames()
    with tarfile.open(str(buildroot_tar), "r:gz") as tf:
        _ = tf.getnames()

    # Verify python.elf is present (exact path match).
    if "bin/python.elf" not in members:
        raise ValueError("Sysroot tarball missing bin/python.elf")

    print("\t\t*** Package verification PASSED ***")

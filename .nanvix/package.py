# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Release packaging and verification for Nanvix CPython.

Replaces package-common.mk and verify-package.mk. Handles sysroot/buildroot
tarball creation, ramfs image inclusion, and tarball verification.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import tarfile
import build as build_mod
import config
import ramfs as ramfs_mod
from nanvix_zutil import paths


def sysroot_pkg() -> Path:
    """Staging tree for the runtime sysroot tarball (tarred verbatim)."""
    return paths.release_dir() / "sysroot-pkg"


def buildroot_pkg() -> Path:
    """Staging tree for the buildroot tarball (tarred verbatim)."""
    return paths.release_dir() / "buildroot-pkg"


def stage() -> None:
    """Stage the two tarball trees under ``release_dir/``.

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


def package(
    args: build_mod.MakeArgs,
) -> None:
    """Tar the two pre-staged trees verbatim.

    Creates two tarballs in ``nanvix_zutil.paths.dist_dir()``:
    - ``cpython-<platform>-<mode>-<memory>.tar.gz`` — runtime sysroot + binary + ramfs
    - ``cpython-<platform>-<mode>-<memory>-buildroot.tar.gz`` — build dependencies
    """
    dist_dir = paths.dist_dir()
    artifact = args.asset_prefix()
    dist_dir.mkdir(parents=True, exist_ok=True)

    for staging, name in [
        (sysroot_pkg(), f"{artifact}.tar.gz"),
        (buildroot_pkg(), f"{artifact}-buildroot.tar.gz"),
    ]:
        with tarfile.open(str(dist_dir / name), "w:gz") as tf:
            for child in sorted(staging.iterdir()):
                tf.add(str(child), arcname=child.name)

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

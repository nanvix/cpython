# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Release packaging and verification for Nanvix CPython.

Provides:
- ``stage_build_output()`` — called by ``./z build`` to produce persistent
  release-ready sysroot, buildroot, binary, and ramfs image.
- ``package()`` — called by ``./z release`` to archive the output from
  ``./z build`` into tarballs (Linux) or zip files (Windows).
- ``verify()`` — validates that release archives are well-formed.
"""

from __future__ import annotations

import json
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _loader import load_sibling

config = load_sibling("config", __file__)
build_mod = load_sibling("build", __file__)
lxml_mod = load_sibling("lxml", __file__)
ramfs_mod = load_sibling("ramfs", __file__)

# Persistent build output directory (produced by ./z build).
BUILD_OUTPUT_DIR = "_build_output"
_BUILD_OUTPUT_TMP = "_build_output.tmp"
_MANIFEST_NAME = "manifest.json"


def build_output_path(repo_root: Path) -> Path:
    """Return the path to the persistent build output directory."""
    return repo_root / ".nanvix" / BUILD_OUTPUT_DIR


def _artifact_base(
    platform: str = config.DEFAULT_PLATFORM,
    process_mode: str = config.DEFAULT_PROCESS_MODE,
    memory_size: str = config.DEFAULT_MEMORY_SIZE,
) -> str:
    """Return the base name for release archives."""
    return f"cpython-{platform}-{process_mode}-{memory_size}"


# ---------------------------------------------------------------------------
# Build output staging (called by ./z build)
# ---------------------------------------------------------------------------


def stage_build_output(
    sysroot: str | Path,
    toolchain: str | Path,
    repo_root: Path,
    *,
    platform: str = config.DEFAULT_PLATFORM,
    process_mode: str = config.DEFAULT_PROCESS_MODE,
    memory_size: str = config.DEFAULT_MEMORY_SIZE,
    install_prefix: str = config.DEFAULT_INSTALL_PREFIX,
    run_fn: Any = None,
    nanvix_home: str | Path | None = None,
    docker: bool = False,
) -> Path:
    """Produce release-ready build output after compilation.

    Installs CPython into a staging directory, splits into runtime sysroot
    and buildroot, trims the runtime sysroot, builds the ramfs image
    (without test files), and writes a manifest.

    The output is written atomically: staging happens in a temporary
    directory and is renamed to the final location only on success.

    Returns the path to the build output directory.
    """
    nanvix_home_path = Path(nanvix_home) if nanvix_home else Path(sysroot)
    output_dir = repo_root / ".nanvix" / BUILD_OUTPUT_DIR
    tmp_dir = repo_root / ".nanvix" / _BUILD_OUTPUT_TMP

    print("Staging build output...")

    # Clean previous temporary staging.
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    # Install into a temporary install tree.
    install_staging = tmp_dir / "_install"
    install_staging.mkdir()

    if config.IS_WINDOWS:
        # On Windows, the install cache from Docker is already available.
        install_cache = repo_root / ".nanvix" / "_install_cache"
        if install_cache.is_dir():
            shutil.copytree(install_cache, install_staging, dirs_exist_ok=True)
        else:
            raise FileNotFoundError(
                "Install cache not found. On Windows, ./z build should "
                "produce _install_cache via Docker."
            )
    else:
        build_mod.install(
            sysroot,
            toolchain,
            repo_root,
            install_staging,
            platform=platform,
            process_mode=process_mode,
            memory_size=memory_size,
            install_prefix=install_prefix,
            release=True,
            run_fn=run_fn,
            docker=docker,
        )

    sysroot_installed = install_staging / "sysroot"
    if not sysroot_installed.is_dir():
        raise FileNotFoundError(f"Install did not produce {sysroot_installed}")

    # Stage lxml runtime into the installed sysroot.
    lxml_mod.stage_lxml_runtime(repo_root, sysroot_installed)

    # --- Buildroot: build/dev dependencies ---
    buildroot_pkg = tmp_dir / "buildroot"
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

    # --- Sysroot: trimmed runtime stdlib (no tests) ---
    sysroot_pkg = tmp_dir / "sysroot"
    sysroot_lib = sysroot_pkg / "lib"
    sysroot_lib.mkdir(parents=True)

    py_lib = sysroot_installed / "lib" / config.PYTHON_LIB_DIR
    if py_lib.is_dir():
        shutil.copytree(py_lib, sysroot_lib / config.PYTHON_LIB_DIR)

    # Wrap in a staging dir for ramfs_mod.trim_sysroot (expects sysroot/ child).
    trim_wrap = tmp_dir / "_trim_wrap"
    trim_wrap.mkdir()
    # Move sysroot_pkg into trim_wrap/sysroot for trimming.
    sysroot_in_wrap = trim_wrap / "sysroot"
    sysroot_pkg.rename(sysroot_in_wrap)
    ramfs_mod.trim_sysroot(trim_wrap, keep_tests=False)
    # Move back.
    sysroot_in_wrap.rename(sysroot_pkg)
    shutil.rmtree(trim_wrap)

    # --- Include python.elf binary ---
    bin_dir = tmp_dir / "bin"
    python_elf = repo_root / f"python{config.EXE}"
    if python_elf.is_file():
        bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(python_elf, bin_dir / "python.elf")
        size = (bin_dir / "python.elf").stat().st_size
        print(f"  Included bin/python.elf ({size // 1024}K)")
    else:
        print(
            "  Warning: python.elf not found — binary will not be "
            "included in build output"
        )

    # --- Build ramfs image (no tests) ---
    ramfs_img = tmp_dir / "cpython-ramfs.img"
    # ramfs_mod.build_image expects staging/sysroot — re-wrap temporarily.
    ramfs_wrap = tmp_dir / "_ramfs_wrap"
    ramfs_wrap.mkdir()
    shutil.copytree(sysroot_pkg, ramfs_wrap / "sysroot")
    # Ensure /tmp exists in ramfs for tempfile.gettempdir().
    (ramfs_wrap / "sysroot" / "tmp").mkdir(exist_ok=True)
    ramfs_mod.build_image(ramfs_wrap, nanvix_home_path, ramfs_img)
    shutil.rmtree(ramfs_wrap)

    # --- Write manifest ---
    manifest = {
        "platform": platform,
        "process_mode": process_mode,
        "memory_size": memory_size,
        "install_prefix": install_prefix,
        "python_version": config.PYTHON_VERSION,
        "release": True,
    }
    manifest_path = tmp_dir / _MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # --- Remove temporary install tree (not part of output) ---
    shutil.rmtree(install_staging)

    # --- Atomic swap ---
    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.move(str(tmp_dir), str(output_dir))

    print("Build output ready:")
    print(f"  {output_dir / 'sysroot'}")
    print(f"  {output_dir / 'buildroot'}")
    print(f"  {output_dir / 'bin' / 'python.elf'}")
    print(f"  {output_dir / 'cpython-ramfs.img'}")

    return output_dir


# ---------------------------------------------------------------------------
# Release packaging (called by ./z release)
# ---------------------------------------------------------------------------


def package(
    repo_root: Path,
    *,
    platform: str = config.DEFAULT_PLATFORM,
    process_mode: str = config.DEFAULT_PROCESS_MODE,
    memory_size: str = config.DEFAULT_MEMORY_SIZE,
) -> None:
    """Package the build output into release archives.

    Reads from the persistent build output directory produced by
    ``./z build`` and creates:
    - On Linux: ``.tar.bz2`` archives in ``dist/``
    - On Windows: ``.zip`` archives in ``dist/``

    Raises FileNotFoundError if ./z build has not been run.
    Raises ValueError if the build output does not match the current config.
    """
    output_dir = build_output_path(repo_root)
    dist_dir = repo_root / "dist"
    artifact = _artifact_base(platform, process_mode, memory_size)

    # Validate build output exists.
    if not output_dir.is_dir():
        raise FileNotFoundError(
            f"Build output not found at {output_dir}. "
            "Run `./z build` first to produce release-ready artifacts."
        )

    # Validate manifest matches current config.
    manifest_path = output_dir / _MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Manifest not found at {manifest_path}. "
            "The build output may be corrupt. Run `./z build` again."
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest(manifest, platform, process_mode, memory_size)

    # Validate expected contents.
    sysroot_dir = output_dir / "sysroot"
    buildroot_dir = output_dir / "buildroot"
    bin_dir = output_dir / "bin"
    ramfs_img = output_dir / "cpython-ramfs.img"

    if not sysroot_dir.is_dir():
        raise FileNotFoundError(f"Sysroot directory missing: {sysroot_dir}")
    if not buildroot_dir.is_dir():
        raise FileNotFoundError(f"Buildroot directory missing: {buildroot_dir}")

    print("Packaging CPython release...")

    dist_dir.mkdir(parents=True, exist_ok=True)

    if config.IS_WINDOWS:
        _package_zip(dist_dir, artifact, sysroot_dir, buildroot_dir, bin_dir, ramfs_img)
    else:
        _package_tar(dist_dir, artifact, sysroot_dir, buildroot_dir, bin_dir, ramfs_img)

    print("Release archives created in dist/")
    for f in sorted(dist_dir.iterdir()):
        if f.name.startswith(artifact):
            size = f.stat().st_size
            print(f"  {f.name} ({size // 1024}K)")


def _validate_manifest(
    manifest: dict[str, object],
    platform: str,
    process_mode: str,
    memory_size: str,
) -> None:
    """Raise ValueError if manifest does not match the requested config."""
    mismatches: list[str] = []
    if manifest.get("platform") != platform:
        mismatches.append(
            f"platform: got '{manifest.get('platform')}', expected '{platform}'"
        )
    if manifest.get("process_mode") != process_mode:
        mismatches.append(
            f"process_mode: got '{manifest.get('process_mode')}', "
            f"expected '{process_mode}'"
        )
    if manifest.get("memory_size") != memory_size:
        mismatches.append(
            f"memory_size: got '{manifest.get('memory_size')}', "
            f"expected '{memory_size}'"
        )
    if mismatches:
        raise ValueError(
            "Build output does not match current configuration. "
            "Run `./z build` again.\n  " + "\n  ".join(mismatches)
        )


def _package_tar(
    dist_dir: Path,
    artifact: str,
    sysroot_dir: Path,
    buildroot_dir: Path,
    bin_dir: Path,
    ramfs_img: Path,
) -> None:
    """Create .tar.bz2 release archives."""
    # Sysroot tarball.
    sysroot_tar = dist_dir / f"{artifact}.tar.bz2"
    with tarfile.open(str(sysroot_tar), "w:bz2") as tf:
        tf.add(str(sysroot_dir), arcname="sysroot")
        if bin_dir.is_dir():
            tf.add(str(bin_dir), arcname="bin")
        if ramfs_img.is_file():
            tf.add(str(ramfs_img), arcname="cpython-ramfs.img")

    # Buildroot tarball (arcname="sysroot" for backward compatibility).
    buildroot_tar = dist_dir / f"{artifact}-buildroot.tar.bz2"
    with tarfile.open(str(buildroot_tar), "w:bz2") as tf:
        tf.add(str(buildroot_dir), arcname="sysroot")


def _package_zip(
    dist_dir: Path,
    artifact: str,
    sysroot_dir: Path,
    buildroot_dir: Path,
    bin_dir: Path,
    ramfs_img: Path,
) -> None:
    """Create .zip release archives."""
    # Sysroot zip.
    sysroot_zip_path = dist_dir / f"{artifact}.zip"
    with zipfile.ZipFile(str(sysroot_zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        _add_dir_to_zip(zf, sysroot_dir, "sysroot")
        if bin_dir.is_dir():
            _add_dir_to_zip(zf, bin_dir, "bin")
        if ramfs_img.is_file():
            zf.write(str(ramfs_img), "cpython-ramfs.img")

    # Buildroot zip (arcname prefix "sysroot" for backward compatibility).
    buildroot_zip_path = dist_dir / f"{artifact}-buildroot.zip"
    with zipfile.ZipFile(str(buildroot_zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        _add_dir_to_zip(zf, buildroot_dir, "sysroot")


def _add_dir_to_zip(zf: zipfile.ZipFile, src_dir: Path, arcname: str) -> None:
    """Recursively add a directory to a zip file."""
    for file_path in sorted(src_dir.rglob("*")):
        if file_path.is_file():
            rel = file_path.relative_to(src_dir)
            zf.write(str(file_path), f"{arcname}/{rel}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify(
    repo_root: Path,
    *,
    platform: str = config.DEFAULT_PLATFORM,
    process_mode: str = config.DEFAULT_PROCESS_MODE,
    memory_size: str = config.DEFAULT_MEMORY_SIZE,
) -> None:
    """Verify release archives.

    Checks that archives exist, are not corrupt, and contain the
    expected contents. Supports both .tar.bz2 and .zip formats.
    """
    artifact = _artifact_base(platform, process_mode, memory_size)
    dist_dir = repo_root / "dist"

    print("Verifying release archives...")

    # Determine format.
    sysroot_tar = dist_dir / f"{artifact}.tar.bz2"
    sysroot_zip = dist_dir / f"{artifact}.zip"
    buildroot_tar = dist_dir / f"{artifact}-buildroot.tar.bz2"
    buildroot_zip = dist_dir / f"{artifact}-buildroot.zip"

    if sysroot_tar.is_file():
        with tarfile.open(str(sysroot_tar), "r:bz2") as tf:
            members = tf.getnames()
        if not buildroot_tar.is_file():
            raise FileNotFoundError(f"Buildroot tarball not found: {buildroot_tar}")
        with tarfile.open(str(buildroot_tar), "r:bz2") as tf:
            _ = tf.getnames()
    elif sysroot_zip.is_file():
        with zipfile.ZipFile(str(sysroot_zip), "r") as zf:
            members = zf.namelist()
        if not buildroot_zip.is_file():
            raise FileNotFoundError(f"Buildroot zip not found: {buildroot_zip}")
        with zipfile.ZipFile(str(buildroot_zip), "r") as zf:
            _ = zf.namelist()
    else:
        raise FileNotFoundError(
            f"No release archive found for '{artifact}' in {dist_dir}. "
            "Expected .tar.bz2 or .zip files."
        )

    # Verify python.elf is present.
    if "bin/python.elf" not in members:
        raise ValueError("Release archive missing bin/python.elf")

    print("\t\t*** Package verification PASSED ***")

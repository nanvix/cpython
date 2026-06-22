# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Ramfs image generation for Nanvix CPython.

Replaces ramfs.mk. Provides sysroot trimming and ramfs image building
via mkramfs.elf.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from nanvix_zutil import paths

import config


def trim_sysroot(
    staging: Path,
    *,
    keep_tests: bool = False,
) -> None:
    """Strip dev-only artifacts from a staged sysroot for ramfs packaging.

    Args:
        staging: Sysroot/install-tree root directory (i.e. the directory
            containing ``bin/``, ``lib/``, ``include/``, …). Trimming is
            performed in place.
        keep_tests: When True, retain ``lib/python3.12/test/`` (needed
            when building a ramfs for the test pipeline).
    """
    if not staging.is_dir():
        raise FileNotFoundError(f"{staging} does not exist")

    print("Trimming sysroot for ramfs...")

    # Remove heavyweight stdlib packages not needed at runtime.
    for reldir in config.SYSROOT_TRIM_DIRS:
        p = staging / reldir
        if p.is_dir():
            shutil.rmtree(p)
        elif p.is_file():
            p.unlink()

    # Optionally remove tests.
    if not keep_tests:
        test_dir = staging / "lib" / config.PYTHON_LIB_DIR / "test"
        if test_dir.is_dir():
            shutil.rmtree(test_dir)

    # Remove static library.
    lib_a = staging / "lib" / f"libpython{config.PYTHON_VERSION}.a"
    if lib_a.is_file():
        lib_a.unlink()

    # Remove dev/config binaries from bin/.
    bin_dir = staging / "bin"
    if bin_dir.is_dir():
        for pattern in config.SYSROOT_TRIM_BIN_PATTERNS:
            for match in bin_dir.glob(pattern):
                match.unlink()
        # Remove all ELF binaries.
        for elf in bin_dir.glob("*.elf"):
            elf.unlink()
        # Remove host-native Windows binaries (nanvixd.exe, mkramfs.exe, …).
        # These are host tools, not guest binaries, and waste VM memory.
        for exe in bin_dir.glob("*.exe"):
            exe.unlink()
        # Remove bin/ if empty.
        try:
            bin_dir.rmdir()
        except OSError:
            pass

    # Remove __pycache__ directories.
    for cache_dir in staging.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)


def build_image(
    staging: Path,
    nanvix_home: Path,
    output: Path | None = None,
) -> Path:
    """Build a ramfs image from a trimmed sysroot.

    Args:
        staging: Sysroot/install-tree root directory to package (should
            be trimmed first via :func:`trim_sysroot`).
        nanvix_home: Path to the Nanvix sysroot (contains
            ``bin/mkramfs.elf`` or ``bin/mkramfs.exe``).
        output: Output path for the ramfs image.

    Returns:
        Path to the generated ramfs image.

    Raises:
        ValueError: If *output* is not provided.
    """
    if output is None:
        raise ValueError("output path is required for build_image()")

    mkramfs_name = config.mkramfs_binary()
    mkramfs = nanvix_home / "bin" / mkramfs_name
    if not mkramfs.is_file():
        raise FileNotFoundError(
            f"{mkramfs_name} not found at {mkramfs}. "
            "Run `./z setup` to download required binaries."
        )

    # Create a temporary image, then move it into place. Prevents cycles.
    if not staging.is_dir():
        raise FileNotFoundError(f"{staging} does not exist")
    prog = [str(mkramfs), "-o", str(paths.out_dir() / "tmp.img"), str(staging)]
    subprocess.run(
        prog,
        check=True,
    )
    shutil.move(paths.out_dir() / "tmp.img", output)

    size = output.stat().st_size
    human = _human_size(size)
    print(f"Built ramfs image: {output} ({human})")
    return output


def trim_and_build(
    staging: Path,
    nanvix_home: Path,
    output: Path | None = None,
    *,
    keep_tests: bool = False,
) -> Path:
    """Convenience: trim sysroot then build ramfs image."""
    trim_sysroot(staging, keep_tests=keep_tests)
    return build_image(staging, nanvix_home, output)


def _human_size(nbytes: int) -> str:
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

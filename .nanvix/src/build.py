# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Build orchestration for Nanvix CPython cross-compilation.

Replaces the ``_run_make`` / ``_make_args`` pattern from z.py and the
build/install/clean targets from common.mk. Constructs and executes
``make -f Makefile.nanvix`` commands with correct variables.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
from pathlib import Path

from nanvix_zutil import paths

import src._docker as docker_mod
import src.test as test_mod
import src.config as config
import src.lxml as lxml_mod
from src.lib import MakeArgs


def build(
    args: MakeArgs,
) -> None:
    """Cross-compile python for Nanvix and install into the appropriate output tree.

    Installs into ``paths.regular_out()`` for release builds and
    ``paths.test_out()`` for non-release builds; non-release builds also
    stage test fixtures via ``_test.stage()``.
    """
    _args = dataclasses.replace(args, targets=["build"])
    dest_dir = paths.regular_out() if args.release else paths.test_out()
    if config.requires_isolated_workspace(paths.repo_root()):
        # Build and install in one Docker invocation on a case-sensitive volume.
        # This is required on Windows and Windows-mounted WSL worktrees, where
        # the `python` output collides with CPython's `Python/` source directory.
        docker_mod.docker_build(paths.repo_root(), args, install_destdir=dest_dir)
    else:
        buildroot_for_setup = (
            Path(config.DOCKER_SYSROOT_PATH) if _args.docker else args.buildroot
        )
        lxml_mod.generate_setup_local(paths.repo_root(), buildroot_for_setup)
        _args.run(cwd=paths.repo_root())
        install(dest_dir, args)

    if not args.release:
        test_mod.stage(args)


def install(
    destdir: Path,
    args: MakeArgs,
    *,
    extra_make_flags: list[str] | None = None,
) -> None:
    """Install CPython into a staging directory (native host only).

    Windows/Docker installs happen inside :func:`_docker.docker_build`
    via ``install_destdir=``; this helper is never reached there.
    """
    # Use a relative DESTDIR so it resolves the same way whether the
    # caller runs make directly or under a wrapper.
    try:
        rel_destdir = destdir.resolve().relative_to(paths.repo_root())
    except ValueError:
        rel_destdir = destdir
    targets = [*(extra_make_flags or []), "install", f"DESTDIR={rel_destdir}"]
    _args = dataclasses.replace(args, targets=targets)
    _args.run(cwd=paths.repo_root())


def clean(preserve_nanvix_root: bool = False, preserve_cache: bool = False) -> None:
    """Remove build artifacts."""
    for name in (".nanvix-configured", *config.DOCKER_OUTPUT_FILES):
        p = paths.repo_root() / name
        if p.is_file():
            p.unlink()
            print(f"Removed {name}")

    if not preserve_nanvix_root:
        if not preserve_cache:
            for name in ("cache", "_benchmark_cache"):
                p = paths.nanvix_root() / name
                if p.is_dir():
                    shutil.rmtree(p)
                    print(f"Removed {name}")

        if paths.out_dir().is_dir():
            shutil.rmtree(paths.out_dir())
            print(f"Removed {paths.out_dir().relative_to(paths.repo_root())}")

    if not config.requires_isolated_workspace(paths.repo_root()):
        subprocess.run(
            ["make", "-f", "Makefile.nanvix", "clean"],
            cwd=paths.repo_root(),
            check=False,
        )
    else:
        docker_mod.remove_build_volume(paths.repo_root())

# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Build orchestration for Nanvix CPython cross-compilation.

Replaces the ``_run_make`` / ``_make_args`` pattern from z.py and the
build/install/clean targets from common.mk. Constructs and executes
``make -f Makefile.nanvix`` commands with correct variables.
"""

from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
from pathlib import Path
from typing import Any

from nanvix_zutil import paths

import _docker as docker_mod
import config
import lxml as lxml_mod


@dataclass
class MakeArgs:
    """
    Common arguments passed to Makefile.nanvix.
    """

    toolchain_path: Path
    release: bool
    targets: list[str]
    platform: str = config.DEFAULT_PLATFORM
    process_mode: str = config.DEFAULT_PROCESS_MODE
    memory_size: str = config.DEFAULT_MEMORY_SIZE
    install_prefix: str = config.DEFAULT_INSTALL_PREFIX
    sysroot: Path = paths.nanvix_root() / "sysroot"
    run_fn: Any = None
    docker: bool = False

    def to_list(self) -> list[str]:
        """Convert to a list suitable to pass to a process runner."""
        nanvix_toolchain = (
            Path(config.DOCKER_TOOLCHAIN_PATH) if self.docker else self.toolchain_path
        )
        nanvix_home = Path(config.DOCKER_SYSROOT_PATH) if self.docker else self.sysroot
        return [
            "make",
            "-f",
            "Makefile.nanvix",
            f"CONFIG_NANVIX=y",
            f"NANVIX_HOME={nanvix_home}",
            f"NANVIX_TOOLCHAIN={nanvix_toolchain}",
            f"PLATFORM={self.platform}",
            f"PROCESS_MODE={self.process_mode}",
            f"MEMORY_SIZE={self.memory_size}",
            f"INSTALL_PREFIX={self.install_prefix}",
            f"NANVIX_RELEASE={'yes' if self.release else 'no'}",
            *self.targets,
        ]

    def to_string(self) -> str:
        import shlex

        return shlex.join(self.to_list())

    def run(self, *, cwd: Path | None = None):
        """Execute a make command.
        Args:
            cwd: Working directory.
        """
        if self.run_fn:
            self.run_fn(*self.to_list(), cwd=cwd)
        else:
            subprocess.run(self.to_list(), cwd=cwd, check=True)

    def asset_prefix(self) -> str:
        return f"cpython-{self.platform}-{self.process_mode}-{self.memory_size}"


def build(
    args: MakeArgs,
) -> None:
    """Cross-compile python.elf for Nanvix."""
    if config.IS_WINDOWS:
        # Build and install in one Docker invocation so the install tree
        # is cached for later use by ``./z test`` (no Docker during tests).
        install_cache = paths.nanvix_root() / "_install_cache"
        args.install_prefix = str(install_cache)
        docker_mod.docker_build(paths.repo_root(), args)
        return
    sysroot_for_setup = Path(config.DOCKER_SYSROOT_PATH) if args.docker else args.sysroot
    lxml_mod.generate_setup_local(paths.repo_root(), sysroot_for_setup)
    args.targets = ["build"]
    args.run(cwd=paths.repo_root())


def install(
    destdir: Path,
    args: MakeArgs,
    *,
    extra_make_flags: list[str] | None = None,
) -> None:
    """Install CPython into a staging directory."""
    if config.IS_WINDOWS:
        docker_mod.docker_install(paths.repo_root(), destdir, args)
        return
    # When running inside Docker, repo_root maps to /mnt/workspace.
    # Use a relative DESTDIR so it resolves correctly inside the container.
    try:
        rel_destdir = destdir.resolve().relative_to(paths.repo_root())
    except ValueError:
        rel_destdir = destdir
    args.targets = [*(extra_make_flags or []), "install", f"DESTDIR={rel_destdir}"]
    args.run(cwd=paths.repo_root())


def clean() -> None:
    """Remove build artifacts."""
    if config.IS_WINDOWS:
        for name in (".nanvix-configured", "python.elf", "python.exe"):
            p = paths.repo_root() / name
            if p.is_file():
                p.unlink()
                print(f"Removed {name}")
        for name in ("_test_staging", "staging", "_install_cache", "_ramfs_cache"):
            p = paths.repo_root() / ".nanvix" / name
            if p.is_dir():
                shutil.rmtree(p)
                print(f"Removed .nanvix/{name}/")
    else:
        subprocess.run(
            ["make", "-f", "Makefile.nanvix", "clean"],
            cwd=paths.repo_root(),
            check=False,
        )

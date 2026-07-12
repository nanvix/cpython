# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Build orchestration for Nanvix CPython cross-compilation.

Replaces the ``_run_make`` / ``_make_args`` pattern from z.py and the
build/install/clean targets from common.mk. Constructs and executes
``make -f Makefile.nanvix`` commands with correct variables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import dataclasses
import shutil
import subprocess
from pathlib import Path
from typing import Any

from nanvix_zutil import paths

import _docker as docker_mod
import _test as test_mod
import config
import lxml as lxml_mod


@dataclass
class MakeArgs:
    """
    Common arguments passed to Makefile.nanvix.
    """

    release: bool
    targets: list[str]
    platform: str = config.DEFAULT_PLATFORM
    process_mode: str = config.DEFAULT_PROCESS_MODE
    memory_size: str = config.DEFAULT_MEMORY_SIZE
    install_prefix: str = config.DEFAULT_INSTALL_PREFIX
    sysroot: Path = field(default_factory=lambda: paths.sysroot())
    buildroot: Path = field(default_factory=lambda: paths.buildroot())
    run_fn: Any = None
    docker: bool = False

    def to_list(self) -> list[str]:
        """Convert to a list suitable to pass to a process runner."""
        buildroot = (
            config.DOCKER_BUILDROOT_PATH if self.docker else self.buildroot.resolve()
        )
        return [
            "make",
            "-f",
            "Makefile.nanvix",
            f"CONFIG_NANVIX=y",
            f"NANVIX_SDK_ROOT={config.DOCKER_SDK_PATH}",
            f"NANVIX_BUILDROOT={buildroot}",
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
    """Cross-compile python for Nanvix and install into the appropriate output tree.

    Installs into ``paths.release_dir()`` for release builds and
    ``paths.test_out()`` for non-release builds; non-release builds also
    stage test fixtures via ``_test.stage()``.
    """
    _args = dataclasses.replace(args, targets=["build"])
    dest_dir = (
        (paths.release_dir() / config.PKG_SYSROOT) if args.release else paths.test_out()
    )
    if config.IS_WINDOWS:
        # Build and install in one Docker invocation, writing directly to
        # release_dir/test_out so ``./z test`` needs no further Docker work.
        docker_mod.docker_build(paths.repo_root(), args, install_destdir=dest_dir)
    else:
        buildroot_for_setup = (
            Path(config.DOCKER_BUILDROOT_PATH) if _args.docker else args.buildroot
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

    if not config.IS_WINDOWS:
        subprocess.run(
            ["make", "-f", "Makefile.nanvix", "clean"],
            cwd=paths.repo_root(),
            check=False,
        )

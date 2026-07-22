# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Shared state + helpers for the CPython ZScript.

:class:`LibMixin` owns the :class:`MakeArgs` used by every lifecycle
stage.  Callers assign ``self.args = self.make_args(release=..., ...)``
once per phase and then invoke ``self.stage()`` /
``self.run_nanvixd_script(...)`` etc. directly, so ``MakeArgs`` does
not have to be threaded through every helper signature.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nanvix_zutil import (
    CFG_SYSROOT,
    EXIT_MISSING_DEP,
    ZScript,
    log,
    paths,
    run,
)

import src.config as config

__all__ = ("CFG_LOCAL_NANVIX", "LibMixin", "MakeArgs")

# Config key for persisting the --with-nanvix path in env.json.
CFG_LOCAL_NANVIX = "local_nanvix_path"


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
    buildroot: Path = field(default_factory=lambda: paths.sysroot())
    run_fn: Any = None
    docker: bool = False

    def to_list(self) -> list[str]:
        """Convert to a list suitable to pass to a process runner."""
        buildroot = (
            config.DOCKER_SYSROOT_PATH if self.docker else self.buildroot.resolve()
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


class LibMixin(ZScript):
    """Shared state + helpers for CPython lifecycle mixins."""

    SYSROOT_REQUIRED_FILES: tuple[str, ...] = (
        "bin/nanvixd.elf",
        "bin/kernel.elf",
        "bin/mkramfs.elf",
    )
    SYSROOT_REQUIRED_FILES_WINDOWS: tuple[str, ...] = (
        "bin/nanvixd.exe",
        "bin/kernel.elf",
        "bin/mkramfs.exe",
    )

    # Populated lazily via the ``args`` property; lifecycle mixins that
    # need a variant (release / docker) assign to ``self.args`` directly.
    _args: MakeArgs | None = None

    # ------------------------------------------------------------------
    # Make args
    # ------------------------------------------------------------------

    @property
    def args(self) -> MakeArgs:
        """The current :class:`MakeArgs`.

        Lazily initialised via ``self.make_args(release=False,
        with_docker=False)`` on first read, so the default requires a
        configured runtime sysroot (``./z setup`` first). Lifecycle
        methods that need a variant assign ``self.args =
        self.make_args(...)`` before invoking helpers.
        """
        if self._args is None:
            self._args = self.make_args(release=False, with_docker=False)
        return self._args

    @args.setter
    def args(self, value: MakeArgs) -> None:
        self._args = value

    def make_args(
        self,
        *targets: str,
        release: bool = False,
        with_docker: bool = False,
    ) -> MakeArgs:
        """Construct a fresh :class:`MakeArgs` from ``self.config``.

        Docker is build-only (see zutils#224 / #666). Callers other than
        ``build()`` MUST leave ``with_docker=False``; ``self.docker`` is
        ignored for those steps.
        """
        sysroot = self._get_host_sysroot()
        use_docker = with_docker and self.docker is not None
        return MakeArgs(
            sysroot=sysroot,
            buildroot=paths.sysroot(),
            targets=list(targets),
            platform=self.config.machine,
            process_mode=self.config.deployment_mode,
            memory_size=self.config.memory_size,
            install_prefix=config.DEFAULT_INSTALL_PREFIX,
            release=release,
            docker=use_docker,
            run_fn=(
                (lambda *a, **kw: run(*a, docker=self.docker, **kw))  # type: ignore[assignment]
                if use_docker
                else None
            ),
        )

    # ------------------------------------------------------------------
    # Sysroot overlay
    # ------------------------------------------------------------------

    def _overlay_local_nanvix(self) -> None:
        """Re-overlay local Nanvix runtime binaries into the runtime sysroot.

        Called before build/test/release so that local changes are
        picked up even after the initial ``setup()`` run.  Reads the
        ``WITH_NANVIX`` environment variable (set by ``z.sh``) or falls
        back to the path persisted in ``.nanvix/env.json``.

        Build-time headers and libraries intentionally remain owned by the SDK
        and the sysroot.
        """
        nanvix_path = os.environ.get("WITH_NANVIX") or self.config.get(
            CFG_LOCAL_NANVIX, ""
        )
        if not nanvix_path:
            return

        nanvix_path = os.path.abspath(os.path.expanduser(nanvix_path))
        if not os.path.isdir(nanvix_path):
            log.warning(f"--with-nanvix path no longer exists: {nanvix_path}")
            return

        # Persist so subsequent commands reuse the same path.
        if self.config.get(CFG_LOCAL_NANVIX, "") != nanvix_path:
            self.config.set(CFG_LOCAL_NANVIX, nanvix_path)
            self.config.save()

        sysroot = self.config.get(CFG_SYSROOT, "")
        if not sysroot:
            return

        source = Path(nanvix_path) / "bin"
        if not source.is_dir():
            log.warning(f"No bin/ runtime artifacts found in {nanvix_path}")
            return

        destination = Path(sysroot) / "bin"
        destination.mkdir(parents=True, exist_ok=True)
        count = 0
        for artifact in source.iterdir():
            if artifact.is_file():
                shutil.copy2(artifact, destination / artifact.name)
                count += 1
        log.info(f"Overlaid {count} local runtime artifact(s) from {nanvix_path}")

    def _get_host_sysroot(self) -> Path:
        """Return the configured runtime sysroot host path."""
        sysroot = self.config.get(CFG_SYSROOT, "")
        if not sysroot:
            log.fatal(
                f"{CFG_SYSROOT} is not set.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` first to download the sysroot.",
            )
        return Path(sysroot)

# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Build lifecycle for the CPython ZScript.

Owns ``./z build`` (:class:`BuildMixin`), the ``docker_config`` override,
and the make/install/clean orchestration helpers that used to live
under ``_run_make`` in z.py.
"""

from __future__ import annotations

from pathlib import Path

from nanvix_zutil import DockerConfig, EXIT_INVALID_ARGS, log, paths

import src._docker as docker_mod
import src.config as config
import src.lxml as lxml_mod
import src.package as package_mod
import src.ramfs as ramfs_mod
from src.lib import MakeArgs
from src.clean import CleanMixin

__all__ = ("BuildMixin", "MakeArgs")


class BuildMixin(CleanMixin):
    """``./z build`` — cross-compile python.elf and libpython.a for Nanvix."""

    def docker_config(self, image: str) -> DockerConfig:
        """Configure the immutable SDK container and repository-local temp paths."""
        if image != config.DOCKER_IMAGE:
            log.fatal(
                f"Unsupported SDK image: {image}",
                code=EXIT_INVALID_ARGS,
                hint=f"Use the pinned SDK image: {config.DOCKER_IMAGE}",
            )
        container_home = paths.nanvix_root() / "container-home"
        container_tmp = paths.nanvix_root() / "container-tmp"
        container_home.mkdir(parents=True, exist_ok=True)
        container_tmp.mkdir(parents=True, exist_ok=True)
        docker = super().docker_config(image)
        docker.extra_env.update(
            {
                "HOME": f"{config.DOCKER_WORKSPACE_PATH}/.nanvix/container-home",
                "TMPDIR": f"{config.DOCKER_WORKSPACE_PATH}/.nanvix/container-tmp",
            }
        )
        return docker

    def build(self) -> None:
        """Cross-compile python.elf and libpython.a for Nanvix."""

        # Two separate builds: first release -> out/release/, then test -> out/test/.
        self.args = self.make_args(release=True, with_docker=True)
        self.clean_impl(preserve_nanvix_root=False, preserve_cache=True)
        self._run_build()
        lxml_mod.stage_lxml_runtime(package_mod.sysroot_pkg())
        package_mod.stage()
        ramfs_mod.build_image(
            package_mod.sysroot_pkg(),
            self.args.sysroot,
            package_mod.sysroot_pkg() / "cpython-ramfs.img",
        )

        # Build for test
        self.args = self.make_args(release=False, with_docker=True)
        self.clean_impl(preserve_nanvix_root=True, preserve_cache=True)
        self._run_build()
        self.stage()
        lxml_mod.stage_lxml_runtime(paths.test_out())
        self.stage_ramfs()

    def _run_build(
        self,
    ) -> None:
        """Cross-compile python for Nanvix and install into the appropriate output tree.

        Installs into ``paths.regular_out()`` for release builds and
        ``paths.test_out()`` for non-release builds; the caller
        (:meth:`BuildMixin.build`) invokes ``self.stage()`` afterwards for
        non-release builds.
        """
        self.args.targets = ["build"]
        dest_dir = paths.regular_out() if self.args.release else paths.test_out()
        if config.requires_isolated_workspace(paths.repo_root()):
            # Build and install in one Docker invocation on a case-sensitive volume.
            # This is required on Windows and Windows-mounted WSL worktrees, where
            # the `python` output collides with CPython's `Python/` source directory.
            docker_mod.docker_build(
                paths.repo_root(), self.args, install_destdir=dest_dir
            )
        else:
            buildroot_for_setup = (
                Path(config.DOCKER_SYSROOT_PATH)
                if self.args.docker
                else self.args.buildroot
            )
            lxml_mod.generate_setup_local(paths.repo_root(), buildroot_for_setup)
            self.args.run(cwd=paths.repo_root())
            self._install(dest_dir)

    def _install(
        self,
        destdir: Path,
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
        self.args.targets = targets
        self.args.run(cwd=paths.repo_root())

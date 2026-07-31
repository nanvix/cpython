# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Build lifecycle for the CPython ZScript.

Owns ``./z build`` (:class:`BuildMixin`), the ``docker_config`` override,
and the make/install/clean orchestration helpers that used to live
under ``_run_make`` in z.py.
"""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

from nanvix_zutil import DockerConfig, paths

import src.config as config
import src.lxml as lxml_mod
import src.package as package_mod
import src.ramfs as ramfs_mod
from src.lib import MakeArgs
from src.clean import CleanMixin

__all__ = ("BuildMixin", "MakeArgs")


class BuildMixin(CleanMixin):
    """``./z build`` — cross-compile python.elf and libpython.a for Nanvix."""

    def build(self, docker: DockerConfig) -> None:
        """Cross-compile python.elf and libpython.a for Nanvix."""
        # Docker is scoped to build (zutils#235). Apply CPython's isolated
        # tar-copy customisations to the config we were handed and stash it
        # so the shared helpers (make_args, _docker_build) can reach it.
        # Per-phase copy-back outputs (DESTDIR install tree) are set in
        # ``_docker_build`` because the destination differs per build.
        docker.tar_excludes = config.DOCKER_TAR_EXCLUDES
        docker.crlf_files = config.DOCKER_CRLF_FILES
        docker.persistent_volume = True
        docker.clean_cmd = (
            "make -f Makefile.nanvix clean 2>/dev/null || true; "
            "rm -f .nanvix-configured"
        )
        # HOME (=/tmp) is provided by zutils. TMPDIR must resolve in both the
        # isolated (/tmp/build) and non-isolated (/mnt/workspace) paths, so use
        # /tmp, which the container always provides.
        docker.extra_env.update({"TMPDIR": "/tmp"})
        self.docker = docker

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
            # Build + install in one isolated container invocation on a
            # case-sensitive volume. Required on Windows and case-insensitive
            # worktrees, where the `python` output collides with CPython's
            # `Python/` source directory. zutils handles source sync, CRLF,
            # the build volume, invalidation, and copy-back.
            self._docker_build(dest_dir)
        else:
            buildroot_for_setup = (
                Path(config.DOCKER_SYSROOT_PATH)
                if self.args.docker
                else self.args.buildroot
            )
            lxml_mod.generate_setup_local(paths.repo_root(), buildroot_for_setup)
            self.args.run(cwd=paths.repo_root())
            self._install(dest_dir)

    def _docker_build(self, dest_dir: Path) -> None:
        """Build and install CPython in one isolated tar-copy container run.

        Configures the copy-back outputs for this phase, generates
        ``Setup.local`` on the host (synced into the volume), then runs the
        fused build+install pipeline via zutils' isolated Docker path.
        """
        assert self.docker is not None
        repo = paths.repo_root()
        # Setup.local references the container-side buildroot (synced in).
        lxml_mod.generate_setup_local(repo, Path(config.DOCKER_SYSROOT_PATH))
        try:
            rel_dest = dest_dir.resolve().relative_to(repo).as_posix()
        except ValueError:
            rel_dest = dest_dir.name
        # The build dir mirrors the workspace, so every output copies back at
        # its own relative path. The install tree is staged directly at the
        # destination path (dir output); the loose files copy back verbatim.
        self.docker.output_files = [*config.DOCKER_OUTPUT_FILES, rel_dest]
        cmd = self.docker.build_windows_run_cmd(
            "sh", "-c", self._fused_build_cmd(rel_dest)
        )
        subprocess.run(cmd, check=True)

    def _fused_build_cmd(self, rel_dest: str) -> str:
        """Build the single shell pipeline run inside the isolated container.

        A fused build+install is required because the source sync is a single
        rsync/tar pass: splitting the phases across container runs would
        re-sync (and could disturb) build state between them.
        """
        assert self.docker is not None
        strip = f"{config.DOCKER_SDK_PATH}/bin/llvm-strip"
        # Stage the install tree at its mirrored destination inside the build
        # dir, so zutils copies it straight back to the workspace.
        staging = f"{self.docker.container_build_dir}/{rel_dest}"
        build_str = dataclasses.replace(self.args, targets=["build"]).to_string()
        install_str = dataclasses.replace(
            self.args, targets=["install", f"DESTDIR={staging}"]
        ).to_string()
        install_bin = (
            f"{staging}{self.args.install_prefix}/bin/{config.python_binary()}"
        )
        strip_build = (
            f"for f in python python{config.EXE}; do "
            f'[ -f "$f" ] && "{strip}" --strip-all "$f" || true; done'
        )
        strip_install = (
            f'{{ [ -f "{install_bin}" ] && "{strip}" --strip-all "{install_bin}" '
            f"|| true; }}"
        )
        return (
            f'{build_str} && {strip_build} && rm -rf "{staging}" && '
            f"{install_str} && {strip_install}"
        )

    def _install(
        self,
        destdir: Path,
        *,
        extra_make_flags: list[str] | None = None,
    ) -> None:
        """Install CPython into a staging directory (native host only).

        Windows/Docker installs happen inside :meth:`_docker_build` as part
        of the fused build+install pipeline; this helper is never reached
        there.
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

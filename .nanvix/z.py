# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Nanvix build script for CPython.

Usage:
    ./z setup      # Download Nanvix sysroot and dependencies
    ./z build      # Cross-compile python.elf and libpython.a
    ./z test       # Run test suite (hello-world on nanvixd.elf)
    ./z benchmark  # Run hello-world benchmark with release ramfs
    ./z release    # Package release tarballs (sysroot + buildroot)
    ./z clean      # Remove build artifacts

Options:
    --with-nanvix PATH  Use local Nanvix binaries from PATH instead of
                        the downloaded sysroot binaries. PATH should point
                        to a Nanvix build directory containing bin/ and lib/.
                        The path is persisted in .nanvix/env.json, so it
                        only needs to be passed once. Pass again to change
                        it. Works on both Linux and Windows.
"""

import os
import shutil
import tarfile
import zipfile
from pathlib import Path

from nanvix_zutil import paths

import _test as test_mod
import build as build_mod
import lxml as lxml_mod
import config
import package as package_mod
import ramfs as ramfs_mod
from nanvix_zutil import (
    CFG_SYSROOT,
    DockerConfig,
    EXIT_INVALID_ARGS,
    EXIT_MISSING_DEP,
    ZScript,
    log,
    run,
)
from nanvix_zutil.paths import nanvix_root

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

# Makefile variable names (build-system-specific).
_MAKE_VAR_CONFIG = "CONFIG_NANVIX"
_MAKE_VAR_PLATFORM = "PLATFORM"
_MAKE_VAR_PROCESS_MODE = "PROCESS_MODE"
_MAKE_VAR_MEMORY_SIZE = "MEMORY_SIZE"
_MAKE_VAR_INSTALL_PREFIX = "INSTALL_PREFIX"

# CPython embeds --prefix into the binary (sys.prefix, sys.path).
_DEFAULT_INSTALL_PREFIX = config.DEFAULT_INSTALL_PREFIX

# Config key for persisting the --with-nanvix path in env.json.
_CFG_LOCAL_NANVIX = "local_nanvix_path"


class CPythonBuild(ZScript):
    """Build script for nanvix/cpython."""

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

    def release_targets(self) -> dict[str, str]:
        name = (
            f"{self.manifest.name}"
            f"-{self.config.machine}"
            f"-{self.config.deployment_mode}"
            f"-{self.config.memory_size}"
        )
        return {
            config.PKG_SYSROOT: f"{name}",
            config.PKG_BUILDROOT: f"{name}-buildroot",
        }

    # ---- Local Nanvix overlay --------------------------------------------

    def _overlay_local_nanvix(self) -> None:
        """Re-overlay local Nanvix runtime binaries into the runtime sysroot.

        Called before build/test/release so that local changes are
        picked up even after the initial ``setup()`` run.  Reads the
        ``WITH_NANVIX`` environment variable (set by ``z.sh``) or falls
        back to the path persisted in ``.nanvix/env.json``.

        Build-time headers and libraries intentionally remain owned by the SDK
        and dependency buildroot.
        """
        nanvix_path = os.environ.get("WITH_NANVIX") or self.config.get(
            _CFG_LOCAL_NANVIX, ""
        )
        if not nanvix_path:
            return

        nanvix_path = os.path.abspath(os.path.expanduser(nanvix_path))
        if not os.path.isdir(nanvix_path):
            log.warning(f"--with-nanvix path no longer exists: {nanvix_path}")
            return

        # Persist so subsequent commands reuse the same path.
        if self.config.get(_CFG_LOCAL_NANVIX, "") != nanvix_path:
            self.config.set(_CFG_LOCAL_NANVIX, nanvix_path)
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

    # ---- Common helpers --------------------------------------------------

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

    def _make_args(
        self,
        *targets: str,
        release: bool = False,
        with_docker: bool = False,
    ) -> build_mod.MakeArgs:
        """Build the make argument list for configure/build/install.

        Docker is build-only (see zutils#224 / #666). Callers other than
        ``build()`` MUST leave ``with_docker=False``; ``self.docker`` is
        ignored for those steps.
        """
        sysroot = self._get_host_sysroot()
        use_docker = with_docker and self.docker is not None
        return build_mod.MakeArgs(
            sysroot=sysroot,
            buildroot=paths.buildroot(),
            targets=list(targets),
            platform=self.config.machine,
            process_mode=self.config.deployment_mode,
            memory_size=self.config.memory_size,
            install_prefix=_DEFAULT_INSTALL_PREFIX,
            release=release,
            docker=use_docker,
            run_fn=(
                (lambda *args, **kw: run(*args, docker=self.docker, **kw))  # type: ignore[assignment]
                if use_docker
                else None
            ),
        )

    def setup(self) -> bool:
        """Download the Nanvix sysroot and dependencies.

        Downloads a runtime-only sysroot and installs build-time dependencies
        into the separate buildroot.
        """
        # Base class handles: sysroot download, WITH_NANVIX overlay,
        # dependency installation, Windows binaries, and verification.
        if self._with_nanvix_path:
            local_nanvix = os.path.abspath(os.path.expanduser(self._with_nanvix_path))
            self.config.set(_CFG_LOCAL_NANVIX, local_nanvix)

        used_fallback = super().setup()
        sysroot = self.config.get(CFG_SYSROOT, "")
        if sysroot:
            sysroot_path = Path(sysroot)
            for build_dir in ("include", "lib"):
                path = sysroot_path / build_dir
                if path.is_dir():
                    shutil.rmtree(path)

        self._install_lxml_runtime_payload()
        self._overlay_local_nanvix()
        self.config.save()
        return used_fallback

    def build(self) -> None:
        """Cross-compile python.elf and libpython.a for Nanvix."""
        self._overlay_local_nanvix()

        # Two separate builds: first release -> out/release/, then test -> out/test/.
        build_mod.clean(preserve_nanvix_root=False, preserve_cache=True)
        args = self._make_args(release=True, with_docker=True)
        build_mod.build(args)
        lxml_mod.stage_lxml_runtime(package_mod.sysroot_pkg())
        package_mod.stage()
        ramfs_mod.build_image(
            package_mod.sysroot_pkg(),
            args.sysroot,
            package_mod.sysroot_pkg() / "cpython-ramfs.img",
        )

        # Build for test
        build_mod.clean(preserve_nanvix_root=True, preserve_cache=True)
        args = self._make_args(release=False, with_docker=True)
        build_mod.build(args)
        lxml_mod.stage_lxml_runtime(paths.test_out())
        test_mod.stage_ramfs(args)

    def test(self) -> None:
        """Run the CPython test suite (hello + regrtest)."""
        self._overlay_local_nanvix()
        args = self._make_args(release=False)
        nanvixd_extra = ["-allow-host-networking"]

        ramfs_img = paths.test_out() / "cpython-rootfs.img"

        test_mod.run_all(args, nanvixd_extra=nanvixd_extra, ramfs_img=ramfs_img)

    def benchmark(self) -> None:
        """Run hello-world benchmark with a release-style ramfs."""
        self._overlay_local_nanvix()
        nanvixd_extra = ["-allow-host-networking"]
        args = self._make_args(release=False)
        test_mod.run_benchmark(
            args,
            nanvixd_extra=nanvixd_extra,
        )

    def clean(self) -> None:
        """Remove build artifacts."""
        build_mod.clean()

    @staticmethod
    def _python_package_path(member_name: str) -> Path | None:
        """Return a safe path below an archive's ``python-packages`` directory."""
        parts = Path(member_name).parts
        try:
            package_index = parts.index("python-packages")
        except ValueError:
            return None
        relative = Path(*parts[package_index + 1 :])
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            return None
        return relative

    def _install_lxml_runtime_payload(self) -> None:
        """Install the exact lxml release's Python payload into the buildroot."""
        cache_dir = nanvix_root() / "cache"
        candidates = (
            list(cache_dir.glob(f"lxml-{self.config.machine}-*"))
            if cache_dir.is_dir()
            else []
        )
        if not candidates:
            raise FileNotFoundError(
                "lxml release archive is missing from .nanvix/cache"
            )

        archive = max(candidates, key=lambda path: path.stat().st_mtime_ns)
        destination = nanvix_root() / "buildroot" / "python-packages"
        if destination.is_dir():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)

        installed = 0
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as source:
                for member in source.infolist():
                    relative = self._python_package_path(member.filename)
                    if relative is None or member.is_dir():
                        continue
                    output = destination / relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(member) as src, output.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    installed += 1
        else:
            with tarfile.open(archive, "r:*") as source:
                for member in source.getmembers():
                    relative = self._python_package_path(member.name)
                    if relative is None or not member.isfile():
                        continue
                    extracted = source.extractfile(member)
                    if extracted is None:
                        continue
                    output = destination / relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with extracted, output.open("wb") as dst:
                        shutil.copyfileobj(extracted, dst)
                    installed += 1

        if installed == 0:
            raise RuntimeError(f"{archive.name} contains no python-packages payload")
        log.info(f"Installed {installed} lxml runtime file(s) from {archive.name}")


if __name__ == "__main__":
    CPythonBuild.main()

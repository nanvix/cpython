# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Nanvix build script for CPython.

Usage:
    ./z setup      # Download Nanvix sysroot and dependencies
    ./z build      # Cross-compile python.elf and libpython.a
    ./z test       # Run test suite (hello-world on nanvixd.elf)
    ./z benchmark  # Run hello-world benchmark with release ramfs
    ./z release    # Package release tarballs
    ./z clean      # Remove build artifacts

Options:
    --with-nanvix PATH  Use local Nanvix binaries from PATH instead of
                        the downloaded sysroot binaries. PATH should point
                        to a Nanvix build directory containing bin/ and lib/.
                        The path is persisted in .nanvix/env.json, so it
                        only needs to be passed once. Pass again to change
                        it. Works on both Linux and Windows.
"""

from nanvix_zutil import paths

import src.test as test_mod
import src.build as build_mod
import src.lxml as lxml_mod
import src.config as config
import src.package as package_mod
import src.ramfs as ramfs_mod
from nanvix_zutil import (
    DockerConfig,
    EXIT_INVALID_ARGS,
    log,
)

from src.setup import SetupMixin

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

# Makefile variable names (build-system-specific).
_MAKE_VAR_CONFIG = "CONFIG_NANVIX"
_MAKE_VAR_PLATFORM = "PLATFORM"
_MAKE_VAR_PROCESS_MODE = "PROCESS_MODE"
_MAKE_VAR_MEMORY_SIZE = "MEMORY_SIZE"
_MAKE_VAR_INSTALL_PREFIX = "INSTALL_PREFIX"


class CPythonBuild(SetupMixin):
    """Build script for nanvix/cpython."""

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
        self._overlay_local_nanvix()

        # Two separate builds: first release -> out/release/, then test -> out/test/.
        build_mod.clean(preserve_nanvix_root=False, preserve_cache=True)
        args = self.make_args(release=True, with_docker=True)
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
        args = self.make_args(release=False, with_docker=True)
        build_mod.build(args)
        lxml_mod.stage_lxml_runtime(paths.test_out())
        test_mod.stage_ramfs(args)

    def test(self) -> None:
        """Run the CPython test suite (hello + regrtest)."""
        self._overlay_local_nanvix()
        args = self.make_args(release=False)
        nanvixd_extra = ["-allow-host-networking"]

        ramfs_img = paths.test_out() / "cpython-rootfs.img"

        test_mod.run_all(args, nanvixd_extra=nanvixd_extra, ramfs_img=ramfs_img)

    def benchmark(self) -> None:
        """Run hello-world benchmark with a release-style ramfs."""
        self._overlay_local_nanvix()
        nanvixd_extra = ["-allow-host-networking"]
        args = self.make_args(release=False)
        test_mod.run_benchmark(
            args,
            nanvixd_extra=nanvixd_extra,
        )

    def clean(self) -> None:
        """Remove build artifacts."""
        build_mod.clean()


if __name__ == "__main__":
    CPythonBuild.main()

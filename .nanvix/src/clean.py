# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Clean lifecycle for the CPython ZScript."""

from __future__ import annotations
import shutil
import subprocess

from nanvix_zutil import paths, remove_build_volume

import src.config as config

from src.lib import LibMixin


class CleanMixin(LibMixin):
    """``./z clean`` — remove build artifacts."""

    def clean(self) -> None:
        """Remove build artifacts."""
        # Docker is scoped to build (zutils#235); the base hook reconstructs
        # the standard config to drop the persistent build volume.
        super().clean()
        self.clean_impl()

    def clean_impl(
        self, preserve_nanvix_root: bool = False, preserve_cache: bool = False
    ) -> None:
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
        elif self.docker is not None:
            # Reached from ``build`` (Docker in scope); ``clean`` proper drops
            # the volume via ``super().clean()`` above.
            volume = self.docker.volume_name()
            if volume is not None:
                remove_build_volume(volume)

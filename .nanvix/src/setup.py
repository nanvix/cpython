# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Setup lifecycle for the CPython ZScript."""

from __future__ import annotations

import shutil
import tarfile
import zipfile
from pathlib import Path

from nanvix_zutil import log
from nanvix_zutil.paths import nanvix_root

from src.lib import LibMixin


class SetupMixin(LibMixin):
    """``./z setup`` — download Nanvix sysroot and dependencies."""

    def setup(self) -> bool:
        """Download the Nanvix sysroot and dependencies."""
        # Base class handles: sysroot download, WITH_NANVIX overlay,
        # dependency installation, Windows binaries, and verification.
        used_fallback = super().setup()
        self._install_lxml_runtime_payload()
        self.config.save()
        return used_fallback

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
        """Install the exact lxml release's Python payload into the sysroot staging area."""
        cache_dir = nanvix_root() / "cache"
        # Magic-path naming: lxml-{host}-{arch}-{machine}-{mode}-{mem}-dev.{ext}.
        # Match any host/arch pair for the current machine + memory + mode.
        pattern = (
            f"lxml-*-{self.config.machine}-"
            f"{self.config.deployment_mode}-{self.config.memory_size}-dev.*"
        )
        candidates = list(cache_dir.glob(pattern)) if cache_dir.is_dir() else []
        if not candidates:
            raise FileNotFoundError(
                "lxml release archive is missing from .nanvix/cache"
            )

        archive = max(candidates, key=lambda path: path.stat().st_mtime_ns)
        destination = nanvix_root() / "sysroot" / "python-packages"
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

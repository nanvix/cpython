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
import sys
import tempfile
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
    EXIT_MISSING_DEP,
    TOOLCHAIN_CONTAINER_PATH,
    ZScript,
    log,
    run,
    suffix_dep,
)
from nanvix_zutil.buildroot import (
    Buildroot,
    Dependency,
    extract_nanvix_version_base,
)
from nanvix_zutil.github import resolve_release_with_fallback
from nanvix_zutil.paths import nanvix_root

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

# Makefile variable names (build-system-specific).
_MAKE_VAR_CONFIG = "CONFIG_NANVIX"
_MAKE_VAR_HOME = "NANVIX_HOME"
_MAKE_VAR_TOOLCHAIN = "NANVIX_TOOLCHAIN"
_MAKE_VAR_PLATFORM = "PLATFORM"
_MAKE_VAR_PROCESS_MODE = "PROCESS_MODE"
_MAKE_VAR_MEMORY_SIZE = "MEMORY_SIZE"
_MAKE_VAR_INSTALL_PREFIX = "INSTALL_PREFIX"

# CPython embeds --prefix into the binary (sys.prefix, sys.path).
_DEFAULT_INSTALL_PREFIX = config.DEFAULT_INSTALL_PREFIX

# Config key for persisting the --with-nanvix path in env.json.
_CFG_LOCAL_NANVIX = "local_nanvix_path"


# Map dependency names to the library files they install into buildroot/lib.
_DEP_EXPECTED_LIBS: dict[str, list[str]] = {
    "bzip2": ["libbz2.a"],
    "libffi": ["libffi.a"],
    "zlib": ["libz.a"],
    "sqlite": ["libsqlite3.a"],
    "openssl": ["libssl.a", "libcrypto.a"],
    "libxml2": ["libxml2.a"],
    "libxslt": ["libxslt.a", "libexslt.a"],
    "lxml": ["liblxml_etree.a", "liblxml_elementpath.a"],
    "xz": ["liblzma.a"],
}


class CPythonBuild(ZScript):
    """Build script for nanvix/cpython."""

    if sys.platform == "win32":
        SYSROOT_REQUIRED_FILES: tuple[str, ...] = (
            "lib/libposix.a",
            "lib/user.ld",
            "bin/nanvixd.exe",
            "bin/kernel.elf",
            "bin/mkramfs.exe",
        )

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
        """Re-overlay local Nanvix binaries into the sysroot.

        Called before build/test/release so that local changes are
        picked up even after the initial ``setup()`` run.  Reads the
        ``WITH_NANVIX`` environment variable (set by ``z.sh``) or falls
        back to the path persisted in ``.nanvix/env.json``.

        Delegates to ``Sysroot.overlay_local_nanvix()``.
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

        from nanvix_zutil import Sysroot

        Sysroot(Path(sysroot)).overlay_local_nanvix(Path(nanvix_path))

    # ---- Common helpers --------------------------------------------------

    def _get_host_paths(self) -> tuple[Path, Path]:
        """Return (sysroot, toolchain) raw host paths from config."""
        sysroot = self.config.get(CFG_SYSROOT, "")
        if not sysroot:
            log.fatal(
                f"{CFG_SYSROOT} is not set.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` first to download the sysroot.",
            )
        toolchain = Path(TOOLCHAIN_CONTAINER_PATH)
        return Path(sysroot), toolchain

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
        sysroot, toolchain = self._get_host_paths()
        use_docker = with_docker and self.docker is not None
        return build_mod.MakeArgs(
            toolchain_path=toolchain,
            sysroot=sysroot,
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

        Delegates sysroot/dependency download, ``--with-nanvix`` overlay,
        and verification to the base class.  Adds cpython-specific
        post-processing: missing-dep fallback and buildroot→sysroot merge.
        """
        # Base class handles: sysroot download, WITH_NANVIX overlay,
        # dependency installation, Windows binaries, and verification.
        used_fallback = super().setup()

        self._install_missing_deps()
        self.config.save()

        buildroot = nanvix_root() / "buildroot"
        sysroot = self.config.get(CFG_SYSROOT, "")
        if not sysroot or not buildroot.is_dir():
            return used_fallback

        sysroot_path = Path(sysroot)
        for subdir in ("lib", "include"):
            src = buildroot / subdir
            dst = sysroot_path / subdir
            if not src.is_dir():
                continue
            dst.mkdir(parents=True, exist_ok=True)
            for item in src.iterdir():
                target = dst / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                    log.info(f"Merged directory {subdir}/{item.name} into sysroot")
                else:
                    shutil.copy2(item, target)
                    log.info(f"Merged {subdir}/{item.name} into sysroot")

        # Overlay local Nanvix binaries last so they take precedence.
        self._overlay_local_nanvix()
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

    def _install_missing_deps(self) -> None:
        """Download missing dependency libraries using fallback assets."""
        buildroot = nanvix_root() / "buildroot"
        buildroot.mkdir(parents=True, exist_ok=True)
        lib_dir = buildroot / "lib"

        sysroot_tag = self.manifest.sysroot_ref.value
        nanvix_version = str(sysroot_tag).removeprefix("v") if sysroot_tag else ""

        for dep in self.manifest.dependencies:
            expected = _DEP_EXPECTED_LIBS.get(dep.name, [])
            if not expected:
                continue
            libs_present = all((lib_dir / lib).exists() for lib in expected)
            # For lxml, also require the python-packages payload.
            if dep.name == "lxml":
                pkg_present = (
                    buildroot / "python-packages" / "lxml" / "__init__.py"
                ).exists()
                if libs_present and pkg_present:
                    continue
            elif libs_present:
                continue
            resolved = suffix_dep(dep, nanvix_version) if nanvix_version else dep
            self._download_dep_fallback(resolved, buildroot)

    def _download_dep_fallback(
        self,
        dep: Dependency,
        buildroot: Path,
    ) -> None:
        """Download *dep* using a fallback asset variant.

        Delegates download and extraction to ``Buildroot.install_dep``
        (which handles ``.tar.gz``, ``.tar.bz2``, and ``.zip``
        transparently).  Adds cpython-specific logic:

        - Fuzzy release discovery (scan releases for ``prefix-nanvix-*``
          when the exact tag is missing).
        - Multiple deployment-mode candidates (standalone, single-process,
          multi-process).
        - Extraction of ``python-packages/`` payload (e.g. lxml).
        """
        dep_name = dep.name
        repo = dep.repo
        ref = str(dep.ref.value)
        platform = self.config.machine
        memory = self.config.memory_size
        deployment = self.config.deployment_mode
        gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

        # --- Resolve release (with fuzzy fallback via zutils) ---
        release: dict[str, object] | None = None
        base_version = extract_nanvix_version_base(ref)
        try:
            if base_version is not None:
                release, _ = resolve_release_with_fallback(
                    repo=repo,
                    version_specifier=ref,
                    base_version=base_version,
                    gh_token=gh_token,
                )
            else:
                from nanvix_zutil.github import resolve_release

                release = resolve_release(
                    repo=repo,
                    version_specifier=ref,
                    gh_token=gh_token,
                )
        except SystemExit:
            log.warning(f"No compatible release for {dep_name} ({ref})")
            return

        # --- Try deployment-mode candidates via Buildroot.install_dep ---
        br = Buildroot.create()
        modes = [deployment, "standalone", "single-process", "multi-process"]
        seen: set[str] = set()
        installed = False
        for mode in modes:
            if mode in seen:
                continue
            seen.add(mode)
            fallback_dep = Dependency(
                name=dep_name,
                repo=repo,
                ref=dep.ref,
            )
            try:
                br.install_dep(
                    fallback_dep,
                    machine=platform,
                    deployment_mode=mode,
                    memory_size=memory,
                    gh_token=gh_token,
                    _release=release,
                )
                installed = True
                break
            except SystemExit:
                continue

        if not installed:
            log.warning(f"No compatible fallback asset for {dep_name}")
            return

        # --- CPython-specific: extract python-packages/ (e.g. lxml) ---
        cache_dir = buildroot.parent / "cache"
        asset_prefix = f"{dep_name}-{platform}-"
        for cached in sorted(cache_dir.iterdir()) if cache_dir.is_dir() else []:
            if not cached.name.startswith(asset_prefix):
                continue
            self._extract_python_packages(cached, buildroot)
            break

    def _extract_python_packages(self, asset_path: Path, buildroot: Path) -> None:
        """Extract ``python-packages/`` from an archive into *buildroot*."""
        import tarfile
        import zipfile

        with tempfile.TemporaryDirectory() as tmpdir:
            extract_dir = Path(tmpdir) / "extracted"
            extract_dir.mkdir()

            if zipfile.is_zipfile(asset_path):
                with zipfile.ZipFile(asset_path) as zf:
                    for member in zf.namelist():
                        if "python-packages" not in member:
                            continue
                        if os.path.isabs(member) or ".." in member.split("/"):
                            continue
                        dest = (extract_dir / member).resolve()
                        if not dest.is_relative_to(extract_dir.resolve()):
                            continue
                        zf.extract(member, extract_dir)
            else:
                with tarfile.open(str(asset_path), "r:*") as tf:
                    pkg_members = [
                        m
                        for m in tf.getmembers()
                        if "python-packages" in m.name
                        and not os.path.isabs(m.name)
                        and ".." not in m.name.split("/")
                    ]
                    if not pkg_members:
                        return
                    try:
                        tf.extractall(
                            str(extract_dir), members=pkg_members, filter="data"
                        )
                    except TypeError:
                        tf.extractall(str(extract_dir), members=pkg_members)

            for pkg_src in extract_dir.rglob("python-packages"):
                if not pkg_src.is_dir():
                    continue
                pkg_dst = buildroot / "python-packages"
                pkg_dst.mkdir(parents=True, exist_ok=True)
                for item in pkg_src.iterdir():
                    target = pkg_dst / item.name
                    if item.is_dir():
                        if target.exists():
                            shutil.rmtree(target)
                        shutil.copytree(item, target)
                    else:
                        shutil.copy2(item, target)
                log.info(f"Installed python packages from {asset_path.name}")
                break


if __name__ == "__main__":
    CPythonBuild.main()

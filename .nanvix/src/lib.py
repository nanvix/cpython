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
import tempfile
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import src.ramfs as ramfs_mod

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

    # ------------------------------------------------------------------
    # Initrd creation helper (standalone mode)
    # ------------------------------------------------------------------

    def create_initrd(
        self,
        bin_dir: Path,
        app_path: Path,
        app_args: list[str] | None = None,
        app_env: str | None = None,
        output: Path | None = None,
    ) -> Path:
        """Create an initrd image bundling *app_path* with system daemons.

        Mirrors :meth:`~nanvix_zutil.ZScript.make_initrd`; this variant
        is retained because ``run_nanvixd_script`` invokes it inline
        with cpython-specific escaping semantics.

        Args:
            bin_dir: Directory containing the system daemon ELFs and mkimage.
            app_path: Absolute path to the application ELF binary.
            app_args: Optional CLI arguments for the app entry.
            app_env: Optional space-separated env vars (e.g.
                ``"PYTHONHOME=/ TMPDIR=/tmp"``).  Appended after a bare
                semicolon in the cmdline so the kernel's ``split_cmdline``
                can separate args from env.
            output: Destination path for the image.  Defaults to
                ``app_path.parent / "<stem>.img"``.

        Returns:
            Path to the generated image file.
        """
        app_stem = app_path.stem
        if output is None:
            output = app_path.parent / f"{app_stem}.img"

        mkimage = bin_dir / config.mkimage_binary()

        def _escape(arg: str) -> str:
            return arg.replace(";", "\\;")

        def _entry(
            elf: Path, argv0: str, extra: list[str] | None, env: str | None
        ) -> str:
            parts = [_escape(argv0)] + [_escape(a) for a in (extra or [])]
            argv = " ".join(parts)
            # The entry format for mkimage is:
            #   <escaped_elf_path>;<cmdline>
            # Within cmdline, the kernel splits on the first unescaped ';':
            #   <escaped_args>;<env_vars>
            cmdline = argv
            if env:
                cmdline += f";{env}"
            return f"{_escape(str(elf))};{cmdline}"

        # Daemons are *guest* binaries — always .elf, even on Windows.
        cmd: list[str] = [
            str(mkimage),
            "-o",
            str(output),
            _entry(bin_dir / "procd.elf", "procd", None, None),
            _entry(bin_dir / "memd.elf", "memd", None, None),
            _entry(bin_dir / "vfsd.elf", "vfsd", None, None),
            _entry(app_path, app_stem, app_args, app_env),
        ]

        subprocess.run(cmd, check=True, timeout=60)
        return output

    # ------------------------------------------------------------------
    # nanvixd script runner
    # ------------------------------------------------------------------

    def run_nanvixd_script(
        self,
        staging: Path,
        script_name: str,
        *,
        nanvixd_extra: list[str] | None = None,
        ramfs_img: Path | None = None,
        timeout: int = 120,
        label: str = "script",
    ) -> tuple[int, str, int]:
        """Run a Python script on nanvixd and return (returncode, output, elapsed_ms).

        This is the low-level execution primitive shared by the hello-world
        test and the benchmark.
        """
        resolved_extra: list[str] = (
            nanvixd_extra
            if nanvixd_extra is not None
            else config.PLATFORM_NANVIXD_ARGS.get(self.args.platform, [])
        )
        # On Windows, CreateProcess searches for the executable relative to the
        # *parent's* CWD, not the child's cwd. Use an absolute path to avoid this.
        nanvixd = str((self.args.sysroot / "bin" / config.nanvixd_binary()).resolve())

        if ramfs_img is None:
            raise ValueError("ramfs_img is required")

        # Copy host tools and daemon ELFs into the staging sysroot.
        # mkramfs is needed for ramfs generation; mkimage and the daemons
        # (procd, memd, vfsd) are needed for initrd creation.
        # Daemons are *guest* binaries — always .elf, even on
        # Windows.  Only host tools use the platform extension.
        _staging_bins = [
            config.mkramfs_binary(),
            config.mkimage_binary(),
            "procd.elf",
            "memd.elf",
            "vfsd.elf",
        ]
        for name in _staging_bins:
            src = self.args.sysroot / "bin" / name
            if src.is_file():
                shutil.copy2(src, staging / "bin" / name)

        # Standalone: bundle python binary with system daemons into an
        # initrd image.  Env vars are passed via app_env so the kernel's
        # split_cmdline sees them after the bare ';' separator.
        bin_dir = staging / "bin"
        app_path = staging / "bin" / config.python_binary()
        app_args = ["-B", f"./{script_name}"]
        app_env = (
            f"PYTHONHOME=/ PYTHONDONTWRITEBYTECODE=1"
            f" _PYTHON_SYSCONFIGDATA_NAME={config.SYSCONFIGDATA_NAME}"
        )
        initrd_img = self.create_initrd(
            bin_dir, app_path, app_args=app_args, app_env=app_env
        )

        cmd = [
            nanvixd,
            "-bin-dir",
            str(bin_dir),
            "-ramfs",
            str(ramfs_img),
            *resolved_extra,
            "--",
            str(initrd_img),
        ]

        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=staging,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"{label} timed out after {timeout}s")
        finally:
            if initrd_img.exists():
                initrd_img.unlink()

        elapsed_ms = int((time.monotonic() - start) * 1000)
        output = (result.stdout + "\n" + result.stderr).strip()
        return result.returncode, output, elapsed_ms

    # ------------------------------------------------------------------
    # Staging
    # ------------------------------------------------------------------

    def stage(self, *, require_array_so: bool = True) -> None:
        """Populate the test install tree with fixtures, runtime binaries, and helpers.

        Invoked by :meth:`BuildMixin.build` after ``install()`` for
        non-release builds so that ``./z test`` can consume
        ``paths.test_out()`` directly with no further staging.

        The complete tree is uploaded for Windows CI after the Linux build.
        """
        staging = paths.test_out()

        # Sysconfigdata fallback: ``make install`` should copy it from
        # build/<pybuilddir>/, but can silently fail when PYTHON_FOR_BUILD
        # is unavailable or the install recipe is interrupted.
        scdata_name = f"{config.SYSCONFIGDATA_NAME}.py"
        scdata_dst = staging / "lib" / config.PYTHON_LIB_DIR / scdata_name
        if not scdata_dst.is_file():
            pybuilddir = paths.repo_root() / "pybuilddir.txt"
            if pybuilddir.is_file():
                bdir = paths.repo_root() / pybuilddir.read_text().strip()
                scdata_src = bdir / scdata_name
                if scdata_src.is_file():
                    shutil.copy2(scdata_src, scdata_dst)
                    print(
                        f"  Copied {scdata_name} from build dir (make install missed it)"
                    )

        # Hello-world test script.  The array check proves that the first
        # stdlib module migrated to a shared extension is loaded through dlopen.
        array_snippet = (
            "import array\n"
            "_array = array.array('i', [1, 2, 3])\n"
            "assert _array.tolist() == [1, 2, 3]\n"
            "print('CPYTHON_TEST_ARRAY: array import and round-trip OK')\n"
        )
        if require_array_so:
            array_snippet += (
                "assert 'array' not in sys.builtin_module_names, 'array still built-in!'\n"
                "print(f'CPYTHON_TEST_ARRAY_SO: array loaded via dlopen from {array.__file__}')\n"
            )

        # The lxml import is exercised against the in-memory FAT ramfs VFS via
        # xmlInitParser().
        lxml_snippet = (
            "try:\n"
            "    import lxml.etree\n"
            "    doc = lxml.etree.fromstring(b'<root><child>lxml OK</child></root>')\n"
            "    assert doc.tag == 'root'\n"
            "    assert doc[0].text == 'lxml OK'\n"
            "    print('CPYTHON_TEST_LXML: lxml.etree import and parse OK')\n"
            "except ImportError as e:\n"
            "    print(f'CPYTHON_TEST_LXML_SKIP: {e}')\n"
            "except Exception as e:\n"
            "    print(f'CPYTHON_TEST_LXML_FAIL: {e}')\n"
            "    sys.exit(1)\n"
        )
        (staging / "test_hello.py").write_text(
            "import sys\n"
            "print('CPYTHON_TEST_HELLO: Hello from Python', sys.version_info[:2])\n"
            "print('CPYTHON_TEST_PLATFORM:', sys.platform)\n"
            + array_snippet
            + lxml_snippet
        )

        # HTTP server smoke-test script must be present in the sysroot before
        # ramfs build (standalone mode mounts ramfs as /).
        httpserver_src = paths.repo_root() / "httpserver.py"
        if httpserver_src.is_file():
            shutil.copy2(httpserver_src, staging / "httpserver.py")

        # Nanvix runtime binaries (host tools + guest daemons).
        bin_dir = staging / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        for binary in [
            "nanvixd.elf",
            "kernel.elf",
            "linuxd.elf",
            "uservm.elf",
            "nanvixd.exe",
            "kernel.exe",
            config.mkramfs_binary(),
            config.mkimage_binary(),
            "procd.elf",
            "memd.elf",
            "vfsd.elf",
        ]:
            src = self.args.sysroot / "bin" / binary
            if src.is_file():
                shutil.copy2(src, bin_dir / binary)

        # Replace unstripped python with the stripped python.elf from the build dir.
        stripped = paths.repo_root() / f"python{config.EXE}"
        if stripped.is_file():
            target = bin_dir / config.python_binary()
            shutil.copy2(stripped, target)
            print(
                f"  Installed stripped python.elf into test_out ({target.stat().st_size // 1024}K)"
            )

        # ``make install`` omits Lib/test/ from the install tree; regrtest needs it.
        pylib_dir = staging / "lib" / config.PYTHON_LIB_DIR

        # Seed from the source tree only when an install did not populate the
        # standard library. Linux CI uploads the complete install tree to Windows.
        lib_src = paths.repo_root() / "Lib"
        if lib_src.is_dir() and not pylib_dir.is_dir():
            shutil.copytree(lib_src, pylib_dir)
            print(
                f"  Seeded {pylib_dir} from source Lib/ (no make install on this host)"
            )

        test_dst = pylib_dir / "test"
        test_src = lib_src / "test"
        if test_src.is_dir() and not test_dst.is_dir():
            shutil.copytree(test_src, test_dst)
            test_count = sum(1 for _ in test_dst.rglob("*.py"))
            print(f"  Copied test suite from source tree ({test_count} files)")

    # ------------------------------------------------------------------
    # Ramfs staging (standalone mode)
    # ------------------------------------------------------------------

    def stage_ramfs(self) -> Path:
        """Build a ramfs image for standalone mode testing.

        Returns the path to the ramfs image.
        """
        ramfs_img = paths.test_out() / "cpython-rootfs.img"
        if ramfs_img.is_file():
            ramfs_img.unlink()

        with tempfile.TemporaryDirectory(prefix="cpython_test_ramfs_") as temporary:
            staging_dir = Path(temporary).resolve()
            output_dir = paths.out_dir().resolve()
            if staging_dir.is_relative_to(output_dir):
                raise RuntimeError(
                    f"test rootfs scratch directory {staging_dir} must be outside "
                    f"out_dir {output_dir}"
                )
            sysroot_dst = staging_dir / "rootfs"
            shutil.copytree(paths.test_out(), sysroot_dst)

            # Create /tmp for tempfile.gettempdir().
            (sysroot_dst / "tmp").mkdir(exist_ok=True)

            # Trim and build ramfs image (keep tests for test pipeline).
            ramfs_mod.trim_and_build(
                sysroot_dst,
                self.args.sysroot,
                ramfs_img,
                keep_tests=True,
            )

        return ramfs_img

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Clean up transient test artifacts (log files).

        The build output at ``paths.test_out()`` is *not* removed — that is
        a build artifact owned by ``./z build`` / ``./z clean``.
        """
        for name in [
            "cpython_test.log",
            "cpython_regrtest.log",
            "cpython_regrtest_batch.log",
        ]:
            p = paths.nanvix_root() / name
            if p.is_file():
                p.unlink()

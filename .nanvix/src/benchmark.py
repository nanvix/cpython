# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Transitional benchmark helpers for Nanvix CPython.

Extracted from the module-level functions in ``test.py`` so ``test.py``
can be replaced wholesale by :class:`TestMixin`. Retired in the next
commit when :class:`BenchmarkMixin` lands.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from nanvix_zutil import paths

import src.build as build_mod
import src.config as config
import src.ramfs as ramfs_mod

# ---------------------------------------------------------------------------
# Initrd creation helper (standalone mode)
# ---------------------------------------------------------------------------


def _create_initrd(
    bin_dir: Path,
    app_path: Path,
    app_args: list[str] | None = None,
    app_env: str | None = None,
    output: Path | None = None,
) -> Path:
    """Create an initrd image bundling *app_path* with system daemons.

    Mirrors :meth:`~nanvix_zutil.ZScript.make_initrd` for use in
    standalone module-level functions that lack a ZScript instance.

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

    def _entry(elf: Path, argv0: str, extra: list[str] | None, env: str | None) -> str:
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


# ---------------------------------------------------------------------------
# Windows: download release artifacts as install cache
# ---------------------------------------------------------------------------


def _run_nanvixd_script(
    staging: Path,
    script_name: str,
    args: build_mod.MakeArgs,
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
        else config.PLATFORM_NANVIXD_ARGS.get(args.platform, [])
    )
    # On Windows, CreateProcess searches for the executable relative to the
    # *parent's* CWD, not the child's cwd. Use an absolute path to avoid this.
    nanvixd = str((args.sysroot / "bin" / config.nanvixd_binary()).resolve())

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
        src = args.sysroot / "bin" / name
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
    initrd_img = _create_initrd(bin_dir, app_path, app_args=app_args, app_env=app_env)

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


def cleanup() -> None:
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


# ---------------------------------------------------------------------------
# Aggregate test runner
# ---------------------------------------------------------------------------


def run_benchmark(
    args: build_mod.MakeArgs,
    *,
    nanvixd_extra: list[str] | None = None,
) -> None:
    """Run a hello-world benchmark.

    The benchmark builds a ramfs with the same trimming applied during
    ``./z release`` (no test/ directory, no dev artifacts) so that the
    image size and boot time reflect a production deployment.

    No regression tests are executed.
    """
    try:
        _run_benchmark_impl(
            args,
            nanvixd_extra=nanvixd_extra,
        )
    finally:
        cleanup()


def _run_benchmark_impl(
    args: build_mod.MakeArgs,
    *,
    nanvixd_extra: list[str] | None = None,
) -> None:
    """Inner implementation of :func:`run_benchmark`."""
    # Consume the test install tree produced by ``./z build``.
    staging = paths.test_out()
    if not staging.is_dir():
        raise RuntimeError(
            f"{staging} not found; run `./z build` before `./z benchmark`"
        )

    # Write a minimal benchmark script.
    bench_script = "bench_hello.py"
    (staging / bench_script).write_text("print('hello world')\n")

    # Build ramfs with release trimming (keep_tests=False).
    ramfs_img = paths.nanvix_root() / "cpython-benchmark.img"
    bench_cache = paths.nanvix_root() / "_benchmark_cache"

    # Always rebuild to reflect the current sysroot.
    if bench_cache.exists():
        shutil.rmtree(bench_cache)
    bench_cache.mkdir(parents=True)

    sysroot_src = staging
    sysroot_dst = bench_cache
    shutil.copytree(sysroot_src, sysroot_dst)
    (sysroot_dst / "tmp").mkdir(exist_ok=True)

    # Release-style trim: no test/ dir, no dev artifacts.
    ramfs_mod.trim_and_build(
        bench_cache,
        args.sysroot,
        ramfs_img,
        keep_tests=False,
    )

    # Scratch directory is no longer needed.
    shutil.rmtree(bench_cache, ignore_errors=True)

    # Run benchmark.
    print(f"Benchmark: Hello world ({args.process_mode})...")

    returncode, output, elapsed_ms = _run_nanvixd_script(
        staging,
        bench_script,
        args,
        nanvixd_extra=nanvixd_extra,
        ramfs_img=ramfs_img,
        label="Benchmark",
    )
    print(f"  Execution time: {elapsed_ms} ms")

    if returncode != 0:
        print(f"  FAIL: Benchmark exited with status {returncode}")
        print(output)
        raise RuntimeError(f"Benchmark exited with status {returncode}")

    if "hello world" not in output:
        print(f"  FAIL: expected 'hello world' in output")
        print(output)
        raise RuntimeError("Benchmark did not produce expected output")

    print("  PASS")

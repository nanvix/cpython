#!/usr/bin/env python3
# run-tests.py - Host-side batched test runner for nanvixd
#
# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.
#
# Splits test modules into batches and runs each batch in its own
# nanvixd invocation.  Each batch gets a fresh VM process, which
# resets the 32MB heap and avoids OOM from cumulative fragmentation.
#
# Batches run sequentially.  All batches are run regardless of
# failures; the overall exit code reflects whether any batch failed.
#
# Runs in standalone mode (ramfs): each batch is bundled with the
# system daemons into an initrd image, and the guest command line uses
# nanvixd's semicolon-delimited format to set PYTHONHOME and
# PYTHONDONTWRITEBYTECODE inside the guest.
#
# Usage:
#     cd <sysroot> && python3 <path>/run-tests.py <module> [<module> ...]
#
# Environment:
#     NANVIX_TEST_BATCH_SIZE - modules per nanvixd invocation (default: 4)
#     NANVIXD_EXTRA_ARGS     - extra flags passed to nanvixd (optional)
#     REGRTEST_TIMEOUT       - per-test timeout in seconds (default: 120)

import os
import shlex
import subprocess
import sys
from pathlib import Path

BATCH_SIZE = int(os.environ.get("NANVIX_TEST_BATCH_SIZE", "4"))
NANVIXD = "./bin/nanvixd.exe" if sys.platform == "win32" else "./bin/nanvixd.elf"
# Must match config.PYTHON_VERSION / config.python_binary().
PYTHON_BIN = os.environ.get("NANVIX_PYTHON_BIN", "./bin/python3.12")
# Must match _sysconfigdata_{ABIFLAGS}_{MACHDEP}_{MULTIARCH} from configure.
SYSCONFIGDATA_NAME = os.environ.get(
    "NANVIX_SYSCONFIGDATA_NAME", "_sysconfigdata__nanvix_"
)
REGRTEST_TIMEOUT = os.environ.get("REGRTEST_TIMEOUT", "120")
# Directory containing system daemon ELFs and mkimage (set by test.py).
BIN_DIR = Path(os.environ.get("NANVIX_BIN_DIR", "./bin"))


# ---------------------------------------------------------------------------
# Initrd creation helper (standalone mode)
# ---------------------------------------------------------------------------

IS_WINDOWS = sys.platform == "win32"


def _create_initrd(
    bin_dir: Path,
    app_path: Path,
    app_args: list[str] | None = None,
    app_env: str | None = None,
    output: Path | None = None,
) -> Path:
    """Create an initrd image bundling *app_path* with system daemons."""
    app_stem = app_path.stem
    if output is None:
        output = app_path.parent / f"{app_stem}.img"

    mkimage = bin_dir / ("mkimage.exe" if IS_WINDOWS else "mkimage.elf")

    def _escape(arg: str) -> str:
        return arg.replace(";", "\\;")

    def _entry(elf: Path, argv0: str, extra: list[str] | None, env: str | None) -> str:
        parts = [_escape(argv0)] + [_escape(a) for a in (extra or [])]
        argv = " ".join(parts)
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


def run_batch(
    batch_num: int,
    batch: list[str],
    nanvixd_extra: list[str],
) -> tuple[int, int, list[str]]:
    """Run a single batch. Returns (batch_num, returncode, modules)."""

    initrd_img: Path | None = None

    try:
        # Standalone: create an initrd image bundling python with
        # system daemons.  Env vars are passed via app_env so the
        # kernel's split_cmdline sees them after the bare ';'.
        #
        # -B (no bytecode) is mandatory: writing a __pycache__/*.pyc via
        # os.replace hangs the guest kernel indefinitely (NSKIP021 — the
        # FAT VFS rename handler never returns, the VM becomes
        # unresponsive, and the test harness hits its 600s wall-clock
        # timeout).  Without -B, importing any source file whose mtime is
        # newer than its compiled pyc — which happens after every code
        # edit, since the install-time compileall snapshot goes stale —
        # locks up the VM.
        app_args = [
            "-B",
            "-m",
            "test",
            f"--timeout={REGRTEST_TIMEOUT}",
            *batch,
        ]
        app_env = (
            f"PYTHONHOME=/ PYTHONDONTWRITEBYTECODE=1"
            f" HOME=/tmp TMPDIR=/tmp"
            f" NANVIX_STANDALONE=1"
            f" _PYTHON_SYSCONFIGDATA_NAME={SYSCONFIGDATA_NAME}"
        )

        app_path = BIN_DIR / Path(PYTHON_BIN).name
        initrd_img = _create_initrd(
            BIN_DIR,
            app_path,
            app_args=app_args,
            app_env=app_env,
            output=Path(f"batch{batch_num}.img"),
        )

        cmd = [
            NANVIXD,
            *nanvixd_extra,
            "--",
            str(initrd_img),
        ]

        try:
            rc = subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=600).returncode
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT: batch {batch_num} exceeded 600s")
            rc = 124  # match GNU timeout exit code
        return batch_num, rc, batch
    finally:
        if initrd_img is not None and initrd_img.exists():
            initrd_img.unlink()


def main() -> int:
    modules = sys.argv[1:]
    if not modules:
        print("run-tests.py: no modules specified", file=sys.stderr)
        return 1

    nanvixd_extra = shlex.split(
        os.environ.get("NANVIXD_EXTRA_ARGS", ""),
        posix=(sys.platform != "win32"),
    )

    batches: list[list[str]] = []
    for i in range(0, len(modules), BATCH_SIZE):
        batches.append(modules[i : i + BATCH_SIZE])

    total_batches = len(batches)
    print(
        f"  Running {len(modules)} modules in {total_batches} batches "
        f"({BATCH_SIZE}/batch, sequential, standalone mode)"
    )
    for i, batch in enumerate(batches, 1):
        print(f"    Batch {i}: {' '.join(batch)}")

    failed: list[str] = []
    failed_batches = 0

    for i, batch in enumerate(batches, 1):
        batch_num, rc, batch = run_batch(i, batch, nanvixd_extra)
        if rc != 0:
            print(f"  FAIL: batch {batch_num} exited with status {rc}")
            failed.extend(batch)
            failed_batches += 1
        else:
            print(f"  OK: batch {batch_num}")

    total = len(modules)
    if failed:
        print(
            f"  FAILED: {failed_batches} batch(es) ({len(failed)}/{total} modules affected):"
        )
        print(f"    {' '.join(failed)}")
        return 1

    print(f"  PASS: all {total} modules passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

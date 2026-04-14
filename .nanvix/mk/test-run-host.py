#!/usr/bin/env python3
# test-run-host.py - Run nanvixd tests on the host (outside Docker/container).
#
# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.
#
# Usage: test-run-host.py <staging-dir> <process-mode> [test-list...]
#
# Unified test runner for both Windows and Linux hosts.
# On Windows, nanvixd.exe is invoked natively.
# On Linux, staging is copied to /tmp for writable access and run directly.

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import time


IS_WINDOWS = platform.system() == "Windows"

# Host tool extensions to try, in order of preference.
_HOST_BIN_EXTS = (".elf", ".exe")


def find_host_bin(base_path):
    """Find a host binary, trying .elf then .exe extension."""
    for ext in _HOST_BIN_EXTS:
        p = base_path + ext
        if os.path.exists(p):
            return p
    return base_path + _HOST_BIN_EXTS[0]  # fallback for error messages


def die(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def validate_test_names(test_list):
    """Validate that test module names contain only alphanumeric and underscores."""
    for t in test_list:
        if not re.fullmatch(r"[A-Za-z0-9_]+", t):
            die(f"Invalid test module name: '{t}'")


def run_command(cmd, timeout, log_path):
    """Run a command, capture output to log_path, return (exit_code, output, elapsed_ms)."""
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        output = (result.stdout + "\n" + result.stderr).strip()
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(output)
        return result.returncode, output, elapsed_ms
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        die(f"Command timed out after {timeout}s")


def prepare_workdir_linux(staging):
    """Copy staging to a writable /tmp location (Linux only)."""
    workdir = "/tmp/cpython-test-staging"
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    shutil.copytree(staging, workdir)
    # Make writable
    for root, dirs, files in os.walk(workdir):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o755)
        for f in files:
            os.chmod(os.path.join(root, f), 0o644)
    return workdir


def build_hello_cmd(mode, staging_dir):
    """Build the command list for the hello-world test."""
    sysroot = os.path.join(os.path.abspath(staging_dir), "sysroot")
    nanvixd = find_host_bin(os.path.join(sysroot, "bin", "nanvixd"))
    python_bin = os.path.join(sysroot, "bin", "python3.12")
    if mode == "standalone":
        ramfs = os.path.join(os.path.abspath(staging_dir), "cpython-rootfs.img")
        return [
            nanvixd,
            "-bin-dir", os.path.join(sysroot, "bin"),
            "-ramfs", ramfs,
            "--", python_bin,
            "-B /test_hello.py;PYTHONHOME=/ PYTHONDONTWRITEBYTECODE=1",
        ]
    else:
        return [nanvixd, "--", python_bin, "./test_hello.py"]


def build_regrtest_cmd(staging_dir, test_list):
    """Build the command list for regrtest."""
    sysroot = os.path.join(os.path.abspath(staging_dir), "sysroot")
    nanvixd = find_host_bin(os.path.join(sysroot, "bin", "nanvixd"))
    python_bin = os.path.join(sysroot, "bin", "python3.12")
    return [nanvixd, "--", python_bin, "-m", "test", "--timeout=120"] + test_list


def run_hello_test(mode, staging_dir, log_dir):
    """Run the hello-world test and validate output."""
    print(f"Test: Hello world ({mode})...")
    log_path = os.path.join(log_dir, "cpython_test.log")
    cmd = build_hello_cmd(mode, staging_dir)

    # Set cwd to sysroot for commands that use relative paths.
    cwd = os.path.join(staging_dir, "sysroot")

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        die("Hello test timed out after 120s")

    elapsed_ms = int((time.monotonic() - start) * 1000)
    output = (result.stdout + "\n" + result.stderr).strip()
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"  Execution time: {elapsed_ms} ms")

    if result.returncode != 0:
        print(f"  FAIL: Hello test exited with status {result.returncode}")
        print(output)
        sys.exit(1)

    # Validate expected output marker
    for line in output.splitlines():
        if line.startswith("CPYTHON_TEST_HELLO:"):
            print(f"  PASS: {line.strip()}")
            return

    print("  FAIL: Hello test did not produce expected output")
    print(output)
    sys.exit(1)


def run_regrtest(staging_dir, test_list, log_dir):
    """Run stdlib regression tests."""
    print(f"Test: regrtest ({len(test_list)} modules)...")
    log_path = os.path.join(log_dir, "cpython_regrtest.log")
    cmd = build_regrtest_cmd(staging_dir, test_list)

    cwd = os.path.join(staging_dir, "sysroot")

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        die("regrtest timed out after 600s")

    elapsed_ms = int((time.monotonic() - start) * 1000)
    output = (result.stdout + "\n" + result.stderr).strip()
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"  Execution time: {elapsed_ms} ms")

    if result.returncode != 0:
        print(f"  FAIL: regrtest exited with status {result.returncode}")
        print(output)
        sys.exit(1)

    print("  PASS: regrtest completed")


def main():
    parser = argparse.ArgumentParser(
        description="Run nanvixd tests on the host (Windows or Linux).",
    )
    parser.add_argument("staging_dir", help="Path to the test staging directory")
    parser.add_argument(
        "process_mode",
        choices=["standalone", "multi-process", "single-process"],
        help="Deployment process mode",
    )
    parser.add_argument(
        "test_list", nargs="*", default=[],
        help="Stdlib test modules for regrtest",
    )
    args = parser.parse_args()

    staging_dir = args.staging_dir
    mode = args.process_mode
    test_list = args.test_list

    # Validate test names
    validate_test_names(test_list)

    # Verify staging directory
    nanvixd_path = find_host_bin(
        os.path.join(staging_dir, "sysroot", "bin", "nanvixd")
    )

    if not os.path.exists(nanvixd_path):
        die(f"nanvixd not found in staging: {nanvixd_path}")

    # On Linux, copy staging to a writable /tmp location
    if not IS_WINDOWS:
        staging_dir = prepare_workdir_linux(staging_dir)

    # Log directory
    if IS_WINDOWS:
        log_dir = staging_dir
    else:
        log_dir = "/tmp"

    # Run hello-world test
    run_hello_test(mode, staging_dir, log_dir)

    # Run regrtest if applicable
    if mode != "standalone" and test_list:
        run_regrtest(staging_dir, test_list, log_dir)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# run-regrtest.py - Run CPython regrtest inside a nanvixd guest
#
# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.
#
# Guest-side test runner.  Reads the test module list from a file and
# invokes regrtest in-process.  No batching, no subprocess, no ramfs —
# all of that is the host's concern.
#
# Test list source (in priority order):
#   1. File at NANVIX_TEST_LIST_FILE (default test-list.txt),
#      one module name per line.  Blank lines and # comments are skipped.
#   2. Command-line arguments (fallback for ad-hoc runs).
#
# Options:
#   --tmpdir DIR           - set TMPDIR for this process (avoids /tmp collisions
#                            when multiple nanvixd instances run in parallel)
#
# Environment variables:
#   NANVIX_TEST_LIST_FILE  - path to the test list file (default: test-list.txt)
#   REGRTEST_TIMEOUT       - per-test timeout in seconds (default: 120)

import os
import sys


def main() -> int:
    # -- Parse --tmpdir (must happen before anything touches tempfile) ----------
    argv = sys.argv[1:]
    if len(argv) >= 2 and argv[0] == "--tmpdir":
        os.environ["TMPDIR"] = argv[1]
        argv = argv[2:]

    # -- Split forwarded regrtest flags from positional module names ----------
    # The host caller (run-tests.py) places a literal "--" between forwarded
    # regrtest flags and module names.  This is the POSIX-standard convention
    # and avoids us having to mirror libregrtest/cmdline.py's option table
    # (which is wrong-by-construction: any new value-taking option upstream
    # would silently consume a module name as its value, corrupting the
    # batch's test list).
    #
    # Legacy/ad-hoc invocation (no "--"): treat any token starting with "-"
    # as a flag, everything else as a module.  Safe because no caller passes
    # value-taking flags via ad-hoc CLI use.
    extra_flags: list[str] = []
    modules: list[str] | None = None
    if argv:
        if "--" in argv:
            sep = argv.index("--")
            extra_flags = argv[:sep]
            positional = argv[sep + 1:]
        else:
            extra_flags = [t for t in argv if t.startswith("-")]
            positional = [t for t in argv if not t.startswith("-")]
        if positional:
            modules = positional

    if modules is None:
        list_file = os.environ.get("NANVIX_TEST_LIST_FILE", "test-list.txt")
        try:
            with open(list_file) as f:
                modules = [
                    line.strip()
                    for line in f
                    if line.strip() and not line.strip().startswith("#")
                ]
        except FileNotFoundError:
            print(f"run-regrtest.py: Could not find list file at {list_file}")
            return 1

    if not modules:
        print("run-regrtest.py: no test modules specified", file=sys.stderr)
        return 1
    print(f"run-regrtest.py: Got modules: {modules}")
    if extra_flags:
        print(f"run-regrtest.py: Forwarding regrtest flags: {extra_flags}")

    # -- Build regrtest arguments ----------------------------------------------
    timeout = os.environ.get("REGRTEST_TIMEOUT", "120")
    args = [f"--timeout={timeout}"] + extra_flags + modules

    # -- Run -------------------------------------------------------------------
    sys.argv[1:] = args
    from test.libregrtest.main import main as regrtest_main

    try:
        regrtest_main()
    except SystemExit as e:
        return e.code
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
    # NOTE(split-PR): This argv-splitter is held back for a separate
    # "hosted-mode tooling" PR; do NOT include in the filesystem-and-io PR.
    # Tracks: regrtest flag forwarding (-m / -x / -u / etc.).
    # Anything starting with "-" is a regrtest flag we should forward (and
    # for short flags like -m/-x/-u, the immediately following token is its
    # value, not a module name).
    _FLAGS_WITH_VALUE = {"-m", "-x", "-u", "--match", "--matchfile",
                         "--ignore", "--ignorefile", "-r", "--randomize"}
    extra_flags: list[str] = []
    modules: list[str] | None = None
    if argv:
        positional: list[str] = []
        i = 0
        while i < len(argv):
            tok = argv[i]
            if tok.startswith("-"):
                extra_flags.append(tok)
                # If it's a known flag-with-value and not joined by =, also
                # consume the next token as its value.
                if tok in _FLAGS_WITH_VALUE and "=" not in tok and i + 1 < len(argv):
                    extra_flags.append(argv[i + 1])
                    i += 2
                    continue
                i += 1
            else:
                positional.append(tok)
                i += 1
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

# Nanvix CPython Test Skip List

This file tracks test cases that are intentionally skipped or known to fail
when running the CPython test suite on Nanvix.  It is updated whenever a new
test module is enabled (see issue #329 and related issues).

Tests are skipped in one of two ways:

1. **Platform guard in `Lib/test/support/__init__.py`** – module-wide helpers
   such as `requires_fork()`, `requires_subprocess()`, and
   `requires_working_socket()` automatically skip decorated tests because
   `is_nanvix = True` sets `has_fork_support`, `has_subprocess_support`, and
   `has_socket_support` all to `False`.

2. **`sed` patch in `Makefile.nanvix` or inline `@unittest.skip`** – for cases
   that are not already guarded by a platform helper.

---

## Platform Constraints Summary

| Constraint | Root cause | Tracking issue |
|---|---|---|
| No `fork()` | Not yet implemented in Nanvix kernel | nanvix/nanvix#321 |
| No subprocess | Depends on `fork()` | nanvix/nanvix#321 |
| No sockets | Network stack not exposed to user-space | nanvix/nanvix#322 |
| No `rmdir()` | Returns `ENOSYS` | nanvix/nanvix#348 |
| No `liblzma` | Library not in sysroot | — |

---

## test_zlib

**Status:** ✅ Enabled in `NANVIX_TEST_LIST_EXTERNAL`

All tests are expected to pass.  zlib 1.3.1 is statically linked into the
binary.  No subprocess or socket usage in `Lib/test/test_zlib.py`.

---

## test_gzip

**Status:** ✅ Enabled in `NANVIX_TEST_LIST_EXTERNAL`

Two test classes use subprocesses and are automatically skipped by the
`@requires_subprocess()` decorator that is already present in
`Lib/test/test_gzip.py`:

| Test | Reason skipped |
|---|---|
| `CommandLineTest.test_compress_stdin_stdout` | `@requires_subprocess()` |
| `CommandLineTest.test_decompress_stdin_stdout` | `@requires_subprocess()` |

All other tests are expected to pass.

---

## test_bz2

**Status:** ✅ Enabled in `NANVIX_TEST_LIST_EXTERNAL`

All tests are expected to pass.  bzip2 1.0.8 is statically linked.  No
subprocess or socket usage in `Lib/test/test_bz2.py`.

---

## test_hashlib

**Status:** ✅ Enabled in `NANVIX_TEST_LIST_EXTERNAL`

OpenSSL 3.5.0 is statically linked.  Two test methods in
`Lib/test/test_hashlib.py` are guarded by `@unittest.skipIf(sys.maxsize < _4G
+ 5, ...)` and are already skipped on 32-bit targets (Nanvix is i686).

No subprocess-based tests remain unguarded after those size checks.

---

## test_hmac

**Status:** ✅ Enabled in `NANVIX_TEST_LIST_EXTERNAL`

All tests are expected to pass.  `test_hmac` is pure-Python and only depends
on `hashlib`.

---

## test_sqlite3

**Status:** ✅ Enabled in `NANVIX_TEST_LIST_EXTERNAL`

SQLite 3.49.0 is statically linked.  The package (`Lib/test/test_sqlite3/`)
contains ten sub-modules:

| Sub-module | Notes |
|---|---|
| `test_backup` | Expected to pass |
| `test_cli` | Expected to pass |
| `test_dbapi` | One class guarded by `@requires_subprocess()` — skipped automatically |
| `test_dump` | Expected to pass |
| `test_factory` | Expected to pass |
| `test_hooks` | Expected to pass |
| `test_regression` | Expected to pass |
| `test_transactions` | Expected to pass |
| `test_types` | Expected to pass |
| `test_userfunctions` | Expected to pass |

**Known limitation:** SQLite WAL (Write-Ahead Logging) journal mode uses
`fcntl` file-range locking.  If `fcntl` is not fully implemented on Nanvix,
any test that switches to WAL mode may fail with `OperationalError`.  Add
individual `@unittest.skip` annotations (and document them here) if observed
during CI runs.

---

## test_ssl

**Status:** ✅ Enabled in `test-external-libs` (separate invocation with `-u network`)

`test_ssl` is invoked **separately** from the main external-library batch
because it requires the `network` resource flag (`-u network`) to enable
loopback TLS tests.  OpenSSL 3.5.0 is statically linked.

Socket support is disabled on Nanvix (`has_socket_support = False`), so any
test that calls `requires_working_socket()` is automatically skipped.  The
remaining tests (certificate parsing, cipher-suite inspection, protocol-version
constants, etc.) are expected to pass.

Tests known to be skipped automatically on Nanvix:

| Test class / method | Reason |
|---|---|
| All tests calling `socket.socket()` directly | `OSError` or `SkipTest` from `requires_working_socket()` |
| `NetworkedTests` | `@support.requires_resource('network')` + no live network |
| `NetworkedBIOTests` | Same |

IPv6 tests are also skipped because `--disable-ipv6` is passed during
cross-compilation configure.

---

## Adding New Skips

When a test fails during a CI run:

1. Run the failing module individually in verbose mode to identify the exact
   test method:
   ```
   ./bin/nanvixd.elf -- ./bin/python3.12 -m test -v <test_module>
   ```
2. Diagnose the root cause (missing syscall, missing library, platform
   limitation, etc.).
3. If the failure is a known platform limitation, add a `sed` patch to the
   relevant `Makefile.nanvix` target **or** add `@unittest.skip` to the test
   file with a comment referencing the tracking issue.
4. Add an entry to this file under the appropriate module section, including
   the test name, reason, and issue reference.
5. Commit the skip and this updated document together.

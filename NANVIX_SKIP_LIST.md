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

**Status:** ❌ Excluded from `NANVIX_TEST_LIST_EXTERNAL`

Garbled `tempfile.mkstemp()` paths cause `PermissionError` in `setUp` for
nearly every test (64 errors).  Cleanup also crashes regrtest with
`OSError: [Errno 88]`.

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

**Status:** ❌ Excluded from `NANVIX_TEST_LIST_EXTERNAL`

Crashes at import time: `from errno import ... ESHUTDOWN` raises `ImportError`.
Same root cause as `test_exception_hierarchy`.

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

---

## External Library Tests (#329)

Tests for CPython C extension modules linked against sysroot libraries
(zlib 1.3.1, bzip2 1.0.8, OpenSSL 3.5.0, SQLite 3.49.0).
Run on **i686** microvm, multi-process mode, 128 MB RAM.

### Manual Skips — External Libraries

| Module | Test | Reason | Failure |
|--------|------|--------|---------|
| test_zlib | `CompressTestCase.test_big_compress_buffer` | 128 MB VM OOM | `check_big_compress_buffer` unconditionally allocates 10 MiB via `random.randbytes(_1M * 10)`, triggering `MemoryError`. |
| test_zlib | `CompressObjectTestCase.test_big_compress_buffer` | 128 MB VM OOM | Same root cause — `CompressObject` variant. |
| test_sqlite3 | `CommandLineInterface.test_cli_on_disk_db` | Garbled TESTFN + SQLITE_IOERR_LOCK | TESTFN resolves to garbled `'@test_1_tmpæ'`; SQLite file-locking (`fcntl`) returns `SQLITE_IOERR_LOCK`. |
| test_sqlite3 | `InteractiveSession.test_interact_on_disk_file` | Garbled TESTFN + SQLITE_IOERR_LOCK | Same root cause. |
| test_sqlite3 | `DateTimeTests.test_sql_timestamp` | Broken system clock | `current_timestamp` returns epoch (1969); `ts.year` ≠ `now.year`. |

### Platform Fixes — External Libraries

| File | Change | Reason |
|------|--------|--------|
| `Lib/test/test_sqlite3/test_dbapi.py` | Wrapped `from _testcapi import INT_MAX, ULLONG_MAX` in `try/except`; defined fallback constants | Unconditional import crashes `test_dbapi` and all 6 sub-modules that depend on it (`test_dump`, `test_hooks`, `test_regression`, `test_transactions`, `test_userfunctions`). |
| `Lib/test/test_bz2.py` | `ext_decompress()`: set `has_cmdline_bunzip2 = False` when `support.is_nanvix` | Prevents 12 test failures from `subprocess.check_output(['bunzip2'], ...)`. Falls back to pure-Python `bz2.decompress()`. |

### Excluded Modules — External Libraries

| Module | Reason |
|--------|--------|
| test_gzip | Garbled `tempfile.mkstemp()` paths cause `PermissionError` in `setUp` for nearly every test (64 errors). Cleanup also crashes regrtest with `OSError: [Errno 88]`. |
| test_ssl | Crashes at import time: `from errno import ... ESHUTDOWN` raises `ImportError`. Same root cause as `test_exception_hierarchy`. |

### Clean-Pass Modules — External Libraries

- test_hashlib, test_hmac

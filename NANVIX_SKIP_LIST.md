# Nanvix Test Skip List

This document records all test-level skips applied to CPython test modules
to achieve zero failures on Nanvix. Each entry explains the reason for the
skip and links to the relevant platform constraint.

---

## Platform Constraints

| Constraint | Description |
|-----------|-------------|
| No subprocess | `support.has_subprocess_support = False` (Nanvix has no fork/exec) |
| No fork | `support.has_fork_support = False` |
| No socket | `support.has_socket_support = False` |
| No `_testcapi` | C test extension module is not built in release mode |
| 32-bit platform | `sys.maxsize == 2**31 - 1` (i686 target) |
| No rmdir | `os.rmdir` returns `ENOSYS`; directory cleanup is best-effort |

---

## test_glob

**File:** `Lib/test/test_glob.py`

| Change | Reason |
|--------|--------|
| `tearDown`: wrapped `shutil.rmtree` in `try/except OSError` | Nanvix does not implement `rmdir` (returns `ENOSYS`). Cleanup must not crash the test run. See [nanvix#348](https://github.com/nanvix/nanvix/issues/348). |

---

## Modules with Pre-Existing Guards (no additional changes needed)

The following modules already carry skip decorators that handle Nanvix
constraints automatically:

| Module | Guard | Reason |
|--------|-------|--------|
| `test_quopri` | `@support.requires_subprocess()` | subprocess tests skip when `has_subprocess_support=False` |
| `test_json/test_tool` | `@support.requires_subprocess()` | subprocess tests skip when `has_subprocess_support=False` |
| `test_re` | `@unittest.skipIf(multiprocessing is None, ...)` | `multiprocessing` import fails without subprocess/fork; test skips |
| `test_unicode` | `@unittest.skipIf(_testcapi is None, ...)` | `_testcapi` unavailable; three tests auto-skip |
| `test_codecs` | `@unittest.skipIf(_testcapi/_testinternalcapi is None, ...)` | C-API tests auto-skip |
| `test_marshal` | `@unittest.skipUnless(_testcapi, ...)` | C-API test class auto-skips |
| `test_csv` | `@support.requires_legacy_unicode_capi()` | legacy unicode C-API test auto-skips |
| `test_unicode` | `@support.cpython_only` + MemoryError guard | `test_case_operation_overflow` skips when 128 MB is not enough |

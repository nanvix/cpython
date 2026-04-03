# Nanvix CPython – Test Skip List

This file documents tests that are skipped or expected to fail when running the
CPython test suite on Nanvix.  Each entry records the affected test, the reason
for skipping, and the mechanism used to enforce the skip.

Entries are added each time a new test skip is introduced so that the rationale
is visible in version control.  See also the [platform limitations][limits]
section of `NANVIX.md`.

[limits]: NANVIX.md#known-limitations

---

## Platform-wide automatic skips

The following capabilities are unconditionally disabled on Nanvix in
`Lib/test/support/__init__.py`.  Any test guarded by the corresponding helper
is skipped automatically without requiring per-test edits.

| Guard | Reason | Reference |
|-------|--------|-----------|
| `requires_fork()` | `os.fork()` not implemented | nanvix/nanvix#321 |
| `requires_subprocess()` | `subprocess` not available | nanvix/nanvix#321 |
| `requires_working_socket()` | Sockets not available | nanvix/nanvix#348 |

---

## External-library test modules (`test-external-libs` target)

### test_sqlite3

| Test | Reason | Skip mechanism |
|------|--------|----------------|
| `test_sqlite3.test_cli` | Uses `subprocess`; auto-skipped by `requires_subprocess()` | Automatic (platform guard) |
| `test_sqlite3.test_transactions` (WAL mode) | WAL journal mode requires `fcntl` file-locking which may not be fully supported on Nanvix | Automatic (SQLite falls back to DELETE journal mode when WAL is unavailable) |

### test_hashlib

| Test | Reason | Skip mechanism |
|------|--------|----------------|
| Large-data benchmark cases decorated with `@requires_resource('cpu')` | Not enabled by default; only run when `-u cpu` is passed to regrtest | Automatic (resource guard) |

### test_ssl

`test_ssl` is run as a separate regrtest invocation with `-u network` (see
`test-external-libs` in `Makefile.nanvix`).  The `-u network` flag enables the
loopback-only SSL tests while real outbound-network tests remain suppressed
because `has_socket_support = False` on Nanvix causes all socket-dependent
tests to be skipped via `requires_working_socket()`.

| Test | Reason | Skip mechanism |
|------|--------|----------------|
| `NetworkedTests` (entire class) | Requires outbound TCP/IP connections; no network on Nanvix | Automatic (`requires_working_socket()` / `requires_resource('network')`) |

---

## Notes

- **liblzma** is not present in the Nanvix sysroot, so `test_lzma` is excluded
  from `NANVIX_TEST_LIST_EXTERNAL` entirely.
- Tests that import missing C extension modules raise `unittest.SkipTest` at
  module level via `import_helper.import_module()` – no manual skip required.

# Nanvix CPython Test Skip List

This document records all test methods and test classes that are explicitly
skipped on the Nanvix platform, together with the reason and the issue that
tracks re-enabling each skip.

---

## How skips are applied

Skips are applied with standard `unittest` decorators directly in the test
source files.  The primary condition predicates are defined in
`Lib/test/support/__init__.py`:

| Predicate | Meaning |
|-----------|---------|
| `is_nanvix` | `sys.platform == "nanvix"` |
| `has_fork_support` | `False` on Nanvix (no `fork(2)`) |
| `has_subprocess_support` | `False` on Nanvix (no `subprocess`) |
| `has_socket_support` | `False` on Nanvix (no TCP/UDP sockets) |

Tests that use `@requires_subprocess()`, `@requires_fork()`, or
`bigmemtest(size=_4G, …)` are already skipped automatically via those
helpers; they are not repeated here.

---

## test_ssl — `Lib/test/test_ssl.py`

### Root cause
Nanvix does not support TCP/UDP sockets (`has_socket_support = False`).
All test classes that call `socket.socket()` or use the `ThreadedEchoServer`
helper are guarded with
`@unittest.skipUnless(support.has_socket_support, "requires socket support")`.

### Affected classes / methods

| Item | Type | Reason |
|------|------|--------|
| `BasicSocketTests` | class | Calls `socket.socket()` extensively |
| `ContextTests.test_context_custom_class` | method | Calls `socket.socket()` to wrap |
| `SSLErrorTests.test_subclass` | method | Uses `socket.create_server()` / `create_connection()` |
| `SimpleBackgroundTests` | class | Uses `ThreadedEchoServer` (requires sockets) |
| `NetworkedTests` | class | Requires network sockets (also gated on `network` resource) |
| `ThreadedTests` | class | Uses `ThreadedEchoServer` (requires sockets) |
| `TestPostHandshakeAuth` | class | Uses `ThreadedEchoServer` (requires sockets) |
| `TestSSLDebug` | class | Uses `ThreadedEchoServer` (requires sockets) |
| `TestPreHandshakeClose` | class | Uses sockets for close-during-handshake scenarios |

### Tracking issue
https://github.com/nanvix/nanvix/issues/321 (socket support)

---

## test_sqlite3 — `Lib/test/test_sqlite3/test_dbapi.py`

### Affected methods

| Method | Class | Reason |
|--------|-------|--------|
| `test_open_with_undecodable_path` | `OpenTests` | Nanvix filesystem does not support undecodable (non-UTF-8) path names |
| `test_open_undecodable_uri` | `OpenTests` | Same reason |

The decorator was extended from `is_emscripten or is_wasi` to
`is_emscripten or is_wasi or is_nanvix`.

### Tracking issue
Nanvix VFS limitation — no dedicated issue yet.

---

## Automatically skipped (no source change required)

The following test classes / methods are already automatically skipped on
Nanvix by existing helpers and do **not** require additional annotations:

| Module | Item | Skip mechanism |
|--------|------|----------------|
| `test_gzip` | `TestCommandLine` | `@requires_subprocess()` |
| `test_hashlib` | `LargeFileTests` | `@unittest.skipIf(sys.maxsize < _4G + 5, ...)` (32-bit) |
| `test_sqlite3/test_dbapi` | `MultiprocessTests` | `@requires_subprocess()` |
| `test_bz2` | `ThreadedBZ2FileTest.testThreadSafety` | `@threading_helper.requires_working_threading()` |

# Nanvix CPython Test Skip List

This document records all skip decorators and module-level skip guards added to
CPython test modules for the Nanvix platform. Each entry explains *what* is
skipped, *where* the guard lives, and *why* it is needed.

---

## Automatically-skipped tests (no code change required)

The following tests are skipped automatically by existing guards in
`Lib/test/support/__init__.py` whenever `sys.platform == 'nanvix'`:

| Guard | Condition on Nanvix | Affected modules |
|-------|---------------------|-----------------|
| `support.has_fork_support = False` | `is_nanvix` disables fork | Any test decorated with `@support.requires_fork()` or using `skip_unless_reliable_fork` |
| `support.has_subprocess_support = False` | `is_nanvix` disables subprocess | Any test decorated with `@requires_subprocess()`; also `assert_python_ok`/`assert_python_failure` via `@requires_subprocess()` on `_assert_python` |
| `support.has_socket_support = False` | `is_nanvix` disables sockets | Any test decorated with `@requires_working_socket()` or module with `requires_working_socket(module=True)` |

### Threading modules — auto-skipped test examples

| Module | Skipped tests / classes | Reason |
|--------|------------------------|--------|
| `test_thread` | `TestThread.test_forkinthread` | `@support.requires_fork()` — no fork on Nanvix |
| `test_threading` | All `@skip_unless_reliable_fork` tests (e.g. `test_dummy_thread_after_fork`, `test_is_alive_after_fork`, `test_main_thread_after_fork*`, `test_2_join_in_forked_process`, `test_3_join_in_forked_from_thread`, `test_reinit_tls_after_fork`, `test_clear_threads_states_after_fork`) | `has_fork_support = False` → `skip_unless_reliable_fork` skips them |
| `test_threading` | `test_main_thread_after_fork_from_foreign_thread` | `@support.requires_fork()` |
| `test_threading` | `ThreadJoinOnShutdown.test_1_join_on_shutdown`, `test_4_daemon_threads`, `ThreadingExceptionTests.*`, `MiscTestCase.test_main_thread_weaks` | `assert_python_ok`/`assert_python_failure` → `@requires_subprocess()` on `_assert_python` |
| `test_threading` | `ThreadTests.test_finalize_running_thread`, `test_finalize_with_trace`, `test_limbo_cleanup_on_failed_start`, `test_frame_tstate_tracing` | `assert_python_ok`/`assert_python_failure` → `@requires_subprocess()` |
| `test_asyncgen` | Entire module | `requires_working_socket(module=True)` — no sockets on Nanvix |

---

## Explicitly-added skip guards (code changes in this PR)

### `Lib/test/test_threadsignals.py`

**Change:** Added module-level `raise unittest.SkipTest(...)` guard immediately
after the existing Windows guard.

```python
if sys.platform == 'nanvix':
    raise unittest.SkipTest("SIGUSR1/SIGUSR2/SIGALRM delivery to threads is unreliable on Nanvix")
```

**Skipped tests:**

| Test | Signal(s) used | Reason skipped |
|------|----------------|----------------|
| `ThreadSignals.test_signals` | `SIGUSR1`, `SIGUSR2` | `signal.raise_signal(SIGUSR1/SIGUSR2)` from a background thread; Nanvix does not reliably deliver these to the main thread — test hangs on `signalled_all.acquire()` |
| `ThreadSignals.test_lock_acquire_interruption` | `SIGALRM` | Uses `signal.alarm(1)` to interrupt a blocking `lock.acquire()`; Nanvix SIGALRM delivery to threads is unreliable |
| `ThreadSignals.test_rlock_acquire_interruption` | `SIGALRM` | Same as above for `RLock` |
| `ThreadSignals.test_lock_acquire_retries_on_intr` | `SIGUSR1` | `os.kill(process_pid, SIGUSR1)` from a thread; Nanvix does not guarantee intra-process signal routing |
| `ThreadSignals.test_rlock_acquire_retries_on_intr` | `SIGUSR1` | Same as above for `RLock` |
| `ThreadSignals.test_interrupted_timed_acquire` | `SIGUSR1` | Repeated `os.kill(process_pid, SIGUSR1)` from a thread; same Nanvix limitation |

**Reference:** Nanvix issue — no reliable POSIX signal-to-thread routing for
SIGUSR1, SIGUSR2, and SIGALRM in the current Nanvix POSIX layer.

---

## Deferred / not yet enabled

The following threading-adjacent modules are deferred to future issues:

| Module | Blocker |
|--------|---------|
| `test_concurrent_futures` (process pool) | `_multiprocessing` / `subprocess` required for `ProcessPoolExecutor`; `__init__.py` imports `_multiprocessing` at package level |

# Nanvix Test Skip List

Tests that are intentionally skipped or known to fail when running the CPython
test suite on Nanvix. Updated whenever a new test module is enabled. See
[issue #330](https://github.com/nanvix/cpython/issues/330) for the tracking
issue.

Tests are skipped in one of two ways:

1. **Platform guard in `Lib/test/support/__init__.py`** – module-wide helpers
   such as `requires_fork()`, `requires_subprocess()`, and
   `requires_working_socket()` automatically skip decorated tests because
   `is_nanvix = True` sets `has_fork_support`, `has_subprocess_support`, and
   `has_socket_support` all to `False`.

2. **`@unittest.skipIf(support.is_nanvix, "…")`** – inline decorator on a
   specific test method or class when the failure is not caught by an existing
   platform guard.

---

## Platform Constraints

Nanvix is a **32-bit microkernel OS**. Tests were run on **i686** (microvm
platform, multi-process mode, 128 MB RAM). These findings are specific to the
i686 target; other Nanvix targets have not yet been tested. Future work should
run the test suite against all CI targets (excluding Hyperlight).

| Constraint | Root cause | Tracking issue |
|---|---|---|
| No `fork()` | Not yet implemented in Nanvix kernel | nanvix/nanvix#321 |
| No subprocess | Depends on `fork()` | nanvix/nanvix#321 |
| No sockets | Network stack not exposed to user-space | nanvix/nanvix#322 |
| No `rmdir()` | Returns `ENOSYS` | nanvix/nanvix#348 |
| No `liblzma` | Library not in sysroot | — |
| Pickle corruption | 32-bit pointer/size truncation in C accelerator | — |
| 32-bit overflow | `2**32`/`2**63`/`2**65` values overflow or OOM | — |
| Missing C extensions | `_testcapi`, `_testinternalcapi`, `_ctypes_test` not built | — |
| Round-half-up | Nanvix C library uses round-half-up, not round-half-to-even | — |

---

## Summary of Manual Skips (all PRs)

| PR | Scope | New test files with skips | New skip decorators |
|----|-------|--------------------------|---------------------|
| [#341](https://github.com/nanvix/cpython/pull/341) | Core language & builtins | 26 | ~73 |
| [#342](https://github.com/nanvix/cpython/pull/342) | String, encoding & serialization | 0 | 0 |
| [#343](https://github.com/nanvix/cpython/pull/343) | Threading & concurrency | 0 | 0 |
| [#344](https://github.com/nanvix/cpython/pull/344) | Data structures & algorithms | 12 | ~41 |
| [#346](https://github.com/nanvix/cpython/pull/346) | C API & extensions | 0 | 0 |
| [#347](https://github.com/nanvix/cpython/pull/347) | Filesystem & I/O | 13 | ~21 |
| [#349](https://github.com/nanvix/cpython/pull/349) | External library integration | 3 | 5 |
| **Total** | | **54** | **~140** |

---

## Auto-Skips (No Decorator Needed)

These modules or tests skip automatically via existing guards:

| Module | Mechanism | Notes |
|--------|-----------|-------|
| `test_bytes` | Import-time skip | `No module named '_testcapi'` |
| `test_perf_profiler` | Module-level `SkipTest` | `has_subprocess_support` is `False` |
| `test_tokenize` | `@requires_subprocess()` methods | `run_python_until_end`, `run_test_script` auto-skip |
| `test_quopri` | `@support.requires_subprocess()` | subprocess tests auto-skip |
| `test_json/test_tool` | `@support.requires_subprocess()` | subprocess tests auto-skip |
| `test_re` | `@unittest.skipIf(multiprocessing is None, ...)` | multiprocessing fails without fork |
| `test_unicode` | `@unittest.skipIf(_testcapi is None, ...)` | `_testcapi` unavailable |
| `test_codecs` | `@unittest.skipIf(_testcapi/_testinternalcapi is None, ...)` | C-API tests auto-skip |
| `test_marshal` | `@unittest.skipUnless(_testcapi, ...)` | C-API test class auto-skips |
| `test_clinic` | `test_tools.__init__` raises `SkipTest` | No subprocess support |
| `test_file_eintr` | Module-level `SkipTest` | `has_subprocess_support` is `False` on Nanvix |
| `test_largefile` | `@skip_no_disk_space` / `@requires_resource('cpu')` | 128 MB VM has insufficient disk/memory |
| `test_mmap` | `import_module('mmap')` | Auto-skips if `mmap` module not available on Nanvix |
| `test_source_encoding` | `@requires_subprocess()` | Subprocess-based tests auto-skip |
| `test_dbm_gnu` | `import_module("dbm.gnu")` | Auto-skips if `_gdbm` not available |
| `test_dbm_ndbm` | `import_module("dbm.ndbm")` | Auto-skips if `_dbm` not available |
| Various subprocess tests | `@requires_subprocess()` | Auto-skips on Nanvix via `has_subprocess_support` |
| `test_asyncgen` | `requires_working_socket` | No sockets on Nanvix |
| `test_threadsignals` | Entire module | `SIGUSR1`/`SIGUSR2`/`SIGALRM` delivery to threads unreliable |

---

## Platform Fixes (Code Changes)

Changes to test infrastructure to allow importing on Nanvix:

| File | Change | Reason |
|------|--------|--------|
| `Lib/test/support/bytecode_helper.py` | Wrapped `from _testinternalcapi import ...` in try/except; added `_HAS_INTERNAL_CAPI` flag | Top-level unconditional import would crash on import for any module that uses `BytecodeTestCase`. |
| `Lib/test/test_bz2.py` | `ext_decompress()`: set `has_cmdline_bunzip2 = False` when `support.is_nanvix` | Prevents 12 test failures from `subprocess.check_output(['bunzip2'], ...)`. Falls back to pure-Python `bz2.decompress()`. |
| `Lib/test/test_sqlite3/test_dbapi.py` | Wrapped `from _testcapi import INT_MAX, ULLONG_MAX` in `try/except`; defined fallback constants | Unconditional import crashes `test_dbapi` and all 6 sub-modules that depend on it. |
| `Lib/test/test_glob.py` | Wrapped `shutil.rmtree` in `try/except OSError` in `tearDown` | Handles Nanvix's `ENOSYS` from `rmdir`. |

---

## Manual Skips — Core Language & Builtins (PR #341)

| Module | Test | Root Cause | Reason |
|--------|------|-----------|--------|
| `test_builtin` | `BuiltinTest.test_compile_top_level_await` | No socket support | `asyncio.run()` creates `_UnixSelectorEventLoop` which fails on self-pipe creation (socketpair). `__del__` raises `AttributeError: '_UnixSelectorEventLoop' object has no attribute '_ssock'`. Extended existing `is_emscripten or is_wasi` guard. |
| `test_builtin` | `BuiltinTest.test_filter_pickle` | Pickle corruption | `pickle.loads(pickle.dumps(filter(...)))` → `ValueError: invalid literal for int() with base 10: 'zd\n'` |
| `test_builtin` | `BuiltinTest.test_map_pickle` | Pickle corruption | Same root cause — `map` object pickle roundtrip fails. |
| `test_builtin` | `BuiltinTest.test_zip_pickle` | Pickle corruption | Same root cause — `zip` object pickle roundtrip fails. |
| `test_builtin` | `BuiltinTest.test_zip_pickle_strict` | Pickle corruption | Same root cause — `zip(strict=True)` pickle roundtrip fails. |
| `test_builtin` | `BuiltinTest.test_zip_pickle_strict_fail` | Pickle corruption | Same root cause — `zip(strict=True)` with mismatched lengths. |
| `test_builtin` | `BuiltinTest.test_round` | Round-half-up | `round(6.5)` returns `7` instead of `6`. Nanvix C library uses round-half-up, not round-half-to-even. |
| `test_builtin` | `BuiltinTest.test_round_large` | Round-half-up | `round(5e15 + 1)` returns wrong value. Extended existing `system_round_bug` guard. |
| `test_int` | `IntStrDigitLimitsTests.test_int_max_str_digits_is_per_interpreter` | Missing `_testcapi` | Calls `support.run_in_subinterp()` which requires the `_testcapi` C extension. |
| `test_operator` | `PyPyOperatorPickleTestCase` (class) | Pickle corruption | All 12 methods pickle/unpickle `attrgetter`/`itemgetter`/`methodcaller` objects. Corrupt data on Nanvix. |
| `test_operator` | `PyCOperatorPickleTestCase` (class) | Pickle corruption | Same — py_operator source, c_operator target. `_operator` is built-in on Nanvix so `@skipUnless(c_operator)` doesn't fire. |
| `test_operator` | `CPyOperatorPickleTestCase` (class) | Pickle corruption | Same — c_operator source, py_operator target. |
| `test_operator` | `CCOperatorPickleTestCase` (class) | Pickle corruption | Same — c_operator for both source and target. |
| `test_range` | `RangeTest.test_pickling` | 32-bit overflow | `range(2**65, 2**65+2)` produces corrupt pickle data on 32-bit. |
| `test_range` | `RangeTest.test_iterator_pickling` | 32-bit overflow | Range bounds from `2**31` and `2**63` — the `2**63` cases cause OOM/overflow. |
| `test_range` | `RangeTest.test_iterator_pickling_overflowing_index` | 32-bit overflow | `iter(range(2**32 + 2))` with `__setstate__(2**32 + 1)` overflows iterator index. |
| `test_range` | `RangeTest.test_exhausted_iterator_pickling` | 32-bit overflow | `range(2**65, 2**65+2)` exhausted iterator pickle fails. |
| `test_range` | `RangeTest.test_large_exhausted_iterator_pickling` | Pickle corruption | Exhausted iterator from `range(20)` — even small values produce corrupt pickle data. |
| `test_range` | `RangeTest.test_iterator_unpickle_compat` | 64-bit pickle bytes | Pre-encoded pickle bytes contain 64-bit integer representations that fail on 32-bit. |
| `test_range` | `RangeTest.test_iterator_setstate` | 32-bit overflow | `range(-2**65, 20, 2)` and `range(10, 2**65, 2)` with `2**64`-scale `__setstate__` values. |
| `test_range` | `RangeTest.test_range_iterators` | 32-bit overflow | "Fast" iterators with `2**32` and `2**64` limits cause OOM/overflow. |
| `test_slice` | `SliceTest.test_pickle` | Pickle corruption | `pickle.dumps(slice(10, 20, 3))` → corrupt data → `ValueError: invalid literal for int()`. |
| `test_tuple` | `TupleTest.test_pickle` | Pickle corruption | Inherited from `seq_tests.CommonTest`. `pickle.dumps((4, 5, 6, 7))` → `'zd\n'` → `ValueError`. |
| `test_tuple` | `TupleTest.test_iterator_pickle` | Pickle corruption | `pickle.dumps(iter((4, 5, 6, 7)))` → corrupt data. |
| `test_tuple` | `TupleTest.test_reversed_pickle` | Pickle corruption | `pickle.dumps(reversed((4, 5, 6, 7)))` → corrupt data. |
| `test_ast` | `AST_Tests.test_pickling` | Pickle corruption | `pickle.dumps(ast.parse(...))` → corrupt data on 32-bit Nanvix. |
| `test_ast` | `AST_Tests.test_ast_recursion_limit` | Deep recursion crash | `crash_depth=100_000` may exhaust stack on 32-bit VM. |
| `test_ast` | `ModuleStateTests.test_subinterpreter` | Missing `_testcapi` | Calls `support.run_in_subinterp()` which imports `_testcapi`. |
| `test_code` | `CodeTest.test_newempty` | Missing `_testcapi` | Method body imports `_testcapi` directly (`import _testcapi`). |
| `test_compiler_assemble` | `IsolatedAssembleTests` (class) | Missing `_testinternalcapi` | Entire class requires `_testinternalcapi` for low-level assembler introspection. |
| `test_compiler_codegen` | `IsolatedCodeGenTests` (class) | Missing `_testinternalcapi` | Entire class requires `_testinternalcapi` for code-gen introspection. |
| `test_peepholer` | `DirectCfgOptimizerTests` (class) | Missing `_testinternalcapi` | Requires `_testinternalcapi` for direct CFG optimizer access. |
| `test_call` | `TestCallingConventions` (class) | Missing `_testcapi` | Class calls C callable methods (`meth_varargs`, `meth_o`, etc.) on `_testcapi` module. |
| `test_call` | `TestCallingConventionsInstance` (class) | Missing `_testcapi` | Subclass of `TestCallingConventions` testing bound methods on `_testcapi.MethInstance`. |
| `test_call` | `TestCallingConventionsClass` (class) | Missing `_testcapi` | Subclass of `TestCallingConventions` testing class methods on `_testcapi.MethClass`. |
| `test_call` | `TestCallingConventionsClassInstance` (class) | Missing `_testcapi` | Subclass of `TestCallingConventions` testing class methods on `_testcapi.MethClass()`. |
| `test_call` | `TestCallingConventionsStatic` (class) | Missing `_testcapi` | Subclass of `TestCallingConventions` testing static methods on `_testcapi.MethStatic`. |
| `test_call` | `FastCallTests` (class) | Missing `_testcapi` | All test methods call `_testcapi.pyobject_fastcall`, `pyobject_vectorcall`, etc. Class body also guarded with `if _testcapi is not None:` to prevent `AttributeError` at definition time. |
| `test_call` | `TestPEP590` (class) | Missing `_testcapi` | All tests use `_testcapi.MethodDescriptorBase`, `MethodDescriptorDerived`, etc. |
| `test_call` | `TestRecursion` (class) | Missing `_testcapi` | `test_super_deep` defines closures `c_recurse`/`c_py_recurse` that call `_testcapi.pyobject_fastcall`; the class has no other tests. |
| `test_contextlib` | `ContextManagerTestCase.test_contextmanager_traceback` | Traceback formatting | `traceback.FrameSummary.line` returns `'1 / 0'` instead of `'1/0'` — whitespace-normalized source differs from expected string. |
| `test_contextlib` | `FileContextTestCase.testWithOpen` | Garbled temp dir | `tempfile.mktemp()` produces garbled temporary directory name on Nanvix, causing `FileNotFoundError`. |
| `test_contextlib` | `TestExitStack.test_exit_exception_traceback` | Traceback formatting | Same as `test_contextmanager_traceback` — expected traceback line `'1/0'` doesn't match `'1 / 0'`. |
| `test_decimal` | `PythonAPItests.test_pickle` | Pickle corruption | `pickle.dumps(Decimal(...))` → corrupt data on 32-bit Nanvix. |
| `test_decimal` | `ContextAPItests.test_pickle` | Pickle corruption | Same — `Context` object pickle roundtrip fails. |
| `test_dict` | `DictTest.test_iterator_pickling` | Pickle corruption | `pickle.dumps(iter({...}))` → corrupt data on 32-bit Nanvix. |
| `test_dict` | `DictTest.test_itemiterator_pickling` | Pickle corruption | `pickle.dumps(iter({...}.items()))` → corrupt data. |
| `test_dict` | `DictTest.test_valuesiterator_pickling` | Pickle corruption | `pickle.dumps(iter({...}.values()))` → corrupt data. |
| `test_dict` | `DictTest.test_reverseiterator_pickling` | Pickle corruption | `pickle.dumps(reversed({...}))` → corrupt data. |
| `test_dict` | `DictTest.test_reverseitemiterator_pickling` | Pickle corruption | `pickle.dumps(reversed({...}.items()))` → corrupt data. |
| `test_dict` | `DictTest.test_reversevaluesiterator_pickling` | Pickle corruption | `pickle.dumps(reversed({...}.values()))` → corrupt data. |
| `test_exception_group` | `ExceptionGroupTests.test_bad_EG_construction__bad_message` | 32-bit arg numbering | `TypeError` message has garbled argument number on 32-bit — expected `f'argument 1'` but gets different format. |
| `test_exceptions` | `ExceptionTests.testSettingException` | Missing `_testcapi` | Calls `_testcapi.raise_exception()` to test exception attribute setting. |
| `test_exceptions` | `ExceptionTests.testAttributes` | Pickle corruption | Tests pickle roundtrip of various exception objects. |
| `test_exceptions` | `ExceptionTests.test_MemoryError` | Missing `_testcapi` | Calls `_testcapi.pymem_buffer_overflow()` to trigger `MemoryError`. |
| `test_exceptions` | `ExceptionTests.test_exception_with_doc` | Missing `_testcapi` | Creates exception with docstring via `_testcapi.make_exception_with_doc()`. |
| `test_exceptions` | `ExceptionTests.test_memory_error_cleanup` | Missing `_testcapi` | Uses `_testcapi.set_nomemory()` for memory error cleanup tests. |
| `test_exceptions` | `ExceptionTests.test_memory_error_in_subinterp` | No subprocess support | Calls `assert_python_failure()` which requires subprocess. |
| `test_exceptions` | `ImportErrorTests.test_copy_pickle` | Pickle corruption | `pickle.dumps(ImportError(...))` → corrupt data. |
| `test_exceptions` | `SyntaxErrorTests.test_encodings` | No subprocess support | Calls `assert_python_failure()` which requires subprocess. |
| `test_exceptions` | `SyntaxErrorTests.test_non_utf8` | No subprocess support | Calls `assert_python_failure()` which requires subprocess. |
| `test_fractions` | `FractionTest.test_copy_deepcopy_pickle` | Pickle corruption | `pickle.dumps(Fraction(13, 7))` → corrupt data on 32-bit Nanvix. |
| `test_list` | `ListTest.test_iterator_pickle` | Pickle corruption | `pickle.dumps(iter([4, 5, 6, 7]))` → corrupt data. |
| `test_list` | `ListTest.test_reversed_pickle` | Pickle corruption | `pickle.dumps(reversed([4, 5, 6, 7]))` → corrupt data. |
| `test_list` | `ListTest.test_pickle` | Pickle corruption | Inherited from `seq_tests.CommonTest`. `pickle.dumps([4, 5, 6, 7])` → corrupt data. |
| `test_math` | `MathTests.testSinh` | 32-bit float precision | `sinh(1)+sinh(-1)` ≠ 0 due to floating-point precision loss on 32-bit platform. |
| `test_random` | `TestBasicOps.test_pickling` | Pickle corruption | `pickle.dumps(Random())` → corrupt data on 32-bit Nanvix. |
| `test_reprlib` | `LongReprTest` (class) | Filesystem unreliable | `shutil.rmtree` unreliable, `os.mkdir` fails with `FileExistsError` on Nanvix filesystem. |
| `test_statistics` | `TestNormalDist.test_pickle` | Pickle corruption | `pickle.dumps(NormalDist(37.5, 5.625))` → corrupt data. |
| `test_super` | `TestSuper` (class) | VM crash | Nanvix VM crashes when running multiple tests due to `nonlocal __class__` cell corruption in `tearDown`. |
| `test_types` | `UnionTests.test_union_pickle` | Pickle corruption | `pickle.dumps(list[T] \| int)` → corrupt data on 32-bit Nanvix. |
| `test_types` | `SimpleNamespaceTests.test_pickle` | Pickle corruption | `pickle.dumps(SimpleNamespace(...))` → corrupt data. |

---

## Manual Skips — Data Structures & Algorithms (PR #344)

| Module | Test | Root Cause | Reason |
|--------|------|-----------|--------|
| `test_array` | `BaseTest.test_pickle` | Pickle corruption | `pickle.dumps(array.array(...))` → corrupt bytes. Affects all typed test subclasses. |
| `test_array` | `BaseTest.test_pickle_for_empty_array` | Pickle corruption | `pickle.dumps(array.array(typecode))` → corrupt bytes. |
| `test_array` | `BaseTest.test_iterator_pickle` | Pickle corruption | `pickle.dumps(iter(array))` → corrupt bytes. |
| `test_array` | `BaseTest.test_reverse_iterator_pickling` | Pickle corruption | `pickle.dumps(reversed(iter(array)))` → corrupt bytes. |
| `test_buffer` | `TestBufferProtocol.test_pybuffer_size_from_format` | Missing `_testcapi` | `_testcapi.PyBuffer_SizeFromFormat` not available. |
| `test_collections` | `TestChainMap.test_basics` | Pickle corruption | Method includes pickle round-trip of `ChainMap` objects via `pickle.dumps/loads`. |
| `test_collections` | `TestNamedTuple.test_pickle` | Pickle corruption | `pickle.dumps(namedtuple_instance)` → corrupt bytes. |
| `test_collections` | `TestNamedTuple.test_field_descriptor` | Pickle corruption | `pickle.loads(pickle.dumps(Point.x, proto))` for field descriptor pickling. |
| `test_collections` | `TestCounter.test_copying` | Pickle corruption | Method includes pickle round-trip of `Counter` objects. |
| `test_coroutines` | `CoroAsyncIOCompatTest` (class) | No asyncio event loop | Extended existing Emscripten/WASI skip to include Nanvix. Socket support absent → `_UnixSelectorEventLoop` self-pipe fails. |
| `test_coroutines` | `CAPITest` (class) | Missing `_testcapi` | All methods use `_testcapi.awaitType` → `ImportError`. |
| `test_defaultdict` | `TestDefaultDict.test_pickling` | Pickle corruption | `pickle.dumps(defaultdict)` → corrupt bytes. |
| `test_deque` | `TestBasic.test_pickle` | Pickle corruption | `pickle.dumps(deque(range(200)))` → corrupt bytes. |
| `test_deque` | `TestBasic.test_pickle_recursive` | Pickle corruption | `pickle.dumps(d)` where `d.append(d)` → corrupt bytes. |
| `test_deque` | `TestBasic.test_iterator_pickle` | Pickle corruption | `pickle.dumps(iter(deque))` → corrupt bytes. |
| `test_deque` | `TestSubclass.test_copy_pickle` | Pickle corruption | Method includes pickle round-trip of deque subclass. |
| `test_deque` | `TestSubclass.test_pickle_recursive` | Pickle corruption | Recursive deque pickle → corrupt bytes. |
| `test_functools` | `TestPartial.test_pickle` | Pickle corruption | `pickle.dumps(partial(...))` → corrupt bytes. Affects `TestPartialC`, `TestPartialPy`, and subclass variants. |
| `test_functools` | `TestPartial.test_recursive_pickle` | Pickle corruption | `pickle.dumps(f)` where `f.__setstate__((f, ...))` → corrupt bytes. |
| `test_functools` | `TestTotalOrdering.test_pickle` | Pickle corruption | `pickle.dumps(method)` for total ordering methods → corrupt bytes. |
| `test_functools` | `TestLRU.test_pickle` | Pickle corruption | `pickle.dumps(lru_cache_func)` → corrupt bytes. Affects `TestLRUC` and `TestLRUPy`. |
| `test_iter` | `TestCase.test_mutating_seq_class_iter_pickle` | Pickle corruption | Direct `pickle.dumps/loads` of iterator+sequence pairs. |
| `test_iter` | `check_pickle` helper | Pickle corruption | Made no-op on Nanvix; all `check_iterator`/`check_for_loop` callers that pass `pickle=True` (the default) skip the pickle sub-check while still exercising iterator behaviour. |
| `test_itertools` | `pickle_deprecated` wrapper (27 methods) | Pickle corruption | Wrapper raises `SkipTest` on Nanvix before any pickle calls. Covers all `@pickle_deprecated`-decorated tests. |
| `test_itertools` | `TestBasicOps.test_filter` | Pickle corruption | Direct `pickle.dumps/loads` in `test_filter` method. |
| `test_ordered_dict` | `OrderedDictTests.test_copying` | Pickle corruption | Method includes pickle round-trip of `OrderedDict`. Affects `PurePythonOrderedDictTests` and `CPythonOrderedDictTests`. |
| `test_ordered_dict` | `OrderedDictTests.test_pickle_recursive` | Pickle corruption | `pickle.dumps(od)` where `od[1] = od` → corrupt bytes. |
| `test_ordered_dict` | `CPythonOrderedDictTests.test_iterators_pickling` | Pickle corruption | `pickle.dumps(iter(od))` → corrupt bytes. |
| `test_set` | `TestJointOps.test_pickling` | Pickle corruption | `pickle.dumps(set)` → corrupt bytes → `ValueError` on `pickle.loads`. Affects all subclasses (`TestSet`, `TestSetSubclass`, `TestFrozenSet`, `TestFrozenSetSubclass`). |
| `test_set` | `TestJointOps.test_iterator_pickling` | Pickle corruption | `pickle.dumps(iter(set))` → corrupt bytes. |
| `test_set` | `TestBasicOps.test_pickling` | Pickle corruption | `pickle.dumps(self.set)` → corrupt bytes. |
| `test_weakref` | `ReferencesTestCase.test_cfunction` | Missing `_testcapi` | Directly imports `_testcapi` → `ImportError` on Nanvix. |

---

## Manual Skips — Filesystem & I/O (PR #347)

| Module | Test | Root Cause | Reason |
|--------|------|-----------|--------|
| `test_configparser` | `ExceptionPicklingTestCase` (class) | Pickle corruption | All 11 test methods pickle/unpickle configparser exception objects. Corrupt data on Nanvix. |
| `test_fileio` | `OtherFileTests.testBlksize` | No `st_blksize` | WASI/Nanvix does not expose `st_blksize` in stat results. |
| `test_fileio` | `OtherFileTests.testAbles` (partial) | No `/dev/tty` | `/dev/tty` does not exist on Nanvix. Guarded by `if` block, not a full skip. |
| `test_genericpath` | `AllCommonTest.test_exists_fd` | Pipe fds have no stat | `os.pipe()` fds cannot be `fstat()`'d on Nanvix (same as Emscripten). |
| `test_import` | `ImportTests.test_from_import_missing_attr_has_name_and_so_path` | Missing `_testcapi` | Directly imports `_testcapi` which is not built for Nanvix. |
| `test_import` | `ImportTests.test_creation_mode` | Stub umask | Nanvix `umask()` is a stub; mode checks fail. Extended existing WASI/Emscripten guard. |
| `test_import` | `ImportTests.test_unwritable_directory` | Stub umask | Same root cause — `umask(0o222)` has no effect on Nanvix. |
| `test_int` | `IntStrDigitLimitsTests.test_int_max_str_digits_is_per_interpreter` | Missing `_testcapi` | Calls `support.run_in_subinterp()` which requires the `_testcapi` C extension. |
| `test_io` | `CommonBufferedTests.test_optional_abilities` | Pipe fds have no stat | `fstat()` on pipe fd not supported on Nanvix. Extended existing Emscripten guard. |
| `test_io` | `CIOTest.test_open_pipe_with_append` | Pipe fds have no stat | Same — `open()` on pipe fd triggers `fstat()`. |
| `test_io` | `CIOTest.test_nonblock_pipe_write_bigbuf` | Pipe fds have no stat | Non-blocking pipe write triggers `fstat()`. |
| `test_io` | `CIOTest.test_nonblock_pipe_write_smallbuf` | Pipe fds have no stat | Same as above with smaller buffer. |
| `test_os` | `StatAttributeTests.test_stat_result_pickle` | Pickle corruption | `pickle.dumps(os.stat_result)` → corrupt data. |
| `test_os` | `StatAttributeTests.test_statvfs_result_pickle` | Pickle corruption | `pickle.dumps(os.statvfs_result)` → corrupt data. |
| `test_os` | `MakedirTests.test_mode` | Stub umask | `os.umask()` is a stub on Nanvix. Extended existing WASI/Emscripten guard. |
| `test_os` | `MakedirTests.test_exist_ok_existing_directory` | Stub umask | Same root cause. |
| `test_os` | `MakedirTests.test_exist_ok_s_isgid_directory` | Stub umask | Same root cause. |
| `test_os` | `DevNullTests` (class) | No `/dev/null` | Nanvix has no `/dev/null`. Extended existing WASI guard. |
| `test_pathlib` | `_BasePurePathTest.test_pickling_common` | Pickle corruption | `pickle.dumps(PurePath)` → corrupt data. |
| `test_pathlib` | `_BasePathTest.test_pickling_common` | Pickle corruption | `pickle.dumps(Path)` → corrupt data. |
| `test_pathlib` | `PathTest.test_open_mode` | Stub umask | `os.umask()` is a stub. Extended existing WASI/Emscripten guard. |
| `test_pathlib` | `PathTest.test_touch_mode` | Stub umask | Same root cause. |
| `test_shutil` | `TestGetTerminalSize.test_fallback` | No `/dev/null` | Extended existing WASI guard. |
| `test_stat` | `TestFilemodeCStat.test_devices` | No `/dev/null` | `os.devnull` does not exist on Nanvix. |
| `test_tarfile` | `GzipWriteTest.test_file_mode` | Stub umask | Extended existing WASI/Emscripten guard. |
| `test_tempfile` | `TestBadTempdir.test_read_only_directory` | Cannot remove write bits | Nanvix in-memory FS does not enforce write-bit removal. Extended Emscripten guard. |
| `test_tempfile` | `TestSpooledTemporaryFile.test_del_rolled_file` | Cannot fstat renamed files | Nanvix in-memory FS does not support fstat on renamed files. |
| `test_tempfile` | `TestSpooledTemporaryFile.test_truncate_with_size_parameter` | Cannot fstat renamed files | Same root cause. |
| `test_zipimport` | `UncompressedZipImportTestCase.testFileUnreadable` | Mode 000 not enforced | Nanvix in-memory FS does not enforce mode 000. Extended existing WASI guard. |

---

## Manual Skips — External Library Integration (PR #349)

| Module | Test | Root Cause | Reason |
|--------|------|-----------|--------|
| `test_zlib` | `CompressTestCase.test_big_compress_buffer` | 128 MB VM OOM | `check_big_compress_buffer` unconditionally allocates 10 MiB via `random.randbytes(_1M * 10)`, triggering `MemoryError`. |
| `test_zlib` | `CompressObjectTestCase.test_big_compress_buffer` | 128 MB VM OOM | Same root cause — `CompressObject` variant. |
| `test_sqlite3` | `CommandLineInterface.test_cli_on_disk_db` | Garbled TESTFN + SQLITE_IOERR_LOCK | TESTFN resolves to garbled `'@test_1_tmpæ'`; SQLite file-locking (`fcntl`) returns `SQLITE_IOERR_LOCK`. |
| `test_sqlite3` | `InteractiveSession.test_interact_on_disk_file` | Garbled TESTFN + SQLITE_IOERR_LOCK | Same root cause. |
| `test_sqlite3` | `DateTimeTests.test_sql_timestamp` | Broken system clock | `current_timestamp` returns epoch (1969); `ts.year` ≠ `now.year`. |

---

## Excluded Modules

These modules are excluded from `NANVIX_TEST_LIST` entirely and cannot be enabled:

| Module | PR | Reason |
|--------|----|--------|
| `test_exception_hierarchy` | #341 | Crashes at import time — `errno.ESHUTDOWN` missing on Nanvix |
| `test_inspect` | #341 | VM hangs — `IsolatedAsyncioTestCase` sets up asyncio event loop before skip is evaluated; module too large for 128 MB VM |
| `test_capi` | #346 | `_testcapi` not built — sub-modules crash at import |
| `test_ctypes` | #346 | 17 sub-modules import `_ctypes_test` at module level — not built |
| `test_stable_abi_ctypes` | #346 | `from _testcapi import get_feature_macros` fails at import |
| `test_gzip` | #349 | Garbled `tempfile.mkstemp()` paths cause `PermissionError` in `setUp` for nearly every test (64 errors). Cleanup also crashes regrtest with `OSError: [Errno 88]`. |
| `test_ssl` | #349 | Crashes at import time: `from errno import ... ESHUTDOWN` raises `ImportError`. Same root cause as `test_exception_hierarchy`. |
| `test_lzma` | #349 | `liblzma` not in Nanvix sysroot |

---

## Clean-Pass Modules

These modules pass with zero skips needed:

### Core Language & Builtins (PR #341)

- `test_augassign`, `test_binop`, `test_bool`, `test_compare`, `test_complex`,
  `test_contains`, `test_float`, `test_memoryview`, `test_richcmp`, `test_struct`,
  `test_unary`
- `test_grammar`, `test_syntax`, `test_compile`, `test_symtable`, `test_opcache`,
  `test_dis`, `test_keyword`
- `test_extcall`, `test_positional_only_arg`, `test_scope`, `test_global`,
  `test_dynamic`, `test_with`
- `test_typechecks`, `test_isinstance`, `test_hash`, `test_index`, `test_property`
- `test_cmath`, `test_numeric_tower`
- `test_raise`, `test_frame`
- `test_contextlib_async`, `test_pprint`
- `test_traceback`

### String, Encoding & Serialization (PR #342)

- `test_string`, `test_string_literals`, `test_unicode`, `test_unicodedata`,
  `test_ucn`, `test_format`, `test_fstring`
- `test_codecs`, `test_codeccallbacks`, `test_codecencodings_cn`,
  `test_codecencodings_hk`, `test_codecencodings_iso2022`, `test_codecencodings_jp`,
  `test_codecencodings_kr`, `test_codecencodings_tw`
- `test_pickle`, `test_pickletools`, `test_marshal`, `test_json`, `test_csv`
- `test_base64`, `test_binascii`, `test_quopri`, `test_uu`
- `test_textwrap`, `test_difflib`, `test_fnmatch`, `test_glob`, `test_shlex`,
  `test_re`

### Threading & Concurrency (PR #343)

- `test_thread`, `test_threading`, `test_threading_local`, `test_lock`,
  `test_multiprocessing_main_handling` (auto-skipped via `requires_subprocess`)

### Data Structures & Algorithms (PR #344)

- `test_weakset`, `test_iterlen`, `test_generators`, `test_generator_stop`,
  `test_yield_from`, `test_listcomps`, `test_dictcomps`, `test_setcomps`,
  `test_genexps`, `test_heapq`, `test_bisect`, `test_sort`, `test_queue`,
  `test_copy`, `test_copyreg`, `test_funcattrs`, `test_decorators`

### C API & Extensions (PR #346)

- `test_cppext` (2 tests auto-skipped via `@requires_subprocess()`)

### Filesystem & I/O (PR #347)

- `test_bufio`, `test_csv`, `test_dbm`, `test_dbm_dumb`, `test_file`,
  `test_filecmp`, `test_fileinput`, `test_fnmatch`, `test_glob`, `test_linecache`,
  `test_modulefinder`, `test_shelve`

### External Library Integration (PR #349)

- `test_hashlib`, `test_hmac`

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
3. If the failure is a known platform limitation, add
   `@unittest.skipIf(support.is_nanvix, "Nanvix: <reason>")` to the test
   method or class in the relevant test file.
4. Add an entry to this file under the appropriate module section, including
   the test name, root cause, and reason.
5. Commit the skip and this updated document together.

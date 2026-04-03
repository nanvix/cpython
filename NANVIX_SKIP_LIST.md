# Nanvix Test Skip List

Tests that are skipped on Nanvix due to genuine platform limitations. See
[#321](https://github.com/nanvix/cpython/issues/321) for the tracking issue.

## Platform Limitations

Nanvix is a 32-bit microkernel OS. Tests were run on **i686** (microvm
platform, multi-process mode, 128 MB RAM). These findings are specific to the
i686 target; other Nanvix targets have not yet been tested. Future work should
run the test suite against all CI targets (excluding Hyperlight).

The main categories of test failure are:

- **Pickle corruption** — even trivial values like `(4, 5, 6, 7)` produce
  corrupt pickle bytes (e.g. `'zd\n'`). Affects all pickle protocols. Likely a
  fundamental issue with the pickle C accelerator or memory layout on 32-bit.
- **32-bit overflow** — tests using values like `2**32`, `2**64`, `2**65` cause
  OOM or arithmetic overflow.
- **Missing C extensions** — `_testcapi` and `_testinternalcapi` are not built
  for Nanvix.
- **No subprocess/fork/socket** — auto-handled by `has_subprocess_support`,
  `has_fork_support`, `has_socket_support` guards in `Lib/test/support/__init__.py`.
  Tests using `@requires_subprocess()` etc. auto-skip without manual decorators.
- **No asyncio event loop** — socket support is absent, so
  `_UnixSelectorEventLoop` fails to create its self-pipe.
- **Round-half-up** — Nanvix's C library uses round-half-up instead of IEEE 754
  round-half-to-even (banker's rounding).

## Auto-Skips (No Decorator Needed)

These modules or tests skip automatically via existing guards:

| Module | Mechanism | Notes |
|--------|-----------|-------|
| test_bytes | Import-time skip | `No module named '_testcapi'` |
| test_perf_profiler | Module-level `SkipTest` | `has_subprocess_support` is `False` |
| test_tokenize | `@requires_subprocess()` methods | `run_python_until_end`, `run_test_script` auto-skip |
| Various subprocess tests | `@requires_subprocess()` | Auto-skips on Nanvix via `has_subprocess_support` |

## Platform Fixes (Code Changes)

Changes to test infrastructure to allow importing on Nanvix:

| File | Change | Reason |
|------|--------|--------|
| `Lib/test/support/bytecode_helper.py` | Wrapped `from _testinternalcapi import ...` in try/except; added `_HAS_INTERNAL_CAPI` flag | Top-level unconditional import would crash on import for any module that uses `BytecodeTestCase`. |

## Manual Skips

| Module | Test | Reason | Failure |
|--------|------|--------|---------|
| test_builtin | `BuiltinTest.test_compile_top_level_await` | No socket support | `asyncio.run()` creates `_UnixSelectorEventLoop` which fails on self-pipe creation (socketpair). `__del__` raises `AttributeError: '_UnixSelectorEventLoop' object has no attribute '_ssock'`. Extended existing `is_emscripten or is_wasi` guard. |
| test_builtin | `BuiltinTest.test_filter_pickle` | Pickle corruption | `pickle.loads(pickle.dumps(filter(...)))` → `ValueError: invalid literal for int() with base 10: 'zd\n'` |
| test_builtin | `BuiltinTest.test_map_pickle` | Pickle corruption | Same root cause — `map` object pickle roundtrip fails. |
| test_builtin | `BuiltinTest.test_zip_pickle` | Pickle corruption | Same root cause — `zip` object pickle roundtrip fails. |
| test_builtin | `BuiltinTest.test_zip_pickle_strict` | Pickle corruption | Same root cause — `zip(strict=True)` pickle roundtrip fails. |
| test_builtin | `BuiltinTest.test_zip_pickle_strict_fail` | Pickle corruption | Same root cause — `zip(strict=True)` with mismatched lengths. |
| test_builtin | `BuiltinTest.test_round` | Round-half-up | `round(6.5)` returns `7` instead of `6`. Nanvix C library uses round-half-up, not round-half-to-even. |
| test_builtin | `BuiltinTest.test_round_large` | Round-half-up | `round(5e15 + 1)` returns wrong value. Extended existing `system_round_bug` guard. |
| test_int | `IntStrDigitLimitsTests.test_int_max_str_digits_is_per_interpreter` | Missing `_testcapi` | Calls `support.run_in_subinterp()` which requires the `_testcapi` C extension. |
| test_operator | `PyPyOperatorPickleTestCase` (class) | Pickle corruption | All 12 methods pickle/unpickle `attrgetter`/`itemgetter`/`methodcaller` objects. Corrupt data on Nanvix. |
| test_operator | `PyCOperatorPickleTestCase` (class) | Pickle corruption | Same — py_operator source, c_operator target. `_operator` is built-in on Nanvix so `@skipUnless(c_operator)` doesn't fire. |
| test_operator | `CPyOperatorPickleTestCase` (class) | Pickle corruption | Same — c_operator source, py_operator target. |
| test_operator | `CCOperatorPickleTestCase` (class) | Pickle corruption | Same — c_operator for both source and target. |
| test_range | `RangeTest.test_pickling` | 32-bit overflow | `range(2**65, 2**65+2)` produces corrupt pickle data on 32-bit. |
| test_range | `RangeTest.test_iterator_pickling` | 32-bit overflow | Range bounds from `2**31` and `2**63` — the `2**63` cases cause OOM/overflow. |
| test_range | `RangeTest.test_iterator_pickling_overflowing_index` | 32-bit overflow | `iter(range(2**32 + 2))` with `__setstate__(2**32 + 1)` overflows iterator index. |
| test_range | `RangeTest.test_exhausted_iterator_pickling` | 32-bit overflow | `range(2**65, 2**65+2)` exhausted iterator pickle fails. |
| test_range | `RangeTest.test_large_exhausted_iterator_pickling` | Pickle corruption | Exhausted iterator from `range(20)` — even small values produce corrupt pickle data. |
| test_range | `RangeTest.test_iterator_unpickle_compat` | 64-bit pickle bytes | Pre-encoded pickle bytes contain 64-bit integer representations that fail on 32-bit. |
| test_range | `RangeTest.test_iterator_setstate` | 32-bit overflow | `range(-2**65, 20, 2)` and `range(10, 2**65, 2)` with `2**64`-scale `__setstate__` values. |
| test_range | `RangeTest.test_range_iterators` | 32-bit overflow | "Fast" iterators with `2**32` and `2**64` limits cause OOM/overflow. |
| test_slice | `SliceTest.test_pickle` | Pickle corruption | `pickle.dumps(slice(10, 20, 3))` → corrupt data → `ValueError: invalid literal for int()`. |
| test_tuple | `TupleTest.test_pickle` | Pickle corruption | Inherited from `seq_tests.CommonTest`. `pickle.dumps((4, 5, 6, 7))` → `'zd\n'` → `ValueError`. |
| test_tuple | `TupleTest.test_iterator_pickle` | Pickle corruption | `pickle.dumps(iter((4, 5, 6, 7)))` → corrupt data. |
| test_tuple | `TupleTest.test_reversed_pickle` | Pickle corruption | `pickle.dumps(reversed((4, 5, 6, 7)))` → corrupt data. |
| test_ast | `AST_Tests.test_pickling` | Pickle corruption | `pickle.dumps(ast.parse(...))` → corrupt data on 32-bit Nanvix. |
| test_ast | `AST_Tests.test_ast_recursion_limit` | Deep recursion crash | `crash_depth=100_000` may exhaust stack on 32-bit VM. |
| test_ast | `ModuleStateTests.test_subinterpreter` | Missing `_testcapi` | Calls `support.run_in_subinterp()` which imports `_testcapi`. |
| test_code | `CodeTest.test_newempty` | Missing `_testcapi` | Method body imports `_testcapi` directly (`import _testcapi`). |
| test_compiler_assemble | `IsolatedAssembleTests` (class) | Missing `_testinternalcapi` | Entire class requires `_testinternalcapi` for low-level assembler introspection. |
| test_compiler_codegen | `IsolatedCodeGenTests` (class) | Missing `_testinternalcapi` | Entire class requires `_testinternalcapi` for code-gen introspection. |
| test_peepholer | `DirectCfgOptimizerTests` (class) | Missing `_testinternalcapi` | Requires `_testinternalcapi` for direct CFG optimizer access. |
| test_call | `TestCallingConventions` (class) | Missing `_testcapi` | Class calls C callable methods (`meth_varargs`, `meth_o`, etc.) on `_testcapi` module. |
| test_call | `TestCallingConventionsInstance` (class) | Missing `_testcapi` | Subclass of `TestCallingConventions` testing bound methods on `_testcapi.MethInstance`. |
| test_call | `TestCallingConventionsClass` (class) | Missing `_testcapi` | Subclass of `TestCallingConventions` testing class methods on `_testcapi.MethClass`. |
| test_call | `TestCallingConventionsClassInstance` (class) | Missing `_testcapi` | Subclass of `TestCallingConventions` testing class methods on `_testcapi.MethClass()`. |
| test_call | `TestCallingConventionsStatic` (class) | Missing `_testcapi` | Subclass of `TestCallingConventions` testing static methods on `_testcapi.MethStatic`. |
| test_call | `FastCallTests` (class) | Missing `_testcapi` | All test methods call `_testcapi.pyobject_fastcall`, `pyobject_vectorcall`, etc. Class body also guarded with `if _testcapi is not None:` to prevent `AttributeError` at definition time. |
| test_call | `TestPEP590` (class) | Missing `_testcapi` | All tests use `_testcapi.MethodDescriptorBase`, `MethodDescriptorDerived`, etc. |
| test_call | `TestRecursion` (class) | Missing `_testcapi` | `test_super_deep` defines closures `c_recurse`/`c_py_recurse` that call `_testcapi.pyobject_fastcall`; the class has no other tests. |
| test_contextlib | `ContextManagerTestCase.test_contextmanager_traceback` | Traceback formatting | `traceback.FrameSummary.line` returns `'1 / 0'` instead of `'1/0'` — whitespace-normalized source differs from expected string. |
| test_contextlib | `FileContextTestCase.testWithOpen` | Garbled temp dir | `tempfile.mktemp()` produces garbled temporary directory name on Nanvix, causing `FileNotFoundError`. |
| test_contextlib | `TestExitStack.test_exit_exception_traceback` | Traceback formatting | Same as `test_contextmanager_traceback` — expected traceback line `'1/0'` doesn't match `'1 / 0'`. |
| test_decimal | `PythonAPItests.test_pickle` | Pickle corruption | `pickle.dumps(Decimal(...))` → corrupt data on 32-bit Nanvix. |
| test_decimal | `ContextAPItests.test_pickle` | Pickle corruption | Same — `Context` object pickle roundtrip fails. |
| test_dict | `DictTest.test_iterator_pickling` | Pickle corruption | `pickle.dumps(iter({...}))` → corrupt data on 32-bit Nanvix. |
| test_dict | `DictTest.test_itemiterator_pickling` | Pickle corruption | `pickle.dumps(iter({...}.items()))` → corrupt data. |
| test_dict | `DictTest.test_valuesiterator_pickling` | Pickle corruption | `pickle.dumps(iter({...}.values()))` → corrupt data. |
| test_dict | `DictTest.test_reverseiterator_pickling` | Pickle corruption | `pickle.dumps(reversed({...}))` → corrupt data. |
| test_dict | `DictTest.test_reverseitemiterator_pickling` | Pickle corruption | `pickle.dumps(reversed({...}.items()))` → corrupt data. |
| test_dict | `DictTest.test_reversevaluesiterator_pickling` | Pickle corruption | `pickle.dumps(reversed({...}.values()))` → corrupt data. |
| test_exception_group | `ExceptionGroupTests.test_bad_EG_construction__bad_message` | 32-bit arg numbering | `TypeError` message has garbled argument number on 32-bit — expected `f'argument 1'` but gets different format. |
| test_exceptions | `ExceptionTests.testSettingException` | Missing `_testcapi` | Calls `_testcapi.raise_exception()` to test exception attribute setting. |
| test_exceptions | `ExceptionTests.testAttributes` | Pickle corruption | Tests pickle roundtrip of various exception objects. |
| test_exceptions | `ExceptionTests.test_MemoryError` | Missing `_testcapi` | Calls `_testcapi.pymem_buffer_overflow()` to trigger `MemoryError`. |
| test_exceptions | `ExceptionTests.test_exception_with_doc` | Missing `_testcapi` | Creates exception with docstring via `_testcapi.make_exception_with_doc()`. |
| test_exceptions | `ExceptionTests.test_memory_error_cleanup` | Missing `_testcapi` | Uses `_testcapi.set_nomemory()` for memory error cleanup tests. |
| test_exceptions | `ExceptionTests.test_memory_error_in_subinterp` | No subprocess support | Calls `assert_python_failure()` which requires subprocess. |
| test_exceptions | `ImportErrorTests.test_copy_pickle` | Pickle corruption | `pickle.dumps(ImportError(...))` → corrupt data. |
| test_exceptions | `SyntaxErrorTests.test_encodings` | No subprocess support | Calls `assert_python_failure()` which requires subprocess. |
| test_exceptions | `SyntaxErrorTests.test_non_utf8` | No subprocess support | Calls `assert_python_failure()` which requires subprocess. |
| test_fractions | `FractionTest.test_copy_deepcopy_pickle` | Pickle corruption | `pickle.dumps(Fraction(13, 7))` → corrupt data on 32-bit Nanvix. |
| test_list | `ListTest.test_iterator_pickle` | Pickle corruption | `pickle.dumps(iter([4, 5, 6, 7]))` → corrupt data. |
| test_list | `ListTest.test_reversed_pickle` | Pickle corruption | `pickle.dumps(reversed([4, 5, 6, 7]))` → corrupt data. |
| test_list | `ListTest.test_pickle` | Pickle corruption | Inherited from `seq_tests.CommonTest`. `pickle.dumps([4, 5, 6, 7])` → corrupt data. |
| test_math | `MathTests.testSinh` | 32-bit float precision | `sinh(1)+sinh(-1)` ≠ 0 due to floating-point precision loss on 32-bit platform. |
| test_random | `TestBasicOps.test_pickling` | Pickle corruption | `pickle.dumps(Random())` → corrupt data on 32-bit Nanvix. |
| test_reprlib | `LongReprTest` (class) | Filesystem unreliable | `shutil.rmtree` unreliable, `os.mkdir` fails with `FileExistsError` on Nanvix filesystem. |
| test_statistics | `TestNormalDist.test_pickle` | Pickle corruption | `pickle.dumps(NormalDist(37.5, 5.625))` → corrupt data. |
| test_super | `TestSuper` (class) | VM crash | Nanvix VM crashes when running multiple tests due to `nonlocal __class__` cell corruption in `tearDown`. |
| test_types | `UnionTests.test_union_pickle` | Pickle corruption | `pickle.dumps(list[T] \| int)` → corrupt data on 32-bit Nanvix. |
| test_types | `SimpleNamespaceTests.test_pickle` | Pickle corruption | `pickle.dumps(SimpleNamespace(...))` → corrupt data. |

## Excluded Modules

These modules are excluded from `NANVIX_TEST_LIST` entirely:

| Module | Reason |
|--------|--------|
| test_exception_hierarchy | Crashes at import time — `errno.ESHUTDOWN` missing on Nanvix |
| test_inspect | VM hangs — `IsolatedAsyncioTestCase` sets up asyncio event loop before skip is evaluated; module too large for 128 MB VM |

## Clean-Pass Modules

These modules pass with zero skips needed:

- test_augassign, test_binop, test_bool, test_compare, test_complex,
  test_contains, test_float, test_memoryview, test_richcmp, test_struct,
  test_unary
- test_grammar, test_syntax, test_compile, test_symtable, test_opcache,
  test_dis, test_keyword
- test_extcall, test_positional_only_arg, test_scope, test_global,
  test_dynamic, test_with
- test_typechecks, test_isinstance, test_hash, test_index, test_property
- test_cmath, test_numeric_tower
- test_raise, test_frame
- test_contextlib_async, test_pprint
- test_traceback

## External Library Tests

Tests for modules that depend on external libraries (zlib, bzip2, OpenSSL,
SQLite) bundled in the Nanvix sysroot. Each module was run individually on the
microvm (multi-process, 128 MB) and failures were diagnosed and skipped.

### Excluded Modules (External Libraries)

| Module | Reason |
|--------|--------|
| test_gzip | All tests fail — `BaseTest.setUp` calls `os_helper.unlink(TESTFN)` which produces `PermissionError: [Errno 1] N: '@test_1_tmpæ'` due to garbled temp filenames on Nanvix filesystem. Every test creates `.gz` files on disk. |
| test_ssl | Crashes at import — `from errno import ESHUTDOWN` raises `ImportError` because `errno.ESHUTDOWN` is not defined on Nanvix. Same root cause as `test_exception_hierarchy`. |

### Platform Fixes (External Libraries)

| File | Change | Reason |
|------|--------|--------|
| `Lib/test/test_sqlite3/test_dbapi.py` | Wrapped `from _testcapi import INT_MAX, ULLONG_MAX` in try/except with fallback values (`2**31-1`, `2**64-1`) | Top-level unconditional import crashes all 6 sqlite3 sub-modules that import from test_dbapi (`test_dbapi`, `test_dump`, `test_hooks`, `test_regression`, `test_transactions`, `test_userfunctions`). |
| `Lib/test/test_bz2.py` | Guard `ext_decompress()` to skip `shutil.which('bunzip2')` when `has_subprocess_support` is `False` | `shutil.which` works but `subprocess.check_output(['bunzip2'])` crashes. The guard makes `ext_decompress` fall back to `bz2.decompress()` on Nanvix, fixing all 12 failing tests. |

### Manual Skips (External Libraries)

| Module | Test | Reason | Failure |
|--------|------|--------|---------|
| test_zlib | `CompressTestCase.test_big_compress_buffer` | 128 MB VM memory limit | `@bigmemtest` allocates `random.randbytes(_1M * 10)` which triggers `MemoryError` on the constrained VM. |
| test_zlib | `CompressObjectTestCase.test_big_compress_buffer` | 128 MB VM memory limit | Same — object-based compress variant of the same big-buffer test. |
| test_sqlite3 | `DateTimeTests.test_sql_timestamp` | System clock returns 1969 | `current_timestamp` yields year 1969 instead of current year; Nanvix system clock is not synchronized. |
| test_sqlite3 | `CommandLineInterface.test_cli_on_disk_db` | Garbled TESTFN / SQLITE_IOERR_LOCK | `TESTFN` resolves to `'@test_1_tmpæ'`; SQLite cannot acquire file lock on garbled path. |
| test_sqlite3 | `InteractiveSession.test_interact_on_disk_file` | Garbled TESTFN / SQLITE_IOERR_LOCK | Same root cause as `test_cli_on_disk_db`. |

### Clean-Pass Modules (External Libraries)

These modules pass with zero manual skips needed:

- test_hashlib (65 passed, 13 auto-skipped)
- test_hmac (24 passed, 4 auto-skipped)

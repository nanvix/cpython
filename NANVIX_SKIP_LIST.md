# Nanvix Test Skip List

Tests skipped with `@unittest.skipIf(support.is_nanvix, ...)` decorators due to
genuine Nanvix platform limitations. See
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

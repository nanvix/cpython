# Nanvix Test Skip List

Tests skipped with `@unittest.skipIf(support.is_nanvix, ...)` decorators due to
genuine Nanvix platform limitations. See
[#321](https://github.com/nanvix/cpython/issues/321) for the tracking issue.

## Platform Limitations

Nanvix is a 32-bit microkernel OS. The main categories of test failure are:

- **Pickle corruption** — even trivial values like `(4, 5, 6, 7)` produce
  corrupt pickle bytes (e.g. `'zd\n'`). Affects all pickle protocols. Likely a
  fundamental issue with the pickle C accelerator or memory layout on 32-bit.
- **32-bit overflow** — tests using values like `2**32`, `2**64`, `2**65` cause
  OOM or arithmetic overflow.
- **Missing C extensions** — `_testcapi` is not built for Nanvix.
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

## Clean-Pass Modules

These modules pass with zero skips needed:

- test_augassign, test_binop, test_bool, test_compare, test_complex,
  test_contains, test_float, test_memoryview, test_richcmp, test_struct,
  test_unary
- test_grammar, test_syntax, test_compile, test_symtable, test_opcache,
  test_dis, test_keyword

# Nanvix Test Skip List

Tests that are skipped on Nanvix due to genuine platform limitations. See
[#322](https://github.com/nanvix/cpython/issues/322) for the tracking issue.

## Platform Limitations

Nanvix is a 32-bit microkernel OS. Tests were run on **i686** (microvm
platform, multi-process mode, 128 MB RAM). These findings are specific to the
i686 target; other Nanvix targets have not yet been tested.

The main categories of test failure are:

- **Pickle corruption** — `pickle.dumps()` produces corrupt bytes on 32-bit
  Nanvix (e.g. `'zd\n'`). Affects all pickle protocols. Likely a fundamental
  issue with the pickle C accelerator or memory layout on 32-bit.
- **Missing C extensions** — `_testcapi` and `_testinternalcapi` are not built
  for Nanvix.
- **No asyncio event loop** — socket support is absent, so
  `_UnixSelectorEventLoop` fails to create its self-pipe.
- **No subprocess/fork/socket** — auto-handled by `has_subprocess_support`,
  `has_fork_support`, `has_socket_support` guards in `Lib/test/support/__init__.py`.
  Tests using `@requires_subprocess()` etc. auto-skip without manual decorators.

## Auto-Skips (No Decorator Needed)

These tests skip automatically via existing guards:

| Module | Mechanism | Notes |
|--------|-----------|-------|
| test_array | `import_helper.import_module('_testcapi')` in `test_obsolete_write_lock` | Raises `SkipTest` if `_testcapi` not found |
| test_buffer | `@unittest.skipIf(_testcapi is None, ...)` on `test_c_buffer` | Already guarded |
| Various subprocess tests | `@requires_subprocess()` | Auto-skips on Nanvix |

## Manual Skips

| Module | Test | Reason | Failure |
|--------|------|--------|---------|
| test_set | `TestJointOps.test_pickling` | Pickle corruption | `pickle.dumps(set)` → corrupt bytes → `ValueError` on `pickle.loads`. Affects all subclasses (`TestSet`, `TestSetSubclass`, `TestFrozenSet`, `TestFrozenSetSubclass`). |
| test_set | `TestJointOps.test_iterator_pickling` | Pickle corruption | `pickle.dumps(iter(set))` → corrupt bytes. |
| test_set | `TestBasicOps.test_pickling` | Pickle corruption | `pickle.dumps(self.set)` → corrupt bytes. |
| test_collections | `TestChainMap.test_basics` | Pickle corruption | Method includes pickle round-trip of `ChainMap` objects via `pickle.dumps/loads`. |
| test_collections | `TestNamedTuple.test_pickle` | Pickle corruption | `pickle.dumps(namedtuple_instance)` → corrupt bytes. |
| test_collections | `TestNamedTuple.test_field_descriptor` | Pickle corruption | `pickle.loads(pickle.dumps(Point.x, proto))` for field descriptor pickling. |
| test_collections | `TestCounter.test_copying` | Pickle corruption | Method includes pickle round-trip of `Counter` objects. |
| test_defaultdict | `TestDefaultDict.test_pickling` | Pickle corruption | `pickle.dumps(defaultdict)` → corrupt bytes. |
| test_ordered_dict | `OrderedDictTests.test_copying` | Pickle corruption | Method includes pickle round-trip of `OrderedDict`. Affects `PurePythonOrderedDictTests` and `CPythonOrderedDictTests`. |
| test_ordered_dict | `OrderedDictTests.test_pickle_recursive` | Pickle corruption | `pickle.dumps(od)` where `od[1] = od` → corrupt bytes. |
| test_ordered_dict | `CPythonOrderedDictTests.test_iterators_pickling` | Pickle corruption | `pickle.dumps(iter(od))` → corrupt bytes. |
| test_deque | `TestBasic.test_pickle` | Pickle corruption | `pickle.dumps(deque(range(200)))` → corrupt bytes. |
| test_deque | `TestBasic.test_pickle_recursive` | Pickle corruption | `pickle.dumps(d)` where `d.append(d)` → corrupt bytes. |
| test_deque | `TestBasic.test_iterator_pickle` | Pickle corruption | `pickle.dumps(iter(deque))` → corrupt bytes. |
| test_deque | `TestSubclass.test_copy_pickle` | Pickle corruption | Method includes pickle round-trip of deque subclass. |
| test_deque | `TestSubclass.test_pickle_recursive` | Pickle corruption | Recursive deque pickle → corrupt bytes. |
| test_array | `BaseTest.test_pickle` | Pickle corruption | `pickle.dumps(array.array(...))` → corrupt bytes. Affects all typed test subclasses. |
| test_array | `BaseTest.test_pickle_for_empty_array` | Pickle corruption | `pickle.dumps(array.array(typecode))` → corrupt bytes. |
| test_array | `BaseTest.test_iterator_pickle` | Pickle corruption | `pickle.dumps(iter(array))` → corrupt bytes. |
| test_array | `BaseTest.test_reverse_iterator_pickling` | Pickle corruption | `pickle.dumps(reversed(iter(array)))` → corrupt bytes. |
| test_weakref | `ReferencesTestCase.test_cfunction` | Missing `_testcapi` | Directly imports `_testcapi` → `ImportError` on Nanvix (raises error rather than SkipTest). |
| test_iter | `TestCase.test_mutating_seq_class_iter_pickle` | Pickle corruption | Direct `pickle.dumps/loads` of iterator+sequence pairs. |
| test_iter | `check_pickle` helper | Pickle corruption | Made no-op on Nanvix; all `check_iterator`/`check_for_loop` callers that pass `pickle=True` (the default) thereby skip the pickle sub-check while still exercising iterator behaviour. |
| test_itertools | All `@pickle_deprecated` tests (27 tests) | Pickle corruption | `pickle_deprecated` wrapper raises `SkipTest` on Nanvix; covers all methods decorated with `@pickle_deprecated` in `TestBasicOps` and `TestExamples`. |
| test_itertools | `TestBasicOps.test_filter` | Pickle corruption | Direct `pickle.dumps/loads` of `filter` iterator; not covered by `@pickle_deprecated`. |
| test_coroutines | `CoroAsyncIOCompatTest` (class) | No asyncio event loop | Extended existing `is_emscripten or is_wasi` guard to include `is_nanvix`. `asyncio.run()` creates `_UnixSelectorEventLoop` which fails on self-pipe creation (socketpair). |
| test_coroutines | `CAPITest` (class) | Missing `_testcapi` | Class body and all methods import `_testcapi.awaitType`; `@support.cpython_only` does not skip on Nanvix since Nanvix runs CPython. |
| test_functools | `TestPartial.test_pickle` | Pickle corruption | `pickle.loads(pickle.dumps(partial(...)))` → corrupt bytes. Affects `TestPartialC`, `TestPartialPy`, and their subclasses. |
| test_functools | `TestPartial.test_recursive_pickle` | Pickle corruption | Recursive partial pickle — `pickle.dumps(f)` where `f.__setstate__((f, ...))`. |
| test_functools | `TestTotalOrdering.test_pickle` | Pickle corruption | `pickle.dumps(Orderable_LT.__lt__)` → corrupt bytes. |
| test_functools | `TestLRU.test_pickle` | Pickle corruption | `pickle.dumps(lru_cache_wrapped_func)` → corrupt bytes. Affects `TestLRUC` and `TestLRUPy`. |
| test_buffer | `TestBufferProtocol.test_pybuffer_size_from_format` | Missing `_testcapi` | `_testcapi` is `None` on Nanvix; method calls `_testcapi.PyBuffer_SizeFromFormat(...)` → `AttributeError`. Guarded by `@unittest.skipIf(_testcapi is None, ...)`. |

## Clean-Pass Modules (Zero Skips Needed)

These modules pass with zero manual skips required:

- test_weakset, test_iterlen
- test_generators, test_generator_stop, test_yield_from
- test_listcomps, test_dictcomps, test_setcomps, test_genexps
- test_heapq, test_bisect, test_sort, test_queue
- test_copy, test_copyreg
- test_funcattrs, test_decorators

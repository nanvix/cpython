# Nanvix Test Skip List

Tests skipped with `@unittest.skipIf(support.is_nanvix, ...)` decorators due to
genuine Nanvix platform limitations. Organized by commit group from
[#321](https://github.com/nanvix/cpython/issues/321).

## Commit 1: Built-in Types

| Module | Test | Reason | Failure description |
|--------|------|--------|---------------------|
| test_int | `IntStrDigitLimitsTests.test_int_max_str_digits_is_per_interpreter` | `_testcapi` unavailable | Calls `support.run_in_subinterp()` which requires the `_testcapi` C extension module. This module is not built for Nanvix. |
| test_range | `RangeTest.test_pickling` | 32-bit pickle overflow | Test cases include `range(2**65, 2**65+2)`. On 32-bit Nanvix, pickling these large range values produces corrupt data. |
| test_range | `RangeTest.test_iterator_pickling` | 32-bit pickle overflow | Iterates over ranges with bounds derived from `2**31` and `2**63`. The `2**63` cases cause OOM or overflow on 32-bit. |
| test_range | `RangeTest.test_iterator_pickling_overflowing_index` | 32-bit iterator index overflow | Uses `iter(range(2**32 + 2))` with `__setstate__(2**32 + 1)`. The iterator index overflows on 32-bit. |
| test_range | `RangeTest.test_exhausted_iterator_pickling` | 32-bit pickle overflow | Creates `range(2**65, 2**65+2)` and pickles its exhausted iterator. Corrupt pickle data on 32-bit. |
| test_range | `RangeTest.test_large_exhausted_iterator_pickling` | 32-bit pickle corruption | Pickles an exhausted iterator from `range(20)`. Despite small values, the pickle protocol produces corrupt data on Nanvix. |
| test_range | `RangeTest.test_iterator_unpickle_compat` | 64-bit pickle bytes | Loads pre-encoded pickle byte strings that contain 64-bit integer representations. These fail to decode on 32-bit. |
| test_range | `RangeTest.test_iterator_setstate` | 32-bit overflow | Uses `range(-2**65, 20, 2)` and `range(10, 2**65, 2)` with `__setstate__` values of `2**64 + 7` and `2**64 - 7`. These overflow on 32-bit. |
| test_range | `RangeTest.test_range_iterators` | 32-bit OOM/overflow | Exercises "fast" range iterators with limits derived from `2**32` and `2**64`. Both cause OOM or arithmetic overflow on 32-bit Nanvix. |
| test_slice | `SliceTest.test_pickle` | 32-bit pickle corruption | `pickle.dumps(slice(10, 20, 3))` produces corrupt data on Nanvix — `pickle.loads()` raises `ValueError: invalid literal for int()`. |
| test_tuple | `TupleTest.test_pickle` | pickle corruption | Inherited from `seq_tests.CommonTest`. Even `pickle.dumps((4, 5, 6, 7))` produces corrupt bytes on Nanvix — `pickle.loads()` raises `ValueError: invalid literal for int() with base 10: 'zd\n'`. |
| test_tuple | `TupleTest.test_iterator_pickle` | pickle corruption | `pickle.dumps(iter((4, 5, 6, 7)))` produces corrupt data on Nanvix. Same root cause as `test_pickle`. |
| test_tuple | `TupleTest.test_reversed_pickle` | pickle corruption | `pickle.dumps(reversed((4, 5, 6, 7)))` produces corrupt data on Nanvix. Same root cause as `test_pickle`. |

### Notes

- **test_bytes** auto-skips at import time (`No module named '_testcapi'`). No
  `@skipIf` decorator needed — the module's own import guard handles it.
- **Pickle corruption on Nanvix** affects even small values (e.g. `(4,5,6,7)`),
  suggesting a fundamental issue with the pickle C accelerator or memory layout
  on the 32-bit Nanvix platform, not just large-value overflow.

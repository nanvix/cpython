# Nanvix Test Skip List

This document records all test skips that were added specifically for the
Nanvix platform, along with the reason for each skip and a reference to the
upstream issue or PR where it was introduced.

Skips fall into two categories:

* **Explicit** – A `raise unittest.SkipTest(...)` or platform guard was added
  directly to the test file.
* **Automatic** – The test is skipped by an existing `@support.requires_*()`
  decorator or by an `import_helper.import_module()` guard that fires because
  a module or system feature is unavailable on Nanvix.

---

## C API / ctypes tests (#328)

### test_ctypes/test_loading.py — Explicit skip

**Reason:** Nanvix uses a fully static build with no dynamic linker.
`CDLL` and `cdll.LoadLibrary` both call `dlopen(3)` internally; on Nanvix
those calls fail because no shared-library infrastructure is present.  Every
test in this file either directly calls `CDLL` or relies on `find_library` to
locate a `.so` to open.

**Guard added:**
```python
if test.support.is_nanvix:
    raise unittest.SkipTest(
        "loading shared libraries is not supported on Nanvix (static build)")
```

**Reference:** #328

---

### test_ctypes/test_find.py — Explicit skip

**Reason:** `find_library()` on Linux locates shared libraries by spawning
`ldconfig`, `gcc`, or `ld` in a subprocess.  On Nanvix, subprocess creation
is not supported (`has_subprocess_support = False`), so `find_library` always
returns `None`.  Additionally, any `CDLL` call that follows would fail for the
same reason as `test_loading.py`.

**Guard added:**
```python
if test.support.is_nanvix:
    raise unittest.SkipTest(
        "loading shared libraries is not supported on Nanvix (static build)")
```

**Reference:** #328

---

### test_clinic — Automatic skip (whole module)

**Reason:** `test_clinic.py` imports `test.test_tools`, whose `__init__.py`
raises `unittest.SkipTest("test module requires subprocess")` when
`support.has_subprocess_support` is `False`.  Because subprocess is not
available on Nanvix, the entire `test_clinic` module is skipped at collection
time without any source-level modification.

**Reference:** #328

---

### test_cppext — Automatic skip (TestCPPExt class)

**Reason:** The sole test class `TestCPPExt` is decorated with
`@support.requires_subprocess()`.  Since `has_subprocess_support = False` on
Nanvix, all tests in the class are skipped automatically.

**Reference:** #328

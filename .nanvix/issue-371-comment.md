## Detailed Skip List — Filesystem/IO Modules (PR #381)

From [PR #381](https://github.com/nanvix/cpython/pull/381) — enable 35 filesystem/IO test modules on Nanvix (issue #324), bringing the total from 64 to 99 modules.

### New Root Causes

In addition to the categories from PR #341, the filesystem/IO modules expose these Nanvix platform limitations:

- **Stub `umask()`** — `os.umask()` is a no-op on Nanvix. Tests that check file creation mode after `umask()` fail. Extended existing WASI/Emscripten guards.
- **No `/dev/null`** — Nanvix has no devfs. `os.devnull` path does not exist. Extended existing WASI guards.
- **No `/dev/tty`** — Terminal device does not exist.
- **Pipe fds have no stat** — `fstat()` on pipe file descriptors is not supported (same as Emscripten).
- **No `st_blksize`** — Nanvix stat results do not expose `st_blksize` (same as WASI).
- **In-memory FS limits** — Write-bit removal and mode 000 not enforced; `fstat()` on renamed files not supported.

### Stats Update

| Metric | PR #341 | + PR #381 | Total |
|--------|---------|-----------|-------|
| Modules enabled | 64 | +35 | 99 |
| `@skipIf(is_nanvix)` decorators | 60 | +29 | 89 |
| Module-level `SkipTest` | 0 | +1 | 1 |
| `@skipIf(is_nanvix)` via extended WASI/Emscripten guards | 0 | +15 | 15 |
| Filesystem/IO auto-skips | 0 | +7 | 7 |
| Clean-pass modules (zero skips) | ~30 | +15 | ~45 |

### Manual Skip Decorators — Filesystem/IO

#### Pickle Corruption (4 skips)

| Module | Test | Reason |
|--------|------|--------|
| test_configparser | `ExceptionPicklingTestCase` (class, 11 methods) | Configparser exception pickle corrupt |
| test_os | `StatAttributeTests.test_stat_result_pickle` | `pickle.dumps(os.stat_result)` → corrupt |
| test_os | `StatAttributeTests.test_statvfs_result_pickle` | `pickle.dumps(os.statvfs_result)` → corrupt |
| test_pathlib | `_BasePurePathTest.test_pickling_common` | `pickle.dumps(PurePath)` → corrupt |
| test_pathlib | `_BasePathTest.test_pickling_common` | `pickle.dumps(Path)` → corrupt |

#### Stub `umask()` (8 skips — extended WASI/Emscripten guards)

| Module | Test | Notes |
|--------|------|-------|
| test_import | `ImportTests.test_creation_mode` | `umask(0o222)` has no effect |
| test_import | `ImportTests.test_unwritable_directory` | Same root cause |
| test_os | `MakedirTests.test_mode` | Extended `is_emscripten or is_wasi` guard |
| test_os | `MakedirTests.test_exist_ok_existing_directory` | Same |
| test_os | `MakedirTests.test_exist_ok_s_isgid_directory` | Same |
| test_pathlib | `PathTest.test_open_mode` | Extended `is_emscripten or is_wasi` guard |
| test_pathlib | `PathTest.test_touch_mode` | Same |
| test_tarfile | `GzipWriteTest.test_file_mode` | Extended `is_emscripten or is_wasi` guard |

#### No `/dev/null` (3 skips — extended WASI guards)

| Module | Test | Notes |
|--------|------|-------|
| test_os | `DevNullTests` (entire class) | Extended existing WASI guard |
| test_shutil | `TestGetTerminalSize.test_fallback` | Extended existing WASI guard |
| test_stat | `TestFilemodeCStat.test_devices` | `os.devnull` does not exist |

#### Pipe fds have no stat (5 skips — extended Emscripten guards)

| Module | Test | Notes |
|--------|------|-------|
| test_genericpath | `AllCommonTest.test_exists_fd` | `os.pipe()` fds cannot be `fstat()`'d |
| test_io | `CommonBufferedTests.test_optional_abilities` | Extended existing Emscripten guard |
| test_io | `CIOTest.test_open_pipe_with_append` | `open()` on pipe fd triggers `fstat()` |
| test_io | `CIOTest.test_nonblock_pipe_write_bigbuf` | Non-blocking pipe write triggers `fstat()` |
| test_io | `CIOTest.test_nonblock_pipe_write_smallbuf` | Same with smaller buffer |

#### In-Memory FS Limits (4 skips)

| Module | Test | Notes |
|--------|------|-------|
| test_tempfile | `TestBadTempdir.test_read_only_directory` | Cannot remove write bits; extended Emscripten guard |
| test_tempfile | `TestSpooledTemporaryFile.test_del_rolled_file` | Cannot fstat renamed files |
| test_tempfile | `TestSpooledTemporaryFile.test_truncate_with_size_parameter` | Same root cause |
| test_zipimport | `UncompressedZipImportTestCase.testFileUnreadable` | Mode 000 not enforced; extended WASI guard |

#### Missing `_testcapi` (1 skip)

| Module | Test | Notes |
|--------|------|-------|
| test_import | `ImportTests.test_from_import_missing_attr_has_name_and_so_path` | Directly imports `_testcapi` |

#### No `st_blksize` / No `/dev/tty` (2 skips)

| Module | Test | Notes |
|--------|------|-------|
| test_fileio | `OtherFileTests.testBlksize` | WASI/Nanvix does not expose `st_blksize` |
| test_fileio | `OtherFileTests.testAbles` (partial) | `/dev/tty` does not exist — guarded by `if` block |

#### Filesystem Unreliable (1 skip — from PR #341, now `@skipIf(is_nanvix)`)

| Module | Test | Notes |
|--------|------|-------|
| test_reprlib | `LongReprTest` (entire class) | `shutil.rmtree` unreliable, `os.mkdir` fails with `FileExistsError` |

#### Module-Level Skip (1 skip)

| Module | Mechanism | Reason |
|--------|-----------|--------|
| test_shelve | `raise unittest.SkipTest(...)` if `support.is_nanvix` | Shelve requires pickle which produces corrupt data |

### Auto-Skips — Filesystem/IO Modules

These modules or tests skip automatically via existing guards — no `@skipIf(is_nanvix)` required:

| Module | Mechanism | Notes |
|--------|-----------|-------|
| test_file_eintr | Module-level `SkipTest` | `has_subprocess_support` is `False` on Nanvix |
| test_largefile | `@skip_no_disk_space` / `@requires_resource('cpu')` | 128 MB VM insufficient for 2.5 GB file tests |
| test_mmap | `import_module('mmap')` | Auto-skips if `mmap` not available |
| test_source_encoding | `@requires_subprocess()` | Subprocess-based tests auto-skip |
| test_dbm_gnu | `import_module("dbm.gnu")` | `_gdbm` not available |
| test_dbm_ndbm | `import_module("dbm.ndbm")` | `_dbm` not available |
| test_shelve | Module-level `SkipTest` | Pickle produces corrupt data on Nanvix |

### Clean-Pass Modules (Zero Skips)

These 15 filesystem/IO modules pass with no skip decorators needed:

- test_bufio, test_csv, test_dbm, test_dbm_dumb, test_file, test_filecmp,
  test_fileinput, test_fnmatch, test_glob, test_linecache, test_modulefinder,
  test_pkgutil, test_posixpath, test_zipapp, test_zipfile

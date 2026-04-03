# Nanvix Test Skip List

This document tracks all tests skipped on the Nanvix platform and the reasons for each skip.

## Platform Constraints

Nanvix is an educational operating system with the following relevant constraints:

| Constraint | Impact on Tests |
|-----------|----------------|
| No subprocess/fork support | Tests using `os.fork()`, `subprocess` module |
| No socket support | Tests using BSD sockets |
| No symlinks | Tests using `os.symlink()`, `os.readlink()` |
| No special files | Tests using `os.mkfifo()`, `os.mknod()` |
| No user accounts | Tests using `expanduser()`, `os.chown()`, `pwd/grp` modules |
| No extended attributes | Tests using `os.getxattr()`, `os.setxattr()` |
| No dynamic linking | Tests using `RTLD_*` constants |
| No `/dev/null` | Tests relying on `/dev/null` |
| umask is a stub | Tests relying on `os.umask()` mode enforcement |
| In-memory FS (no write-bit enforcement) | Tests using chmod to restrict directory access |
| No tty/pipe fstat | Tests using `fstat()` on pipe/tty file descriptors |
| 32-bit architecture | Tests requiring 64-bit arithmetic |

## Automatically Handled by Support Infrastructure

The following categories are automatically handled by the test support module:

- **Subprocess/fork**: `@support.requires_subprocess()` / `@support.requires_fork()` — `has_subprocess_support` and `has_fork_support` are both `False` on Nanvix
- **Socket**: `@support.requires_working_socket()` — `has_socket_support` is `False` on Nanvix
- **Symlinks**: `@os_helper.skip_unless_symlink` — `can_symlink()` returns `False` on Nanvix
- **chown/mkfifo/mknod/xattr**: `@unittest.skipUnless(hasattr(os, '...'), ...)` guards

## Explicit Nanvix Skip Decorators

### `Lib/test/test_os.py`

| Test | Reason |
|------|--------|
| `MakedirTests.test_mode` | umask is a stub on Nanvix |
| `MakedirTests.test_exist_ok_existing_directory` | umask is a stub on Nanvix |
| `MakedirTests.test_exist_ok_s_isgid_directory` | umask is a stub on Nanvix |
| `DevNullTests` (class) | Nanvix has no `/dev/null` |

### `Lib/test/test_pathlib.py`

| Test | Reason |
|------|--------|
| `PurePosixPathTest`/`PosixPathTest` inline `if not is_nanvix` in `test_flavour_specific_operations` | Nanvix has no user accounts (expanduser) |
| `PurePosixPathTest.test_expanduser_common` | Nanvix has no user accounts |
| `PosixPathTest.test_is_socket_true` | Nanvix has no socket support |
| `PosixPathTest.test_open_mode` | umask is a stub on Nanvix |
| `PosixPathTest.test_touch_mode` | umask is a stub on Nanvix |

### `Lib/test/test_posix.py`

| Test | Reason |
|------|--------|
| `PosixTester.test_rtld_constants` | No dynamic linking on Nanvix |
| `PosixTester.test_link_dir_fd` | Symlink following on `path_link` not supported |

### `Lib/test/test_tarfile.py`

| Test | Reason |
|------|--------|
| `symlink_test`-decorated tests in `TestExtractionFilters` | Symlink behavior cannot be tested on Nanvix |

### `Lib/test/test_shutil.py`

| Test | Reason |
|------|--------|
| `TestGetTerminalSize.test_fallback` | Nanvix has no `/dev/null` |

### `Lib/test/test_fileio.py`

| Test | Reason |
|------|--------|
| `FileIOTest.testBlksize` | Nanvix does not expose `st_blksize` in `stat` results |

### `Lib/test/test_zipimport.py`

| Test | Reason |
|------|--------|
| `UncompressedZipImportTestCase.testFileUnreadable` | mode 000 not supported on Nanvix in-memory FS |

### `Lib/test/test_import/__init__.py`

| Test | Reason |
|------|--------|
| `ImportTests.test_creation_mode` | umask is a stub on Nanvix |
| `ImportTests.test_unwritable_directory` | umask is a stub on Nanvix |

### `Lib/test/test_tempfile.py`

| Test | Reason |
|------|--------|
| `TestBadTempdir.test_read_only_directory` | Nanvix in-memory FS cannot remove write bits |
| `SpooledTemporaryFileTest.test_del_rolled_file` | Nanvix cannot fstat renamed files |
| `SpooledTemporaryFileTest.test_truncate_with_size_parameter` | Nanvix cannot fstat renamed files |

### `Lib/test/test_genericpath.py`

| Test | Reason |
|------|--------|
| `GenericTest.test_exists_fd` | Nanvix pipe fds have no stat |

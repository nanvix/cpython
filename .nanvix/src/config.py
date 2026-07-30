# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Shared configuration for the Nanvix CPython build system.

Centralizes constants, defaults, and path helpers previously spread
across defaults.mk, common.mk, and the various test-*.mk files.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import cast

# ---------------------------------------------------------------------------
# Platform defaults
# ---------------------------------------------------------------------------


def _manifest_sdk_image() -> str:
    """Return the canonical immutable build image from nanvix.toml."""
    with Path(__file__).parent.with_name("nanvix.toml").open("rb") as manifest_file:
        manifest: dict[str, object] = tomllib.load(manifest_file)
    raw_toolchain = manifest.get("toolchain")
    if not isinstance(raw_toolchain, dict):
        raise RuntimeError("nanvix.toml has no canonical toolchain")
    toolchain = cast(dict[str, object], raw_toolchain)
    image = toolchain.get("build-image", toolchain.get("sdk-image"))
    digest = toolchain.get("build-digest", toolchain.get("sdk-digest"))
    if not isinstance(image, str) or not isinstance(digest, str):
        raise RuntimeError("nanvix.toml has no immutable build image")
    return f"{image}@{digest}"


DOCKER_IMAGE = _manifest_sdk_image()
DEFAULT_PLATFORM = "microvm"
DEFAULT_PROCESS_MODE = "standalone"
DEFAULT_MEMORY_SIZE = "256mb"
DEFAULT_INSTALL_PREFIX = "/"

# Python version string — centralized to avoid shotgun surgery if updated.
PYTHON_VERSION = "3.12"
PYTHON_LIB_DIR = f"python{PYTHON_VERSION}"

# ELF suffix for cross-compiled binaries
EXE = ".elf"

# The sysconfig data module name baked into the build.
# Matches _sysconfigdata_{ABIFLAGS}_{MACHDEP}_{MULTIARCH} from configure.
# Must be passed as _PYTHON_SYSCONFIGDATA_NAME inside the guest VM so that
# sysconfig can find the module regardless of how sys.platform resolves
# at runtime in the guest kernel.
SYSCONFIGDATA_NAME = "_sysconfigdata__nanvix_"

# ---------------------------------------------------------------------------
# Toolchain
# ---------------------------------------------------------------------------

TARGET_TRIPLE = "i686-unknown-nanvix"
SDK_C_ABI = "i686-nanvix-sysv-1"

# Docker-internal paths
DOCKER_SDK_PATH = "/opt/nanvix"
DOCKER_SYSROOT_PATH = "/mnt/sysroot"
DOCKER_WORKSPACE_PATH = "/mnt/workspace"
DOCKER_BUILDROOT_PATH = "/mnt/buildroot"


# ---------------------------------------------------------------------------
# Test module lists
# ---------------------------------------------------------------------------

# Canonical list of stdlib test modules known to pass on Nanvix.
NANVIX_TEST_LIST: list[str] = [
    "test_float",
    "test_complex",
    "test_bool",
    "test_struct",
    "test_int",
    "test_range",
    "test_slice",
    "test_memoryview",
    "test_bytes",
    "test_tuple",
    "test_builtin",
    "test_operator",
    "test_binop",
    "test_unary",
    "test_compare",
    "test_richcmp",
    "test_augassign",
    "test_contains",
    "test_grammar",
    "test_syntax",
    "test_compile",
    "test_compiler_assemble",
    "test_compiler_codegen",
    "test_ast",
    "test_symtable",
    "test_opcache",
    "test_peepholer",
    "test_dis",
    "test_code",
    "test_keyword",
    "test_tokenize",
    "test_perf_profiler",
    "test_call",
    "test_extcall",
    "test_positional_only_arg",
    "test_scope",
    "test_global",
    "test_dynamic",
    "test_with",
    "test_types",
    "test_typechecks",
    "test_isinstance",
    "test_hash",
    "test_index",
    "test_super",
    "test_property",
    "test_math",
    "test_cmath",
    "test_decimal",
    "test_fractions",
    "test_statistics",
    "test_random",
    "test_numeric_tower",
    "test_exception_group",
    "test_exceptions",
    "test_raise",
    "test_traceback",
    "test_frame",
    "test_contextlib",
    "test_contextlib_async",
    "test_pprint",
    "test_reprlib",
    "test_format",
    "test_print",
    "test_textwrap",
    "test_difflib",
    "test_list",
    "test_dict",
    "test_listcomps",
    "test_dictcomps",
    "test_setcomps",
    "test_genexps",
    "test_set",
    "test_heapq",
    "test_bisect",
    "test_queue",
    "test_sort",
    "test_iter",
    "test_itertools",
    "test_iterlen",
    "test_generators",
    "test_generator_stop",
    "test_yield_from",
    "test_coroutines",
    "test_functools",
    "test_funcattrs",
    "test_decorators",
    "test_copy",
    "test_copyreg",
    "test_collections",
    "test_defaultdict",
    "test_ordered_dict",
    "test_deque",
    "test_array",
    "test_weakref",
    "test_weakset",
    "test_buffer",
    "test_genericpath",
    "test_posixpath",
    "test_ntpath",
    "test_pathlib",
    "test_fnmatch",
    "test_glob",
    "test_filecmp",
    "test_linecache",
    "test_stat",
    "test_memoryio",
    "test_bufio",
    "test_fileinput",
    "test_io",
    "test_fileio",
    "test_file",
    "test_file_eintr",
    "test_source_encoding",
    "test_os",
    "test_posix",
    "test_tempfile",
    "test_shutil",
    "test_zipfile",
    "test_zipapp",
    "test_zipimport",
    "test_tarfile",
    "test_gzip",
    "test_bz2",
    "test_zlib",
    "test_dbm_dumb",
    "test_shelve",
    "test_import",
    "test_pkgutil",
    "test_modulefinder",
    "test_importlib",
    "test_base64",
    "test_binascii",
    "test_quopri",
    "test_uu",
    "test_string",
    "test_string_literals",
    "test_unicode",
    "test_unicodedata",
    "test_ucn",
    "test_utf8_mode",
    "test_utf8source",
    "test_codecs",
    "test_multibytecodec",
    "test_codecencodings_cn",
    "test_codecencodings_hk",
    "test_codecencodings_iso2022",
    "test_codecencodings_jp",
    "test_codecencodings_kr",
    "test_codecencodings_tw",
    "test_codecmaps_cn",
    "test_codecmaps_hk",
    "test_codecmaps_jp",
    "test_codecmaps_kr",
    "test_codecmaps_tw",
    # #323 wave 6 — pickle and marshal
    "test_pickle",
    "test_picklebuffer",
    "test_pickletools",
    "test_marshal",
    # #323 wave 7 — json sub-package
    "test_json",
    # #323 wave 8 — regex and plistlib
    "test_re",
    "test_plistlib",
    # #600 — lxml built-in smoke test
    "test_nanvix_lxml",
    # #526 — _lzma stdlib enablement
    "test_lzma",
    # #327 — network and protocol tests (IPv4 only; IPv6 disabled)
    # Core networking
    "test_socket",
    "test_ssl",
    "test_timeout",
    # HTTP & Web
    "test_httplib",
    "test_http_cookiejar",
    "test_http_cookies",
    # URL handling
    "test_urllib",
    "test_urllib2",
    "test_urlparse",
    "test_urllib_response",
    # Mail protocols
    "test_ftplib",
    "test_poplib",
    "test_imaplib",
    "test_nntplib",
    "test_smtplib",
    # RPC
    "test_xmlrpc",
    # I/O multiplexing
    "test_select",
    "test_selectors",
    "test_poll",
    # Server infrastructure
    "test_socketserver",
    # Network utilities
    "test_ipaddress",
]

# Default batch size for regrtest VM invocations.
DEFAULT_TEST_BATCH_SIZE = 4

# Per-mode test exclusions (passed to regrtest --ignore).
STANDALONE_EXCLUDE: list[str] = [
    "test_queue",  # NSKIP019: standalone 32 MB heap too small for module
    "test_itertools",  # NSKIP019: standalone 32 MB heap too small for module
    "test_functools",  # NSKIP019: standalone 32 MB heap too small for module
    "test_io",  # NSKIP019: standalone 32 MB heap too small for module
    "test_zipfile",  # NSKIP019: standalone too slow / heap too small for module
    "test_import",  # NSKIP019: standalone 32 MB heap too small for module
    "test_unicode",  # NSKIP019: standalone 32 MB heap too small for module
    "test_os",  # initrd mode (v0.14.3+): 1 error + 1 failure in OS subtests
    "test_socket",  # NSKIP019: standalone 32 MB heap too small for module
    "test_ssl",  # NSKIP019: standalone 32 MB heap too small for module
    # #327: standalone kernel getsockopt/setsockopt returns errno 134;
    # these tests require full socket option support, which is unavailable
    # until the standalone network stack is complete.
    "test_httplib",
    "test_urllib",
    "test_urllib2",
    "test_urllib_response",
    "test_ftplib",
    "test_poplib",
    "test_imaplib",
    "test_nntplib",
    "test_smtplib",
    "test_xmlrpc",
    "test_select",
    "test_selectors",
    "test_poll",
    "test_socketserver",
    # #327: asyncio event-loop not yet supported in standalone mode.
    "test_contextlib_async",
]

# Platform-specific nanvixd extra arguments.
PLATFORM_NANVIXD_ARGS: dict[str, list[str]] = {
    "microvm": [],
}

# ---------------------------------------------------------------------------
# Sysroot trimming
# ---------------------------------------------------------------------------

# Directories removed from sysroot during ramfs trimming.
SYSROOT_TRIM_DIRS: list[str] = [
    f"lib/{PYTHON_LIB_DIR}/config-{PYTHON_VERSION}",
    f"lib/{PYTHON_LIB_DIR}/idlelib",
    f"lib/{PYTHON_LIB_DIR}/tkinter",
    f"lib/{PYTHON_LIB_DIR}/turtledemo",
    f"lib/{PYTHON_LIB_DIR}/lib2to3",
    f"lib/{PYTHON_LIB_DIR}/ensurepip",
    f"lib/{PYTHON_LIB_DIR}/pydoc_data",
    f"lib/{PYTHON_LIB_DIR}/venv",
    f"lib/{PYTHON_LIB_DIR}/__phello__",
    "include",
    "share",
    "lib/pkgconfig",
]

# site-packages is no longer trimmed because lxml runtime files may be
# installed there by downstream packaging.  When the directory is empty
# it remains harmlessly on disk (ramfs.trim_sysroot only removes empty
# bin/).  To force-trim site-packages for minimal images, add the path
# back into SYSROOT_TRIM_DIRS above.

# Files removed from sysroot bin/ during ramfs trimming.
SYSROOT_TRIM_BIN_PATTERNS: list[str] = [
    "2to3*",
    "idle3*",
    "pydoc3*",
    "python3-config",
    f"python{PYTHON_VERSION}-config",
    "python3",
    f"python{PYTHON_VERSION}",
]

# ---------------------------------------------------------------------------
# Docker tar excludes (for Windows host-side source sync)
# ---------------------------------------------------------------------------

DOCKER_TAR_EXCLUDES: list[str] = [
    ".git",
    ".nanvix/venv",
    ".nanvix/cache",
    ".nanvix/sysroot",
    ".nanvix/buildroot",
    ".nanvix/out",
    "Doc",
    "Lib/idlelib",
    "Lib/tkinter",
    "Lib/turtledemo",
    "Lib/ensurepip",
    "PC",
    "PCbuild",
]

# Files needing CRLF → LF normalization for autotools.
DOCKER_CRLF_FILES: list[str] = [
    "configure",
    "config.guess",
    "config.sub",
    "install-sh",
    "Modules/makesetup",
    "Modules/Setup",
    "Modules/Setup.local",
    "Modules/Setup.bootstrap.in",
    "Modules/Setup.stdlib.in",
    "Modules/config.c.in",
    "Modules/ld_so_aix.in",
    "Makefile.pre.in",
    "pyconfig.h.in",
    "aclocal.m4",
    "configure.ac",
    "Misc/python.pc.in",
    "Misc/python-embed.pc.in",
    "Misc/python-config.sh.in",
    "Misc/python-config.in",
]

# Docker output files to copy back to host workspace.
DOCKER_OUTPUT_FILES: list[str] = [
    "python",
    "python.exe",
    "python.elf",
    "python.wasm",
    f"libpython{PYTHON_VERSION}.a",
    "pybuilddir.txt",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

IS_WINDOWS = sys.platform == "win32"


def requires_isolated_workspace(workspace: Path) -> bool:
    """Return whether build outputs would collide with case-folded source paths."""
    if IS_WINDOWS:
        return True
    try:
        return (workspace / "Python").samefile(workspace / "python")
    except OSError:
        return False


def nanvixd_binary() -> str:
    """Return the nanvixd binary name for the current platform."""
    if IS_WINDOWS:
        return "nanvixd.exe"
    return "nanvixd.elf"


def mkramfs_binary() -> str:
    """Return the mkramfs binary name for the current platform."""
    if IS_WINDOWS:
        return "mkramfs.exe"
    return "mkramfs.elf"


def mkimage_binary() -> str:
    """Return the mkimage binary name for the current platform."""
    if IS_WINDOWS:
        return "mkimage.exe"
    return "mkimage.elf"


# Windows host-native binaries needed for local test execution.
# These are downloaded from the Nanvix release page during setup.
# kernel.elf is a *guest* binary (not .exe) — nanvixd loads it directly.
# Daemons (procd, memd, vfsd) are also guest binaries (.elf).
WINDOWS_HOST_BINARIES: list[str] = [
    "nanvixd.exe",
    "mkramfs.exe",
    "mkimage.exe",
    "kernel.elf",
    "procd.elf",
    "memd.elf",
    "vfsd.elf",
]


def python_binary() -> str:
    """Return the cross-compiled Python binary name."""
    return f"python{PYTHON_VERSION}"

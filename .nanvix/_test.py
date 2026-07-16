# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Test orchestration for Nanvix CPython.

Replaces test-common.mk, test-standalone.mk, test-microvm.mk, and
test-run-host.py.

Provides staging, hello-world validation, and regrtest dispatch for
the standalone deployment mode.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
import urllib.request

from nanvix_zutil import paths

import build as build_mod
import config
import ramfs as ramfs_mod

# ---------------------------------------------------------------------------
# Shared-extension smoke checks
# ---------------------------------------------------------------------------

_SO_MODULE_SANITY_CHECKS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "CPYTHON_TEST_DATA_PRIMITIVES",
        (
            ("_bisect", "m.bisect_left([1, 3, 5], 4) == 2"),
            ("_heapq", "m.heappush([], 1) is None"),
            ("_struct", "m.pack('i', 42) == b'\\x2a\\x00\\x00\\x00'"),
            ("_random", "hasattr(m, 'Random')"),
            ("_opcode", "hasattr(m, 'stack_effect')"),
            ("_queue", "hasattr(m, 'SimpleQueue')"),
            ("_csv", "hasattr(m, 'reader')"),
            ("binascii", "m.hexlify(b'\\xab') == b'ab'"),
            ("_json", "hasattr(m, 'encode_basestring_ascii')"),
            ("_pickle", "hasattr(m, 'Pickler')"),
            ("_zoneinfo", "hasattr(m, 'ZoneInfo')"),
        ),
    ),
    (
        "CPYTHON_TEST_MATH",
        (
            ("math", "abs(m.sqrt(4.0) - 2.0) < 1e-9"),
            ("cmath", "abs(m.sqrt(complex(-1)) - complex(0, 1)) < 1e-9"),
            ("_statistics", "hasattr(m, '_normal_dist_inv_cdf')"),
            ("mmap", "hasattr(m, 'mmap')"),
            ("_contextvars", "hasattr(m, 'ContextVar')"),
        ),
    ),
    (
        "CPYTHON_TEST_CODECS",
        (
            ("unicodedata", "m.lookup('LATIN SMALL LETTER A') == 'a'"),
            ("_codecs_cn", "hasattr(m, 'getcodec')"),
            ("_codecs_hk", "hasattr(m, 'getcodec')"),
            ("_codecs_iso2022", "hasattr(m, 'getcodec')"),
            ("_codecs_jp", "hasattr(m, 'getcodec')"),
            ("_codecs_kr", "hasattr(m, 'getcodec')"),
            ("_codecs_tw", "hasattr(m, 'getcodec')"),
        ),
    ),
    (
        "CPYTHON_TEST_BUNDLED_DEPS",
        (
            ("_asyncio", "hasattr(m, 'Future')"),
            ("_decimal", "m.Decimal('1.1') + m.Decimal('2.2') == m.Decimal('3.3')"),
            ("_elementtree", "hasattr(m, 'XMLParser')"),
            ("_md5", "hasattr(m, 'md5')"),
            ("_sha1", "hasattr(m, 'sha1')"),
            ("_sha2", "hasattr(m, 'sha256')"),
            ("_sha3", "hasattr(m, 'sha3_256')"),
            ("_blake2", "hasattr(m, 'blake2b')"),
            ("select", "hasattr(m, 'select')"),
            ("_socket", "hasattr(m, 'socket')"),
            ("_posixsubprocess", "hasattr(m, 'fork_exec')"),
            ("fcntl", "hasattr(m, 'fcntl')"),
            ("termios", "hasattr(m, 'tcgetattr')"),
        ),
    ),
)


def _render_so_sanity_snippets(
    checks: tuple[
        tuple[str, tuple[tuple[str, str], ...]], ...
    ] = _SO_MODULE_SANITY_CHECKS,
) -> str:
    """Render imports that prove each migrated module loads through dlopen."""
    snippets: list[str] = []
    for log_tag, modules in checks:
        items = ",\n".join(
            f"    ({name!r}, lambda m: {check})" for name, check in modules
        )
        snippets.append(
            f"_so_checks = [\n{items},\n]\n"
            "for _name, _check in _so_checks:\n"
            "    _mod = __import__(_name)\n"
            "    assert _name not in sys.builtin_module_names, "
            "f'{_name} still built-in!'\n"
            "    assert _check(_mod), f'{_name} sanity check failed'\n"
            f"    print(f'{log_tag}: "
            "{_name} loaded via dlopen from {_mod.__file__}')\n"
        )
    return "".join(snippets)


# ---------------------------------------------------------------------------
# Initrd creation helper (standalone mode)
# ---------------------------------------------------------------------------


def _create_initrd(
    bin_dir: Path,
    app_path: Path,
    app_args: list[str] | None = None,
    app_env: str | None = None,
    output: Path | None = None,
) -> Path:
    """Create an initrd image bundling *app_path* with system daemons.

    Mirrors :meth:`~nanvix_zutil.ZScript.make_initrd` for use in
    standalone module-level functions that lack a ZScript instance.

    Args:
        bin_dir: Directory containing the system daemon ELFs and mkimage.
        app_path: Absolute path to the application ELF binary.
        app_args: Optional CLI arguments for the app entry.
        app_env: Optional space-separated env vars (e.g.
            ``"PYTHONHOME=/ TMPDIR=/tmp"``).  Appended after a bare
            semicolon in the cmdline so the kernel's ``split_cmdline``
            can separate args from env.
        output: Destination path for the image.  Defaults to
            ``app_path.parent / "<stem>.img"``.

    Returns:
        Path to the generated image file.
    """
    app_stem = app_path.stem
    if output is None:
        output = app_path.parent / f"{app_stem}.img"

    mkimage = bin_dir / config.mkimage_binary()

    def _escape(arg: str) -> str:
        return arg.replace(";", "\\;")

    def _entry(elf: Path, argv0: str, extra: list[str] | None, env: str | None) -> str:
        parts = [_escape(argv0)] + [_escape(a) for a in (extra or [])]
        argv = " ".join(parts)
        # The entry format for mkimage is:
        #   <escaped_elf_path>;<cmdline>
        # Within cmdline, the kernel splits on the first unescaped ';':
        #   <escaped_args>;<env_vars>
        cmdline = argv
        if env:
            cmdline += f";{env}"
        return f"{_escape(str(elf))};{cmdline}"

    # Daemons are *guest* binaries — always .elf, even on Windows.
    cmd: list[str] = [
        str(mkimage),
        "-o",
        str(output),
        _entry(bin_dir / "procd.elf", "procd", None, None),
        _entry(bin_dir / "memd.elf", "memd", None, None),
        _entry(bin_dir / "vfsd.elf", "vfsd", None, None),
        _entry(app_path, app_stem, app_args, app_env),
    ]

    subprocess.run(cmd, check=True, timeout=60)
    return output


# ---------------------------------------------------------------------------
# Windows: download release artifacts as install cache
# ---------------------------------------------------------------------------


def _download_release_as_cache(args: build_mod.MakeArgs) -> Path:
    """Download the latest cpython release tarball and extract it into ``paths.test_out()``.

    This lets ``./z test`` work on Windows without a prior ``./z build``
    (which requires Docker). The release tarball contains the same
    sysroot tree that ``./z build`` would produce.
    """
    cache_dir = paths.test_out()
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Resolve the latest release from nanvix/cpython.
    gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    api_url = "https://api.github.com/repos/nanvix/cpython/releases/latest"
    req = urllib.request.Request(api_url)
    req.add_header("Accept", "application/vnd.github+json")
    if gh_token:
        req.add_header("Authorization", f"Bearer {gh_token}")

    with urllib.request.urlopen(req, timeout=30) as resp:
        release = json.loads(resp.read())

    tag = release["tag_name"]
    print(f"  Resolved cpython release: {tag}")

    # Find a standalone tarball asset (.tar.gz preferred, .tar.bz2 fallback).
    asset_url = None
    asset_name = None
    for ext in (".tar.gz", ".tar.bz2"):
        for a in release.get("assets", []):
            name = a.get("name", "")
            if (
                name.startswith(args.asset_prefix())
                and name.endswith(ext)
                and "buildroot" not in name
            ):
                asset_url = a["browser_download_url"]
                asset_name = name
                break
        if asset_url:
            break

    if not asset_url:
        raise FileNotFoundError(
            f"No cpython release asset matching '{args.asset_prefix()}*.tar.gz' or '*.tar.bz2' "
            f"in release {tag}. Available assets: "
            + ", ".join(a["name"] for a in release.get("assets", []))
        )

    # Download.
    dl_dir = paths.nanvix_root() / "cache"
    dl_dir.mkdir(parents=True, exist_ok=True)
    assert asset_name is not None
    tarball = dl_dir / asset_name
    if not tarball.is_file():
        print(f"  Downloading {asset_name}...")
        urllib.request.urlretrieve(asset_url, str(tarball))

    # Extract into cache_dir with path-traversal protection.
    print(f"  Extracting to {cache_dir}...")
    with tarfile.open(tarball, "r:*") as tf:
        base = cache_dir.resolve()
        for member in tf.getmembers():
            if member.issym() or member.islnk():
                raise tarfile.TarError(f"refusing to extract link entry: {member.name}")
            resolved = (base / member.name).resolve()
            if os.path.commonpath([str(base), str(resolved)]) != str(base):
                raise tarfile.TarError(
                    f"refusing to extract path outside destination: {member.name}"
                )
        tf.extractall(cache_dir)

    # Flatten legacy tarballs that still wrap everything in a top-level
    # ``sysroot/`` directory (releases predating the strip-sysroot change).
    # Newer tarballs extract directly into ``cache_dir`` and this is a no-op.
    extracted_wrapper = cache_dir / "sysroot"
    if extracted_wrapper.is_dir():
        for item in extracted_wrapper.iterdir():
            shutil.move(str(item), str(cache_dir / item.name))
        extracted_wrapper.rmdir()
    sysroot = cache_dir

    # Copy the stripped python binary into sysroot/bin/ if present.
    bin_dir = sysroot / "bin"
    bin_dir.mkdir(exist_ok=True)
    python_elf = cache_dir / "bin" / "python.elf"
    if python_elf.is_file():
        shutil.copy2(python_elf, bin_dir / config.python_binary())
        print(f"  Installed python binary ({python_elf.stat().st_size // 1024}K)")

    # Copy the test suite from the source tree into the sysroot.
    # The release tarball is trimmed (no Lib/test/), but regrtest
    # needs it. The source checkout has the full Lib/test/.
    pylib_dir = sysroot / "lib" / config.PYTHON_LIB_DIR
    test_dst = pylib_dir / "test"
    test_src = paths.repo_root() / "Lib" / "test"
    if test_src.is_dir() and not test_dst.is_dir():
        shutil.copytree(test_src, test_dst)
        test_count = sum(1 for _ in test_dst.rglob("*.py"))
        print(f"  Copied test suite from source tree ({test_count} files)")

    print(f"  Install cache ready at {cache_dir}")
    return cache_dir


# ---------------------------------------------------------------------------
# Staging
# ---------------------------------------------------------------------------


def stage(args: build_mod.MakeArgs) -> None:
    """Populate the test install tree with fixtures, runtime binaries, and helpers.

    Invoked by ``build_mod.build`` after ``install()`` for non-release
    builds so that ``./z test`` can consume ``paths.test_out()`` directly
    with no further staging.

    The complete tree is uploaded for Windows CI after the Linux build.
    """
    staging = paths.test_out()

    # Sysconfigdata fallback: ``make install`` should copy it from
    # build/<pybuilddir>/, but can silently fail when PYTHON_FOR_BUILD
    # is unavailable or the install recipe is interrupted.
    scdata_name = f"{config.SYSCONFIGDATA_NAME}.py"
    scdata_dst = staging / "lib" / config.PYTHON_LIB_DIR / scdata_name
    if not scdata_dst.is_file():
        pybuilddir = paths.repo_root() / "pybuilddir.txt"
        if pybuilddir.is_file():
            bdir = paths.repo_root() / pybuilddir.read_text().strip()
            scdata_src = bdir / scdata_name
            if scdata_src.is_file():
                shutil.copy2(scdata_src, scdata_dst)
                print(f"  Copied {scdata_name} from build dir (make install missed it)")

    # Hello-world test script.  The array check proves that the first
    # stdlib module migrated to a shared extension is loaded through dlopen.
    array_snippet = (
        "import array\n"
        "assert 'array' not in sys.builtin_module_names, 'array still built-in!'\n"
        "_array = array.array('i', [1, 2, 3])\n"
        "assert _array.tolist() == [1, 2, 3]\n"
        "print(f'CPYTHON_TEST_ARRAY_SO: array loaded via dlopen from {array.__file__}')\n"
    )
    nested_import_snippet = (
        "import xml.etree.ElementTree as _elementtree_api\n"
        "assert _elementtree_api.fromstring('<root/>').tag == 'root'\n"
        "assert '_elementtree' not in sys.builtin_module_names\n"
        "assert 'pyexpat' in sys.builtin_module_names\n"
        "import encodings.gb2312\n"
        "assert '\\u4e2d\\u6587'.encode('gb2312') == b'\\xd6\\xd0\\xce\\xc4'\n"
        "assert '_codecs_cn' not in sys.builtin_module_names\n"
        "assert '_multibytecodec' in sys.builtin_module_names\n"
        "print('CPYTHON_TEST_NESTED_IMPORTS: static C API anchors OK')\n"
    )

    (staging / "test_hello.py").write_text(
        "import sys\n"
        "print('CPYTHON_TEST_HELLO: Hello from Python', sys.version_info[:2])\n"
        "print('CPYTHON_TEST_PLATFORM:', sys.platform)\n"
        + array_snippet
        + nested_import_snippet
        + _render_so_sanity_snippets()
    )

    # HTTP server smoke-test script must be present in the sysroot before
    # ramfs build (standalone mode mounts ramfs as /).
    httpserver_src = paths.repo_root() / "httpserver.py"
    if httpserver_src.is_file():
        shutil.copy2(httpserver_src, staging / "httpserver.py")

    # Nanvix runtime binaries (host tools + guest daemons).
    bin_dir = staging / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for binary in [
        "nanvixd.elf",
        "kernel.elf",
        "linuxd.elf",
        "uservm.elf",
        "nanvixd.exe",
        "kernel.exe",
        config.mkramfs_binary(),
        config.mkimage_binary(),
        "procd.elf",
        "memd.elf",
        "vfsd.elf",
    ]:
        src = args.sysroot / "bin" / binary
        if src.is_file():
            shutil.copy2(src, bin_dir / binary)

    # Replace unstripped python with the stripped python.elf from the build dir.
    stripped = paths.repo_root() / f"python{config.EXE}"
    if stripped.is_file():
        target = bin_dir / config.python_binary()
        shutil.copy2(stripped, target)
        print(
            f"  Installed stripped python.elf into test_out ({target.stat().st_size // 1024}K)"
        )

    # ``make install`` omits Lib/test/ from the install tree; regrtest needs it.
    pylib_dir = staging / "lib" / config.PYTHON_LIB_DIR

    # Seed from the source tree only when an install did not populate the
    # standard library. Linux CI uploads the complete install tree to Windows.
    lib_src = paths.repo_root() / "Lib"
    if lib_src.is_dir() and not pylib_dir.is_dir():
        shutil.copytree(lib_src, pylib_dir)
        print(f"  Seeded {pylib_dir} from source Lib/ (no make install on this host)")

    test_dst = pylib_dir / "test"
    test_src = lib_src / "test"
    if test_src.is_dir() and not test_dst.is_dir():
        shutil.copytree(test_src, test_dst)
        test_count = sum(1 for _ in test_dst.rglob("*.py"))
        print(f"  Copied test suite from source tree ({test_count} files)")


# ---------------------------------------------------------------------------
# Ramfs staging (standalone mode)
# ---------------------------------------------------------------------------


def stage_ramfs(
    args: build_mod.MakeArgs,
) -> Path:
    """Build a ramfs image for standalone mode testing.
    Returns the path to the ramfs image.
    """
    ramfs_img = paths.test_out() / "cpython-rootfs.img"
    ramfs_cache = paths.out_dir() / "_ramfs_cache"

    # Build fresh ramfs.
    paths.out_dir().mkdir(parents=True, exist_ok=True)
    if ramfs_cache.exists():
        shutil.rmtree(ramfs_cache)

    # Copy sysroot from test staging.
    sysroot_src = paths.test_out()
    sysroot_dst = ramfs_cache
    shutil.copytree(sysroot_src, sysroot_dst)

    # Create /tmp for tempfile.gettempdir().
    (sysroot_dst / "tmp").mkdir(exist_ok=True)

    # Trim and build ramfs image (keep tests for test pipeline).
    ramfs_mod.trim_and_build(
        ramfs_cache,
        args.sysroot,
        ramfs_img,
        keep_tests=True,
    )

    return ramfs_img


# ---------------------------------------------------------------------------
# Hello-world test
# ---------------------------------------------------------------------------


def _run_nanvixd_script(
    staging: Path,
    script_name: str,
    args: build_mod.MakeArgs,
    *,
    nanvixd_extra: list[str] | None = None,
    ramfs_img: Path | None = None,
    timeout: int = 120,
    label: str = "script",
) -> tuple[int, str, int]:
    """Run a Python script on nanvixd and return (returncode, output, elapsed_ms).

    This is the low-level execution primitive shared by the hello-world
    test and the benchmark.
    """
    resolved_extra: list[str] = (
        nanvixd_extra
        if nanvixd_extra is not None
        else config.PLATFORM_NANVIXD_ARGS.get(args.platform, [])
    )
    # On Windows, CreateProcess searches for the executable relative to the
    # *parent's* CWD, not the child's cwd. Use an absolute path to avoid this.
    nanvixd = str((args.sysroot / "bin" / config.nanvixd_binary()).resolve())

    if ramfs_img is None:
        raise ValueError("ramfs_img is required")

    # Copy host tools and daemon ELFs into the staging sysroot.
    # mkramfs is needed for ramfs generation; mkimage and the daemons
    # (procd, memd, vfsd) are needed for initrd creation.
    # Daemons are *guest* binaries — always .elf, even on
    # Windows.  Only host tools use the platform extension.
    _staging_bins = [
        config.mkramfs_binary(),
        config.mkimage_binary(),
        "procd.elf",
        "memd.elf",
        "vfsd.elf",
    ]
    for name in _staging_bins:
        src = args.sysroot / "bin" / name
        if src.is_file():
            shutil.copy2(src, staging / "bin" / name)

    # Standalone: bundle python binary with system daemons into an
    # initrd image.  Env vars are passed via app_env so the kernel's
    # split_cmdline sees them after the bare ';' separator.
    bin_dir = staging / "bin"
    app_path = staging / "bin" / config.python_binary()
    app_args = ["-B", f"./{script_name}"]
    app_env = (
        f"PYTHONHOME=/ PYTHONDONTWRITEBYTECODE=1"
        f" _PYTHON_SYSCONFIGDATA_NAME={config.SYSCONFIGDATA_NAME}"
    )
    initrd_img = _create_initrd(bin_dir, app_path, app_args=app_args, app_env=app_env)

    cmd = [
        nanvixd,
        "-bin-dir",
        str(bin_dir),
        "-ramfs",
        str(ramfs_img),
        *resolved_extra,
        "--",
        str(initrd_img),
    ]

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=staging,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{label} timed out after {timeout}s")
    finally:
        if initrd_img.exists():
            initrd_img.unlink()

    elapsed_ms = int((time.monotonic() - start) * 1000)
    output = (result.stdout + "\n" + result.stderr).strip()
    return result.returncode, output, elapsed_ms


def run_hello(
    staging: Path,
    args: build_mod.MakeArgs,
    nanvixd_extra: list[str] | None = None,
    ramfs_img: Path | None = None,
) -> None:
    """Run the hello-world test via nanvixd.

    Standalone mode uses ramfs + ``-bin-dir`` + the semicolon-delimited
    environment variable syntax.
    """
    print(f"Test: Hello world ({args.process_mode})...")

    returncode, output, elapsed_ms = _run_nanvixd_script(
        staging,
        "test_hello.py",
        args,
        nanvixd_extra=nanvixd_extra,
        ramfs_img=ramfs_img,
        label="Hello test",
    )
    print(f"  Execution time: {elapsed_ms} ms")

    if returncode != 0:
        print(f"  FAIL: Hello test exited with status {returncode}")
        print(output)
        raise RuntimeError(f"Hello test exited with status {returncode}")

    # Validate output.
    found_hello = False
    for line in output.splitlines():
        if line.startswith("CPYTHON_TEST_"):
            tag = line.split(":")[0].replace("CPYTHON_TEST_", "")
            print(f"  {tag}: {line.strip()}")
            if tag == "HELLO":
                found_hello = True

    if not found_hello:
        print("  FAIL: Hello test did not produce expected output")
        print(output)
        raise RuntimeError("Hello test did not produce expected output")

    print("  PASS")


# ---------------------------------------------------------------------------
# HTTP server smoke test
# ---------------------------------------------------------------------------


def run_smoke_httpserver(
    staging: Path,
    args: build_mod.MakeArgs,
    *,
    nanvixd_extra: list[str] | None = None,
    ramfs_img: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 9999,
    boot_timeout: float = 60.0,
    request_timeout: float = 10.0,
    listening_marker: str = "HTTP server listening",
) -> None:
    """Launch ``httpserver.py`` on nanvixd and probe it from the host.

    Assumes ``httpserver.py`` has already been staged into the sysroot
    by :func:`stage` (and therefore into the ramfs image for standalone
    mode).  Starts nanvixd as a background process, waits for the
    server's "listening" log line on stdout, issues a single HTTP/1.0
    GET, and validates the response body.  The nanvixd process is
    always terminated before this function returns.
    """
    import socket as _socket
    import tempfile

    script_name = "httpserver.py"
    if not (staging / script_name).is_file():
        raise RuntimeError(
            f"{script_name} not found in staging ({staging}); "
            "stage() did not copy it"
        )

    resolved_extra: list[str] = (
        nanvixd_extra
        if nanvixd_extra is not None
        else config.PLATFORM_NANVIXD_ARGS.get(args.platform, [])
    )
    nanvixd = str((staging / "bin" / config.nanvixd_binary()).resolve())

    if ramfs_img is None:
        raise ValueError("ramfs_img is required for standalone mode")

    for name in (
        config.mkramfs_binary(),
        config.mkimage_binary(),
        "procd.elf",
        "memd.elf",
        "vfsd.elf",
    ):
        hp = args.sysroot / "bin" / name
        if hp.is_file():
            shutil.copy2(hp, staging / "bin" / name)

    bin_dir = staging / "bin"
    app_path = staging / "bin" / config.python_binary()
    app_args = ["-B", f"./{script_name}"]
    app_env = (
        f"PYTHONHOME=/ PYTHONDONTWRITEBYTECODE=1"
        f" _PYTHON_SYSCONFIGDATA_NAME={config.SYSCONFIGDATA_NAME}"
    )
    initrd_img = _create_initrd(bin_dir, app_path, app_args=app_args, app_env=app_env)
    cmd = [
        nanvixd,
        "-bin-dir",
        str(bin_dir),
        "-ramfs",
        str(ramfs_img),
        *resolved_extra,
        "--",
        str(initrd_img),
    ]

    print(f"Test: HTTP server smoke ({args.process_mode}) on {host}:{port}...")

    # Capture stdout/stderr to a file so we can both poll for the
    # "listening" marker without risking PIPE deadlock and include the
    # output in error messages.
    log_fd, log_path_str = tempfile.mkstemp(prefix="nanvixd-smoke-", suffix=".log")
    os.close(log_fd)
    log_path = Path(log_path_str)
    log_fh = open(log_path, "wb")
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        cwd=staging,
    )

    def _read_log() -> str:
        try:
            return log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    try:
        # Wait for the server to log that it is listening.  Only then
        # is it safe to attempt a TCP connection (otherwise we might
        # race with the kernel's own host stack or unrelated services
        # on the same port).
        deadline = time.monotonic() + boot_timeout
        ready = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"nanvixd exited prematurely (rc={proc.returncode}) "
                    f"before server became ready:\n{_read_log()}"
                )
            if listening_marker in _read_log():
                ready = True
                break
            time.sleep(0.5)
        if not ready:
            raise RuntimeError(
                f"HTTP server did not log '{listening_marker}' "
                f"within {boot_timeout:.0f}s:\n{_read_log()}"
            )

        # Issue a minimal HTTP/1.0 request.
        try:
            with _socket.create_connection((host, port), timeout=request_timeout) as s:
                s.sendall(b"GET / HTTP/1.0\r\nHost: nanvix\r\n\r\n")
                s.settimeout(request_timeout)
                chunks: list[bytes] = []
                while True:
                    try:
                        data = s.recv(4096)
                    except OSError:
                        break
                    if not data:
                        break
                    chunks.append(data)
        except OSError as e:
            raise RuntimeError(
                f"HTTP smoke test failed to connect to {host}:{port}: {e}\n"
                f"nanvixd output:\n{_read_log()}"
            )
        response = b"".join(chunks)

        if b"200 OK" not in response or b"Hello from Nanvix!" not in response:
            raise RuntimeError(
                "HTTP smoke test received unexpected response:\n"
                + response.decode("utf-8", errors="replace")
                + "\nnanvixd output:\n"
                + _read_log()
            )

        print("  PASS")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        log_fh.close()
        try:
            log_path.unlink()
        except OSError:
            pass
        if initrd_img.exists():
            initrd_img.unlink()


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def run_regrtest(
    staging: Path,
    args: build_mod.MakeArgs,
    *,
    test_list: list[str] | None = None,
    batch_size: int = config.DEFAULT_TEST_BATCH_SIZE,
    nanvixd_extra: list[str] | None = None,
    ramfs_img: Path | None = None,
) -> None:
    """Run stdlib regression tests via run-tests.py."""
    if args.release:
        print("Test: regrtest skipped (NANVIX_RELEASE=yes)")
        return

    if test_list is None:
        test_list = list(config.NANVIX_TEST_LIST)

    resolved_nanvixd_extra: list[str] = (
        nanvixd_extra
        if nanvixd_extra is not None
        else config.PLATFORM_NANVIXD_ARGS.get(args.platform, [])
    )

    run_tests_script = paths.nanvix_root() / "run-tests.py"

    env = os.environ.copy()
    env["NANVIX_TEST_BATCH_SIZE"] = str(batch_size)
    env["NANVIX_PYTHON_BIN"] = f"./bin/{config.python_binary()}"

    # Standalone: ramfs + initrd-based invocation.
    if ramfs_img is None:
        ramfs_img = paths.nanvix_root() / "cpython-rootfs.img"
    bin_dir = staging / "bin"
    extra_str = f"-bin-dir {bin_dir} -ramfs {ramfs_img}"
    if resolved_nanvixd_extra:
        extra_str += " " + " ".join(resolved_nanvixd_extra)
    env["NANVIXD_EXTRA_ARGS"] = extra_str
    env["NANVIX_BIN_DIR"] = str(bin_dir)
    exclude_set = set(config.STANDALONE_EXCLUDE)
    test_list = [m for m in test_list if m not in exclude_set]

    cmd = [sys.executable, str(run_tests_script)] + test_list

    print(f"Test: regrtest ({len(test_list)} modules, {args.process_mode})...")
    result = subprocess.run(cmd, cwd=staging, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"regrtest failed with exit code {result.returncode}")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def cleanup() -> None:
    """Clean up transient test artifacts (log files).

    The build output at ``paths.test_out()`` is *not* removed — that is
    a build artifact owned by ``./z build`` / ``./z clean``.
    """
    for name in [
        "cpython_test.log",
        "cpython_regrtest.log",
        "cpython_regrtest_batch.log",
    ]:
        p = paths.nanvix_root() / name
        if p.is_file():
            p.unlink()


# ---------------------------------------------------------------------------
# Aggregate test runner
# ---------------------------------------------------------------------------


def run_all(
    args: build_mod.MakeArgs,
    *,
    test_list: list[str] | None = None,
    batch_size: int = config.DEFAULT_TEST_BATCH_SIZE,
    nanvixd_extra: list[str] | None = None,
    ramfs_img: Path | None = None,
) -> None:
    """Run the complete test pipeline: hello → regrtest → cleanup.

    Consumes the test install tree produced by ``./z build`` at
    ``paths.test_out()``; see :func:`stage`.
    """
    staging = paths.test_out()
    print("Running CPython tests on Nanvix...")

    if config.IS_WINDOWS:
        python = staging / "bin" / config.python_binary()
        if os.environ.get("CI") is not None and not python.is_file():
            raise FileNotFoundError(
                f"Windows test artifact is missing the SDK-built interpreter: {python}"
            )
        if os.environ.get("CI") is not None:
            stage(args)
        if os.environ.get("CI") is None and not python.is_file():
            print("Downloading release artifacts for local Windows testing...")
            _download_release_as_cache(args)
            stage(args)
            stage_ramfs(args)

    # Hello test.
    run_hello(
        staging,
        args,
        nanvixd_extra=nanvixd_extra,
        ramfs_img=ramfs_img,
    )

    # HTTP server smoke test.
    run_smoke_httpserver(
        staging,
        args,
        nanvixd_extra=nanvixd_extra,
        ramfs_img=ramfs_img,
    )

    # Regression tests.
    run_regrtest(
        staging,
        args,
        test_list=test_list,
        batch_size=batch_size,
        nanvixd_extra=nanvixd_extra,
        ramfs_img=ramfs_img,
    )

    # Cleanup.
    cleanup()

    print("\t\t*** CPython tests PASSED ***")


# ---------------------------------------------------------------------------
# Benchmark (hello-world only, release ramfs)
# ---------------------------------------------------------------------------


def run_benchmark(
    args: build_mod.MakeArgs,
    *,
    nanvixd_extra: list[str] | None = None,
) -> None:
    """Run a hello-world benchmark.

    The benchmark builds a ramfs with the same trimming applied during
    ``./z release`` (no test/ directory, no dev artifacts) so that the
    image size and boot time reflect a production deployment.

    No regression tests are executed.
    """
    try:
        _run_benchmark_impl(
            args,
            nanvixd_extra=nanvixd_extra,
        )
    finally:
        cleanup()


def _run_benchmark_impl(
    args: build_mod.MakeArgs,
    *,
    nanvixd_extra: list[str] | None = None,
) -> None:
    """Inner implementation of :func:`run_benchmark`."""
    # Consume the test install tree produced by ``./z build``.
    staging = paths.test_out()
    if not staging.is_dir():
        raise RuntimeError(
            f"{staging} not found; run `./z build` before `./z benchmark`"
        )

    # Write a minimal benchmark script.
    bench_script = "bench_hello.py"
    (staging / bench_script).write_text("print('hello world')\n")

    # Build ramfs with release trimming (keep_tests=False).
    ramfs_img = paths.nanvix_root() / "cpython-benchmark.img"
    bench_cache = paths.nanvix_root() / "_benchmark_cache"

    # Always rebuild to reflect the current sysroot.
    if bench_cache.exists():
        shutil.rmtree(bench_cache)
    bench_cache.mkdir(parents=True)

    sysroot_src = staging
    sysroot_dst = bench_cache
    shutil.copytree(sysroot_src, sysroot_dst)
    (sysroot_dst / "tmp").mkdir(exist_ok=True)

    # Release-style trim: no test/ dir, no dev artifacts.
    ramfs_mod.trim_and_build(
        bench_cache,
        args.sysroot,
        ramfs_img,
        keep_tests=False,
    )

    # Scratch directory is no longer needed.
    shutil.rmtree(bench_cache, ignore_errors=True)

    # Run benchmark.
    print(f"Benchmark: Hello world ({args.process_mode})...")

    returncode, output, elapsed_ms = _run_nanvixd_script(
        staging,
        bench_script,
        args,
        nanvixd_extra=nanvixd_extra,
        ramfs_img=ramfs_img,
        label="Benchmark",
    )
    print(f"  Execution time: {elapsed_ms} ms")

    if returncode != 0:
        print(f"  FAIL: Benchmark exited with status {returncode}")
        print(output)
        raise RuntimeError(f"Benchmark exited with status {returncode}")

    if "hello world" not in output:
        print(f"  FAIL: expected 'hello world' in output")
        print(output)
        raise RuntimeError("Benchmark did not produce expected output")

    print("  PASS")

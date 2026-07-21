# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Test lifecycle for the CPython ZScript.

Owns ``./z test`` and the test-only helpers. Cross-mixin helpers
(``stage``, ``stage_ramfs``, ``cleanup``, ``run_nanvixd_script``,
``create_initrd``) live on :class:`~src.lib.LibMixin` because they are
also consumed by the build and benchmark stages.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

from nanvix_zutil import paths

import src.config as config
import src.lxml as lxml_mod
from src.lib import LibMixin

_DOWNLOADED_RELEASE_MARKER = ".downloaded-release"


class TestMixin(LibMixin):
    """``./z test`` — run the CPython test suite (hello + regrtest)."""

    def test(self) -> None:
        """Run the CPython test suite (hello + regrtest)."""
        self._overlay_local_nanvix()
        self.args = self.make_args(release=False)
        nanvixd_extra = ["-allow-host-networking"]
        ramfs_img = paths.test_out() / "cpython-rootfs.img"
        self.run_all(nanvixd_extra=nanvixd_extra, ramfs_img=ramfs_img)

    # ------------------------------------------------------------------
    # Windows: download release artifacts as install cache
    # ------------------------------------------------------------------

    def _download_release_as_cache(self) -> Path:
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
        asset_id = None
        asset_stem = (
            f"cpython-linux-x86-{self.args.platform}-{self.args.process_mode}"
            f"-{self.args.memory_size}"
        )
        for ext in (".tar.gz", ".tar.bz2"):
            for a in release.get("assets", []):
                name = a.get("name", "")
                if isinstance(name, str) and (
                    name == f"{self.args.asset_prefix()}{ext}"
                    or name == f"{asset_stem}{ext}"
                ):
                    asset_url = a["browser_download_url"]
                    asset_name = name
                    asset_id = a["id"]
                    break
            if asset_url:
                break

        if not asset_url:
            raise FileNotFoundError(
                f"No cpython runtime release asset named "
                f"'{asset_stem}.tar.gz' or '{asset_stem}.tar.bz2' "
                f"in release {tag}. Available assets: "
                + ", ".join(a["name"] for a in release.get("assets", []))
            )

        # Download.
        dl_dir = paths.nanvix_root() / "cache"
        dl_dir.mkdir(parents=True, exist_ok=True)
        assert asset_name is not None
        assert asset_id is not None
        tarball = dl_dir / f"{asset_id}-{asset_name}"
        if not tarball.is_file():
            print(f"  Downloading {asset_name}...")
            partial = tarball.with_name(f".{tarball.name}.partial")
            try:
                urllib.request.urlretrieve(asset_url, str(partial))
                partial.replace(tarball)
            finally:
                if partial.exists():
                    partial.unlink()

        # Extract into cache_dir with path-traversal protection.
        print(f"  Extracting to {cache_dir}...")
        with tarfile.open(tarball, "r:*") as tf:
            base = cache_dir.resolve()
            for member in tf.getmembers():
                if member.issym() or member.islnk():
                    raise tarfile.TarError(
                        f"refusing to extract link entry: {member.name}"
                    )
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

        (cache_dir / _DOWNLOADED_RELEASE_MARKER).write_text(tag, encoding="utf-8")
        print(f"  Install cache ready at {cache_dir}")
        return cache_dir

    # ------------------------------------------------------------------
    # Hello test
    # ------------------------------------------------------------------

    def run_hello(
        self,
        staging: Path,
        nanvixd_extra: list[str] | None = None,
        ramfs_img: Path | None = None,
        require_array_so: bool = True,
    ) -> None:
        """Run the hello-world test via nanvixd.

        Standalone mode uses ramfs + ``-bin-dir`` + the semicolon-delimited
        environment variable syntax.
        """
        print(f"Test: Hello world ({self.args.process_mode})...")

        returncode, output, elapsed_ms = self.run_nanvixd_script(
            staging,
            "test_hello.py",
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
        found_array = False
        found_array_so = False
        found_lxml = False
        for line in output.splitlines():
            if line.startswith("CPYTHON_TEST_"):
                tag = line.split(":")[0].replace("CPYTHON_TEST_", "")
                print(f"  {tag}: {line.strip()}")
                if tag == "HELLO":
                    found_hello = True
                elif tag == "ARRAY":
                    found_array = True
                elif tag == "ARRAY_SO":
                    found_array_so = True
                elif tag in ("LXML", "LXML_SKIP"):
                    found_lxml = True

        if not found_hello:
            print("  FAIL: Hello test did not produce expected output")
            print(output)
            raise RuntimeError("Hello test did not produce expected output")

        if not found_array:
            print("  FAIL: Hello test did not exercise array")
            print(output)
            raise RuntimeError("Hello test did not exercise array")

        if require_array_so and not found_array_so:
            print("  FAIL: Hello test did not load array as a shared module")
            print(output)
            raise RuntimeError("Hello test did not load array as a shared module")

        if not found_lxml:
            # lxml staging is best-effort — if the runtime package was not
            # available (e.g. release asset missing), the test is non-fatal.
            print("  WARNING: lxml import/parse test did not produce expected output")

        print("  PASS")

    # ------------------------------------------------------------------
    # HTTP server smoke test
    # ------------------------------------------------------------------

    def run_smoke_httpserver(
        self,
        staging: Path,
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
        by :meth:`~src.lib.LibMixin.stage` (and therefore into the ramfs
        image for standalone mode).  Starts nanvixd as a background
        process, waits for the server's "listening" log line on stdout,
        issues a single HTTP/1.0 GET, and validates the response body.
        The nanvixd process is always terminated before this function
        returns.
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
            else config.PLATFORM_NANVIXD_ARGS.get(self.args.platform, [])
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
            hp = self.args.sysroot / "bin" / name
            if hp.is_file():
                shutil.copy2(hp, staging / "bin" / name)

        bin_dir = staging / "bin"
        app_path = staging / "bin" / config.python_binary()
        app_args = ["-B", f"./{script_name}"]
        app_env = (
            f"PYTHONHOME=/ PYTHONDONTWRITEBYTECODE=1"
            f" _PYTHON_SYSCONFIGDATA_NAME={config.SYSCONFIGDATA_NAME}"
        )
        initrd_img = self.create_initrd(
            bin_dir, app_path, app_args=app_args, app_env=app_env
        )
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

        print(f"Test: HTTP server smoke ({self.args.process_mode}) on {host}:{port}...")

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
                with _socket.create_connection(
                    (host, port), timeout=request_timeout
                ) as s:
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

    # ------------------------------------------------------------------
    # Regression tests
    # ------------------------------------------------------------------

    def run_regrtest(
        self,
        staging: Path,
        *,
        test_list: list[str] | None = None,
        batch_size: int = config.DEFAULT_TEST_BATCH_SIZE,
        nanvixd_extra: list[str] | None = None,
        ramfs_img: Path | None = None,
    ) -> None:
        """Run stdlib regression tests via run-tests.py."""
        if self.args.release:
            print("Test: regrtest skipped (NANVIX_RELEASE=yes)")
            return

        if test_list is None:
            test_list = list(config.NANVIX_TEST_LIST)

        resolved_nanvixd_extra: list[str] = (
            nanvixd_extra
            if nanvixd_extra is not None
            else config.PLATFORM_NANVIXD_ARGS.get(self.args.platform, [])
        )

        run_tests_script = paths.nanvix_root() / "src" / "run-tests.py"

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

        print(f"Test: regrtest ({len(test_list)} modules, {self.args.process_mode})...")
        result = subprocess.run(cmd, cwd=staging, env=env)
        if result.returncode != 0:
            raise RuntimeError(f"regrtest failed with exit code {result.returncode}")

    # ------------------------------------------------------------------
    # Aggregate test runner
    # ------------------------------------------------------------------

    def run_all(
        self,
        *,
        test_list: list[str] | None = None,
        batch_size: int = config.DEFAULT_TEST_BATCH_SIZE,
        nanvixd_extra: list[str] | None = None,
        ramfs_img: Path | None = None,
    ) -> None:
        """Run the complete test pipeline: hello → regrtest → cleanup.

        Consumes the test install tree produced by ``./z build`` at
        ``paths.test_out()``; see :meth:`~src.lib.LibMixin.stage`.
        """
        staging = paths.test_out()
        print("Running CPython tests on Nanvix...")
        require_array_so = True

        if config.IS_WINDOWS:
            release_marker = staging / _DOWNLOADED_RELEASE_MARKER
            downloaded_release = release_marker.is_file()
            python = staging / "bin" / config.python_binary()
            if os.environ.get("CI") is not None and not python.is_file():
                raise FileNotFoundError(
                    f"Windows test artifact is missing the SDK-built interpreter: {python}"
                )
            if os.environ.get("CI") is None and not python.is_file():
                print("Downloading release artifacts for local Windows testing...")
                self._download_release_as_cache()
                downloaded_release = True
            require_array_so = not downloaded_release
            self.stage(require_array_so=require_array_so)
            if downloaded_release:
                self.stage_ramfs()

        lxml_mod.stage_lxml_runtime(staging)

        # Hello test.
        self.run_hello(
            staging,
            nanvixd_extra=nanvixd_extra,
            ramfs_img=ramfs_img,
            require_array_so=require_array_so,
        )

        # HTTP server smoke test.
        self.run_smoke_httpserver(
            staging,
            nanvixd_extra=nanvixd_extra,
            ramfs_img=ramfs_img,
        )

        # Regression tests.
        self.run_regrtest(
            staging,
            test_list=test_list,
            batch_size=batch_size,
            nanvixd_extra=nanvixd_extra,
            ramfs_img=ramfs_img,
        )

        # Cleanup.
        self.cleanup()

        print("\t\t*** CPython tests PASSED ***")

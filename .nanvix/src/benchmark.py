# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Benchmark lifecycle for the CPython ZScript."""

from __future__ import annotations

import shutil

from nanvix_zutil import paths

import src.ramfs as ramfs_mod
from src.lib import LibMixin


class BenchmarkMixin(LibMixin):
    """``./z benchmark`` — run hello-world benchmark with a release-style ramfs."""

    def benchmark(self) -> None:
        """Run hello-world benchmark with a release-style ramfs."""
        self._overlay_local_nanvix()
        self.args = self.make_args(release=False)
        self.run_benchmark(nanvixd_extra=["-allow-host-networking"])

    def run_benchmark(
        self,
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
            self._run_benchmark_impl(nanvixd_extra=nanvixd_extra)
        finally:
            self.cleanup()

    def _run_benchmark_impl(
        self,
        *,
        nanvixd_extra: list[str] | None = None,
    ) -> None:
        """Inner implementation of :meth:`run_benchmark`."""
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
            self.args.sysroot,
            ramfs_img,
            keep_tests=False,
        )

        # Scratch directory is no longer needed.
        shutil.rmtree(bench_cache, ignore_errors=True)

        # Run benchmark.
        print(f"Benchmark: Hello world ({self.args.process_mode})...")

        returncode, output, elapsed_ms = self.run_nanvixd_script(
            staging,
            bench_script,
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

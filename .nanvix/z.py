# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Nanvix build script for cpython."""

from nanvix_zutil import CFG_SYSROOT, CFG_TOOLCHAIN, EXIT_MISSING_DEP, ZScript, log


class CpythonBuild(ZScript):
    """Build script for nanvix/cpython."""

    def _make_args(self, *targets: str) -> list[str]:
        """Build the common make argument list."""
        sysroot = self.config.get(CFG_SYSROOT, "")
        if not sysroot:
            log.fatal(
                f"{CFG_SYSROOT} is not set.",
                code=EXIT_MISSING_DEP,
                hint="Run `nanvix-zutil setup` first to download the sysroot.",
            )
        toolchain = self.config.get(CFG_TOOLCHAIN, "/opt/nanvix")

        args = [
            "make", "-f", "Makefile.nanvix",
            "CONFIG_NANVIX=y",
            f"NANVIX_HOME={sysroot}",
            f"NANVIX_TOOLCHAIN={toolchain}",
            f"PLATFORM={self.config.machine}",
            f"PROCESS_MODE={self.config.deployment_mode}",
            f"MEMORY_SIZE={self.config.memory_size}",
        ]
        args.extend(targets)
        return args

    def setup(self) -> None:
        """Download sysroot and all 5 dependencies, then verify."""
        super().setup()
        if self.buildroot is None:
            log.fatal(
                "nanvix.toml must declare dependencies.",
                code=EXIT_MISSING_DEP,
                hint="Add dependencies to [dependencies] in nanvix.toml, then re-run setup.",
            )
        self.buildroot.verify([
            "libz.a", "libsqlite3.a", "libssl.a",
            "libcrypto.a", "libbz2.a", "libffi.a",
        ])

    def build(self) -> None:
        """Cross-compile python.elf for Nanvix."""
        self.run(*self._make_args("all"), cwd=self.repo_root)

    def test(self) -> None:
        """Run the cpython test suite."""
        targets = self.targets if self.targets else ["test"]
        self.run(*self._make_args(*targets), cwd=self.repo_root)

    def release(self) -> None:
        """Package the cpython release tarball and verify it."""
        self.run(*self._make_args("package"), cwd=self.repo_root)
        self.run(*self._make_args("verify-package"), cwd=self.repo_root)

    def clean(self) -> None:
        """Remove build artifacts."""
        self.run("make", "-f", "Makefile.nanvix", "clean", cwd=self.repo_root)


if __name__ == "__main__":
    CpythonBuild.main()

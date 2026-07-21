# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Nanvix build script for CPython.

Usage:
    ./z setup      # Download Nanvix sysroot and dependencies
    ./z build      # Cross-compile python.elf and libpython.a
    ./z test       # Run test suite (hello-world on nanvixd.elf)
    ./z benchmark  # Run hello-world benchmark with release ramfs
    ./z release    # Package release tarballs
    ./z clean      # Remove build artifacts

Options:
    --with-nanvix PATH  Use local Nanvix binaries from PATH instead of
                        the downloaded sysroot binaries. PATH should point
                        to a Nanvix build directory containing bin/ and lib/.
                        The path is persisted in .nanvix/env.json, so it
                        only needs to be passed once. Pass again to change
                        it. Works on both Linux and Windows.

All lifecycle behaviour is contributed by mixins in ``src/``; this
class only exists to compose them.
"""

from src.benchmark import BenchmarkMixin
from src.build import BuildMixin
from src.clean import CleanMixin
from src.setup import SetupMixin
from src.test import TestMixin


class CPythonBuild(SetupMixin, BuildMixin, TestMixin, BenchmarkMixin, CleanMixin):
    """Build script for nanvix/cpython."""


if __name__ == "__main__":
    CPythonBuild.main()

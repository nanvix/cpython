"""numpy build helpers and runtime staging for Nanvix CPython."""

from __future__ import annotations

import shutil
from pathlib import Path

import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _loader import load_sibling

config = load_sibling("config", __file__)

_SETUP_LOCAL_LINES = """\
# numpy _multiarray_umath (statically linked via pre-built archive).
_np_multiarray_umath _np_multiarray_umath_builtin.c -L{sysroot}/lib -lnumpy_core -lstdc++ -lm
"""


def generate_setup_local_lines(sysroot: Path) -> str:
    """Return Setup.local lines for numpy modules."""
    return _SETUP_LOCAL_LINES.format(sysroot=sysroot)


def stage_numpy_runtime(repo_root: Path, sysroot: Path) -> None:
    """Copy numpy Python files from buildroot into the sysroot."""
    np_src = repo_root / ".nanvix" / "buildroot" / "python-packages" / "numpy"
    if not np_src.is_dir():
        print(
            f"[numpy] Python package not found at {np_src}; "
            "skipping runtime staging."
        )
        return

    py_lib = sysroot / "lib" / config.PYTHON_LIB_DIR
    np_dst = py_lib / "numpy"

    if np_dst.exists():
        shutil.rmtree(np_dst)

    shutil.copytree(np_src, np_dst)
    print(f"[numpy] Staged Python files to {np_dst}")

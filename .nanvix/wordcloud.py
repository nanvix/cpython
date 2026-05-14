"""wordcloud build helpers and runtime staging for Nanvix CPython."""

from __future__ import annotations

import shutil
from pathlib import Path

import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _loader import load_sibling

config = load_sibling("config", __file__)

_SETUP_LOCAL_LINES = """\
# wordcloud Cython extension module (statically linked via pre-built archive).
_wc_query_integral_image _wc_query_integral_image_builtin.c -L{sysroot}/lib -lquery_integral_image
"""


def generate_setup_local_lines(sysroot: Path) -> str:
    """Return Setup.local lines for wordcloud modules."""
    return _SETUP_LOCAL_LINES.format(sysroot=sysroot)


def stage_wordcloud_runtime(repo_root: Path, sysroot: Path) -> None:
    """Copy wordcloud Python files from buildroot into the sysroot.

    Then writes the Python shim that bridges _wc_query_integral_image
    to wordcloud.query_integral_image.
    """
    wc_src = repo_root / ".nanvix" / "buildroot" / "python-packages" / "wordcloud"
    if not wc_src.is_dir():
        print(
            f"[wordcloud] Python package not found at {wc_src}; "
            "skipping runtime staging."
        )
        return

    py_lib = sysroot / "lib" / config.PYTHON_LIB_DIR
    if not py_lib.is_dir():
        raise RuntimeError(f"Python runtime library directory is missing: {py_lib}")

    dst = py_lib / "wordcloud"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(wc_src, dst)

    # Write Python shim bridging flat builtin to package path
    (dst / "query_integral_image.py").write_text(
        "from _wc_query_integral_image import *\n",
        encoding="utf-8",
    )

    print(f"[wordcloud] Staged {wc_src} -> {dst}")

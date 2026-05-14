"""rapidfuzz build helpers and runtime staging for Nanvix CPython."""

from __future__ import annotations

import shutil
from pathlib import Path

import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _loader import load_sibling

config = load_sibling("config", __file__)

# Each line: <flat_module_name> <builtin_c_file> <link_flags>
# The flat name avoids dotted-module limitations in Setup.local.
# Python shims bridge flat names back to the expected import paths.
_SETUP_LOCAL_LINES = """\
# rapidfuzz C++ extension modules (statically linked via pre-built archives).
_rf_utils_cpp _rf_utils_cpp_builtin.c -L{sysroot}/lib -lutils_cpp -lstdc++
_rf_fuzz_cpp _rf_fuzz_cpp_builtin.c -L{sysroot}/lib -lfuzz_cpp -lstdc++
_rf_fuzz_cpp_sse2 _rf_fuzz_cpp_sse2_builtin.c -L{sysroot}/lib -lfuzz_cpp_sse2 -lstdc++
_rf_feature_detector_cpp _rf_feature_detector_cpp_builtin.c -L{sysroot}/lib -l_feature_detector_cpp -lstdc++
_rf_dist_initialize_cpp _rf_dist_initialize_cpp_builtin.c -L{sysroot}/lib -ldist__initialize_cpp -lstdc++
_rf_dist_metrics_cpp _rf_dist_metrics_cpp_builtin.c -L{sysroot}/lib -ldist_metrics_cpp -lstdc++
_rf_dist_metrics_cpp_sse2 _rf_dist_metrics_cpp_sse2_builtin.c -L{sysroot}/lib -ldist_metrics_cpp_sse2 -lstdc++
"""


def generate_setup_local_lines(sysroot: Path) -> str:
    """Return Setup.local lines for rapidfuzz modules."""
    return _SETUP_LOCAL_LINES.format(sysroot=sysroot)


def stage_rapidfuzz_runtime(repo_root: Path, sysroot: Path) -> None:
    """Copy rapidfuzz Python files from buildroot into the sysroot.

    Looks for rapidfuzz in ``.nanvix/buildroot/python-packages/rapidfuzz/``.
    Then writes Python shim modules that bridge the flat builtin names
    to the expected ``rapidfuzz.*`` / ``rapidfuzz.distance.*`` import paths.
    """
    rf_src = repo_root / ".nanvix" / "buildroot" / "python-packages" / "rapidfuzz"
    if not rf_src.is_dir():
        print(
            f"[rapidfuzz] Python package not found at {rf_src}; "
            "skipping runtime staging."
        )
        return

    py_lib = sysroot / "lib" / config.PYTHON_LIB_DIR
    if not py_lib.is_dir():
        raise RuntimeError(f"Python runtime library directory is missing: {py_lib}")

    dst = py_lib / "rapidfuzz"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(rf_src, dst)

    # Write Python shims that bridge flat builtin names to package paths
    _write_shims(dst)

    print(f"[rapidfuzz] Staged {rf_src} -> {dst}")


# Python shim content: each maps a rapidfuzz.X import to _rf_X builtin
_CORE_SHIMS = {
    "utils_cpp.py": "from _rf_utils_cpp import *\n",
    "fuzz_cpp.py": "from _rf_fuzz_cpp import *\n",
    "fuzz_cpp_sse2.py": "from _rf_fuzz_cpp_sse2 import *\n",
    "_feature_detector_cpp.py": "from _rf_feature_detector_cpp import *\n",
}

_DISTANCE_SHIMS = {
    "_initialize_cpp.py": "from _rf_dist_initialize_cpp import *\n",
    "metrics_cpp.py": "from _rf_dist_metrics_cpp import *\n",
    "metrics_cpp_sse2.py": "from _rf_dist_metrics_cpp_sse2 import *\n",
}


def _write_shims(pkg_dir: Path) -> None:
    """Write Python shim modules that bridge flat builtins to package paths."""
    for name, content in _CORE_SHIMS.items():
        (pkg_dir / name).write_text(content, encoding="utf-8")

    dist_dir = pkg_dir / "distance"
    dist_dir.mkdir(exist_ok=True)
    for name, content in _DISTANCE_SHIMS.items():
        (dist_dir / name).write_text(content, encoding="utf-8")

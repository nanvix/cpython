"""Pillow build helpers and runtime staging for Nanvix CPython."""

from __future__ import annotations

from pathlib import Path

import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _loader import load_sibling

config = load_sibling("config", __file__)

_SETUP_LOCAL_LINES = """\
# Pillow C extension modules (statically linked via pre-built archive).
_pil_imaging _pil_imaging_builtin.c -L{sysroot}/lib -l_imaging -lz
_pil_imagingmath _pil_imagingmath_builtin.c -L{sysroot}/lib -l_imaging
_pil_imagingmorph _pil_imagingmorph_builtin.c -L{sysroot}/lib -l_imaging
"""


def generate_setup_local_lines(sysroot: Path) -> str:
    """Return Setup.local lines for Pillow modules."""
    return _SETUP_LOCAL_LINES.format(sysroot=sysroot)

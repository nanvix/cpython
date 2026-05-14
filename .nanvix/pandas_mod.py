"""Pandas build helpers for Nanvix CPython static linking."""

from __future__ import annotations
from pathlib import Path
import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _loader import load_sibling

config = load_sibling("config", __file__)

# All pandas extension modules with their flat builtin names
_PANDAS_MODULES = [
    # pandas/_libs/ Cython modules
    "_pd_algos",
    "_pd_arrays",
    "_pd_byteswap",
    "_pd_groupby",
    "_pd_hashing",
    "_pd_hashtable",
    "_pd_index",
    "_pd_indexing",
    "_pd_internals",
    "_pd_interval",
    "_pd_join",
    "_pd_lib",
    "_pd_missing",
    "_pd_ops",
    "_pd_ops_dispatch",
    "_pd_parsers",
    "_pd_properties",
    "_pd_reshape",
    "_pd_sas",
    "_pd_sparse",
    "_pd_testing",
    "_pd_tslib",
    "_pd_writers",
    # pandas/_libs/ pure-C modules
    "_pd_pandas_datetime",
    "_pd_pandas_parser",
    "_pd_ujson",
    # pandas/_libs/tslibs/ Cython modules
    "_pd_tslibs_base",
    "_pd_tslibs_ccalendar",
    "_pd_tslibs_conversion",
    "_pd_tslibs_dtypes",
    "_pd_tslibs_fields",
    "_pd_tslibs_nattype",
    "_pd_tslibs_np_datetime",
    "_pd_tslibs_offsets",
    "_pd_tslibs_parsing",
    "_pd_tslibs_period",
    "_pd_tslibs_strptime",
    "_pd_tslibs_timedeltas",
    "_pd_tslibs_timestamps",
    "_pd_tslibs_timezones",
    "_pd_tslibs_tzconversion",
    "_pd_tslibs_vectorized",
    # pandas/_libs/window/ Cython modules
    "_pd_window_aggregations",
    "_pd_window_indexers",
]

_SETUP_LOCAL_TEMPLATE = """\
# Pandas C extension modules (statically linked via pre-built archive).
{entries}
"""


def generate_setup_local_lines(sysroot: Path) -> str:
    """Return Setup.local lines for all pandas extension modules."""
    entries: list[str] = []
    for mod in _PANDAS_MODULES:
        entries.append(
            f"{mod} {mod}_builtin.c "
            f"-L{sysroot}/lib -lpandas -lnumpy_core -lstdc++ -lm"
        )
    return _SETUP_LOCAL_TEMPLATE.format(entries="\n".join(entries))

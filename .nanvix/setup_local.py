# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Single source of truth for Modules/Setup.local on Nanvix builds.

The host build path in ``lxml.generate_setup_local()`` and the Docker build
path in ``_docker._generate_setup_local_cmd()`` both render this table.

Module ordering matters: makesetup applies "first rule wins" semantics when
the same module is declared both here and in ``Modules/Setup.stdlib``.
Declaring a shared duplicate before the upstream static default switches that
module to a runtime-loaded extension.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, NamedTuple, Sequence


class Linkage(Enum):
    STATIC = "*static*"
    SHARED = "*shared*"


class SetupEntry(NamedTuple):
    """One Modules/Setup.local entry with optional surrounding comments."""

    name: str
    linkage: Linkage
    tokens: Sequence[str] = ()
    comment: str = ""
    section_header: str = ""


SETUP_LOCAL_ENTRIES: tuple[SetupEntry, ...] = (
    SetupEntry(
        name="_nanvix",
        linkage=Linkage.STATIC,
        tokens=("_nanvixmodule.c",),
        comment="Nanvix OS interface module (snapshot, host-mount).",
    ),
    SetupEntry(
        name="_lxml_etree",
        linkage=Linkage.STATIC,
        tokens=(
            "lxml_etree_builtin.c",
            "-L{buildroot}/lib",
            "-llxml_etree",
            "-lxslt",
            "-lexslt",
            "-lxml2",
            "-lz",
        ),
        comment="lxml C extensions linked with their pre-built archives.",
    ),
    SetupEntry(
        name="_lxml_elementpath",
        linkage=Linkage.STATIC,
        tokens=(
            "lxml_elementpath_builtin.c",
            "-L{buildroot}/lib",
            "-llxml_elementpath",
            "-lxml2",
            "-lz",
        ),
    ),
    SetupEntry(
        name="array",
        linkage=Linkage.SHARED,
        tokens=("arraymodule.c",),
        section_header=(
            "`array` is the proof-of-concept shared module. It appears before "
            "Setup.stdlib so makesetup selects this shared definition."
        ),
    ),
    *(
        SetupEntry(
            name=name,
            linkage=Linkage.SHARED,
            tokens=(source,),
            section_header=header if index == 0 else "",
        )
        for index, (name, source) in enumerate(
            (
                ("_bisect", "_bisectmodule.c"),
                ("_heapq", "_heapqmodule.c"),
                ("_struct", "_struct.c"),
                ("_random", "_randommodule.c"),
                ("_opcode", "_opcode.c"),
                ("_queue", "_queuemodule.c"),
                ("_csv", "_csv.c"),
                ("binascii", "binascii.c"),
                ("_json", "_json.c"),
                ("_pickle", "_pickle.c"),
                ("_zoneinfo", "_zoneinfo.c"),
            )
        )
        for header in ("Data primitives without external dependencies.",)
    ),
    *(
        SetupEntry(
            name=name,
            linkage=Linkage.SHARED,
            tokens=(source,),
            section_header=header if index == 0 else "",
        )
        for index, (name, source) in enumerate(
            (
                ("math", "mathmodule.c"),
                ("cmath", "cmathmodule.c"),
                ("_statistics", "_statisticsmodule.c"),
                ("mmap", "mmapmodule.c"),
                ("_contextvars", "_contextvarsmodule.c"),
            )
        )
        for header in ("Math and memory modules using the SDK shared runtime.",)
    ),
    *(
        SetupEntry(
            name=name,
            linkage=Linkage.SHARED,
            tokens=(source,),
            section_header=header if index == 0 else "",
        )
        for index, (name, source) in enumerate(
            (
                ("unicodedata", "unicodedata.c"),
                ("_codecs_cn", "cjkcodecs/_codecs_cn.c"),
                ("_codecs_hk", "cjkcodecs/_codecs_hk.c"),
                ("_codecs_iso2022", "cjkcodecs/_codecs_iso2022.c"),
                ("_codecs_jp", "cjkcodecs/_codecs_jp.c"),
                ("_codecs_kr", "cjkcodecs/_codecs_kr.c"),
                ("_codecs_tw", "cjkcodecs/_codecs_tw.c"),
            )
        )
        for header in ("Text codecs without external dependencies.",)
    ),
    # Keep _datetime, pyexpat, and _multibytecodec static: migrated consumers
    # import their C APIs while a shared object initializes, which Nanvix cannot
    # nest safely yet.
    SetupEntry(
        name="_asyncio",
        linkage=Linkage.SHARED,
        tokens=("_asynciomodule.c",),
        section_header=(
            "Modules with bundled CPython dependencies. Each extension keeps "
            "its vendored archive, matching the upstream build."
        ),
    ),
    SetupEntry(
        name="_decimal", linkage=Linkage.SHARED, tokens=("_decimal/_decimal.c",)
    ),
    SetupEntry(name="_elementtree", linkage=Linkage.SHARED, tokens=("_elementtree.c",)),
    SetupEntry(
        name="_md5",
        linkage=Linkage.SHARED,
        tokens=(
            "md5module.c",
            "-I$(srcdir)/Modules/_hacl/include",
            "_hacl/Hacl_Hash_MD5.c",
            "-D_BSD_SOURCE",
            "-D_DEFAULT_SOURCE",
        ),
    ),
    SetupEntry(
        name="_sha1",
        linkage=Linkage.SHARED,
        tokens=(
            "sha1module.c",
            "-I$(srcdir)/Modules/_hacl/include",
            "_hacl/Hacl_Hash_SHA1.c",
            "-D_BSD_SOURCE",
            "-D_DEFAULT_SOURCE",
        ),
    ),
    SetupEntry(
        name="_sha2",
        linkage=Linkage.SHARED,
        tokens=(
            "sha2module.c",
            "-I$(srcdir)/Modules/_hacl/include",
            "Modules/_hacl/libHacl_Hash_SHA2.a",
        ),
    ),
    SetupEntry(
        name="_sha3",
        linkage=Linkage.SHARED,
        tokens=(
            "sha3module.c",
            "-I$(srcdir)/Modules/_hacl/include",
            "_hacl/Hacl_Hash_SHA3.c",
            "-D_BSD_SOURCE",
            "-D_DEFAULT_SOURCE",
            "$(COMPILER_RT_BUILTINS)",
        ),
    ),
    SetupEntry(
        name="_blake2",
        linkage=Linkage.SHARED,
        tokens=(
            "_blake2/blake2module.c",
            "_blake2/blake2b_impl.c",
            "_blake2/blake2s_impl.c",
        ),
    ),
    SetupEntry(name="select", linkage=Linkage.SHARED, tokens=("selectmodule.c",)),
    SetupEntry(name="_socket", linkage=Linkage.SHARED, tokens=("socketmodule.c",)),
    SetupEntry(
        name="_posixsubprocess", linkage=Linkage.SHARED, tokens=("_posixsubprocess.c",)
    ),
    SetupEntry(name="fcntl", linkage=Linkage.SHARED, tokens=("fcntlmodule.c",)),
    SetupEntry(name="termios", linkage=Linkage.SHARED, tokens=("termios.c", "-lc")),
)


def _wrap_comment(text: str, *, width: int = 78) -> list[str]:
    """Return wrapped Setup.local comment lines."""
    if not text:
        return []

    import textwrap

    return [f"# {line}" for line in textwrap.wrap(text, width=width - 2)]


def render_setup_local(
    entries: Iterable[SetupEntry] = SETUP_LOCAL_ENTRIES,
    *,
    buildroot: str,
    header_comment: str,
) -> str:
    """Render entries to a complete Modules/Setup.local file."""
    lines = [f"# {header_comment}", ""]
    current_linkage: Linkage | None = None

    for entry in entries:
        if entry.linkage is not current_linkage:
            if current_linkage is not None:
                lines.append("")
            if entry.section_header:
                lines.extend(_wrap_comment(entry.section_header))
            elif current_linkage is None and entry.linkage is Linkage.STATIC:
                lines.append("# Statically-linked extension modules for Nanvix builds.")
            lines.append(entry.linkage.value)
            current_linkage = entry.linkage
        elif entry.section_header:
            lines.append("")
            lines.extend(_wrap_comment(entry.section_header))

        if entry.comment:
            lines.extend(_wrap_comment(entry.comment))
        tokens = " ".join(entry.tokens).replace("{buildroot}", buildroot)
        lines.append(f"{entry.name} {tokens}".rstrip())

    lines.append("")
    return "\n".join(lines)

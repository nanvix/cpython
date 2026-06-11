# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Docker host mode for Windows cross-compilation.

Replaces docker-host.mk and sync-sources.sh. Handles tar-based source
sync, CRLF normalization, named Docker volume management, and container
invocation for configure/build/install only.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import build as build_mod

import config


def _workspace_id(workspace: Path) -> str:
    """Generate a deterministic volume suffix from the workspace path."""
    # Use a short hash to match the old cksum-based approach.
    h = hashlib.md5(str(workspace.resolve()).encode()).hexdigest()[:8]
    return h


def _volume_name(workspace: Path) -> str:
    return f"cpython-nanvix-build-{_workspace_id(workspace)}"


def _docker_mount_source(path: Path) -> str:
    """Render *path* as a Docker bind-mount source.

    Docker's ``-v src:dst[:mode]`` syntax splits fields on ``:``.  On
    Windows, ``Path`` renders drive-letter paths like ``C:\\Users\\foo``,
    whose colon is misread as a field separator -- producing errors such
    as ``invalid mode: /mnt/host-workspace``.  Translate drive-letter
    paths to the ``/c/Users/foo`` form that Docker accepts and which
    contains no colon.  POSIX paths are returned unchanged.
    """
    resolved = path.resolve()
    drive = resolved.drive
    # Drive-letter prefix, e.g. "C:" (UNC drives are longer and skipped).
    if len(drive) == 2 and drive[1] == ":":
        letter = drive[0].lower()
        rest = str(resolved)[len(drive) :].replace("\\", "/").lstrip("/")
        return f"/{letter}/{rest}"
    return str(resolved)


def _docker_run_base(
    workspace: Path,
    args: build_mod.MakeArgs,
    image: str = config.DOCKER_IMAGE,
) -> list[str]:
    """Build the common ``docker run`` prefix."""
    volume = _volume_name(workspace)
    uid = getattr(os, "getuid", lambda: 1000)()
    gid = getattr(os, "getgid", lambda: 1000)()
    return [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{uid}:{gid}",
        "-v",
        f"{volume}:{config.DOCKER_WORKSPACE_PATH}",
        "-v",
        f"{_docker_mount_source(workspace)}:/mnt/host-workspace",
        "-v",
        f"{_docker_mount_source(args.sysroot)}:{config.DOCKER_SYSROOT_PATH}:ro",
        "-w",
        config.DOCKER_WORKSPACE_PATH,
        "-e",
        "HOME=/tmp",
        image,
    ]


def sync_sources(
    workspace: Path,
    build_dir: str = config.DOCKER_WORKSPACE_PATH,
) -> str:
    """Generate a shell script that syncs sources into the container.

    Uses rsync when available (preserves timestamps, deletes stale files).
    Falls back to tar-based copy otherwise.

    Returns a shell command string that can be passed to ``sh -c``.
    """
    # Build exclude flags.
    excludes = " ".join(f"--exclude={e}" for e in config.DOCKER_TAR_EXCLUDES)

    # CRLF normalization commands.
    crlf_cmds = " && ".join(
        f'[ -f "{build_dir}/{f}" ] && sed -i "s/\\r$//" "{build_dir}/{f}" || true'
        for f in config.DOCKER_CRLF_FILES
    )

    rsync_excludes = " ".join(f"--exclude={e}" for e in config.DOCKER_TAR_EXCLUDES)
    rsync_cmd = f"rsync -a --delete {rsync_excludes} /mnt/host-workspace/ {build_dir}/"
    tar_cmd = (
        f"cd /mnt/host-workspace && tar -cf - {excludes} . | tar -xf - -C {build_dir}"
    )

    return (
        f"if command -v rsync >/dev/null 2>&1; then {rsync_cmd}; "
        f"else {tar_cmd}; fi && "
        f"{crlf_cmds}"
    )


def docker_build(
    workspace: Path,
    args: build_mod.MakeArgs,
    *,
    install_destdir: Path | None = None,
) -> None:
    """Run cross-compilation inside Docker (Windows host mode).

    Syncs sources into a named Docker volume, runs configure+build,
    and copies outputs back to the host workspace.

    If *install_destdir* is provided, also runs ``make install`` inside
    the same container and copies the install tree to the host.  This
    avoids a second Docker invocation during testing.
    """
    _args = dataclasses.replace(args, docker=True, targets=["build"])
    base = _docker_run_base(workspace, _args)
    sync = sync_sources(workspace)
    copy_back = _copy_outputs_cmd()

    # Explicit strip command — ensure binaries are fully stripped even if
    # the Makefile's strip step is skipped (e.g. toolchain detection fails
    # inside the container).
    strip_bin = f"{config.DOCKER_TOOLCHAIN_PATH}/bin/{config.TOOLCHAIN_TRIPLET}-strip"
    strip_build = (
        f'if [ -x "{strip_bin}" ]; then '
        f"for f in python python{config.EXE}; do "
        f'[ -f "{config.DOCKER_WORKSPACE_PATH}/$f" ] && '
        f'"{strip_bin}" --strip-all "{config.DOCKER_WORKSPACE_PATH}/$f" && '
        f'echo "Stripped $f"; done; fi'
    )

    # Detect sysroot changes and force a clean rebuild when needed.
    # Without rsync (unavailable in the minimal Docker image), the tar-based
    # sync does not delete stale build artifacts from the named volume.
    # If the sysroot changes (e.g. switching between downloaded and local
    # Nanvix via --with-nanvix), stale object files and the old python
    # binary remain.  Make sees no source changes and skips recompilation,
    # producing a binary linked against the *old* sysroot libraries.
    # Fix: fingerprint key sysroot files and force `make clean` when the
    # fingerprint changes.
    sysroot_check = (
        f"_sr_hash=$(cat "
        f"{config.DOCKER_SYSROOT_PATH}/lib/libposix.a "
        f"{config.DOCKER_SYSROOT_PATH}/lib/user.ld "
        f'2>/dev/null | md5sum | cut -d" " -f1); '
        f"_stored=$(cat {config.DOCKER_WORKSPACE_PATH}/.sysroot-hash 2>/dev/null || true); "
        f'if [ "$_sr_hash" != "$_stored" ]; then '
        f'echo "Sysroot changed -- forcing clean rebuild"; '
        f"make -f Makefile.nanvix clean 2>/dev/null || true; "
        f"rm -f {config.DOCKER_WORKSPACE_PATH}/.nanvix-configured; "
        f"fi; "
        f'echo "$_sr_hash" > {config.DOCKER_WORKSPACE_PATH}/.sysroot-hash'
    )

    shell_cmd = (
        f"{sync} && cd {config.DOCKER_WORKSPACE_PATH} && "
        f"{sysroot_check} && "
        f"{_generate_setup_local_cmd()} && "
        f"{_args.to_string()} && {strip_build}"
    )

    if install_destdir is not None:
        targets = [
            "install",
            f"DESTDIR={config.DOCKER_WORKSPACE_PATH}/_install_staging",
        ]
        _args = dataclasses.replace(_args, targets=targets)
        try:
            rel_dest = install_destdir.relative_to(workspace).as_posix()
        except ValueError:
            rel_dest = install_destdir.name

        # Strip the installed binary too so the install cache is lean.
        install_bin = (
            f"{config.DOCKER_WORKSPACE_PATH}/_install_staging"
            f"{_args.install_prefix}/bin/{config.python_binary()}"
        )
        strip_install = (
            f'[ -x "{strip_bin}" ] && [ -f "{install_bin}" ] && '
            f'"{strip_bin}" --strip-all "{install_bin}" && '
            f'echo "Stripped installed {config.python_binary()}"'
        )

        install_copy = (
            f"rm -rf /mnt/host-workspace/{rel_dest} && "
            f"mkdir -p /mnt/host-workspace/{rel_dest} && "
            f"cp -a {config.DOCKER_WORKSPACE_PATH}/_install_staging/* "
            f"/mnt/host-workspace/{rel_dest}/"
        )
        shell_cmd += (
            f" && {_args.to_string()} && {strip_install}; rc=$?; "
            f"{copy_back}; {install_copy}; exit $rc"
        )
    else:
        shell_cmd += f"; rc=$?; {copy_back}; exit $rc"

    subprocess.run(
        [*base, "sh", "-c", shell_cmd],
        check=True,
    )


def clean_volume(workspace: Path) -> None:
    """Remove the persistent Docker build volume."""
    volume = _volume_name(workspace)
    subprocess.run(
        ["docker", "volume", "rm", volume],
        capture_output=True,
    )


def _generate_setup_local_cmd() -> str:
    """Shell command to generate Modules/Setup.local inside the container."""
    sysroot = config.DOCKER_SYSROOT_PATH
    ws = config.DOCKER_WORKSPACE_PATH
    return (
        f"printf '%s\\n' "
        f"'# Auto-generated by .nanvix/docker.py -- do not edit manually.' "
        f"'# Statically-linked extension modules for Nanvix builds.' "
        f"'#' "
        f"'# Nanvix OS interface module (snapshot, host-mount).' "
        f"'_nanvix _nanvixmodule.c' "
        f"'# lxml C extension modules (statically linked via pre-built archives).' "
        f"'_lxml_etree lxml_etree_builtin.c -L{sysroot}/lib -llxml_etree -lxslt -lexslt -lxml2 -lz' "
        f"'_lxml_elementpath lxml_elementpath_builtin.c -L{sysroot}/lib -llxml_elementpath -lxml2 -lz' "
        f"> {ws}/Modules/Setup.local"
    )


def _copy_outputs_cmd() -> str:
    """Build shell command to copy build outputs back to host workspace."""
    copies: list[str] = []
    for f in config.DOCKER_OUTPUT_FILES:
        copies.append(
            f"[ -f {config.DOCKER_WORKSPACE_PATH}/{f} ] && "
            f"cp -f {config.DOCKER_WORKSPACE_PATH}/{f} /mnt/host-workspace/{f}"
        )
    return " ; ".join(copies)

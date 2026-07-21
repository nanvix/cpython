# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Isolated Docker mode for case-insensitive host workspaces.

Replaces docker-host.mk and sync-sources.sh. Handles tar-based source
sync, CRLF normalization, named Docker volume management, and container
invocation for configure/build/install only.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from .lib import MakeArgs

if TYPE_CHECKING:
    import src.build as build_mod

import src.config as config


def _workspace_volume_key(path: str) -> str:
    """Normalize equivalent native Windows and WSL workspace paths."""
    forward = path.replace("\\", "/")
    if len(forward) >= 2 and forward[1] == ":":
        drive = forward[0].lower()
        rest = forward[2:].lstrip("/")
        return f"/mnt/{drive}/{rest}".casefold()
    parts = forward.split("/")
    if len(parts) >= 4 and parts[1].casefold() == "mnt" and len(parts[2]) == 1:
        drive = parts[2].lower()
        rest = "/".join(parts[3:])
        return f"/mnt/{drive}/{rest}".casefold()
    return forward


def _workspace_id(workspace: Path) -> str:
    """Generate a deterministic volume suffix from the workspace path."""
    # Use a short hash to match the old cksum-based approach.
    key = _workspace_volume_key(str(workspace.resolve()))
    h = hashlib.md5(key.encode()).hexdigest()[:8]
    return h


def _volume_name(workspace: Path) -> str:
    return f"cpython-nanvix-build-{_workspace_id(workspace)}"


def _volume_aliases(workspace: Path) -> set[str]:
    """Return Docker volume names for native Windows and WSL views of a checkout."""
    current = str(workspace.resolve())
    workspace_paths = {current}
    forward = current.replace("\\", "/")
    if len(forward) >= 2 and forward[1] == ":":
        drive = forward[0].lower()
        workspace_paths.add(f"/mnt/{drive}/{forward[2:].lstrip('/')}")
    else:
        parts = forward.split("/")
        if len(parts) >= 4 and parts[1] == "mnt" and len(parts[2]) == 1:
            workspace_paths.add(f"{parts[2].upper()}:\\" + "\\".join(parts[3:]))
    canonical_paths = {_workspace_volume_key(path) for path in workspace_paths}
    workspace_paths.update(canonical_paths)
    return {
        f"cpython-nanvix-build-{hashlib.md5(path.encode()).hexdigest()[:8]}"
        for path in workspace_paths
    }


def remove_build_volume(workspace: Path) -> None:
    """Remove the persistent isolated build workspace when it exists."""
    if shutil.which("docker") is None:
        return
    for volume in sorted(_volume_aliases(workspace)):
        inspect = subprocess.run(
            ["docker", "volume", "inspect", volume],
            capture_output=True,
            check=False,
        )
        if inspect.returncode == 0:
            subprocess.run(["docker", "volume", "rm", "--force", volume], check=False)


def _docker_mount_source(path: Path) -> str:
    """Render *path* as a Docker bind-mount source.

    Docker's ``-v src:dst[:mode]`` syntax splits fields on ``:``.  On
    Windows, ``Path`` renders drive-letter paths like ``C:\\Users\\foo``,
    whose colon is misread as a field separator -- producing errors such
    as ``invalid mode: /mnt/host-workspace``.  Translate drive-letter
    paths to the ``//c/Users/foo`` form that Docker accepts and which
    contains no colon.  POSIX paths are returned unchanged.
    """
    resolved = path.resolve()
    drive = resolved.drive
    # Drive-letter prefix, e.g. "C:" (UNC drives are longer and skipped).
    if len(drive) == 2 and drive[1] == ":":
        letter = drive[0].lower()
        rest = str(resolved)[len(drive) :].replace("\\", "/").lstrip("/")
        return f"//{letter}/{rest}"
    return str(resolved)


def _docker_run_base(
    workspace: Path,
    args: build_mod.MakeArgs,
    image: str = config.DOCKER_IMAGE,
) -> list[str]:
    """Build the common ``docker run`` prefix."""
    volume = _volume_name(workspace)
    # A fresh Windows named volume is root-owned; the image user must initialize it.
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{volume}:{config.DOCKER_WORKSPACE_PATH}",
        "-v",
        f"{_docker_mount_source(workspace)}:/mnt/host-workspace",
        "-v",
        f"{_docker_mount_source(args.sysroot)}:{config.DOCKER_SYSROOT_PATH}:ro",
        "-v",
        f"{_docker_mount_source(args.buildroot)}:{config.DOCKER_BUILDROOT_PATH}:ro",
        "-w",
        config.DOCKER_WORKSPACE_PATH,
        "-e",
        f"HOME={config.DOCKER_WORKSPACE_PATH}/.nanvix/container-home",
        "-e",
        f"TMPDIR={config.DOCKER_WORKSPACE_PATH}/.nanvix/container-tmp",
    ]
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        command.extend(
            ["-e", f"HOST_UID={os.getuid()}", "-e", f"HOST_GID={os.getgid()}"]
        )
    command.append(image)
    return command


def _restore_owner(path: str, *, recursive: bool = False) -> str:
    option = "-R " if recursive else ""
    return (
        'if [ -n "${HOST_UID:-}" ] && [ -n "${HOST_GID:-}" ]; then '
        f'chown {option}"$HOST_UID:$HOST_GID" {shlex.quote(path)} || true; fi'
    )


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
        f'if [ -f "{build_dir}/{f}" ]; then ' f'sed -i "s/\\r$//" "{build_dir}/{f}"; fi'
        for f in config.DOCKER_CRLF_FILES
    )

    rsync_excludes = " ".join(f"--exclude={e}" for e in config.DOCKER_TAR_EXCLUDES)
    rsync_cmd = f"rsync -a --delete {rsync_excludes} /mnt/host-workspace/ {build_dir}/"
    tar_cmd = (
        f"cd /mnt/host-workspace && tar -cf - {excludes} . | tar -xf - -C {build_dir}"
    )

    return (
        f"if command -v rsync >/dev/null 2>&1; then {rsync_cmd}; "
        f"else {tar_cmd}; fi && {crlf_cmds}"
    )


def docker_build(
    workspace: Path,
    args: MakeArgs,
    *,
    install_destdir: Path | None = None,
) -> None:
    """Run cross-compilation in an isolated Docker workspace.

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
    strip_bin = f"{config.DOCKER_SDK_PATH}/bin/llvm-strip"
    strip_build = (
        f'if [ -x "{strip_bin}" ]; then '
        f"for f in python python{config.EXE}; do "
        f'[ -f "{config.DOCKER_WORKSPACE_PATH}/$f" ] && '
        f'"{strip_bin}" --strip-all "{config.DOCKER_WORKSPACE_PATH}/$f" && '
        f'echo "Stripped $f"; done; fi'
    )

    # Detect configuration, SDK, or dependency changes and force a clean rebuild.
    # Without rsync (unavailable in the minimal Docker image), the tar-based
    # sync does not delete stale build artifacts from the named volume.
    # The runtime sysroot is intentionally excluded because it contributes no
    # target headers or libraries.
    build_signature = shlex.quote(_args.to_string())
    build_inputs_check = (
        f"_input_hash=$( (printf '%s\\n' {build_signature}; "
        f"cat {config.DOCKER_WORKSPACE_PATH}/Makefile.nanvix; "
        f"cat {config.DOCKER_SDK_PATH}/nanvix-sdk.json; "
        f"find {config.DOCKER_BUILDROOT_PATH} -type f -print0 "
        f"| sort -z | xargs -0 sha256sum) | sha256sum | cut -d' ' -f1); "
        f"_stored=$(cat {config.DOCKER_WORKSPACE_PATH}/.build-inputs-hash "
        f"2>/dev/null || true); "
        f'if [ "$_input_hash" != "$_stored" ]; then '
        f'echo "Build configuration, SDK, or buildroot changed -- forcing clean rebuild"; '
        f"make -f Makefile.nanvix clean 2>/dev/null || true; "
        f"rm -f {config.DOCKER_WORKSPACE_PATH}/.nanvix-configured; "
        f"fi; "
        f'echo "$_input_hash" > {config.DOCKER_WORKSPACE_PATH}/.build-inputs-hash'
    )

    shell_cmd = (
        f"set -e; {sync} && cd {config.DOCKER_WORKSPACE_PATH} && "
        f"mkdir -p .nanvix/container-home .nanvix/container-tmp && "
        f"{build_inputs_check} && "
        f"{_generate_setup_local_cmd()} && "
        f"{_args.to_string()} && {strip_build}"
    )

    if install_destdir is not None:
        targets = [
            "install",
            f"DESTDIR={config.DOCKER_WORKSPACE_PATH}/_install_staging",
        ]
        _args = dataclasses.replace(_args, targets=targets)
        # The named Docker volume persists across builds; wipe the
        # install staging dir so stale files (e.g. from a prior
        # INSTALL_PREFIX) don't leak into the tarball.
        clean_install_staging = (
            f"rm -rf {config.DOCKER_WORKSPACE_PATH}/_install_staging"
        )
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
            f'if [ -x "{strip_bin}" ] && [ -f "{install_bin}" ]; then '
            f'"{strip_bin}" --strip-all "{install_bin}" && '
            f'echo "Stripped installed {config.python_binary()}"; fi'
        )

        host_dest = f"/mnt/host-workspace/{rel_dest}"
        host_temporary = f"{host_dest}.tmp"
        host_backup = f"{host_dest}.old"
        install_copy = (
            f"{{ rm -rf {shlex.quote(host_temporary)} {shlex.quote(host_backup)}; "
            f"mkdir -p {shlex.quote(host_temporary)}; "
            f"cp -a {config.DOCKER_WORKSPACE_PATH}/_install_staging/. "
            f"{shlex.quote(host_temporary)}/; "
            f"{_restore_owner(host_temporary, recursive=True)}; "
            f"if [ -e {shlex.quote(host_dest)} ]; then "
            f"mv {shlex.quote(host_dest)} {shlex.quote(host_backup)}; fi; "
            f"if mv {shlex.quote(host_temporary)} {shlex.quote(host_dest)}; then "
            f"rm -rf {shlex.quote(host_backup)}; else copy_rc=$?; "
            f"if [ -e {shlex.quote(host_backup)} ]; then "
            f"mv {shlex.quote(host_backup)} {shlex.quote(host_dest)}; fi; "
            f"exit $copy_rc; fi; }}"
        )
        shell_cmd += (
            f" && {clean_install_staging} && {_args.to_string()}"
            f" && {strip_install} && {copy_back} && {install_copy}"
        )
    else:
        shell_cmd += f" && {copy_back}"

    subprocess.run(
        [*base, "sh", "-c", shell_cmd],
        check=True,
    )


def _generate_setup_local_cmd() -> str:
    """Shell command to generate Modules/Setup.local inside the container."""
    buildroot = config.DOCKER_BUILDROOT_PATH
    ws = config.DOCKER_WORKSPACE_PATH
    return (
        f"printf '%s\\n' "
        f"'# Auto-generated by .nanvix/docker.py -- do not edit manually.' "
        f"'' "
        f"'# Statically-linked extension modules for Nanvix builds.' "
        f"'*static*' "
        f"'# Nanvix OS interface module (snapshot, host-mount).' "
        f"'_nanvix _nanvixmodule.c' "
        f"'# lxml C extension modules (statically linked via pre-built archives).' "
        f"'_lxml_etree lxml_etree_builtin.c -L{buildroot}/lib -llxml_etree -lxslt -lexslt -lxml2 -lz' "
        f"'_lxml_elementpath lxml_elementpath_builtin.c -L{buildroot}/lib -llxml_elementpath -lxml2 -lz' "
        f"'' "
        f"'# Phase 0 of the .a -> .so migration: array as a proof-of-concept shared module.' "
        f"'# Listed before Setup.stdlib static declaration so makesetup first rule wins.' "
        f"'*shared*' "
        f"'array arraymodule.c' "
        f"> {ws}/Modules/Setup.local"
    )


def _copy_outputs_cmd() -> str:
    """Build shell command to copy build outputs back to host workspace."""
    copies: list[str] = []
    for f in config.DOCKER_OUTPUT_FILES:
        source = f"{config.DOCKER_WORKSPACE_PATH}/{f}"
        destination = f"/mnt/host-workspace/{f}"
        copies.append(
            f"if [ -f {shlex.quote(source)} ] && [ ! -d {shlex.quote(destination)} ]; "
            f"then cp -f {shlex.quote(source)} {shlex.quote(destination)}; "
            f"{_restore_owner(destination)}; fi"
        )
    return "{ " + "; ".join(copies) + "; }"

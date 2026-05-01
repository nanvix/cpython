# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Docker host mode for Windows cross-compilation.

Replaces docker-host.mk and sync-sources.sh. Handles tar-based source
sync, CRLF normalization, named Docker volume management, and container
invocation for configure/build/install only.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parent))
from _loader import load_sibling

config = load_sibling("config", __file__)


def _workspace_id(workspace: Path) -> str:
    """Generate a deterministic volume suffix from the workspace path."""
    # Use a short hash to match the old cksum-based approach.
    h = hashlib.md5(str(workspace.resolve()).encode()).hexdigest()[:8]
    return h


def _volume_name(workspace: Path) -> str:
    return f"cpython-nanvix-build-{_workspace_id(workspace)}"


def _host_sysroot_path(workspace: Path, nanvix_home: Path) -> Path:
    """Return a host-mountable NanVix sysroot path."""
    def valid_sysroot(path: Path) -> bool:
        return (
            path.is_dir()
            and (path / "lib" / "libposix.a").is_file()
            and (path / "lib" / "user.ld").is_file()
        )

    nanvix_home = Path(nanvix_home)
    if valid_sysroot(nanvix_home):
        return nanvix_home

    for candidate in (
        Path(workspace) / ".nanvix" / "sysroot",
        Path(workspace) / ".nanvix" / "extracted" / "nanvix",
    ):
        if valid_sysroot(candidate):
            return candidate

    return nanvix_home


def _docker_run_base(
    workspace: Path,
    nanvix_home: Path,
    image: str = config.DOCKER_IMAGE,
) -> list[str]:
    """Build the common ``docker run`` prefix."""
    volume = _volume_name(workspace)
    # Run as root inside ephemeral containers — matches the reusable CI
    # workflow and avoids permission issues with named volumes on CI runners.
    uid = 0
    gid = 0
    host_sysroot = _host_sysroot_path(workspace, nanvix_home)
    return [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{uid}:{gid}",
        "-v",
        f"{volume}:{config.DOCKER_WORKSPACE_PATH}",
        "-v",
        f"{workspace}:/mnt/host-workspace",
        "-v",
        f"{host_sysroot.resolve()}:{config.DOCKER_SYSROOT_PATH}:ro",
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
    rsync_cmd = (
        f"rsync -a --delete {rsync_excludes} " f"/mnt/host-workspace/ {build_dir}/"
    )
    tar_cmd = (
        f"cd /mnt/host-workspace && "
        f"tar -cf - {excludes} . | tar -xf - -C {build_dir}"
    )

    return (
        f"if command -v rsync >/dev/null 2>&1; then {rsync_cmd}; "
        f"else {tar_cmd}; fi && "
        f"{crlf_cmds}"
    )


def docker_build_lxml_deps(
    workspace: Path,
    nanvix_home: Path,
    *,
    platform: str = config.DEFAULT_PLATFORM,
    process_mode: str = config.DEFAULT_PROCESS_MODE,
    memory_size: str = config.DEFAULT_MEMORY_SIZE,
    install_prefix: str = config.DEFAULT_INSTALL_PREFIX,
) -> None:
    """Build lxml + libxml2 + libxslt static archives inside Docker.

    Runs as a separate Docker invocation with the sysroot mounted
    **writable** so that ``nanvix-port/build-lxml-deps.sh`` can install
    archives into ``nanvix_home/lib/`` on the host.  After this call the
    archives are available on the host, so the main ``docker_build()``
    invocation (which mounts the sysroot read-only) can link against them.

    The build sequence inside the container is:
      1. Sync workspace sources (needed for build scripts and headers).
      2. ``make configure`` — generates ``pyconfig.h``, which the lxml
         C-extension compile step requires.
      3. ``bash nanvix-port/build-lxml-deps.sh`` — compiles libxml2,
         libxslt, lxml archives and stages the Python package.

    Skips immediately when all :data:`lxml.LXML_ARCHIVES` are already
    present in *nanvix_home*/lib (idempotent across repeated builds).

    Args:
        workspace:   Host-side repository root (Windows or Linux path).
        nanvix_home: Host-side Nanvix sysroot directory.  Mounted into
                     the container as ``/mnt/sysroot`` with write access
                     so archives can be persisted to the host.
        platform:    Make ``PLATFORM`` variable (passed to configure).
        process_mode: Make ``PROCESS_MODE`` variable.
        memory_size: Make ``MEMORY_SIZE`` variable.
        install_prefix: Make ``INSTALL_PREFIX`` variable.
    """
    nanvix_home = _host_sysroot_path(workspace, nanvix_home)
    lxml_mod = load_sibling("lxml", __file__)

    if (
        lxml_mod._lxml_archives_present(nanvix_home)
        and lxml_mod._staged_lxml_present(workspace)
    ):
        print("[lxml] lxml archives and staged package already present; skipping Docker prebuild.")
        return

    print(f"[lxml] Building lxml deps inside Docker (sysroot={nanvix_home})")

    volume = _volume_name(workspace)
    uid = 0
    gid = 0

    # Mount sysroot writable (no :ro) so build-lxml-deps.sh can write archives.
    base = [
        "docker", "run", "--rm",
        "--user", f"{uid}:{gid}",
        "-v", f"{volume}:{config.DOCKER_WORKSPACE_PATH}",
        "-v", f"{workspace}:/mnt/host-workspace",
        "-v", f"{nanvix_home.resolve()}:{config.DOCKER_SYSROOT_PATH}",
        "-w", config.DOCKER_WORKSPACE_PATH,
        "-e", "HOME=/tmp",
        config.DOCKER_IMAGE,
    ]

    sync = sync_sources(workspace)

    # make configure generates pyconfig.h in the Docker volume workspace.
    # build-lxml-deps.sh requires pyconfig.h to compile lxml C extensions.
    configure_cmd = _inner_make_cmd(
        "configure",
        platform=platform,
        process_mode=process_mode,
        memory_size=memory_size,
        install_prefix=install_prefix,
        release=False,
    )

    # Pass NANVIX_HOME and NANVIX_TOOLCHAIN explicitly so the script does
    # not fall back to reading env.json (which is a host-side file).
    build_deps_cmd = (
        f"NANVIX_HOME={config.DOCKER_SYSROOT_PATH} "
        f"NANVIX_TOOLCHAIN={config.DOCKER_TOOLCHAIN_PATH} "
        f"bash {config.DOCKER_WORKSPACE_PATH}/nanvix-port/build-lxml-deps.sh"
    )
    copy_lxml_deps = (
        f'test -f /mnt/host-workspace/Makefile.nanvix && '
        f"rm -rf /mnt/host-workspace/.nanvix/lxml-deps && "
        f"mkdir -p /mnt/host-workspace/.nanvix && "
        f"cp -a {config.DOCKER_WORKSPACE_PATH}/.nanvix/lxml-deps "
        f"/mnt/host-workspace/.nanvix/lxml-deps && "
        f"chmod -R a+rwX /mnt/host-workspace/.nanvix/lxml-deps"
    )

    shell_cmd = (
        f"{sync} && cd {config.DOCKER_WORKSPACE_PATH} && "
        f"{configure_cmd} && {build_deps_cmd} && {copy_lxml_deps}"
    )

    subprocess.run([*base, "sh", "-c", shell_cmd], check=True)


def _purge_stale_setup_local_cmd() -> str:
    """Return a shell snippet that removes a stale lxml-generated
    Modules/Setup.local from the Docker workspace volume when the host
    copy has already been deleted.

    The tar-based sync fallback (used when rsync is unavailable) does
    not delete files from the Docker volume that have been removed on
    the host.  This command fills that gap for the specific case of
    our generated Setup.local.

    Safe heuristic (mirrors :func:`lxml._is_lxml_generated_setup_local`):
    - ``_sl_active``: all non-blank, non-comment lines in the file.
    - ``_sl_lxml``:   lines starting with ``_lxml_etree`` or
      ``_lxml_elementpath``.
    - Remove the file only when ``_sl_active`` is non-empty AND equals
      ``_sl_lxml`` (i.e. every active entry is one of our lxml lines).
    - A Setup.local with any unrelated active entry is never removed.

    The command is a no-op when the host workspace still has its own
    Setup.local (rsync already handled the sync in that case).
    """
    sl_host = "/mnt/host-workspace/Modules/Setup.local"
    sl_work = f"{config.DOCKER_WORKSPACE_PATH}/Modules/Setup.local"
    # Shell single-quotes protect the regex patterns from variable expansion.
    # $() and $varname are intentional shell syntax, not Python interpolation.
    return (
        f'if [ ! -f "{sl_host}" ] && [ -f "{sl_work}" ]; then '
        f'_sl_active=$(grep -vE \'^[[:space:]]*(#|$)\' "{sl_work}" 2>/dev/null || true); '
        f'_sl_lxml=$(grep -E \'^_lxml_(etree|elementpath) \' "{sl_work}" 2>/dev/null || true); '
        f'if [ -n "$_sl_active" ] && [ "$_sl_active" = "$_sl_lxml" ]; then '
        f'rm -f "{sl_work}"; '
        f'echo "[lxml] Removed stale generated Modules/Setup.local from Docker workspace"; '
        f'fi; fi'
    )


def docker_build(
    workspace: Path,
    nanvix_home: Path,
    *,
    platform: str = config.DEFAULT_PLATFORM,
    process_mode: str = config.DEFAULT_PROCESS_MODE,
    memory_size: str = config.DEFAULT_MEMORY_SIZE,
    install_prefix: str = config.DEFAULT_INSTALL_PREFIX,
    release: bool = False,
    install_destdir: Path | None = None,
) -> None:
    """Run cross-compilation inside Docker (Windows host mode).

    Syncs sources into a named Docker volume, runs configure+build,
    and copies outputs back to the host workspace.

    If *install_destdir* is provided, also runs ``make install`` inside
    the same container and copies the install tree to the host.  This
    avoids a second Docker invocation during testing.
    """
    base = _docker_run_base(workspace, nanvix_home)
    sync = sync_sources(workspace)
    inner_make = _inner_make_cmd(
        "build",
        platform=platform,
        process_mode=process_mode,
        memory_size=memory_size,
        install_prefix=install_prefix,
        release=release,
    )
    copy_back = _copy_outputs_cmd(workspace)

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
        f"{_purge_stale_setup_local_cmd()} && "
        f"{sysroot_check} && {inner_make} && {strip_build}"
    )

    if install_destdir is not None:
        install_make = _inner_make_cmd(
            f"install DESTDIR={config.DOCKER_WORKSPACE_PATH}/_install_staging",
            platform=platform,
            process_mode=process_mode,
            memory_size=memory_size,
            install_prefix=install_prefix,
            release=release,
        )
        try:
            rel_dest = install_destdir.relative_to(workspace).as_posix()
        except ValueError:
            rel_dest = install_destdir.name

        # Strip the installed binary too so the install cache is lean.
        install_bin = (
            f"{config.DOCKER_WORKSPACE_PATH}/_install_staging"
            f"{install_prefix}/bin/{config.python_binary()}"
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
            f" && {install_make} && {strip_install}; rc=$?; "
            f"{copy_back}; {install_copy}; exit $rc"
        )
    else:
        shell_cmd += f"; rc=$?; {copy_back}; exit $rc"

    subprocess.run(
        [*base, "sh", "-c", shell_cmd],
        check=True,
    )


def docker_install(
    workspace: Path,
    nanvix_home: Path,
    destdir: Path,
    *,
    platform: str = config.DEFAULT_PLATFORM,
    process_mode: str = config.DEFAULT_PROCESS_MODE,
    memory_size: str = config.DEFAULT_MEMORY_SIZE,
    install_prefix: str = config.DEFAULT_INSTALL_PREFIX,
    release: bool = False,
) -> None:
    """Run make install inside Docker (Windows host mode)."""
    base = _docker_run_base(workspace, nanvix_home)
    sync = sync_sources(workspace)
    inner_make = _inner_make_cmd(
        f"install DESTDIR={config.DOCKER_WORKSPACE_PATH}/_install_staging",
        platform=platform,
        process_mode=process_mode,
        memory_size=memory_size,
        install_prefix=install_prefix,
        release=release,
    )

    # Compute relative path so nested destdirs (e.g. .nanvix/_test_staging)
    # are preserved correctly on the host.
    try:
        rel_dest = destdir.relative_to(workspace).as_posix()
    except ValueError:
        rel_dest = destdir.name

    # Copy install staging back to host, stripping the binary first.
    strip_bin = f"{config.DOCKER_TOOLCHAIN_PATH}/bin/{config.TOOLCHAIN_TRIPLET}-strip"
    install_bin = (
        f"{config.DOCKER_WORKSPACE_PATH}/_install_staging"
        f"{install_prefix}/bin/{config.python_binary()}"
    )
    strip_cmd = (
        f'[ -x "{strip_bin}" ] && [ -f "{install_bin}" ] && '
        f'"{strip_bin}" --strip-all "{install_bin}" || true'
    )
    shell_cmd = (
        f"{sync} && cd {config.DOCKER_WORKSPACE_PATH} && {inner_make}; rc=$?; "
        f"{strip_cmd}; "
        f"if [ -d {config.DOCKER_WORKSPACE_PATH}/_install_staging ]; then "
        f"mkdir -p /mnt/host-workspace/{rel_dest} && "
        f"cp -a {config.DOCKER_WORKSPACE_PATH}/_install_staging/* /mnt/host-workspace/{rel_dest}/; fi; "
        f"exit $rc"
    )

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


def _inner_make_cmd(
    targets: str,
    *,
    platform: str,
    process_mode: str,
    memory_size: str,
    install_prefix: str,
    release: bool,
) -> str:
    """Build the inner make command string for execution inside Docker."""
    release_str = "yes" if release else "no"
    return (
        f"make -f Makefile.nanvix "
        f"CONFIG_NANVIX=y "
        f"NANVIX_HOME={config.DOCKER_SYSROOT_PATH} "
        f"NANVIX_TOOLCHAIN={config.DOCKER_TOOLCHAIN_PATH} "
        f"PLATFORM={platform} "
        f"PROCESS_MODE={process_mode} "
        f"MEMORY_SIZE={memory_size} "
        f"INSTALL_PREFIX={install_prefix} "
        f"NANVIX_RELEASE={release_str} "
        f"{targets}"
    )


def _copy_outputs_cmd(workspace: Path) -> str:
    """Build shell command to copy build outputs back to host workspace."""
    copies: list[str] = []
    for f in config.DOCKER_OUTPUT_FILES:
        copies.append(
            f"[ -f {config.DOCKER_WORKSPACE_PATH}/{f} ] && "
            f"cp -f {config.DOCKER_WORKSPACE_PATH}/{f} /mnt/host-workspace/{f}"
        )
    return " ; ".join(copies)

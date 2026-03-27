# CPython Port for Nanvix

> **TL;DR:** This is a port of the CPython interpreter for the Nanvix operating system. Jump to [Quick Start](#quick-start) to get started immediately.

---

## Overview

This document describes the port of [CPython](https://www.python.org/) interpreter for the [Nanvix](https://github.com/nanvix/nanvix) operating system. This port enables Python to run on Nanvix, a POSIX-compatible educational operating system.

| Property | Value |
|----------|-------|
| **Base Version** | CPython 3.12.x |
| **Target Platform** | Nanvix (i686) |
| **Build System** | GNU Make (wrapping autoconf), orchestrated by `nanvix-zutil` |

**What's included:**
- ✅ Cross-compilation support for Nanvix
- ✅ Static library build (`libpython3.12.a`)
- ✅ Python interpreter executable (`python.elf`)
- ✅ `nanvix-zutil` build orchestration
- ✅ CI/CD integration with versioned releases

**Dependencies:**
- zlib (compression support)
- bzip2 (compression support)
- OpenSSL (cryptography support)
- libffi (foreign function interface)
- SQLite (database support)

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Building](#building)
4. [Testing](#testing)
5. [Changes Summary](#changes-summary)
6. [Known Limitations](#known-limitations)
7. [CI/CD](#cicd)

---

## Quick Start

For experienced users who want to build quickly:

```bash
# 1. Install nanvix-zutil
pip install nanvix-zutil  # or install from the latest wheel

# 2. Setup (downloads sysroot + all 5 dependencies automatically)
nanvix-zutil setup

# 3. Build
nanvix-zutil build

# 4. Test
nanvix-zutil test

# 5. Package a release tarball
nanvix-zutil release
```

Continue reading for detailed instructions.

---

## Prerequisites

You need the following components to build CPython for Nanvix:

| Component | Description | Default Location |
|-----------|-------------|------------------|
| **Nanvix Toolchain** | i686-nanvix cross-compiler | `/opt/nanvix` |
| **nanvix-zutil** | Build orchestration CLI | Installed via pip |

All other dependencies (sysroot, zlib, bzip2, OpenSSL, libffi, SQLite) are automatically downloaded by `nanvix-zutil setup` based on the `.nanvix/nanvix.toml` manifest.

### Available Platform Configurations

| Platform | Process Mode | Artifact Pattern |
|----------|--------------|------------------|
| hyperlight | multi-process | `hyperlight.*multi-process` |
| hyperlight | single-process | `hyperlight.*single-process` |
| microvm | single-process | `microvm.*single-process` |
| microvm | multi-process | `microvm.*multi-process` |
| microvm | standalone | `microvm.*standalone` |

---

## Building

### Using nanvix-zutil (Recommended)

```bash
# Setup downloads Nanvix sysroot + all 5 dependency libraries
nanvix-zutil setup

# Build cross-compiles python.elf
nanvix-zutil build
```

### Using the Makefile Directly

For advanced users who manage dependencies manually:

```bash
export NANVIX_TOOLCHAIN=/path/to/toolchain
export NANVIX_HOME=/path/to/nanvix/sysroot
make -f Makefile.nanvix CONFIG_NANVIX=y all
```

> **Note:** The sysroot (`NANVIX_HOME`) must contain `lib/libposix.a`, `lib/libz.a`, `lib/libsqlite3.a`, `lib/libssl.a`, `lib/libcrypto.a`, `lib/libbz2.a`, `lib/libffi.a`, and `lib/user.ld` from a Nanvix build.

**Docker Fallback Behavior:**
- If `NANVIX_TOOLCHAIN` points to a valid toolchain, it uses the native compiler
- If the native toolchain is not found, it automatically uses Docker if available
- Use `CONFIG_NANVIX_DOCKER=y` to force Docker usage even when native toolchain exists

### Build Outputs

| File | Description |
|------|-------------|
| `python.elf` | Python interpreter executable |
| `libpython3.12.a` | Python static library |

---

## Testing

> **Important:** Tests must be run through the Nanvix daemon (`nanvixd.elf`).

```bash
# Run all tests via nanvix-zutil
nanvix-zutil test

# Or via Makefile directly
make -f Makefile.nanvix CONFIG_NANVIX=y NANVIX_HOME=/path/to/nanvix test
```

### Test Coverage

The test target verifies:
- Python interpreter starts correctly
- Basic print functionality works
- Arithmetic operations work
- Core module imports work (e.g., `sys`)

---

## Changes Summary

The following changes were made to support Nanvix.

### Build System Changes

| Change | Description |
|--------|-------------|
| New Makefile | Added `Makefile.nanvix` for Nanvix cross-compilation |
| ZScript integration | `.nanvix/z.py` orchestrates build via `nanvix-zutil` CLI |
| Manifest | `.nanvix/nanvix.toml` declares all 5 dependencies |
| Cross-compilation | Uses `CONFIG_NANVIX=y` option to enable Nanvix build |
| Docker support | Automatic Docker fallback when native toolchain not available |
| Linker flags | Added Nanvix-specific flags (`-T user.ld -static`) |

### New Files

| File | Purpose |
|------|---------|
| `Makefile.nanvix` | Standalone Makefile for Nanvix cross-compilation |
| `.nanvix/nanvix.toml` | Dependency manifest (zlib, bzip2, openssl, libffi, sqlite) |
| `.nanvix/z.py` | ZScript build orchestration |
| `NANVIX.md` | This documentation file |
| `.github/workflows/nanvix-ci.yml` | CI workflow for automated builds |
| `.github/workflows/prune-releases.yml` | Release retention policy (90-day) |

---

## Known Limitations

| Limitation | Impact |
|------------|--------|
| **No shared libraries** | Only static library (`libpython3.12.a`) is built |
| **No pip** | Package installer not available (`--with-ensurepip=no`) |
| **No IPv6** | IPv6 networking disabled |
| **No test modules** | Test suite modules not built |
| **Static linking only** | All executables are statically linked |
| **Limited I/O** | Some file and network operations may be limited |

---

## CI/CD

The GitHub Actions workflow at `.github/workflows/nanvix-ci.yml` automates building, testing, and releasing CPython for Nanvix using the `nanvix-zutil` CLI.

### Trigger Events

| Event | Description |
|-------|-------------|
| Push to `nanvix/**` | Any push to Nanvix branches |
| PR to `nanvix/**` | Pull requests targeting Nanvix branches |
| Daily schedule | Runs at midnight UTC |
| Manual dispatch | Can be triggered manually |
| Repository dispatch | Triggered by dependency releases (sqlite, openssl, bzip2, libffi) |

### Build Matrix

The CI runs on 6 different platform/process-mode configurations in parallel with `fail-fast: false`:

| Platform | Process Mode |
|----------|--------------|
| hyperlight | multi-process, single-process, standalone |
| microvm | multi-process, single-process, standalone |

### Dependency Management

Dependencies are managed automatically via `nanvix-zutil setup`, which reads `.nanvix/nanvix.toml` and downloads matching releases of all 5 dependency libraries from their respective `nanvix/*` repositories.

### Release Strategy

Releases use dual tags:
- **Semver tag:** `{cpython_version}-nanvix-{nanvix_version}` (marked `--latest`)
- **Commitish tag:** `{cpython_version}-nanvix-{nanvix_sha}` (for commit-based resolution)

A `nanvix.lock` lockfile is included in every release, capturing the full dependency tree.

---

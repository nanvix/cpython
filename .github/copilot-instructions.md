# CPython NanVix Port — Copilot Instructions

## Build Environment

### CRITICAL: Do NOT build from Windows-mounted paths

CPython's `configure` runs ~500 small test programs. Each compiles and links against
46MB `libposix.a`. On Docker-for-Windows with volume mounts (`/mnt/c/...` or `/mnt/a/...`),
the I/O overhead makes configure take **60+ minutes** and frequently fails.

**Correct approach:** Clone into WSL2 native filesystem, then build from there:
```bash
# Inside WSL2:
cp -r /mnt/a/Repos/NanVix-CPython /tmp/cpython-build
cd /tmp/cpython-build
./z setup && ./z build
```

Previous successful build (March 19, 2026) used `/tmp/cpython-build/` on WSL2 ext4.
See `A:\Work\NanVix\What-We-Did-CPython.md` for the full build journey.

### CRITICAL: Pin libposix.a After `./z setup` (March 25, 2026)

`./z setup` downloads the **latest** NanVix sysroot from GitHub releases. If the
downloaded `libposix.a` is newer than the kernel/nanvixd at `A:\Repos\NanVix\bin\`,
the resulting binary will fail silently (zero syscalls, no output, exits 0).

**After `./z setup`, always pin libposix.a:**
```bash
cp /mnt/a/Repos/NanVix/registry-extract/lib/libposix.a \
   .nanvix/extracted/nanvix/lib/libposix.a
```

See `C:\Users\modanish\.copilot\research\NanVix-CPython\pptx-build-root-cause.md`
for the full investigation (LLM council, 8 hypotheses tested, runtime traces).

### env.sh Hardcodes NANVIX_HOME Path

`.nanvix/env.sh` stores the **absolute path** to the sysroot from the original
repo checkout. When building from a `/tmp/` copy, Docker still mounts the
ORIGINAL repo's sysroot. Pin libposix in the ORIGINAL path, not the copy.

### Known Cross-Compilation Issues (March 24, 2026)

When building via `make -f Makefile.nanvix` (as opposed to `./z build`), three issues arise:

1. **CRLF in config.site** — Windows git checkout produces `\r\n` in `nanvix-port/config.site`.
   The `\r` contaminates autoconf cache values (e.g., `ac_cv_sizeof_void_p=4\r`), causing
   `config.status` to fail pyconfig.h substitutions. Fix: `sed -i 's/\r$//' nanvix-port/config.site`

2. **`-std=c11` kills POSIX visibility** — CPython's `configure.ac` unconditionally adds
   `-std=c11` to `CFLAGS_NODIST` for GCC. This sets `__STRICT_ANSI__` which causes newlib
   to `#undef __POSIX_VISIBLE`, hiding `fdopen()`/`fileno()`. Fix: post-configure
   `sed -i 's/-std=c11/-std=gnu11/g' Makefile` (or patch `configure` line 9507 directly).

3. **pyconfig.h SIZEOF_* not substituted** — Even with config.site fixes, `config.status`
   sometimes fails to write `#define SIZEOF_VOID_P 4` into pyconfig.h during cross-compilation.
   Fix: post-configure `sed` to replace `#undef SIZEOF_*` with `#define SIZEOF_* <value>`.

These issues do NOT affect CI (which runs natively inside the Docker container).

### Pre-built Artifacts Already Exist

The following artifacts are already built and available at `A:\Repos\NanVix\bin\`:
- `python.elf` (9.11 MB) — CPython 3.12.3 for NanVix (67 built-in modules)
- `cpython-ramfs.img` (35.62 MB) — FAT32 stdlib image (469 trimmed .py files)
- `nanvixd.exe` (7.47 MB) — NanVix daemon
- `kernel.elf` (10.48 MB) — NanVix kernel
- `mkramfs.exe` (261 KB) — FAT32 image builder

**Do not rebuild these unless specifically asked.** Use them for testing.

### Configure Workarounds (already in Makefile.nanvix)

| Problem | Fix (already applied) |
|---------|----------------------|
| `i686-nanvix` not recognized | `--build=x86_64-pc-linux-gnux32 --host=i686-nanvix` |
| Can't link test executables | `-T user.ld -static` in LDFLAGS |
| `SA_RESTART` undeclared | `-DSA_RESTART=0x4` in CFLAGS |
| Cross-compile needs build Python | `--with-build-python` from toolchain |
| CRLF line endings (Windows checkout) | Run `sed -i 's/\r$//' configure config.sub config.guess install-sh aclocal.m4` before Docker build |

### Docker Image

```bash
docker pull nanvix/toolchain:latest-minimal
```

## Script Execution (Stdin Piping)

Python scripts are executed via stdin piping — NOT via `-c` on the cmdline
(NanVix has a 255-byte cmdline limit and splits on spaces).

```bash
echo "print('Hello')" | nanvixd.exe -bin-dir bin -ramfs cpython-ramfs.img \
  -- python.elf "-S -B -c exec(__import__('sys').stdin.read());PYTHONHOME=/sysroot"
```

Key facts:
- The `;` in the argument string is NanVix's separator between argv and env vars
- `exec(__import__('sys').stdin.read())` has NO spaces — safe from NanVix space-splitting
- stdout = clean script output, stderr = kernel traces
- Exit codes propagate: `sys.exit(42)` → nanvixd exits 42
- Verified with 6/6 test types: spaces, multiline, quotes, special chars, imports, large scripts

## Stdlib Trimming

The `ramfs` Makefile target trims 11 module groups from the stdlib:
- `idlelib`, `tkinter`, `turtledemo` — GUI (no display on NanVix)
- `ensurepip` — pip (no network/subprocess)
- `lib2to3`, `distutils` — build tools
- `unittest` — test framework
- `config-3.12-*` — C extension build config
- `pydoc_data` — docs
- `__pycache__`, `.pyc/.pyo` — bytecode cache
- `test/tests` — test suites

Result: 108 MB → 34 MB (~69% reduction, ~469 files remaining).

## Research Files

Detailed research is stored at:
- `C:\Users\modanish\.copilot\research\sandbox-architecture\07-cpython-on-nanvix.md`
- `C:\Users\modanish\.copilot\research\nanvix-cpython\council-space-support.md`
- `C:\Users\modanish\.copilot\research\NanVix-CPython\python-pptx-enablement-plan.md` — Plan for enabling python-pptx (lxml + Pillow static linking via nanvix-python pattern)
- `C:\Users\modanish\.copilot\research\NanVix-CPython\pptx-build-root-cause.md` — Root cause investigation: libposix.a mismatch, LLM council analysis, 8 hypotheses tested
- `A:\Work\NanVix\What-We-Did-CPython.md`
- `A:\Work\NanVix\code-review-findings.md`
- `A:\Work\NanVix\council-review-364dc9152a7.md` — LLM council review of commit 364dc9152a7 (config.site trimming, stubs.c, build.sh issues)
- `A:\Work\NanVix\handoff-python-pptx-build.md` — Current handoff state for python-pptx build
- `A:\Work\NanVix\mxc-architecture.md`
- `A:\Work\NanVix\windows-build-instructions.md`
- `A:\Work\NanVix\patches\` — Ready-to-use patch files for lxml/Pillow static builtin integration
- `A:\Work\NanVix\build-configs\` — Makefile.nanvix templates for libxml2, libxslt, lxml cross-compilation

## Related Repos

| Repo | Path | What |
|------|------|------|
| NanVix (kernel) | `A:\Repos\NanVix` | Microkernel + nanvixd + mkramfs |
| MXC (sandbox) | `A:\Repos\MXC` | wxc-exec.exe with NanVix backend |
| CPython (this repo) | `A:\Repos\NanVix-CPython` | CPython 3.12.3 fork for NanVix |

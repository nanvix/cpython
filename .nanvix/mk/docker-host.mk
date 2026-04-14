# docker-host.mk - Windows Docker host-side re-invocation
#
# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.
#
# When DOCKER_HOST_MODE=windows is passed, all build targets are re-invoked
# inside a Docker container with tar-based source copying to avoid the
# Docker Desktop bind mount I/O penalty.
#
# The inner make invocation runs without DOCKER_HOST_MODE, so it uses the
# native toolchain inside the container (no Docker wrapping).

ifdef DOCKER_HOST_MODE

include $(dir $(lastword $(MAKEFILE_LIST)))defaults.mk

# Docker paths for the inner build
_DHM_BUILD_DIR  := /tmp/build
_DHM_WS_MOUNT   := /mnt/workspace
_DHM_SYS_MOUNT  := /mnt/sysroot

# Named Docker volume that persists the build tree across container runs,
# so that Make's timestamp-based dependency tracking can skip up-to-date
# targets on subsequent builds instead of rebuilding from scratch.
# The volume name is derived from the workspace path, sanitised for Docker
# volume naming rules. On Windows the path may contain spaces and other
# punctuation that Docker volume names do not accept, so normalise common
# problematic characters to hyphens using only Make text functions.
_DHM_EMPTY :=
_DHM_SPACE := $(_DHM_EMPTY) $(_DHM_EMPTY)
_DHM_BAD_CHARS := : \ / ( ) [ ] { } , ; = + & ' " * ? ! # % ^ ~ ` @

# $(call _dhm_sanitise,string,char-list) — replace each char in the list with a hyphen.
_dhm_sanitise = $(if $2,$(call _dhm_sanitise,$(subst $(firstword $2),-,$1),$(wordlist 2,$(words $2),$2)),$1)

_DHM_WORKSPACE_PATH := $(abspath $(CURDIR))
_DHM_WORKSPACE_ID   := $(call _dhm_sanitise,$(subst $(_DHM_SPACE),-,$(_DHM_WORKSPACE_PATH)),$(_DHM_BAD_CHARS))
_DHM_BUILD_VOLUME ?= cpython-nanvix-build-$(_DHM_WORKSPACE_ID)

# Files that need CRLF -> LF normalization for autotools
_DHM_CRLF_FILES := configure config.guess config.sub install-sh \
    Modules/makesetup Modules/Setup \
    Modules/Setup.bootstrap.in Modules/Setup.stdlib.in \
    Modules/config.c.in Modules/ld_so_aix.in \
    Makefile.pre.in pyconfig.h.in aclocal.m4 configure.ac \
    Misc/python.pc.in Misc/python-embed.pc.in \
    Misc/python-config.sh.in Misc/python-config.in

# Tar excludes (saves ~200MB of transfer)
_DHM_TAR_EXCLUDES := --exclude=.git --exclude=.nanvix/venv \
    --exclude=.nanvix/cache --exclude=.nanvix/sysroot \
    --exclude=.nanvix/buildroot --exclude=Doc \
    --exclude=Lib/idlelib --exclude=Lib/tkinter \
    --exclude=Lib/turtledemo --exclude=Lib/ensurepip \
    --exclude=PC --exclude=PCbuild

# Inner make arguments (no DOCKER_HOST_MODE => runs natively inside container)
_DHM_INNER_ARGS := make -f Makefile.nanvix \
    CONFIG_NANVIX=y \
    NANVIX_HOME=$(_DHM_SYS_MOUNT) \
    NANVIX_TOOLCHAIN=/opt/nanvix \
    PLATFORM=$(PLATFORM) \
    PROCESS_MODE=$(PROCESS_MODE) \
    MEMORY_SIZE=$(MEMORY_SIZE) \
    INSTALL_PREFIX=$(INSTALL_PREFIX) \
    NANVIX_RELEASE=$(NANVIX_RELEASE)

# Build output files to copy back to the host workspace
_DHM_OUTPUT_FILES := python python.exe python.elf python.wasm libpython3.12.a

# Path to the source-sync helper (resolved inside the container via the
# workspace bind mount).  The script is piped through sed to strip any
# Windows CRLF line endings before execution.
_DHM_SYNC_SCRIPT := $(_DHM_WS_MOUNT)/.nanvix/mk/sync-sources.sh

# Common docker-run prefix shared by all container invocations.
define _dhm_docker_run
docker run --rm \
    -v $(_DHM_BUILD_VOLUME):$(_DHM_BUILD_DIR) \
    -v $(CURDIR):$(_DHM_WS_MOUNT) \
    -v $(abspath $(NANVIX_HOME)):$(_DHM_SYS_MOUNT):ro \
    -w $(_DHM_BUILD_DIR) \
    -e HOME=/tmp \
    $(NANVIX_DOCKER_IMAGE)
endef

# Common shell preamble: CRLF-strip the sync script, run it, then cd into
# the build directory.
define _dhm_sync_preamble
        sed "s/\r$$//" $(_DHM_SYNC_SCRIPT) > /tmp/_sync.sh && \
        TAR_EXCLUDES="$(_DHM_TAR_EXCLUDES)" \
            sh /tmp/_sync.sh $(_DHM_WS_MOUNT) $(_DHM_BUILD_DIR) $(_DHM_CRLF_FILES) && \
        cd $(_DHM_BUILD_DIR)
endef

# docker-host-run: sync sources into container via a persistent Docker volume,
# run inner make, copy outputs back.
#   $(1) = inner make targets
define docker-host-run
$(call _dhm_docker_run) \
    sh -c '\
        $(_dhm_sync_preamble) && \
        $(_DHM_INNER_ARGS) $(1); rc=$$?; \
        for f in $(_DHM_OUTPUT_FILES); do \
            [ -f $(_DHM_BUILD_DIR)/$$f ] && \
            cp -f $(_DHM_BUILD_DIR)/$$f $(_DHM_WS_MOUNT)/$$f; \
        done; exit $$rc'
endef

# docker-host-test-prepare: like docker-host-run but also copies the test
# staging directory back to the host so that nanvixd can run natively.
#   $(1) = inner make prepare target(s)
define docker-host-test-prepare
$(call _dhm_docker_run) \
    sh -c '\
        $(_dhm_sync_preamble) && \
        $(_DHM_INNER_ARGS) $(1); rc=$$?; \
        for f in $(_DHM_OUTPUT_FILES); do \
            [ -f $(_DHM_BUILD_DIR)/$$f ] && \
            cp -f $(_DHM_BUILD_DIR)/$$f $(_DHM_WS_MOUNT)/$$f; \
        done; \
        rm -rf $(_DHM_WS_MOUNT)/.nanvix/_test_staging; \
        if [ -d $(_DHM_BUILD_DIR)/.nanvix/_test_staging ]; then \
            cp -a $(_DHM_BUILD_DIR)/.nanvix/_test_staging \
                   $(_DHM_WS_MOUNT)/.nanvix/_test_staging; \
            chmod -R a+rwX $(_DHM_WS_MOUNT)/.nanvix/_test_staging; \
        fi; \
        if [ -f /tmp/cpython-rootfs.img ]; then \
            cp -f /tmp/cpython-rootfs.img \
                   $(_DHM_WS_MOUNT)/.nanvix/_test_staging/cpython-rootfs.img; \
        fi; \
        exit $$rc'
endef

# Test staging directory on the host (populated by docker-host-test-prepare)
_DHM_TEST_STAGING := $(CURDIR)/.nanvix/_test_staging

# Determine the Docker-side prepare target.
# For standalone: use the install-only target (no ramfs) — ramfs is built
# natively on the host.  For other modes: use the standard prepare target.
ifeq ($(PROCESS_MODE),standalone)
  _DHM_TEST_PREPARE := test-hello-standalone-install test-regrtest-standalone
else ifeq ($(PROCESS_MODE),single-process)
  _DHM_TEST_PREPARE := test-hello-single-process-prepare test-regrtest-single-process-prepare
else
  _DHM_TEST_PREPARE := test-hello-multi-process-prepare test-regrtest-multi-process-prepare
endif

# Convert a Windows path to a WSL /mnt/ path via wslpath at Make parse time.
_dhm_to_wsl = $(shell wsl wslpath -a '$(subst \,/,$(1))')

# Path to the host-side test runner script (runs natively on Windows and Linux)
_DHM_TEST_RUNNER := $(dir $(lastword $(MAKEFILE_LIST)))test-run-host.py

# Regrtest arguments: pass test list for non-release, non-standalone builds
ifeq ($(PROCESS_MODE),standalone)
  _DHM_REGRTEST_ARGS :=
else ifeq ($(NANVIX_RELEASE),yes)
  _DHM_REGRTEST_ARGS :=
else
  _DHM_REGRTEST_ARGS := $(NANVIX_TEST_LIST)
endif

# Override main targets when running from Windows host
all: build

build:
	$(call docker-host-run,build)

# Test: cross-compile artifacts in Docker, then run nanvixd natively.
#
# Phase 1 (Docker): install + strip — only if staging is not already
#   populated from a previous run.  No rebuild is triggered.
# Phase 1b (native, standalone only): build ramfs with mkramfs.exe.
# Phase 2 (native): execute nanvixd.exe on the host.

# Sentinel file that indicates the staging directory is fully populated.
_DHM_STAGING_READY := $(subst /,\,$(_DHM_TEST_STAGING)\sysroot\bin\python3.12)

# Ramfs image path on the host (standalone mode only).
_DHM_RAMFS_IMG := $(subst /,\,$(_DHM_TEST_STAGING)\cpython-rootfs.img)

# Conditionally run Docker install+strip, then build ramfs natively.
test-prepare:
	@python -c "import sys,os; sys.exit(0 if os.path.isfile(r'$(_DHM_STAGING_READY)') else 1)" || $(MAKE) -f Makefile.nanvix test-prepare-docker CONFIG_NANVIX=$(CONFIG_NANVIX) DOCKER_HOST_MODE=$(DOCKER_HOST_MODE) NANVIX_HOME=$(NANVIX_HOME) NANVIX_TOOLCHAIN=$(NANVIX_TOOLCHAIN) PLATFORM=$(PLATFORM) PROCESS_MODE=$(PROCESS_MODE) MEMORY_SIZE=$(MEMORY_SIZE) INSTALL_PREFIX=$(INSTALL_PREFIX) NANVIX_RELEASE=$(NANVIX_RELEASE)
ifeq ($(PROCESS_MODE),standalone)
	@python -c "import sys,os; sys.exit(0 if os.path.isfile(r'$(_DHM_RAMFS_IMG)') else 1)" || $(MAKE) -f Makefile.nanvix test-prepare-ramfs CONFIG_NANVIX=$(CONFIG_NANVIX) DOCKER_HOST_MODE=$(DOCKER_HOST_MODE) NANVIX_HOME=$(NANVIX_HOME) NANVIX_TOOLCHAIN=$(NANVIX_TOOLCHAIN) PLATFORM=$(PLATFORM) PROCESS_MODE=$(PROCESS_MODE) MEMORY_SIZE=$(MEMORY_SIZE) INSTALL_PREFIX=$(INSTALL_PREFIX) NANVIX_RELEASE=$(NANVIX_RELEASE)
endif

# Docker phase: install + strip (no rebuild, no ramfs).
test-prepare-docker:
	@echo === Phase 1: Installing test artifacts via Docker ===
	$(call docker-host-test-prepare,$(_DHM_TEST_PREPARE))

# Native ramfs build (standalone mode only).
# Runs mkramfs.exe directly on the Windows host.
test-prepare-ramfs:
	@echo === Phase 1b: Building ramfs natively with mkramfs.exe ===
	@python -c "open(r'$(subst /,\,$(_DHM_TEST_STAGING)\sysroot\test_hello.py)','w').write(\"import sys; print('CPYTHON_TEST_HELLO: Hello from Python', sys.version_info[:2])\n\")"
	@python -c "import shutil,os; src=r'$(subst /,\,$(_DHM_TEST_STAGING)\sysroot\lib)'; dst=r'$(subst /,\,$(_DHM_TEST_STAGING)\ramfs-content\sysroot\lib)'; os.makedirs(os.path.dirname(dst),exist_ok=True); shutil.copytree(src,dst,dirs_exist_ok=True)"
	@python -c "import shutil; shutil.copy2(r'$(subst /,\,$(_DHM_TEST_STAGING)\sysroot\test_hello.py)',r'$(subst /,\,$(_DHM_TEST_STAGING)\ramfs-content\sysroot\test_hello.py)')"
	python $(dir $(lastword $(MAKEFILE_LIST)))ramfs-trim-host.py $(subst /,\,$(_DHM_TEST_STAGING)\ramfs-content\sysroot)
	$(subst /,\,$(abspath $(NANVIX_HOME))\bin\mkramfs.exe) -o $(_DHM_RAMFS_IMG) $(subst /,\,$(_DHM_TEST_STAGING)\ramfs-content\sysroot)
	@echo Built ramfs image: $(_DHM_RAMFS_IMG)

test: test-prepare
	@echo "=== Phase 2: Running tests on host ==="
	python $(_DHM_TEST_RUNNER) $(subst /,\,$(_DHM_TEST_STAGING)) $(PROCESS_MODE) $(_DHM_REGRTEST_ARGS)
	@echo "		*** CPython tests PASSED ***"

install:
	$(call docker-host-run,install)

package:
	$(call docker-host-run,package)

# Clean does not need Docker; just remove local artifacts
clean:
	-del /f .nanvix-configured python.elf python.exe 2>nul
	-rmdir /s /q .nanvix\_test_staging 2>nul
	-rmdir /s /q _test_staging 2>nul
	-rmdir /s /q staging 2>nul
	-docker volume rm $(_DHM_BUILD_VOLUME) 2>nul

distclean: clean

.PHONY: all build test install package clean distclean

endif # DOCKER_HOST_MODE

# test-standalone.mk - Standalone deployment mode tests
#
# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.
#
# In standalone mode the runtime filesystem is a ramfs image.  Binaries
# (nanvixd.elf, python3.12, etc.) are NOT included in the ramfs — they are
# passed to nanvixd via -bin-dir.  The ramfs contains only the stdlib and
# test fixtures.
#
# regrtest is used for all modes including standalone.  A /tmp directory is
# created on the ramfs so tempfile.gettempdir() works.  Per-mode test
# exclusions use regrtest --ignore via EXCLUDE_TESTS.

include .nanvix/mk/test-common.mk

# Separate directory for ramfs content (copy of sysroot for ramfs image).
# The main TEST_STAGING/sysroot is left intact so binaries remain available
# for the nanvixd invocation on the host.
TEST_RAMFS_CONTENT = $(TEST_STAGING)/ramfs-content
RAMFS_STAGING = $(TEST_RAMFS_CONTENT)
RAMFS_IMG = /tmp/cpython-rootfs.img
MKRAMFS = $(abspath $(NANVIX_HOME))/bin/mkramfs.elf

# Per-mode test exclusions for standalone (passed to regrtest --ignore).
#   test_filter_dealloc: creates 1M nested filter objects, OOMs the 32MB heap.
#   Threading modules: the 32MB standalone heap cannot allocate thread stacks
#     (each 512KB).  These pass in single-process / multi-process modes.
#     See: https://github.com/nanvix/cpython/issues/371
NANVIX_STANDALONE_EXCLUDE = test_filter_dealloc \
    test_thread test_threading_local test_threadsignals test_threadedtempfile \
    test_queue test_sched test_context \
    test_concurrent_futures

include .nanvix/mk/ramfs.mk

# ramfs-stage: copy the full sysroot and build a trimmed ramfs image via
# ramfs-build (which chains ramfs-trim from ramfs.mk).  The trimmed sysroot
# directory is kept as a template — the hello test uses the trimmed ramfs
# directly, and the batch runner injects per-batch test modules into the
# template before rebuilding the image for each batch.
ramfs-stage: test-stage
	@rm -rf $(TEST_RAMFS_CONTENT)
	@mkdir -p $(TEST_RAMFS_CONTENT)
	@cp -a $(TEST_STAGING)/sysroot $(TEST_RAMFS_CONTENT)/sysroot
	$(MAKE) -f Makefile.nanvix ramfs-build \
		RAMFS_STAGING="$(TEST_RAMFS_CONTENT)" \
		RAMFS_IMG="$(RAMFS_IMG)" \
		CONFIG_NANVIX=$(CONFIG_NANVIX) \
		NANVIX_HOME=$(NANVIX_HOME)

# test-hello-standalone: run hello test via nanvixd with the trimmed ramfs
test-hello-standalone: ramfs-stage
	@cp "$(MKRAMFS)" $(TEST_STAGING)/sysroot/bin/ 2>/dev/null || true
ifdef CONFIG_NANVIX_DOCKER
	$(DOCKER_RUN) sh -c '\
		if [ -x "$(DOCKER_TOOLCHAIN_PATH)/bin/i686-nanvix-strip" ] && [ -f "$(DOCKER_WORKSPACE_PATH)/.nanvix/_test_staging/sysroot/bin/python3.12" ]; then \
			"$(DOCKER_TOOLCHAIN_PATH)/bin/i686-nanvix-strip" --strip-debug \
				"$(DOCKER_WORKSPACE_PATH)/.nanvix/_test_staging/sysroot/bin/python3.12" || true; \
		fi'
else
	$(if $(wildcard $(TOOLCHAIN_PREFIX)/bin/i686-nanvix-strip),\
		$(TOOLCHAIN_PREFIX)/bin/i686-nanvix-strip --strip-debug $(TEST_STAGING)/sysroot/bin/python3.12 2>/dev/null || true)
endif
	@echo "Test: Hello world (standalone)..."
	cd $(TEST_STAGING)/sysroot && \
		{ \
			: > /tmp/cpython_test.log; \
			start_time=$$(date +%s%N); \
			timeout 120 ./bin/nanvixd.elf \
			  -bin-dir ./bin -ramfs $(RAMFS_IMG) $(NANVIXD_EXTRA_ARGS) \
			  -- ./bin/python3.12 \
			  "-B /test_hello.py;PYTHONHOME=/ PYTHONDONTWRITEBYTECODE=1" \
			  < /dev/null > /tmp/cpython_test.log 2>&1; \
			test_status=$$?; \
			end_time=$$(date +%s%N); \
			elapsed=$$(( (end_time - start_time) / 1000000 )); \
			echo "  Execution time: $${elapsed} ms"; \
			if [ $$test_status -ne 0 ]; then \
				echo "  FAIL: Hello test timed out or exited with status $$test_status"; cat /tmp/cpython_test.log; exit 1; \
			fi; \
		}
	$(call validate-hello,/tmp/cpython_test.log)

# test-regrtest-standalone: per-batch ramfs tests via regrtest.
#
# Uses regrtest with /tmp on the ramfs so tempfile.gettempdir() works.
#
# Each batch builds its own ramfs image (~55M) containing the trimmed
# stdlib + batch test modules + cross-import whitelist + infra
# subpackages + data files.  Only the batch's own test_*.py files are
# included (not all 405), keeping images small enough for the 32MB
# heap in the 256MB standalone VM.
# See: https://github.com/nanvix/cpython/issues/369
test-regrtest-standalone: ramfs-stage
	@echo "Test: regrtest ($(words $(NANVIX_TEST_LIST)) modules, standalone)..."
	cd $(TEST_STAGING)/sysroot && \
		RAMFS_TEMPLATE="$(TEST_RAMFS_CONTENT)/sysroot" \
		TEST_SOURCE="$(TEST_STAGING)/sysroot" \
		MKRAMFS="$(MKRAMFS)" \
		NANVIXD_RAMFS="$(RAMFS_IMG)" \
		NANVIXD_BIN_DIR="./bin" \
		EXCLUDE_TESTS="$(NANVIX_STANDALONE_EXCLUDE)" \
		BATCH_SIZE=$(NANVIX_TEST_BATCH_SIZE) \
		NANVIXD_EXTRA_ARGS="$(NANVIXD_EXTRA_ARGS)" \
		$(CURDIR)/.nanvix/run-regrtest-batched.sh $(NANVIX_TEST_LIST)

# Aggregate test target for standalone mode
test: test-hello-standalone test-regrtest-standalone test-cleanup
	@rm -f $(RAMFS_IMG)
	@rm -rf $(TEST_RAMFS_CONTENT)

.PHONY: ramfs-stage test-hello-standalone test-regrtest-standalone test

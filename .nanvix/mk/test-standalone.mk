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
# regrtest is NOT used in standalone mode because it triggers a fatfs panic
# in nanvixd 0.12.x (poll() → OperationNotSupported → byte index out of
# bounds in dir.rs).  Instead, test modules are loaded and run via
# unittest.TextTestRunner through run-standalone-unittest.py, which
# bypasses the problematic regrtest startup code path entirely.

include .nanvix/mk/test-common.mk

# Separate directory for ramfs content (copy of sysroot for ramfs image).
# The main TEST_STAGING/sysroot is left intact so binaries remain available
# for the nanvixd invocation on the host.
TEST_RAMFS_CONTENT = $(TEST_STAGING)/ramfs-content
RAMFS_STAGING = $(TEST_RAMFS_CONTENT)
RAMFS_IMG = /tmp/cpython-rootfs.img
MKRAMFS = $(abspath $(NANVIX_HOME))/bin/mkramfs.elf

# Standalone unittest runner — injected into per-batch ramfs by run-regrtest-batched.sh
UNITTEST_RUNNER = $(CURDIR)/.nanvix/run-standalone-unittest.py

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

# test-regrtest-standalone: per-batch ramfs tests via unittest runner.
#
# Uses run-standalone-unittest.py instead of regrtest because the regrtest
# runner triggers a fatal fatfs panic in nanvixd.  The unittest runner loads
# test modules via unittest.TextTestRunner directly, which works cleanly.
#
# Each batch builds its own ramfs image (~50M) containing the trimmed
# stdlib + ALL top-level test files (for cross-test imports) +
# infrastructure subpackages + only that batch's test subpackage
# directories.  This scales to the full test suite without hitting
# the 256MB VM memory limit.
# See: https://github.com/nanvix/cpython/issues/369
test-regrtest-standalone: ramfs-stage
	@echo "Test: unittest ($(words $(NANVIX_TEST_LIST)) modules, standalone)..."
	cd $(TEST_STAGING)/sysroot && \
		RAMFS_TEMPLATE="$(TEST_RAMFS_CONTENT)/sysroot" \
		TEST_SOURCE="$(TEST_STAGING)/sysroot" \
		MKRAMFS="$(MKRAMFS)" \
		NANVIXD_RAMFS="$(RAMFS_IMG)" \
		NANVIXD_BIN_DIR="./bin" \
		UNITTEST_RUNNER="$(UNITTEST_RUNNER)" \
		BATCH_SIZE=$(NANVIX_TEST_BATCH_SIZE) \
		NANVIXD_EXTRA_ARGS="$(NANVIXD_EXTRA_ARGS)" \
		$(CURDIR)/.nanvix/run-regrtest-batched.sh $(NANVIX_TEST_LIST)

# Aggregate test target for standalone mode
test: test-hello-standalone test-regrtest-standalone test-cleanup
	@rm -f $(RAMFS_IMG)
	@rm -rf $(TEST_RAMFS_CONTENT)

.PHONY: ramfs-stage test-hello-standalone test-regrtest-standalone test

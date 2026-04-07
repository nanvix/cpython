# test-common.mk - Common test infrastructure
#
# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.
#
# Provides shared test staging setup used by all deployment modes.
# The actual test execution is delegated to deployment-mode-specific includes
# (test-standalone.mk, test-multi-process.mk, test-single-process.mk).
#
# Required variables (set by includer before including this file):
#   TEST_STAGING  - directory for the staged test install

ifndef _TEST_COMMON_MK
_TEST_COMMON_MK := 1

# Staging directory for tests (inside workspace so Docker can access it)
TEST_STAGING ?= $(CURDIR)/.nanvix/_test_staging

# Stage the CPython install and test fixtures into TEST_STAGING.
# After this target, $(TEST_STAGING)/sysroot/ contains the full install tree
# plus the hello test script and Nanvix runtime binaries.
test-stage: build
	@echo "Running CPython tests on Nanvix..."
	@rm -rf $(TEST_STAGING)
	@# Install python and stdlib into a test staging area
ifdef CONFIG_NANVIX_DOCKER
	$(DOCKER_RUN) make install DESTDIR="$(DOCKER_WORKSPACE_PATH)/.nanvix/_test_staging"
else
	make install DESTDIR="$(TEST_STAGING)"
endif
	@# Copy test script into the staging sysroot
	@echo "import sys; print('CPYTHON_TEST_HELLO: Hello from Python', sys.version_info[:2])" > $(TEST_STAGING)/sysroot/test_hello.py
	@# Copy Nanvix runtime binaries into the staging sysroot
	@mkdir -p $(TEST_STAGING)/sysroot/bin
	@cp "$(abspath $(NANVIX_HOME))/bin/nanvixd.elf" $(TEST_STAGING)/sysroot/bin/ 2>/dev/null || true
	@cp "$(abspath $(NANVIX_HOME))/bin/kernel.elf"  $(TEST_STAGING)/sysroot/bin/ 2>/dev/null || true
	@cp "$(abspath $(NANVIX_HOME))/bin/linuxd.elf"  $(TEST_STAGING)/sysroot/bin/ 2>/dev/null || true
	@cp "$(abspath $(NANVIX_HOME))/bin/uservm.elf"  $(TEST_STAGING)/sysroot/bin/ 2>/dev/null || true

# Validate hello-world test output in a log file.
# Usage: $(call validate-hello,/path/to/logfile)
define validate-hello
	@if grep -q '^CPYTHON_TEST_HELLO:' $(1); then \
		echo "  PASS: $$(grep -m 1 '^CPYTHON_TEST_HELLO:' $(1))"; \
	else \
		echo "  FAIL: Hello test did not produce expected output"; cat $(1); exit 1; \
	fi
endef

# Run regrtest in batches of NANVIX_TEST_BATCH_SIZE modules.
# The microVM limits command-line length to ~512 bytes, so running all modules
# in a single invocation may exceed this.  This macro splits the module list
# and launches one nanvixd invocation per batch.
# Usage: $(call run-regrtest-batched)
define run-regrtest-batched
	@echo "Test: regrtest ($(words $(NANVIX_TEST_LIST)) modules, batch size $(NANVIX_TEST_BATCH_SIZE))..."
	@: > /tmp/cpython_regrtest.log
	@batch_num=0; \
	set -- $(NANVIX_TEST_LIST); \
	while [ $$# -gt 0 ]; do \
		batch_num=$$((batch_num + 1)); \
		batch=""; count=0; \
		while [ $$# -gt 0 ] && [ $$count -lt $(NANVIX_TEST_BATCH_SIZE) ]; do \
			batch="$$batch $$1"; shift; count=$$((count + 1)); \
		done; \
		echo "  Batch $$batch_num ($$count modules):$$batch"; \
		cd $(TEST_STAGING)/sysroot && \
		timeout 600 ./bin/nanvixd.elf $(NANVIXD_EXTRA_ARGS) -- ./bin/python3.12 -m test \
		  --timeout=120 $$batch \
		  < /dev/null >> /tmp/cpython_regrtest.log 2>&1; \
		regrtest_status=$$?; \
		if [ $$regrtest_status -ne 0 ]; then \
			echo "  FAIL: regrtest batch $$batch_num exited with status $$regrtest_status"; \
			cat /tmp/cpython_regrtest.log; exit 1; \
		fi; \
	done
	@echo "  PASS: all regrtest batches completed"
endef

# Clean up test artifacts.
test-cleanup:
	@rm -rf $(TEST_STAGING) /tmp/cpython_test.log /tmp/cpython_regrtest.log /tmp/cpython-rootfs.img
	@echo "		*** CPython tests PASSED ***"

.PHONY: test-stage test-cleanup

endif # _TEST_COMMON_MK

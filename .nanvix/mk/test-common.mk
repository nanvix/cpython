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
#
# If the staging directory already contains the python binary from a
# previous run, rebuild and re-staging are skipped entirely.
test-stage:
	@if [ -f "$(TEST_STAGING)/sysroot/bin/python3.12" ]; then \
		echo "Staging already populated — skipping build"; \
	else \
		$(MAKE) -f Makefile.nanvix build \
			CONFIG_NANVIX=$(CONFIG_NANVIX) \
			NANVIX_HOME=$(NANVIX_HOME) \
			NANVIX_TOOLCHAIN=$(NANVIX_TOOLCHAIN) \
			PLATFORM=$(PLATFORM) \
			PROCESS_MODE=$(PROCESS_MODE) \
			MEMORY_SIZE=$(MEMORY_SIZE) \
			INSTALL_PREFIX=$(INSTALL_PREFIX) \
			NANVIX_RELEASE=$(NANVIX_RELEASE) && \
		echo "Running CPython tests on Nanvix..." && \
		rm -rf $(TEST_STAGING) && \
		$(MAKE) install DESTDIR="$(TEST_STAGING)" && \
		echo "import sys; print('CPYTHON_TEST_HELLO: Hello from Python', sys.version_info[:2])" > $(TEST_STAGING)/sysroot/test_hello.py && \
		cp $(CURDIR)/.nanvix/run-regrtest.py $(TEST_STAGING)/sysroot/run-regrtest.py && \
		mkdir -p $(TEST_STAGING)/sysroot/bin && \
		for bin in nanvixd kernel linuxd uservm; do \
			for ext in .elf .exe; do \
				src="$(abspath $(NANVIX_HOME))/bin/$${bin}$${ext}"; \
				if [ -f "$$src" ]; then cp "$$src" $(TEST_STAGING)/sysroot/bin/; break; fi; \
			done; \
		done; \
	fi

# Validate hello-world test output in a log file.
# Usage: $(call validate-hello,/path/to/logfile)
define validate-hello
	@if grep -q '^CPYTHON_TEST_HELLO:' $(1); then \
		echo "  PASS: $$(grep -m 1 '^CPYTHON_TEST_HELLO:' $(1))"; \
	else \
		echo "  FAIL: Hello test did not produce expected output"; cat $(1); exit 1; \
	fi
endef

# Clean up test artifacts (keeps caches for next run).
test-cleanup:
	@rm -rf $(TEST_STAGING) /tmp/cpython_test.log /tmp/cpython_regrtest.log /tmp/cpython_regrtest_batch.log
	@echo "		*** CPython tests PASSED ***"

# Deep clean: remove cached ramfs template.
test-distclean: test-cleanup
	@rm -rf $(CURDIR)/.nanvix/_ramfs_cache
	@rm -f $(RAMFS_IMG)

.PHONY: test-stage test-cleanup test-distclean

endif # _TEST_COMMON_MK

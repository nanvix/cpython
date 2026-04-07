# test-single-process.mk - Single-process deployment mode tests
#
# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.
#
# Single-process mode: placeholder for future implementation.
# Currently behaves identically to multi-process mode.

include .nanvix/mk/test-common.mk

# test-hello-single-process: run hello test via nanvixd with direct file access
test-hello-single-process: test-stage
	@echo "Test: Hello world (single-process)..."
	cd $(TEST_STAGING)/sysroot && \
		{ \
			: > /tmp/cpython_test.log; \
			start_time=$$(date +%s%N); \
			timeout 120 ./bin/nanvixd.elf $(NANVIXD_EXTRA_ARGS) -- ./bin/python3.12 ./test_hello.py < /dev/null > /tmp/cpython_test.log 2>&1; \
			test_status=$$?; \
			end_time=$$(date +%s%N); \
			elapsed=$$(( (end_time - start_time) / 1000000 )); \
			echo "  Execution time: $${elapsed} ms"; \
			if [ $$test_status -ne 0 ]; then \
				echo "  FAIL: Hello test timed out or exited with status $$test_status"; cat /tmp/cpython_test.log; exit 1; \
			fi; \
		}
	$(call validate-hello,/tmp/cpython_test.log)

# test-regrtest-single-process: run stdlib regression tests in batches
# The microVM limits command-line length, so we split the module list into
# batches of NANVIX_TEST_BATCH_SIZE modules per invocation.
test-regrtest-single-process: test-stage
ifneq ($(NANVIX_RELEASE),yes)
	$(call run-regrtest-batched)
else
	@echo "Test: regrtest skipped (NANVIX_RELEASE=yes)"
endif

# Aggregate test target for single-process mode
test: test-hello-single-process test-regrtest-single-process test-cleanup

.PHONY: test-hello-single-process test-regrtest-single-process test

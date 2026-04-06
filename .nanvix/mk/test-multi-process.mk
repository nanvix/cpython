# test-multi-process.mk - Multi-process deployment mode tests
#
# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.
#
# In multi-process mode the runtime accesses files directly via the host
# filesystem — no ramfs image is needed.

include .nanvix/mk/test-common.mk

# test-hello-multi-process: run hello test via nanvixd with direct file access
test-hello-multi-process: test-stage
	@echo "Test: Hello world..."
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

# test-regrtest-multi-process: run stdlib regression tests
test-regrtest-multi-process: test-stage
ifneq ($(NANVIX_RELEASE),yes)
	@echo "Test: regrtest ($(words $(NANVIX_TEST_LIST)) modules, batched)..."
	@cd $(TEST_STAGING)/sysroot && \
		BATCH_SIZE=$(NANVIX_TEST_BATCH_SIZE) NANVIXD_EXTRA_ARGS="$(NANVIXD_EXTRA_ARGS)" \
		$(CURDIR)/.nanvix/run-regrtest-batched.sh $(NANVIX_TEST_LIST)
else
	@echo "Test: regrtest skipped (NANVIX_RELEASE=yes)"
endif

# Aggregate test target for multi-process mode
test: test-hello-multi-process test-regrtest-multi-process test-cleanup

.PHONY: test-hello-multi-process test-regrtest-multi-process test

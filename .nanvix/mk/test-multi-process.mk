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

# test-regrtest-multi-process: run stdlib regression tests in batches
# The microVM limits command-line length, so we split the module list into
# batches of NANVIX_TEST_BATCH_SIZE modules per invocation.
test-regrtest-multi-process: test-stage
ifneq ($(NANVIX_RELEASE),yes)
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
else
	@echo "Test: regrtest skipped (NANVIX_RELEASE=yes)"
endif

# Aggregate test target for multi-process mode
test: test-hello-multi-process test-regrtest-multi-process test-cleanup

.PHONY: test-hello-multi-process test-regrtest-multi-process test

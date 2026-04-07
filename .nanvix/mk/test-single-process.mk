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
test-regrtest-single-process: test-stage
ifneq ($(NANVIX_RELEASE),yes)
	@echo "Test: regrtest ($(words $(NANVIX_TEST_LIST)) modules, batch size $(NANVIX_TEST_BATCH_SIZE))..."
	@cd $(TEST_STAGING)/sysroot && \
		set -- $(NANVIX_TEST_LIST); \
		batch_num=0; total=$$#; \
		total_batches=$$(( (total + $(NANVIX_TEST_BATCH_SIZE) - 1) / $(NANVIX_TEST_BATCH_SIZE) )); \
		while [ $$# -gt 0 ]; do \
			batch_num=$$((batch_num + 1)); \
			batch=""; i=0; \
			while [ $$# -gt 0 ] && [ $$i -lt $(NANVIX_TEST_BATCH_SIZE) ]; do \
				batch="$$batch $$1"; shift; i=$$((i + 1)); \
			done; \
			echo "  Batch $$batch_num/$$total_batches:$$batch"; \
			: > /tmp/cpython_regrtest.log; \
			timeout 600 ./bin/nanvixd.elf $(NANVIXD_EXTRA_ARGS) -- ./bin/python3.12 -m test \
			  --timeout=120 $$batch \
			  < /dev/null > /tmp/cpython_regrtest.log 2>&1; \
			regrtest_status=$$?; \
			if [ $$regrtest_status -ne 0 ]; then \
				echo "  FAIL: regrtest batch $$batch_num exited with status $$regrtest_status"; cat /tmp/cpython_regrtest.log; exit 1; \
			fi; \
			echo "  PASS: batch $$batch_num completed"; \
		done; \
		echo "  PASS: all $$total_batches batches completed"
else
	@echo "Test: regrtest skipped (NANVIX_RELEASE=yes)"
endif

# Aggregate test target for single-process mode
test: test-hello-single-process test-regrtest-single-process test-cleanup

.PHONY: test-hello-single-process test-regrtest-single-process test

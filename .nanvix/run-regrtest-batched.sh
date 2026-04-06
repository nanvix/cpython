#!/bin/sh
# run-regrtest-batched.sh - Run CPython regrtest in batches via nanvixd
#
# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.
#
# Splits NANVIX_TEST_LIST into batches of BATCH_SIZE modules and runs each
# batch in its own nanvixd.elf invocation to stay within per-process memory
# limits.  Exits non-zero on the first batch failure.
#
# Usage:
#   BATCH_SIZE=4 NANVIXD_EXTRA_ARGS="..." \
#     .nanvix/run-regrtest-batched.sh <module> [<module> ...]
#
# Environment:
#   BATCH_SIZE           - modules per VM invocation (default: 4)
#   NANVIXD_EXTRA_ARGS   - extra flags passed to nanvixd.elf (optional)
#   BATCH_TIMEOUT        - per-batch timeout in seconds (default: 300)
#
# Standalone mode (per-batch ramfs):
#   RAMFS_TEMPLATE       - trimmed sysroot directory (no test/)
#   TEST_SOURCE          - original staging sysroot (has full test/)
#   MKRAMFS              - path to mkramfs.elf
#   NANVIXD_RAMFS        - output path for per-batch ramfs image
#   NANVIXD_BIN_DIR      - binary directory for nanvixd -bin-dir flag
#
# When RAMFS_TEMPLATE is set, each batch builds its own ramfs image
# containing only that batch's test modules (plus test/__init__.py,
# test/support/, and test/data/).  This keeps each image small enough
# to fit in the standalone VM's memory.

set -e

batch_size="${BATCH_SIZE:-4}"
timeout_sec="${BATCH_TIMEOUT:-300}"
logfile="/tmp/cpython_regrtest_batch.log"

# Clean up leftover /tmp/test_python_* directories from prior runs.
# The Nanvix VM shares the host /tmp and each run leaves garbled-name temp
# dirs that cause tempfile.mkdtemp() to fail in later batches with EEXIST
# ("No usable temporary directory name found") because the fixed random seed
# means the same candidate names are always tried first.
rm -rf /tmp/test_python_* 2>/dev/null || true

modules="$*"
if [ -z "$modules" ]; then
	echo "run-regrtest-batched.sh: no modules specified" >&2
	exit 1
fi

# Detect standalone per-batch ramfs mode.
if [ -n "$RAMFS_TEMPLATE" ]; then
	standalone=1
	if [ -z "$TEST_SOURCE" ] || [ -z "$MKRAMFS" ] || [ -z "$NANVIXD_RAMFS" ]; then
		echo "run-regrtest-batched.sh: standalone mode requires TEST_SOURCE, MKRAMFS, and NANVIXD_RAMFS" >&2
		exit 1
	fi
	if [ ! -x "$MKRAMFS" ]; then
		echo "run-regrtest-batched.sh: mkramfs not found at $MKRAMFS" >&2
		exit 1
	fi
	test_src="$TEST_SOURCE/lib/python3.12/test"
	test_dst="$RAMFS_TEMPLATE/lib/python3.12/test"
	ramfs_args="-bin-dir ${NANVIXD_BIN_DIR:-./bin} -ramfs $NANVIXD_RAMFS"
else
	standalone=0
	ramfs_args=""
fi

# inject_test_files <mod1> [<mod2> ...]
# Copy test infrastructure and specific test modules into the ramfs template.
inject_test_files() {
	mkdir -p "$test_dst/support"
	cp "$test_src/__init__.py" "$test_dst/"
	# __main__.py is required for `python -m test` to work
	cp "$test_src/__main__.py" "$test_dst/"
	cp -a "$test_src/support/." "$test_dst/support/"
	# libregrtest/ is the test runner imported by __main__.py
	if [ -d "$test_src/libregrtest" ]; then
		cp -a "$test_src/libregrtest" "$test_dst/"
	fi
	# test/data/ contains fixtures some tests load at runtime
	if [ -d "$test_src/data" ]; then
		cp -a "$test_src/data" "$test_dst/"
	fi
	for mod in "$@"; do
		# Handle both test_foo.py (file) and test_foo/ (package) forms
		if [ -f "$test_src/test_${mod}.py" ]; then
			cp "$test_src/test_${mod}.py" "$test_dst/"
		elif [ -d "$test_src/test_${mod}" ]; then
			cp -a "$test_src/test_${mod}" "$test_dst/"
		elif [ -f "$test_src/${mod}.py" ]; then
			cp "$test_src/${mod}.py" "$test_dst/"
		else
			echo "  Warning: test source not found for module '$mod'" >&2
		fi
	done
}

# clean_test_files - remove injected test files from the ramfs template.
clean_test_files() {
	rm -rf "$test_dst"
}

batch_num=0
total_pass=0

while [ -n "$modules" ]; do
	batch_num=$((batch_num + 1))
	batch=$(echo $modules | tr ' ' '\n' | head -n "$batch_size" | tr '\n' ' ')
	remaining=$(echo $modules | tr ' ' '\n' | tail -n +"$((batch_size + 1))" | tr '\n' ' ')
	modules=$remaining
	batch_count=$(echo $batch | wc -w)

	echo "  Batch $batch_num ($batch_count modules): $batch"
	: >"$logfile"

	if [ "$standalone" = "1" ]; then
		# Build per-batch ramfs with only this batch's test modules.
		clean_test_files
		inject_test_files $batch
		"$MKRAMFS" -o "$NANVIXD_RAMFS" "$RAMFS_TEMPLATE" >/dev/null 2>&1
		img_size=$(du -h "$NANVIXD_RAMFS" | cut -f1)
		echo "    ramfs: $img_size"
	fi

	set +e
	if [ "$standalone" = "1" ]; then
		timeout "$timeout_sec" ./bin/nanvixd.elf $ramfs_args $NANVIXD_EXTRA_ARGS \
			-- ./bin/python3.12 \
			"-B -m test $batch;PYTHONHOME=/ PYTHONDONTWRITEBYTECODE=1" \
			</dev/null >"$logfile" 2>&1
	else
		timeout "$timeout_sec" ./bin/nanvixd.elf $NANVIXD_EXTRA_ARGS \
			-- ./bin/python3.12 -m test $batch \
			</dev/null >"$logfile" 2>&1
	fi
	batch_status=$?
	set -e

	if [ $batch_status -ne 0 ]; then
		echo "  FAIL: batch $batch_num exited with status $batch_status"
		cat "$logfile"
		# Clean up before exiting
		[ "$standalone" = "1" ] && clean_test_files
		exit 1
	fi

	grep -E "^(== Tests result:|Total tests:|All [0-9]+ tests OK)" "$logfile" || true
	total_pass=$((total_pass + batch_count))
done

# Final cleanup
[ "$standalone" = "1" ] && clean_test_files

echo "  PASS: all $total_pass tests passed ($batch_num batches)"

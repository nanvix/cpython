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
# Standalone mode (per-batch ramfs with unittest runner):
#   RAMFS_TEMPLATE       - trimmed sysroot directory (no test/)
#   TEST_SOURCE          - original staging sysroot (has full test/)
#   MKRAMFS              - path to mkramfs.elf
#   NANVIXD_RAMFS        - output path for per-batch ramfs image
#   NANVIXD_BIN_DIR      - binary directory for nanvixd -bin-dir flag
#   UNITTEST_RUNNER      - path to run-standalone-unittest.py on the HOST
#
# When RAMFS_TEMPLATE is set, each batch builds its own ramfs image.
# To handle cross-test imports (e.g. test_int imports from test_grammar),
# ALL top-level files from test/ are included in every image (~17M),
# along with infrastructure subpackages (typinganndata, etc., ~5M).
# Test subpackage directories (test_asyncio/, test_email/, etc.) are only
# copied when that module is in the batch.  This keeps images at ~50M
# base + per-batch subpackages, well within the 256MB VM limit even as
# the full test suite grows.
#
# Standalone uses run-standalone-unittest.py instead of regrtest because
# the regrtest runner triggers a fatfs panic in nanvixd (poll() →
# OperationNotSupported → byte index out of bounds in dir.rs).  The
# unittest runner loads test modules via unittest.TextTestRunner directly,
# which avoids the problematic regrtest startup code path.

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
	if [ -z "$UNITTEST_RUNNER" ] || [ ! -f "$UNITTEST_RUNNER" ]; then
		echo "run-regrtest-batched.sh: standalone mode requires UNITTEST_RUNNER (path to run-standalone-unittest.py)" >&2
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
# Copy test infrastructure and test modules into the ramfs template.
# ALL top-level files from test/ are always included: .py files for
# cross-test imports (~15M) and data files (.txt, .json, etc.) that
# tests load at runtime (~1.6M).  Infrastructure subpackages
# (typinganndata, tokenizedata, etc.) are always included too (~5M)
# since they are imported at module load time by many tests.  Test
# subpackage directories (test_asyncio/, test_email/, etc.) are only
# copied when that module is in the current batch.  This keeps each
# per-batch ramfs image at ~50M, well within the 256MB VM limit.
inject_test_files() {
	mkdir -p "$test_dst/support"
	cp -a "$test_src/support/." "$test_dst/support/"
	# Copy ALL top-level files (*.py + data files like .txt, .json, .pck).
	# The .py files handle cross-test imports (~15M); the data files are
	# test fixtures loaded by open() at runtime (~1.6M).
	for f in "$test_src"/*; do
		[ -f "$f" ] && cp "$f" "$test_dst/"
	done
	# Copy infrastructure subpackages — always needed (~5M total).
	# These are non-test_* subdirectories like typinganndata, tokenizedata,
	# audiodata, etc. that test modules import at load time.
	for d in "$test_src"/*/; do
		name=$(basename "$d")
		case "$name" in
		__pycache__ | support | data | libregrtest) continue ;;
		test_*) continue ;; # test subpackages are per-batch
		*) cp -a "$d" "$test_dst/" ;;
		esac
	done
	# test/data/ contains fixtures some tests load at runtime
	if [ -d "$test_src/data" ]; then
		cp -a "$test_src/data" "$test_dst/"
	fi
	# Copy test subpackage directories only for modules in this batch
	for mod in "$@"; do
		if [ -d "$test_src/test_${mod}" ]; then
			cp -a "$test_src/test_${mod}" "$test_dst/"
		elif [ -d "$test_src/${mod}" ]; then
			cp -a "$test_src/${mod}" "$test_dst/"
		fi
	done
	# Copy the standalone unittest runner into ramfs root
	cp "$UNITTEST_RUNNER" "$RAMFS_TEMPLATE/run-standalone-unittest.py"
}

# clean_test_files - remove injected test files from the ramfs template.
clean_test_files() {
	rm -rf "$test_dst"
	rm -f "$RAMFS_TEMPLATE/run-standalone-unittest.py"
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
		# Build per-batch ramfs with this batch's test modules.
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
			"-B /run-standalone-unittest.py $batch;PYTHONHOME=/ PYTHONDONTWRITEBYTECODE=1" \
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

	if [ "$standalone" = "1" ]; then
		grep -E "^(All [0-9]+ tests OK|FAILED:)" "$logfile" || true
	else
		grep -E "^(== Tests result:|Total tests:|All [0-9]+ tests OK)" "$logfile" || true
	fi
	total_pass=$((total_pass + batch_count))
done

# Final cleanup
[ "$standalone" = "1" ] && clean_test_files

echo "  PASS: all $total_pass tests passed ($batch_num batches)"

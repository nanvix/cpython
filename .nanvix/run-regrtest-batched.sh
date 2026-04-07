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
#   EXCLUDE_TESTS        - space-separated test patterns to exclude via
#                          regrtest --ignore (optional)
#
# Standalone mode (per-batch ramfs):
#   RAMFS_TEMPLATE       - trimmed sysroot directory (no test/)
#   TEST_SOURCE          - original staging sysroot (has full test/)
#   MKRAMFS              - path to mkramfs.elf
#   NANVIXD_RAMFS        - output path for per-batch ramfs image
#   NANVIXD_BIN_DIR      - binary directory for nanvixd -bin-dir flag
#
# When RAMFS_TEMPLATE is set, each batch builds its own ramfs image.
# A /tmp directory is created on the ramfs so regrtest's
# tempfile.gettempdir() works without triggering the fatfs panic.
# To handle cross-test imports (e.g. test_int imports from test_grammar),
# a whitelist of cross-imported .py files is included in every image,
# along with infrastructure subpackages (typinganndata, etc., ~2M) and
# non-.py data files (~1.4M).  Only the batch's own test_*.py modules
# and the whitelist are copied — NOT all 405 test_*.py files (~15M),
# which would balloon images to ~95M and OOM.  Test subpackage dirs
# (test_asyncio/, test_email/, etc.) and heavy data dirs
# (decimaltestdata/) are only copied when that module is in the batch.
# This keeps images at ~55M, well within the 256MB VM limit.
#
# Per-mode test exclusions are supported via EXCLUDE_TESTS, which is
# converted to regrtest --ignore flags.  This allows excluding specific
# test methods that fail in a given mode (e.g. OOM on standalone's
# 32MB heap) without modifying CPython test source files.

set -e

batch_size="${BATCH_SIZE:-4}"
timeout_sec="${BATCH_TIMEOUT:-300}"
exclude_tests="${EXCLUDE_TESTS:-}"
exclude_args=""
if [ -n "$exclude_tests" ]; then
	for pat in $exclude_tests; do
		exclude_args="$exclude_args -i $pat"
	done
fi
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

# Cross-import whitelist: test modules imported by OTHER test modules.
# Derived from static analysis of `from test.X import ...` / `import test.X`
# across all modules in NANVIX_TEST_LIST.  Update when adding new modules.
#
#   test_grammar.py      ← test_float, test_complex, test_int, test_tokenize
#   string_tests.py      ← test_bytes
#   list_tests.py        ← test_bytes
#   seq_tests.py         ← list_tests (transitive)
#   test_math.py         ← test_cmath
#   test_iter.py         ← test_math (test_math.testSumProd imports BasicIterClass)
#   test_contextlib.py   ← test_contextlib_async
#   test_set.py          ← test_pprint
#   mapping_tests.py     ← test_dict (via mapping_tests import)
#   pickletester.py      ← various pickle-related tests
#   lock_tests.py        ← test_thread (from test import lock_tests)
#   test_longexp.py      ← padding (ensures ≥10 test_*.py for test_tokenize.test_random_files)
#   test_errno.py        ← padding (same reason — random.sample(testfiles, 10) needs ≥10)
CROSS_IMPORT_WHITELIST="test_grammar.py string_tests.py list_tests.py seq_tests.py test_math.py test_iter.py test_contextlib.py test_set.py mapping_tests.py pickletester.py lock_tests.py test_longexp.py test_errno.py"

# inject_test_files <mod1> [<mod2> ...]
# Copy test infrastructure and test modules into the ramfs template.
#
# To keep ramfs images small (~55M instead of ~95M), we do NOT copy all
# 405 test_*.py files.  Instead we copy:
#   1. Essential package files (__init__.py, __main__.py, regrtest.py)
#   2. The batch's own test modules
#   3. Cross-import whitelist (handful of .py files imported across modules)
#   4. Non-.py data files (.txt, .json, .pck — ~1.4M of test fixtures)
#   5. Infrastructure subpackages (typinganndata, tokenizedata, etc. — ~2M)
#   6. test/data/ directory (shared fixtures)
#   7. Per-batch test subpackage directories (test_asyncio/, etc.)
# Heavy data directories like decimaltestdata/ (4.5M) are only included
# when the corresponding test module is in the batch.
inject_test_files() {
	mkdir -p "$test_dst/support"
	mkdir -p "$RAMFS_TEMPLATE/tmp"
	cp -a "$test_src/support/." "$test_dst/support/"
	# 1. Essential package files
	for f in __init__.py __main__.py regrtest.py; do
		[ -f "$test_src/$f" ] && cp "$test_src/$f" "$test_dst/"
	done
	# 2. Batch's own test modules
	for mod in "$@"; do
		[ -f "$test_src/${mod}.py" ] && cp "$test_src/${mod}.py" "$test_dst/"
	done
	# 3. Cross-import whitelist
	for f in $CROSS_IMPORT_WHITELIST; do
		[ -f "$test_src/$f" ] && cp "$test_src/$f" "$test_dst/"
	done
	# 4. Non-.py data files (test fixtures: .txt, .json, .pck, etc. — ~1.4M)
	for f in "$test_src"/*; do
		[ -f "$f" ] || continue
		case "$f" in *.py) continue ;; esac
		cp "$f" "$test_dst/"
	done
	# 5. Infrastructure subpackages — always needed (~2M without decimaltestdata).
	# These are non-test_* subdirectories like typinganndata, tokenizedata,
	# audiodata, etc. that test modules import at load time.
	for d in "$test_src"/*/; do
		name=$(basename "$d")
		case "$name" in
		__pycache__ | support | data) continue ;;
		test_*) continue ;;          # test subpackages are per-batch
		decimaltestdata) continue ;; # large (4.5M), per-batch only
		*) cp -a "$d" "$test_dst/" ;;
		esac
	done
	# 6. test/data/ contains fixtures some tests load at runtime
	if [ -d "$test_src/data" ]; then
		cp -a "$test_src/data" "$test_dst/"
	fi
	# 7. Per-batch: test subpackage directories and heavy data dirs
	for mod in "$@"; do
		if [ -d "$test_src/test_${mod}" ]; then
			cp -a "$test_src/test_${mod}" "$test_dst/"
		elif [ -d "$test_src/${mod}" ]; then
			cp -a "$test_src/${mod}" "$test_dst/"
		fi
	done
	# decimaltestdata/ only when test_decimal is in the batch
	for mod in "$@"; do
		case "$mod" in
		test_decimal)
			[ -d "$test_src/decimaltestdata" ] && cp -a "$test_src/decimaltestdata" "$test_dst/"
			break
			;;
		esac
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
		# Build per-batch ramfs with this batch's test modules.
		clean_test_files
		inject_test_files $batch
		"$MKRAMFS" -o "$NANVIXD_RAMFS" "$RAMFS_TEMPLATE" >/dev/null 2>&1
		img_size=$(du -h "$NANVIXD_RAMFS" | cut -f1)
		echo "    ramfs: $img_size"
	fi

	# Build the nanvixd arg string.  nanvixd splits on spaces to form argv,
	# and does NOT collapse consecutive spaces — each extra space creates an
	# empty-string argv entry that regrtest interprets as an unnamed test
	# module (→ "No module named 'test.'").  Trim batch and exclude_args to
	# prevent stray spaces.
	batch_trimmed=$(echo $batch)
	exclude_trimmed=$(echo $exclude_args)

	set +e
	if [ "$standalone" = "1" ]; then
		timeout "$timeout_sec" ./bin/nanvixd.elf $ramfs_args $NANVIXD_EXTRA_ARGS \
			-- ./bin/python3.12 \
			"-B -m test ${batch_trimmed}${exclude_trimmed:+ $exclude_trimmed};PYTHONHOME=/ PYTHONDONTWRITEBYTECODE=1" \
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

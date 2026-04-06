"""Standalone unittest runner for Nanvix — bypasses regrtest.

In standalone deployment mode, the regrtest runner crashes due to a fatfs
driver bug triggered during its startup (poll() → OperationNotSupported →
fatfs panic in dir.rs).  Individual test modules work fine when loaded via
unittest.TextTestRunner directly.

Usage (inside nanvixd):
    python3.12 -B /run-standalone-unittest.py test_bool test_int ...

Each argument is a test module name (with or without the 'test_' prefix).
The script imports test.<module>, discovers all TestCase subclasses, and
runs them.  Exit code 0 = all passed, 1 = failures/errors.
"""

import sys
import unittest


def run_tests(module_names):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    import_failures = []

    for name in module_names:
        # Normalise: accept both "test_bool" and "bool"
        if not name.startswith("test_"):
            name = "test_" + name
        fqn = "test." + name
        try:
            mod = __import__(fqn, fromlist=[name])
            suite.addTests(loader.loadTestsFromModule(mod))
        except Exception as e:
            import_failures.append((fqn, e))
            print(f"IMPORT ERROR: {fqn}: {e}", flush=True)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary line compatible with regrtest output parsing
    total = result.testsRun
    failures = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)

    if import_failures:
        print(f"\nIMPORT FAILURES: {len(import_failures)}")
        for fqn, exc in import_failures:
            print(f"  {fqn}: {exc}")

    if result.wasSuccessful() and not import_failures:
        print(f"\nAll {total} tests OK (skipped={skipped})")
        return 0
    else:
        print(f"\nFAILED: {failures} failures, {total} run, {skipped} skipped")
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: run-standalone-unittest.py <module> [<module> ...]", file=sys.stderr
        )
        sys.exit(2)
    sys.exit(run_tests(sys.argv[1:]))

/*
 * _rf_fuzz_cpp_sse2_builtin.c - Shim to register rapidfuzz.fuzz_cpp_sse2 as a CPython built-in.
 *
 * The Cython-generated code exports PyInit_fuzz_cpp_sse2.
 * This wrapper provides PyInit__rf_fuzz_cpp_sse2 so the flat name matches
 * the entry in Modules/Setup.local.
 */

#include "Python.h"

extern PyObject* PyInit_fuzz_cpp_sse2(void);

PyMODINIT_FUNC
PyInit__rf_fuzz_cpp_sse2(void)
{
    return PyInit_fuzz_cpp_sse2();
}

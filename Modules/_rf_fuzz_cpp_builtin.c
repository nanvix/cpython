/*
 * _rf_fuzz_cpp_builtin.c - Shim to register rapidfuzz.fuzz_cpp as a CPython built-in.
 *
 * The Cython-generated code exports PyInit_fuzz_cpp.
 * This wrapper provides PyInit__rf_fuzz_cpp so the flat name matches
 * the entry in Modules/Setup.local.
 */

#include "Python.h"

extern PyObject* PyInit_fuzz_cpp(void);

PyMODINIT_FUNC
PyInit__rf_fuzz_cpp(void)
{
    return PyInit_fuzz_cpp();
}

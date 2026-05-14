/*
 * _rf_utils_cpp_builtin.c - Shim to register rapidfuzz.utils_cpp as a CPython built-in.
 *
 * The Cython-generated code exports PyInit_utils_cpp.
 * This wrapper provides PyInit__rf_utils_cpp so the flat name matches
 * the entry in Modules/Setup.local.
 */

#include "Python.h"

extern PyObject* PyInit_utils_cpp(void);

PyMODINIT_FUNC
PyInit__rf_utils_cpp(void)
{
    return PyInit_utils_cpp();
}

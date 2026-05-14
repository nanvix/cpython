/*
 * _rf_dist_initialize_cpp_builtin.c - Shim to register rapidfuzz.distance._initialize_cpp as a CPython built-in.
 *
 * The Cython-generated code exports PyInit__initialize_cpp.
 * This wrapper provides PyInit__rf_dist_initialize_cpp so the flat name matches
 * the entry in Modules/Setup.local.
 */

#include "Python.h"

extern PyObject* PyInit__initialize_cpp(void);

PyMODINIT_FUNC
PyInit__rf_dist_initialize_cpp(void)
{
    return PyInit__initialize_cpp();
}

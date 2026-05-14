/*
 * _rf_dist_metrics_cpp_builtin.c - Shim to register rapidfuzz.distance.metrics_cpp as a CPython built-in.
 *
 * The Cython-generated code exports PyInit_metrics_cpp.
 * This wrapper provides PyInit__rf_dist_metrics_cpp so the flat name matches
 * the entry in Modules/Setup.local.
 */

#include "Python.h"

extern PyObject* PyInit_metrics_cpp(void);

PyMODINIT_FUNC
PyInit__rf_dist_metrics_cpp(void)
{
    return PyInit_metrics_cpp();
}

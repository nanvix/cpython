/*
 * _rf_feature_detector_cpp_builtin.c - Shim to register rapidfuzz._feature_detector_cpp as a CPython built-in.
 *
 * The Cython-generated code exports PyInit__feature_detector_cpp.
 * This wrapper provides PyInit__rf_feature_detector_cpp so the flat name matches
 * the entry in Modules/Setup.local.
 */

#include "Python.h"

extern PyObject* PyInit__feature_detector_cpp(void);

PyMODINIT_FUNC
PyInit__rf_feature_detector_cpp(void)
{
    return PyInit__feature_detector_cpp();
}

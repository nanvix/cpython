/*
 * Builtin shim for numpy.core._multiarray_umath
 *
 * Registers the numpy _multiarray_umath C extension as a flat
 * built-in module "_np_multiarray_umath".  A Python bridge shim
 * in numpy/core/ maps it back to the expected import path.
 */

#include "Python.h"

/* Forward-declare the real init function from numpy */
PyMODINIT_FUNC PyInit__multiarray_umath(void);

PyMODINIT_FUNC
PyInit__np_multiarray_umath(void)
{
    return PyInit__multiarray_umath();
}

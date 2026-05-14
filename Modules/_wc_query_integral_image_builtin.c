/* Builtin shim: wordcloud.query_integral_image
 *
 * The Cython extension defines PyInit_query_integral_image.
 * CPython's static-module table needs a flat name: _wc_query_integral_image.
 * This wrapper simply forwards the call.
 */
#include "Python.h"

extern PyObject *PyInit_query_integral_image(void);

PyMODINIT_FUNC PyInit__wc_query_integral_image(void)
{
    return PyInit_query_integral_image();
}

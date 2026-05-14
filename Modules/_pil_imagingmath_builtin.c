/* Builtin shim: PIL._imagingmath
 *
 * The Pillow C extension defines PyInit__imagingmath.
 * CPython's static-module table needs a flat name: _pil_imagingmath.
 */
#include "Python.h"

extern PyObject *PyInit__imagingmath(void);

PyMODINIT_FUNC PyInit__pil_imagingmath(void)
{
    return PyInit__imagingmath();
}

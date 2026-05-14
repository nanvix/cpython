/* Builtin shim: PIL._imagingmorph
 *
 * The Pillow C extension defines PyInit__imagingmorph.
 * CPython's static-module table needs a flat name: _pil_imagingmorph.
 */
#include "Python.h"

extern PyObject *PyInit__imagingmorph(void);

PyMODINIT_FUNC PyInit__pil_imagingmorph(void)
{
    return PyInit__imagingmorph();
}

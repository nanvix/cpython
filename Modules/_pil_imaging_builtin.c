/* Builtin shim: PIL._imaging
 *
 * The Pillow C extension defines PyInit__imaging.
 * CPython's static-module table needs a flat name: _pil_imaging.
 */
#include "Python.h"

extern PyObject *PyInit__imaging(void);

PyMODINIT_FUNC PyInit__pil_imaging(void)
{
    return PyInit__imaging();
}

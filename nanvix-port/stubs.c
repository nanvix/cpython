/* GCC CRT frame registration stubs for NanVix.
 *
 * frame_dummy (in crtbegin.o .init) calls __register_frame_info if the
 * pointer is non-NULL. NanVix does not need DWARF unwinding, so these
 * provide no-op link-time resolution.
 */

void __register_frame_info(const void *begin, void *ob) {
    (void)begin; (void)ob;
}

void __deregister_frame_info(const void *begin) {
    (void)begin;
}

void *__deregister_frame_info_bases(const void *begin) {
    (void)begin;
    return (void *)0;
}

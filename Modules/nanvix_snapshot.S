# Nanvix VM snapshot trigger via int 0x80 (syscall 35)
# This is in a separate .S file to survive LTO optimization.
    .text
    .globl nanvix_snapshot
    .type nanvix_snapshot, @function
nanvix_snapshot:
    movl $35, %eax
    int $0x80
    ret
    .size nanvix_snapshot, .-nanvix_snapshot

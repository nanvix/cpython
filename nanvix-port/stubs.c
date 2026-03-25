/* Stubs for POSIX functions NanVix does not implement.
 * CPython's configure is told these don't exist (config.site),
 * but some code paths still reference them. These stubs provide
 * link-time resolution with proper error returns.
 */

#include <errno.h>
#include <sys/types.h>
#include <signal.h>

/* fork() — NanVix does not support process forking (Issue #321). */
pid_t fork(void) {
    errno = ENOSYS;
    return -1;
}

/* vfork() — same limitation as fork(). */
pid_t vfork(void) {
    errno = ENOSYS;
    return -1;
}

/* sigaction() — NanVix does not implement full signal handling. */
int sigaction(int signum, const struct sigaction *act,
              struct sigaction *oldact) {
    (void)signum;
    (void)act;
    (void)oldact;
    errno = ENOSYS;
    return -1;
}

/* siginterrupt() — depends on sigaction. */
int siginterrupt(int sig, int flag) {
    (void)sig;
    (void)flag;
    errno = ENOSYS;
    return -1;
}

/* popen/pclose — requires fork+exec. */
#include <stdio.h>

FILE *popen(const char *command, const char *type) {
    (void)command;
    (void)type;
    errno = ENOSYS;
    return NULL;
}

int pclose(FILE *stream) {
    (void)stream;
    errno = ENOSYS;
    return -1;
}

/* system() — requires fork+exec. */
int system(const char *command) {
    (void)command;
    errno = ENOSYS;
    return -1;
}

/* getpgid() — NanVix does not implement process groups. */
pid_t getpgid(pid_t pid) {
    (void)pid;
    errno = ENOSYS;
    return -1;
}

/* setpgid() — NanVix does not implement process groups. */
int setpgid(pid_t pid, pid_t pgid) {
    (void)pid;
    (void)pgid;
    errno = ENOSYS;
    return -1;
}

/* getppid() — stub if not in libposix. */
pid_t getppid(void) {
    return 1;
}

/* CPython fork lifecycle hooks (Python/pylifecycle.c).
 * These are only defined when HAVE_FORK is set, but _posixsubprocess.c
 * references them unconditionally. Since fork() returns ENOSYS on NanVix,
 * these are never actually called — they only satisfy the linker. */
void PyOS_BeforeFork(void) { }
void PyOS_AfterFork_Parent(void) { }
void PyOS_AfterFork_Child(void) { }

"""Linux child network denial before exec of the credential-free SDK encoder."""
import ctypes
import errno
import os
import resource
import socket
import sys

lib = ctypes.CDLL('libseccomp.so.2', use_errno=True)
lib.seccomp_init.argtypes = [ctypes.c_uint32]
lib.seccomp_init.restype = ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
lib.seccomp_load.argtypes = [ctypes.c_void_p]
lib.seccomp_release.argtypes = [ctypes.c_void_p]
ctx = lib.seccomp_init(0x7fff0000)
if not ctx:raise SystemExit(2)
for name in ('socket','socketpair','connect','bind','listen','accept','accept4',
             'sendto','sendmsg','sendmmsg','recvfrom','recvmsg','recvmmsg'):
    number = lib.seccomp_syscall_resolve_name(name.encode())
    if number >= 0 and lib.seccomp_rule_add(ctx, 0x00050000|errno.EPERM, number, 0) != 0:
        raise SystemExit(2)
if lib.seccomp_load(ctx) != 0:raise SystemExit(2)
lib.seccomp_release(ctx)
try:socket.socket()
except OSError as exc:
    if exc.errno != errno.EPERM:raise SystemExit(2)
else:raise SystemExit(2)
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
if len(sys.argv) != 2:raise SystemExit(2)
os.execve(sys.argv[1],[sys.argv[1]],{'GOMEMLIMIT':'192MiB','GOTELEMETRY':'off'})

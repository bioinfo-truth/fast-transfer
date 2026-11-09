"""Child-only seccomp network denial, then exec with an isolated environment."""
import ctypes
import errno
import os
from pathlib import Path
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
ctx = lib.seccomp_init(0x7fff0000)  # ALLOW default; deny all socket entry points.
if not ctx:
    raise SystemExit('seccomp_init_failed')
for name in ('socket', 'socketpair', 'connect', 'bind', 'listen', 'accept', 'accept4',
             'sendto', 'sendmsg', 'sendmmsg', 'recvfrom', 'recvmsg', 'recvmmsg'):
    number = lib.seccomp_syscall_resolve_name(name.encode())
    if number >= 0 and lib.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM, number, 0) != 0:
        raise SystemExit('seccomp_rule_failed')
if lib.seccomp_load(ctx) != 0:
    raise SystemExit('seccomp_load_failed')
lib.seccomp_release(ctx)
try:
    socket.socket()
except OSError as exc:
    if exc.errno != errno.EPERM:
        raise SystemExit('network_guard_wrong_error')
else:
    raise SystemExit('network_guard_missing')
root = Path(__file__).resolve().parent
folders = {name: root / name for name in ('home', 'cache', 'tmp', 'gopath')}
for folder in folders.values():
    folder.mkdir(exist_ok=True)
env = {'HOME': str(folders['home']), 'XDG_CONFIG_HOME': str(folders['home'] / 'config'),
       'GOCACHE': str(folders['cache']), 'GOPATH': str(folders['gopath']),
       'TMPDIR': str(folders['tmp']), 'GOTMPDIR': str(folders['tmp']),
       'PATH': str(root / 'go/bin') + ':/usr/bin:/bin', 'GOROOT': str(root / 'go'),
       'GOTOOLCHAIN': 'local', 'GOPROXY': 'off', 'GOSUMDB': 'off', 'GOWORK': 'off',
       'GOENV': 'off', 'GO111MODULE': 'off', 'CGO_ENABLED': '0', 'GOTELEMETRY': 'off'}
os.execve(sys.argv[1], sys.argv[1:], env)

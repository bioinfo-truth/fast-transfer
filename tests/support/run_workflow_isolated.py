"""Run reviewed local tests with child-inherited kernel network denial.
Use python3 -I -S; no external packages or persisted configuration are loaded.
Filesystem access is controlled by reviewed paths, not a filesystem sandbox.
"""
import ctypes
import errno
import os
from pathlib import Path
import runpy
import socket
import sys
import tempfile

lib=ctypes.CDLL('libseccomp.so.2',use_errno=True)
lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_release.argtypes=[ctypes.c_void_p]
ctx=lib.seccomp_init(0x7fff0000)
if not ctx:raise SystemExit('seccomp_init_failed')
for name in ('socket','socketpair','connect','bind','listen','accept','accept4','sendto','sendmsg','sendmmsg','recvfrom','recvmsg','recvmmsg'):
    n=lib.seccomp_syscall_resolve_name(name.encode())
    if n>=0 and lib.seccomp_rule_add(ctx,0x00050000|errno.EPERM,n,0)!=0:raise SystemExit('seccomp_rule_failed')
if lib.seccomp_load(ctx)!=0:raise SystemExit('seccomp_load_failed')
lib.seccomp_release(ctx)
try:socket.socket()
except OSError as exc:assert exc.errno==errno.EPERM
else:raise SystemExit('network_guard_missing')
repo=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='ft-workflow-isolated-') as tmp:
    home=Path(tmp)/'home';home.mkdir();os.environ.clear()
    os.environ.update(HOME=str(home),XDG_CONFIG_HOME=str(home/'config'),TMPDIR=tmp,PYTHONDONTWRITEBYTECODE='1')
    tempfile.tempdir=tmp
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(repo));sys.path.insert(0,str(repo/'tests'))
    sys.argv=['unittest','-v',*(sys.argv[1:] or ['test_workflow_process','test_workflow'])]
    runpy.run_module('unittest',run_name='__main__')

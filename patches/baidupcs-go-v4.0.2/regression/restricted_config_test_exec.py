"""Runtime only: child Landlock filesystem allowlist + inherited seccomp network deny."""
import ctypes
import errno
import os
from pathlib import Path
import socket
import sys
root=Path(__file__).resolve().parent
binary=Path(sys.argv[1]).resolve()
if binary != root/'config-regression-reviewed.test':raise SystemExit('unapproved_test_target')
canary=Path(sys.argv[2]);link=root/'config-outside-canary-link'
if link.is_symlink():link.unlink()
if link.exists():raise SystemExit('unexpected_probe_path')
link.symlink_to(canary)
home=root/'config-runtime-empty-home';home.mkdir(exist_ok=False)
tmp=root/'config-runtime-tmp';tmp.mkdir(exist_ok=False)
lib=ctypes.CDLL('libseccomp.so.2',use_errno=True)
lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_release.argtypes=[ctypes.c_void_p]
ctx=lib.seccomp_init(0x7fff0000)
if not ctx:raise SystemExit('seccomp_init_failed')
for name in ('socket','socketpair','connect','bind','listen','accept','accept4','sendto','sendmsg','sendmmsg','recvfrom','recvmsg','recvmmsg'):
 number=lib.seccomp_syscall_resolve_name(name.encode())
 if number>=0 and lib.seccomp_rule_add(ctx,0x00050000|errno.EPERM,number,0)!=0:raise SystemExit('seccomp_rule_failed')
if lib.seccomp_load(ctx)!=0:raise SystemExit('seccomp_load_failed')
lib.seccomp_release(ctx)
class Ruleset(ctypes.Structure):_fields_=[('handled_access_fs',ctypes.c_uint64)]
class Beneath(ctypes.Structure):
 _layout_='ms'
 _pack_=1
 _fields_=[('allowed_access',ctypes.c_uint64),('parent_fd',ctypes.c_int32)]
libc=ctypes.CDLL(None,use_errno=True)
abi=libc.syscall(444,0,0,1)
if abi<3:raise SystemExit('landlock_abi_insufficient')
handled=(1<<15)-1  # v1 filesystem rights, REFER and TRUNCATE.
attr=Ruleset(handled);fd=libc.syscall(444,ctypes.byref(attr),ctypes.sizeof(attr),0)
if fd<0:raise SystemExit('landlock_create_failed')
for path,rights in [(root,handled & ~1),(binary,1 | (1<<2))]:
 parent=os.open(path,os.O_PATH|os.O_CLOEXEC)
 rule=Beneath(rights,parent)
 if libc.syscall(445,fd,1,ctypes.byref(rule),0)!=0:raise SystemExit('landlock_rule_failed')
 os.close(parent)
if libc.prctl(38,1,0,0,0)!=0:raise SystemExit('no_new_privs_failed')
if libc.syscall(446,fd,0)!=0:raise SystemExit('landlock_restrict_failed')
os.close(fd)
for probe in (canary,link):
 try:probe.read_bytes()
 except PermissionError:pass
 else:raise SystemExit('filesystem_guard_missing')
try:socket.socket()
except OSError as err:
 if err.errno!=errno.EPERM:raise SystemExit('network_guard_wrong_error')
else:raise SystemExit('network_guard_missing')
env={'HOME':str(home),'XDG_CONFIG_HOME':str(home/'config'),'TMPDIR':str(tmp),
 'BAIDUPCS_GO_CONFIG_DIR':str(home/'baidupcs-config'),'FT_OUTSIDE_CANARY':str(canary),
 'FT_CANARY_SYMLINK':str(link),'GOTELEMETRY':'off'}
os.execve(binary,[str(binary),'-test.run=^TestFT(IdentityEntrypointsDenyBeforeParsing|AccountSaveDeniedBeforeFileCreation)$','-test.v','-test.timeout=30s'],env)

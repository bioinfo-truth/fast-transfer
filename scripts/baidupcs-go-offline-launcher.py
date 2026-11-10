"""Installed patched BaiduPCS-Go: offline version/help only until live review.

No real config, credentials, network, login or share. Linux x86_64 only.
The parent loads only its fixed installation metadata and generated canaries.
Child guards are installed before the target executable's initialization.
"""
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import socket
import stat
import sys
import tempfile


def fail(code):
    raise RuntimeError(code) from None


def guards(root,binary,canary,link):
    lib=ctypes.CDLL('libseccomp.so.2',use_errno=True)
    lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
    lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
    lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_release.argtypes=[ctypes.c_void_p]
    ctx=lib.seccomp_init(0x7fff0000)
    if not ctx:fail('seccomp_unavailable')
    for name in ('socket','socketpair','connect','bind','listen','accept','accept4',
                 'sendto','sendmsg','sendmmsg','recvfrom','recvmsg','recvmmsg'):
        number=lib.seccomp_syscall_resolve_name(name.encode())
        if number>=0 and lib.seccomp_rule_add(ctx,0x00050000|errno.EPERM,number,0)!=0:fail('seccomp_rule_failed')
    if lib.seccomp_load(ctx)!=0:fail('seccomp_load_failed')
    lib.seccomp_release(ctx)
    class Ruleset(ctypes.Structure):
        _fields_=[('handled_access_fs',ctypes.c_uint64)]
    class Beneath(ctypes.Structure):
        _layout_='ms';_pack_=1
        _fields_=[('allowed_access',ctypes.c_uint64),('parent_fd',ctypes.c_int32)]
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.syscall(444,0,0,1)<3:fail('landlock_unavailable')
    handled=(1<<15)-1
    attr=Ruleset(handled);fd=libc.syscall(444,ctypes.byref(attr),ctypes.sizeof(attr),0)
    if fd<0:fail('landlock_create_failed')
    for path,rights in ((root,handled&~1),(binary,1|(1<<2))):
        parent=os.open(path,os.O_PATH|os.O_CLOEXEC)
        rule=Beneath(rights,parent)
        if libc.syscall(445,fd,1,ctypes.byref(rule),0)!=0:fail('landlock_rule_failed')
        os.close(parent)
    if libc.prctl(38,1,0,0,0)!=0 or libc.syscall(446,fd,0)!=0:fail('landlock_restrict_failed')
    os.close(fd)
    for path in (canary,link):
        try:path.read_bytes()
        except PermissionError:pass
        else:fail('filesystem_guard_missing')
    try:socket.socket()
    except OSError as exc:
        if exc.errno!=errno.EPERM:fail('network_guard_wrong_error')
    else:fail('network_guard_missing')


def main():
    modes={('--version',):('--version',),('version',):('--version',),
           ('--help',):('--help',),('help',):('--help',),
           ('login','--help'):('login','--help'),('help','login'):('help','login')}
    mode=modes.get(tuple(sys.argv[1:]))
    if mode is None:
        print('Safety candidate: --version, --help and login --help are available. Online login/account/share operations are not enabled.')
        return 2
    install=Path(__file__).resolve().parent
    manifest=json.loads((install/'installation.json').read_text())
    binary=install/'BaiduPCS-Go.patched'
    st=binary.lstat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_mode&0o022):fail('installed_binary_rejected')
    with binary.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=manifest['binary_sha256']:fail('installed_binary_hash_mismatch')
    print('BaiduPCS-Go safety candidate; offline isolated '+' '.join(mode)+' only. No real login configuration is loaded.',flush=True)
    with tempfile.TemporaryDirectory(prefix='ft-pcs-offline-') as folder, tempfile.NamedTemporaryFile(prefix='ft-pcs-generated-canary-') as outside:
        root=Path(folder);home=root/'home';home.mkdir();config=home/'config';config.mkdir();tmp=root/'tmp';tmp.mkdir()
        outside.write(b'GENERATED_FAKE_ONLY');outside.flush()
        link=root/'outside-link';link.symlink_to(outside.name)
        pid=os.fork()
        if pid==0:
            try:
                resource.setrlimit(resource.RLIMIT_CORE,(0,0));signal.alarm(20)
                # Close inherited terminal input; no prompt or credential entry.
                null=os.open('/dev/null',os.O_RDONLY);os.dup2(null,0);os.close(null)
                # Include high inherited FDs; do not assume they are below 1024.
                for name in os.listdir('/proc/self/fd'):
                    descriptor=int(name)
                    if descriptor>=3:
                        try:os.close(descriptor)
                        except OSError:pass  # The enumeration FD is already closed.
                guards(root,binary,Path(outside.name),link)
                env={'HOME':str(home),'XDG_CONFIG_HOME':str(config),'TMPDIR':str(tmp),
                     'BAIDUPCS_GO_CONFIG_DIR':str(config),'GOTELEMETRY':'off'}
                os.execve(binary,[str(binary),*mode],env)
            except BaseException:
                os.write(2,b'offline_startup_rejected\n');os._exit(1)
        _,status=os.waitpid(pid,0)
        return os.waitstatus_to_exitcode(status) if os.WIFEXITED(status) else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('offline_launcher_failed',file=sys.stderr);raise SystemExit(1)

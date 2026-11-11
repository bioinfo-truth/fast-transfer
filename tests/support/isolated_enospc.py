"""Run only in an explicitly approved private mount namespace; no network/account I/O."""
import errno,hashlib,json,os,sqlite3,subprocess,tempfile
from pathlib import Path

exec(compile('"""Run reviewed local tests with child-inherited kernel network denial.\nUse python3 -I -S; no external packages or persisted configuration are loaded.\nFilesystem access is controlled by reviewed paths, not a filesystem sandbox.\n"""\nimport ctypes\nimport errno\nimport os\nfrom pathlib import Path\nimport runpy\nimport socket\nimport sys\nimport tempfile\n\nlib=ctypes.CDLL(\'libseccomp.so.2\',use_errno=True)\nlib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p\nlib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int\nlib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]\nlib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_release.argtypes=[ctypes.c_void_p]\nctx=lib.seccomp_init(0x7fff0000)\nif not ctx:raise SystemExit(\'seccomp_init_failed\')\nfor name in (\'socket\',\'socketpair\',\'connect\',\'bind\',\'listen\',\'accept\',\'accept4\',\'sendto\',\'sendmsg\',\'sendmmsg\',\'recvfrom\',\'recvmsg\',\'recvmmsg\'):\n    n=lib.seccomp_syscall_resolve_name(name.encode())\n    if n>=0 and lib.seccomp_rule_add(ctx,0x00050000|errno.EPERM,n,0)!=0:raise SystemExit(\'seccomp_rule_failed\')\nif lib.seccomp_load(ctx)!=0:raise SystemExit(\'seccomp_load_failed\')\nlib.seccomp_release(ctx)\ntry:socket.socket()\nexcept OSError as exc:assert exc.errno==errno.EPERM\nelse:raise SystemExit(\'network_guard_missing\')\n','reviewed-network-denial','exec'))

assert os.geteuid()==0
# Refuse host namespace even if invoked accidentally as root.
assert os.readlink('/proc/self/ns/mnt')!=os.readlink('/proc/1/ns/mnt')
os.umask(0o077)
env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/nonexistent'}
with tempfile.TemporaryDirectory(prefix='ft-enospc-isolated-',dir='/var/tmp') as tmp:
    root=Path(tmp);root.chmod(0o700);mounted=False;db=None
    try:
        subprocess.run(['/usr/bin/mount','-t','tmpfs','-o','size=32m,nr_inodes=1024,mode=0700,nodev,nosuid,noexec','tmpfs',str(root)],env=env,check=True,capture_output=True)
        mounted=True
        stat=os.statvfs(root);assert 0<stat.f_blocks*stat.f_frsize<=32*1024**2
        assert root.stat().st_dev!=root.parent.stat().st_dev
        marker=root/'canary';marker.write_bytes(b'synthetic-preserved')
        db=sqlite3.connect(root/'state.sqlite3');db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE intent(outcome TEXT NOT NULL)');db.execute("INSERT INTO intent VALUES('unknown')");db.commit()
        hit=False
        with (root/'synthetic-filler').open('wb',buffering=0) as f:
            for _ in range(33):
                try:f.write(b'X'*(1024**2))
                except OSError as exc:
                    assert exc.errno==errno.ENOSPC;hit=True;break
        assert hit
        sqlite_full=False
        try:
            with db:db.execute("UPDATE intent SET outcome='confirmed'")
        except sqlite3.OperationalError as exc:
            assert exc.sqlite_errorcode==sqlite3.SQLITE_FULL;sqlite_full=True
        assert sqlite_full
        db.close();db=None
        (root/'synthetic-filler').unlink()
        db=sqlite3.connect(root/'state.sqlite3')
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT outcome FROM intent').fetchone()[0]=='unknown'
        assert marker.read_bytes()==b'synthetic-preserved'
        print(json.dumps({'scope':'isolated-filesystem-only','tmpfs_bytes':32*1024**2,'actual_file_ENOSPC':True,
            'actual_sqlite_FULL':True,'intent_unknown_after_reopen':True,'database_integrity_ok':True,
            'canary_unchanged':True,'network_or_credentials_or_real_tasks':False,
            'not_task_worker_ENOSPC_acceptance':True}))
    finally:
        if db is not None:db.close()
        if mounted:subprocess.run(['/usr/bin/umount',str(root)],env=env,check=True,capture_output=True)

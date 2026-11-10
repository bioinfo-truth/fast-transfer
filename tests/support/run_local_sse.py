"""Loopback TCP/TLS verification runner. No existing restrictions are relaxed.

Fresh process, empty env/HOME; Landlock restricts TCP bind/connect to the single
owned ephemeral fixture port. Driver additionally hard-pins numeric loopback.
No filesystem sandbox or UDP/IP-destination isolation is claimed by Landlock.
"""
import ctypes
import errno
import os
from pathlib import Path
import runpy
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading

repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo));sys.path.insert(0,str(repo/'tests'));sys.path.insert(0,str(repo/'tests/support'))
sys.dont_write_bytecode=True
with tempfile.TemporaryDirectory(prefix='ft-local-sse-',dir='/tmp') as tmp:
    root=Path(tmp);home=root/'home';home.mkdir();os.umask(0o077)
    openssl=shutil.which('openssl')
    if not openssl:raise SystemExit('fixture_openssl_unavailable')
    os.environ.clear();os.environ.update(HOME=str(home),XDG_CONFIG_HOME=str(home/'config'),TMPDIR=tmp)
    tempfile.tempdir=tmp
    certs={}
    for name,san in [('good','IP:127.0.0.1'),('wrong','DNS:fixture.invalid')]:
        key=root/(name+'.key');cert=root/(name+'.crt')
        subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=synthetic-fixture','-addext','subjectAltName='+san,'-config','/dev/null'],check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=dict(os.environ),close_fds=True)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert,key);certs[name]=(str(cert),context)
    from support.local_sse_server import Server
    server=Server(certs['good'][1]);port=server.server_port
    class Ruleset(ctypes.Structure):_fields_=[('fs',ctypes.c_uint64),('net',ctypes.c_uint64)]
    class Port(ctypes.Structure):_fields_=[('rights',ctypes.c_uint64),('port',ctypes.c_uint64)]
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.syscall(444,0,0,1)<4:raise SystemExit('landlock_tcp_unavailable')
    attr=Ruleset(0,3);fd=libc.syscall(444,ctypes.byref(attr),ctypes.sizeof(attr),0)
    rule=Port(3,port)
    if fd<0 or libc.syscall(445,fd,2,ctypes.byref(rule),0)!=0:raise SystemExit('landlock_tcp_rule_failed')
    if libc.prctl(38,1,0,0,0)!=0 or libc.syscall(446,fd,0)!=0:raise SystemExit('landlock_tcp_restrict_failed')
    os.close(fd)
    probe=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try:probe.connect(('127.0.0.1',1))
    except OSError as exc:
        if exc.errno!=errno.EACCES:raise SystemExit('TCP_guard_wrong_error')
    else:raise SystemExit('TCP_guard_missing')
    finally:probe.close()
    server_thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);server_thread.start()
    import test_mcp_local_http as tests
    tests.FIXTURE_SERVER=server;tests.CERTS=certs
    sys.argv=['unittest','-v','test_mcp_local_http']
    try:runpy.run_module('unittest',run_name='__main__')
    finally:server.finish_fixture();server_thread.join(3)

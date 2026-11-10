"""Explicit owner-terminal new-login preparation; no saved credentials or sharing.

Reuses the reviewed no-echo terminal routine from this project's MCP terminal,
not its service/transport. This standalone installed frontend has no MCP calls.
Only the user can start the prompt; development/tests must not use real inputs.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import select
import signal
import stat
import subprocess
import sys
import tempfile
import termios
import time


class Failure(Exception):pass


def secret(prompt,limit=1024,timeout=120):
    if not all(os.isatty(fd) for fd in (0,1,2)):raise Failure('interactive_terminal_required')
    fd=None;old=None;handlers={};data=bytearray()
    def cancel(*a):raise Failure('terminal_cancelled')
    try:
        fd=os.open('/dev/tty',os.O_RDWR|os.O_NOCTTY|os.O_CLOEXEC)
        if not os.isatty(fd) or os.tcgetpgrp(fd)!=os.getpgrp():raise Failure('controlling_terminal_required')
        old=termios.tcgetattr(fd);new=termios.tcgetattr(fd)
        new[0]&=~(termios.IXON|termios.IXOFF)
        new[3]&=~(termios.ECHO|termios.ECHONL|termios.ICANON|termios.ISIG)
        new[6][termios.VMIN]=1;new[6][termios.VTIME]=0
        for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):handlers[sig]=signal.signal(sig,cancel)
        termios.tcsetattr(fd,termios.TCSAFLUSH,new)
        if termios.tcgetattr(fd)[3]&(termios.ECHO|termios.ECHONL|termios.ICANON):raise Failure('terminal_echo_disable_failed')
        os.write(fd,prompt.encode('ascii'));deadline=time.monotonic()+timeout
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not select.select([fd],[],[],max(0,remaining))[0]:raise Failure('terminal_input_timeout')
            ch=os.read(fd,1)
            if not ch or ch==b'\x04':raise Failure('terminal_input_eof')
            if ch in (b'\x03',b'\x1a'):raise Failure('terminal_cancelled')
            if ch in (b'\n',b'\r'):
                if not data:raise Failure('empty_input')
                return bytes(data).decode('utf-8')
            if ch in (b'\x08',b'\x7f'):
                if data:data.pop()
                continue
            if ch==b'\x15':data.clear();continue
            if ch[0]<32 or len(data)>=limit:raise Failure('input_format_rejected')
            data.extend(ch)
    except Failure:raise
    except Exception:raise Failure('terminal_input_unavailable') from None
    finally:
        for i in range(len(data)):data[i]=0
        if fd is not None:
            restored=True
            try:
                termios.tcflush(fd,termios.TCIFLUSH)
                if old is not None:termios.tcsetattr(fd,termios.TCSANOW,old)
                os.write(fd,b'\n')
            except Exception:restored=False
            os.close(fd)
            for sig,handler in handlers.items():signal.signal(sig,handler)
            if not restored:raise Failure('terminal_restore_unconfirmed')


ALLOWED_STATUS=frozenset(('input_rejected','bootstrap_failed_no_authentication','authentication_outcome_unknown',
 'phone_or_email_challenge_required_not_sent','image_challenge_required_not_fetched','authentication_rejected',
 'success_code_without_session_cookie','login_created_identity_unverified','account_mismatch',
 'session_identity_verified_no_persistence','session_internal_failure'))
REPORT_FIELDS=frozenset(('status','phase','request_attempts','authentication_post_attempts','auth_code',
 'session_cookie_received','netdisk_identity_accepted','expected_account_checked','expected_account_matches',
 'credentials_saved','share_requests','closed'))
PHASES=frozenset(('validation','bootstrap_time','bootstrap_key','bootstrap_trace','login_post','session_identity',''))


def safe_report(raw):
    if type(raw) is not bytes or len(raw)>8192:raise Failure('helper_result_rejected')
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out:raise Failure('helper_result_rejected')
            out[key]=value
        return out
    r=json.loads(raw,object_pairs_hook=unique)
    if type(r) is not dict or set(r)-REPORT_FIELDS or r.get('status') not in ALLOWED_STATUS or r.get('phase','') not in PHASES:raise Failure('helper_result_rejected')
    for key,value in r.items():
        if key in ('status','phase'):continue
        if key=='auth_code':
            if value!='other' and (type(value) is not str or not 1<=len(value)<=8 or any(c not in '-0123456789' for c in value)):raise Failure('helper_result_rejected')
        elif key in ('request_attempts','authentication_post_attempts','share_requests'):
            if type(value) is not int or not 0<=value<=5:raise Failure('helper_result_rejected')
        elif type(value) is not bool:raise Failure('helper_result_rejected')
    if r.get('credentials_saved') is not False or r.get('share_requests')!=0 or r.get('authentication_post_attempts',0)>1:raise Failure('helper_result_rejected')
    return r


def main():
    if sys.argv[1:]==['--help']:
        print('BaiduPCS-Go login --session-only\nExplicit new WAP password login; one submission, no persistence, no sharing.\nChallenges stop without SMS/captcha requests. Credentials are entered only in the controlling terminal.\nThe legacy upstream password protocol is long-unmaintained; live compatibility is unverified.')
        return 0
    if sys.argv[1:]!=['--session-only']:raise Failure('session_only_arguments_required')
    if not all(os.isatty(fd) for fd in (0,1,2)):raise Failure('interactive_terminal_required')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parent;helper=root/'BaiduPCS-Go.login-session'
    st=helper.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_mode&0o022:raise Failure('helper_file_rejected')
    manifest=json.loads((root/'installation.json').read_text())
    with helper.open('rb') as source:actual=hashlib.file_digest(source,'sha256').hexdigest()
    if actual!=manifest['login_session_sha256']:raise Failure('helper_hash_mismatch')
    print('NEW login: password goes once to https://wappass.baidu.com/wp/api/login.\nOnly returned BDUSS is used for identity at https://pan.baidu.com/api/user/getinfo.\nNothing is saved; no OAuth/refresh/upload/share/SMS send. Server sessions may outlive this process.\nOld WAP login compatibility is unverified. Both account and password input are hidden.',flush=True)
    if secret('Type LOGIN-SESSION to proceed (hidden): ',limit=16)!='LOGIN-SESSION':raise Failure('session_confirmation_declined')
    username=password=None
    try:
        username=secret('Baidu account (hidden): ',limit=256)
        password=secret('Baidu password (hidden): ',limit=512)
        payload=json.dumps({'username':username,'password':password,'expected_account_sha256':'','session_only':True},ensure_ascii=False).encode()
        with tempfile.TemporaryDirectory(prefix='ft-login-empty-') as tmp:
            env={'HOME':tmp,'XDG_CONFIG_HOME':tmp,'TMPDIR':tmp,'GOTELEMETRY':'off'}
            try:
                child=subprocess.run([str(helper)],input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                     env=env,close_fds=True,timeout=50)
            except (subprocess.TimeoutExpired,KeyboardInterrupt):
                print('{"status":"authentication_outcome_unknown","credentials_saved":false,"share_requests":0}')
                return 1
        username=password=payload=None
        # No stderr or exception text can be reflected from the helper.
        report=safe_report(child.stdout)
        print(json.dumps(report))
        return 0 if report.get('status')=='session_identity_verified_no_persistence' else 1
    finally:username=password=None


if __name__=='__main__':
    try:raise SystemExit(main())
    except (Exception,KeyboardInterrupt):
        print('{"status":"login_session_frontend_stopped","credentials_saved":false,"share_requests":0}')
        raise SystemExit(1)

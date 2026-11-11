"""Explicit owner-terminal login and original-sample sharing; no saved credentials.

Reuses the reviewed no-echo terminal routine from this project's MCP terminal,
not its service/transport. This standalone installed frontend has no MCP calls.
Only the user can start the prompt; development/tests must not use real inputs.
"""
import argparse
import hashlib
import re
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
 'session_identity_verified_no_persistence','session_internal_failure',
 'share_plan_rejected_no_login','share_intent_already_consumed_no_login','share_intent_unavailable_no_login',
 'share_original_object_unverified','share_intent_write_failed','share_creation_outcome_unknown','share_creation_rejected',
 'share_created_unverified','share_record_unverified','share_password_unverified',
 'share_mapping_verified_private_result_failed','share_mapping_verified_private_result_ready','operation_internal_outcome_unknown'))
REPORT_FIELDS=frozenset(('status','phase','request_attempts','authentication_post_attempts','auth_code',
 'session_cookie_received','netdisk_identity_accepted','expected_account_checked','expected_account_matches',
 'credentials_saved','share_requests','closed','original_object_matched','share_intent_consumed',
 'share_creation_outcome_unknown','share_created','own_share_record_matched','share_password_confirmed','share_expiry_bounded',
 'own_share_page_read','private_result_written','recipient_access_verified','share_errno'))
PHASES=frozenset(('validation','bootstrap_time','bootstrap_key','bootstrap_trace','login_post','session_identity','sample_object','share_create','share_record','share_password',''))


def safe_report(raw,share=False):
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
        elif key=='share_errno':
            if type(value) is not int or not -1000000<=value<=1000000:raise Failure('helper_result_rejected')
        elif key in ('request_attempts','authentication_post_attempts','share_requests'):
            if type(value) is not int or not 0<=value<=(9 if share else 5):raise Failure('helper_result_rejected')
        elif type(value) is not bool:raise Failure('helper_result_rejected')
    if r.get('credentials_saved') is not False or r.get('share_requests') not in ((0,1) if share else (0,)) or r.get('authentication_post_attempts',0)>1:raise Failure('helper_result_rejected')
    return r


def main():
    if sys.argv[1:2]==['--share-original']:
        return share_main(sys.argv[2:])
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



class ShareParser(argparse.ArgumentParser):
    def error(self,message):raise Failure('share_arguments_rejected')


def sample_expectation(filename):
    path=Path(filename)
    if not path.is_absolute():raise Failure('absolute_expectation_path_required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as source:
        st=os.fstat(source.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_nlink!=1 or st.st_mode&0o077:raise Failure('private_expectation_required')
        raw=source.read(16385)
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise Failure('expectation_rejected')
            d[k]=v
        return d
    if len(raw)>16384:raise Failure('expectation_rejected')
    e=json.loads(raw,object_pairs_hook=unique)
    names={'task','account','application','fsid','path','size','md5','sha256','mapping_sha256'}
    if type(e) is not dict or set(e)!=names or any(type(e[k]) is not str for k in names-{'size'}):raise Failure('expectation_rejected')
    name='GCF_000005845.2_ASM584v2_genomic.fna.gz'
    if (not re.fullmatch('job-[0-9a-f]{32}',e['task']) or not re.fullmatch('sha256:[0-9a-f]{64}',e['account'])
       or not re.fullmatch('[1-9][0-9]{0,18}',e['fsid']) or int(e['fsid'])>2**63-1 or e['application']!='Xtransfer'
       or e['path']!='/apps/Xtransfer/mvp-validation/'+e['task']+'/'+name or type(e['size']) is not int or e['size']!=1379902
       or e['md5']!='c13d459b5caa702ff7e1f26fe44b8ad7' or e['sha256']!='a96d3cfa58c88d477013c768f90a11d2386d42a70d566abfb6d9013dcbd24255'):
        raise Failure('expectation_rejected')
    mapping=hashlib.sha256(json.dumps({k:v for k,v in e.items() if k!='mapping_sha256'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if mapping!=e['mapping_sha256']:raise Failure('expectation_rejected')
    return e


def private_intent_directory(filename):
    path=Path(filename)
    if not path.is_absolute() or any(x in ('.','..') for x in path.parts):raise Failure('private_intent_directory_required')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        for component in path.parts[1:]:
            try:following=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(component,0o700,dir_fd=fd)
                following=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            os.close(fd);fd=following
        st=os.fstat(fd)
        if st.st_uid!=os.geteuid() or st.st_mode&0o077:raise Failure('private_intent_directory_required')
        result=fd;fd=None;return result
    finally:
        if fd is not None:os.close(fd)


def private_delivery(raw,code,period):
    if not raw or len(raw)>4096:raise Failure('private_result_rejected')
    value=json.loads(raw)
    if type(value) is not dict or set(value)!={'link','code','period'} or value['code']!=code or type(value['period']) is not int or value['period']!=period:raise Failure('private_result_rejected')
    link=value['link']
    if type(link) is not str or len(link)>2048 or not re.fullmatch(r'https://pan\.baidu\.com/(?:s/[A-Za-z0-9_-]{6,128}|netdisk/share\?surl=[A-Za-z0-9_-]{6,128})',link):raise Failure('private_result_rejected')
    if not all(os.isatty(fd) for fd in (0,1,2)):raise Failure('private_terminal_required')
    fd=os.open('/dev/tty',os.O_WRONLY|os.O_NOCTTY|os.O_CLOEXEC)
    try:
        if not os.isatty(fd) or os.tcgetpgrp(fd)!=os.getpgrp():raise Failure('private_terminal_required')
        os.write(fd,('Private owner review only; recipient access has not been tested.\n'+link+'\nCode: '+code+'\nPeriod days: '+str(period)+'\n').encode())
    finally:os.close(fd)


def share_main(argv):
    parser=ShareParser(description='One new in-memory login, one original-sample share, one own-share history page for verification. No saved credentials.')
    parser.add_argument('--expectations',required=True,metavar='PRIVATE_JSON')
    parser.add_argument('--period',required=True,type=int,choices=range(1,8))
    parser.add_argument('--allow-own-share-page',action='store_true')
    parser.add_argument('--intent-dir',metavar='PRIVATE_DIR')
    args=parser.parse_args(argv)
    if not args.allow_own_share_page:raise Failure('own_share_page_scope_required')
    expected=sample_expectation(args.expectations)
    intent=private_intent_directory(args.intent_dir or str(Path.home()/'.local/state/fast-transfer/original-share-intents'))
    rd=wr=None;process=None;report=None;username=password=code=payload=None
    try:
        key=hashlib.sha256((expected['account']+':'+expected['fsid']).encode()).hexdigest()+'.json'
        try:
            os.stat(key,dir_fd=intent,follow_symlinks=False)
        except FileNotFoundError:pass
        else:
            print('{"status":"share_intent_already_consumed_no_login","credentials_saved":false,"share_requests":0}')
            return 1
        if not all(os.isatty(fd) for fd in (0,1,2)):raise Failure('interactive_terminal_required')
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        root=Path(__file__).resolve().parent;helper=root/'BaiduPCS-Go.login-session'
        st=helper.lstat();manifest=json.loads((root/'installation.json').read_text())
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_mode&0o022:raise Failure('helper_file_rejected')
        with helper.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
        if digest!=manifest['login_session_sha256']:raise Failure('helper_hash_mismatch')
        print('NEW login and ONE exact original-sample share. Password: wappass.baidu.com; BDUSS: pan.baidu.com only.\nReads the exact original parent and ONE newest own-share history page; no other pages.\nPeriod days: '+str(args.period)+'. Cookie stays in memory; durable private intent stores no credentials/link/code.\nNo retry, upload or migration. A created share may require manual review if verification fails.',flush=True)
        if secret('Type LOGIN-SHARE to proceed (hidden): ',limit=16)!='LOGIN-SHARE':raise Failure('share_confirmation_declined')
        code=secret('Choose 4 lowercase letters/digits (hidden): ',limit=4)
        if not re.fullmatch('[a-z0-9]{4}',code):raise Failure('share_code_rejected')
        username=secret('Baidu account (hidden): ',limit=256);password=secret('Baidu password (hidden): ',limit=512)
        rd,wr=os.pipe()
        data={'username':username,'password':password,'expected_account_sha256':'','session_only':True,
              'share':{'sample':expected,'period':args.period,'code':code,'allow_own_share_page':True,'intent_dir_fd':intent,'private_result_fd':wr}}
        payload=json.dumps(data).encode();data=None
        with tempfile.TemporaryDirectory(prefix='ft-login-share-empty-') as tmp:
            process=subprocess.Popen([str(helper)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                  pass_fds=(intent,wr),close_fds=True,env={'HOME':tmp,'TMPDIR':tmp,'XDG_CONFIG_HOME':tmp,'GOTELEMETRY':'off'})
            os.close(wr);wr=None
            try:stdout,_=process.communicate(payload,timeout=100)
            except (subprocess.TimeoutExpired,KeyboardInterrupt):
                process.kill();process.communicate()
                print('{"status":"authentication_or_share_outcome_unknown","credentials_saved":false,"automatic_retry_allowed":false}')
                return 1
        payload=username=password=None
        report=safe_report(stdout,share=True)
        private=os.read(rd,4097)
        required=('netdisk_identity_accepted','expected_account_checked','own_share_page_read','closed','original_object_matched','share_intent_consumed','share_created','own_share_record_matched','share_password_confirmed','share_expiry_bounded','expected_account_matches','private_result_written')
        if report.get('private_result_written'):
            if not all(report.get(k) is True for k in required) or report.get('share_requests')!=1 or report.get('share_creation_outcome_unknown') is not False:raise Failure('private_result_rejected')
            private_delivery(private,code,args.period)
            report['owner_terminal_delivery_confirmed']=True
        elif private:raise Failure('unexpected_private_result')
        print(json.dumps(report))
        return 0 if report.get('private_result_written') is True else 1
    except (Exception,KeyboardInterrupt):
        if process is not None:
            if report is not None:
                report['status']='share_created_private_delivery_failed' if report.get('share_created') else 'authentication_or_share_outcome_unknown'
                report['owner_terminal_delivery_confirmed']=False
                report['automatic_retry_allowed']=False
                print(json.dumps(report))
            else:
                print('{"status":"authentication_or_share_outcome_unknown","credentials_saved":false,"share_requests_may_have_occurred":true,"automatic_retry_allowed":false}')
            return 1
        raise
    finally:
        username=password=code=payload=None
        if process is not None and process.poll() is None:process.kill();process.communicate()
        for fd in (rd,wr,intent):
            if fd is not None:os.close(fd)


if __name__=='__main__':
    try:raise SystemExit(main())
    except (Exception,KeyboardInterrupt):
        print('{"status":"login_session_frontend_stopped","credentials_saved":false,"share_requests":0}')
        raise SystemExit(1)

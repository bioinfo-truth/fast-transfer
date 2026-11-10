"""Only generated credentials on owned PTYs; no auth/helper invocation."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_mcp_terminal as terminal_tests
SYNTHETIC=terminal_tests.SYNTHETIC

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/baidupcs-go-login-session.py'
spec=importlib.util.spec_from_file_location('pcs_session_frontend',SCRIPT);p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class PCSFrontendTests(unittest.TestCase):
    setUp=terminal_tests.TerminalTests.setUp
    until=terminal_tests.TerminalTests.until
    finish=terminal_tests.TerminalTests.finish
    # Reuse only PTY lifecycle helpers; test the new installed frontend routine.
    def start(self,tail='',timeout=.6):
        import fcntl,pty,termios
        master,slave=pty.openpty();original=termios.tcgetattr(slave)
        code="""import importlib.util,sys,hashlib
s=importlib.util.spec_from_file_location('front',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
try:
 value=m.secret('SECRET> ',timeout=float(sys.argv[2]));print('HASH='+hashlib.sha256(value.encode()).hexdigest(),flush=True)
except m.Failure as e:print('STOP='+str(e),flush=True)
"""
        def attach():fcntl.ioctl(0,termios.TIOCSCTTY,0)
        proc=subprocess.Popen([sys.executable,'-I','-S','-B','-c',code,str(SCRIPT),str(timeout)],stdin=slave,stdout=slave,stderr=slave,env={},close_fds=True,start_new_session=True,preexec_fn=attach)
        def cleanup():
            if proc.poll() is None:proc.kill();proc.wait(timeout=3)
            os.close(master);os.close(slave)
        self.addCleanup(cleanup)
        return proc,master,slave,original,self.until(master,b'SECRET> ')
    def test_new_frontend_echo_and_restoration(self):
        terminal_tests.TerminalTests.test_real_pty_input_not_echoed_and_terminal_restored(self)
    def test_new_frontend_cancel(self):
        proc,master,slave,old,trace=self.start();os.write(master,SYNTHETIC+b'\x03PENDING\n')
        output=self.finish(proc,master,slave,old,trace)
        self.assertIn(b'terminal_cancelled',output);self.assertNotIn(b'PENDING',output)
    def test_new_frontend_timeout(self):
        proc,master,slave,old,trace=self.start(timeout=.1)
        self.assertIn(b'terminal_input_timeout',self.finish(proc,master,slave,old,trace))
    def test_new_frontend_noninteractive_has_no_fallback(self):
        with patch.object(p.os,'isatty',return_value=False),patch.object(p.os,'open',side_effect=AssertionError('no file read')):
            with self.assertRaises(p.Failure):p.secret('secret:')
    def test_new_frontend_rejects_reflected_or_extra_fields(self):
        good={'status':'session_identity_verified_no_persistence','phase':'session_identity','request_attempts':5,'authentication_post_attempts':1,'auth_code':'0','session_cookie_received':True,'netdisk_identity_accepted':True,'expected_account_checked':False,'expected_account_matches':False,'credentials_saved':False,'share_requests':0,'closed':True}
        self.assertEqual(p.safe_report(json.dumps(good).encode()),good)
        for key,value in [('bduss',SYNTHETIC.decode()),('auth_code',SYNTHETIC.decode()),('status',SYNTHETIC.decode()),('credentials_saved',True),('share_requests',1),('authentication_post_attempts',2),('request_attempts',True)]:
            bad={**good,key:value}
            with self.assertRaises(p.Failure):p.safe_report(json.dumps(bad).encode())
    def test_new_frontend_argv_or_pipe_rejected_before_helper(self):
        for args in (['--session-only'],['--password=SYNTHETIC_DO_NOT_ECHO']):
            result=subprocess.run([sys.executable,'-I','-S','-B',str(SCRIPT),*args],env={},stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3)
            self.assertEqual(result.returncode,1);self.assertNotIn(b'SYNTHETIC_DO_NOT_ECHO',result.stdout+result.stderr)

class PCSShareFrontendTests(unittest.TestCase):
    def setUp(self):
        import tempfile,hashlib
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        task='job-'+'a'*32
        self.e={'task':task,'account':'sha256:'+hashlib.sha256(b'3003').hexdigest(),'application':'Xtransfer','fsid':'4004','path':'/apps/Xtransfer/mvp-validation/'+task+'/GCF_000005845.2_ASM584v2_genomic.fna.gz','size':1379902,'md5':'c13d459b5caa702ff7e1f26fe44b8ad7','sha256':'a96d3cfa58c88d477013c768f90a11d2386d42a70d566abfb6d9013dcbd24255'}
        self.e['mapping_sha256']=hashlib.sha256(json.dumps(self.e,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.file=self.root/'expected.json';self.file.write_text(json.dumps(self.e));self.file.chmod(0o600)
    def test_private_source_shape_and_mapping(self):
        self.assertEqual(p.sample_expectation(self.file),self.e)
        v={**self.e,'fsid':'5005'};self.file.write_text(json.dumps(v))
        with self.assertRaises(p.Failure):p.sample_expectation(self.file)
    def test_public_permission_and_symlink_rejected(self):
        self.file.chmod(0o644)
        with self.assertRaises(p.Failure):p.sample_expectation(self.file)
        self.file.chmod(0o600);link=self.root/'link.json';link.symlink_to(self.file)
        with self.assertRaises(OSError):p.sample_expectation(link)
    def test_history_consent_precedes_all_credentials(self):
        with patch.object(p,'secret',side_effect=AssertionError('no input')):
            with self.assertRaises(p.Failure):p.share_main(['--expectations',str(self.file),'--period','7'])
    def test_consumed_intent_stops_before_login(self):
        import hashlib,contextlib,io
        d=self.root/'intents';d.mkdir(mode=0o700);key=hashlib.sha256((self.e['account']+':'+self.e['fsid']).encode()).hexdigest()+'.json';(d/key).write_text('{}')
        with patch.object(p,'secret',side_effect=AssertionError('no input')),contextlib.redirect_stdout(io.StringIO()) as out:
            result=p.share_main(['--expectations',str(self.file),'--period','7','--allow-own-share-page','--intent-dir',str(d)])
        self.assertEqual(result,1);self.assertIn('already_consumed',out.getvalue())
    def test_directory_symlink_is_not_followed(self):
        target=self.root/'real';target.mkdir(mode=0o700);link=self.root/'link';link.symlink_to(target)
        with self.assertRaises(OSError):p.private_intent_directory(link)
    def test_private_link_never_falls_back_to_stdout(self):
        raw=b'{"link":"https://pan.baidu.com/s/SYNTHETIC_LINK_ONLY","code":"a1b2","period":7}'
        with patch.object(p.os,'isatty',return_value=False),patch.object(p.os,'open',side_effect=AssertionError('no fallback')):
            with self.assertRaises(p.Failure):p.private_delivery(raw,'a1b2',7)
    def test_share_status_does_not_authorize_other_commands(self):
        result={'status':'share_mapping_verified_private_result_ready','phase':'share_password','request_attempts':9,'authentication_post_attempts':1,'share_requests':1,'credentials_saved':False,'private_result_written':True}
        self.assertEqual(p.safe_report(json.dumps(result).encode(),share=True),result)
        with self.assertRaises(p.Failure):p.safe_report(json.dumps(result).encode())

    def test_combined_frontend_pipe_keeps_link_off_status_stdout(self):
        import fcntl,hashlib,pty,select,shutil,termios,time
        install=self.root/'installation';install.mkdir()
        frontend=install/'login-session.py';shutil.copyfile(SCRIPT,frontend)
        helper=install/'BaiduPCS-Go.login-session'
        helper.write_text('''#!/usr/bin/python3
import json,os,stat,sys
v=json.load(sys.stdin);p=v['share'];assert stat.S_ISDIR(os.fstat(p['intent_dir_fd']).st_mode)
assert v['username']=='SYNTHETIC_USER' and v['password']=='SYNTHETIC_PASSWORD'
os.write(p['private_result_fd'],json.dumps({'link':'https://pan.baidu.com/s/SYNTHETIC_LINK_ONLY','code':p['code'],'period':p['period']}).encode())
r={'status':'share_mapping_verified_private_result_ready','phase':'share_password','request_attempts':9,'authentication_post_attempts':1,'share_requests':1,'credentials_saved':False,'netdisk_identity_accepted':True,'expected_account_checked':True,'expected_account_matches':True,'original_object_matched':True,'share_intent_consumed':True,'share_creation_outcome_unknown':False,'share_created':True,'own_share_record_matched':True,'share_password_confirmed':True,'share_expiry_bounded':True,'own_share_page_read':True,'private_result_written':True,'recipient_access_verified':False,'closed':True}
print(json.dumps(r))
''');helper.chmod(0o700)
        (install/'installation.json').write_text(json.dumps({'login_session_sha256':hashlib.sha256(helper.read_bytes()).hexdigest()}))
        master,slave=pty.openpty();status_master,status_slave=pty.openpty()
        def attach():fcntl.ioctl(0,termios.TIOCSCTTY,0)
        proc=subprocess.Popen([sys.executable,'-I','-S','-B',str(frontend),'--share-original','--expectations',str(self.file),'--period','7','--allow-own-share-page','--intent-dir',str(self.root/'intents')],stdin=slave,stdout=status_slave,stderr=slave,env={},close_fds=True,start_new_session=True,preexec_fn=attach)
        transcript=bytearray();status=bytearray()
        try:
            for marker,value in [(b'Type LOGIN-SHARE',b'LOGIN-SHARE\n'),(b'Choose 4',b'a1b2\n'),(b'Baidu account',b'SYNTHETIC_USER\n'),(b'Baidu password',b'SYNTHETIC_PASSWORD\n')]:
                deadline=time.monotonic()+4
                while marker not in transcript:
                    if time.monotonic()>deadline:self.fail('synthetic PTY marker timeout')
                    ready,_,_=select.select([master,status_master],[],[],.1)
                    for fd in ready:
                        data=os.read(fd,8192)
                        (transcript if fd==master else status).extend(data)
                self.assertFalse(termios.tcgetattr(slave)[3]&termios.ECHO)
                os.write(master,value)
            proc.wait(timeout=5)
            for fd,target in [(master,transcript),(status_master,status)]:
                while select.select([fd],[],[],.05)[0]:target.extend(os.read(fd,8192))
            self.assertEqual(proc.returncode,0)
            self.assertIn(b'SYNTHETIC_LINK_ONLY',transcript);self.assertIn(b'a1b2',transcript)
            self.assertNotIn(b'SYNTHETIC_LINK_ONLY',status);self.assertNotIn(b'a1b2',status)
            for secret in (b'SYNTHETIC_PASSWORD',b'SYNTHETIC_USER'):
                self.assertNotIn(secret,transcript+status)
        finally:
            if proc.poll() is None:proc.kill();proc.wait(timeout=3)
            for fd in (master,slave,status_master,status_slave):os.close(fd)

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

"""Synthetic TTY-only data flow. Child network remains seccomp-denied.

Parent sends only synthetic bytes to an owned PTY, never existing terminals.
Child argv/env contain no synthetic token. No real credentials/config/services.
"""
import contextlib
from dataclasses import asdict
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest.mock import patch,MagicMock

from test_mcp_share import guarded
from fast_transfer import mcp_terminal as t,mcp_share as m,mcp_sse as s
from fast_transfer.mcp_binding import ExpectedObject
from fast_transfer.mcp_official_http import OfficialHTTPSDriver

ROOT=Path(__file__).resolve().parents[1]
SYNTHETIC=b'SYNTHETIC_TOKEN_9x7+/='


def expected():return ExpectedObject('synthetic-task','3003','Xtransfer','4004','/apps/Xtransfer/synthetic',16,'a'*32,'b'*64,'c'*64)


class TerminalTests(unittest.TestCase):
    def setUp(self):
        if not guarded():self.skipTest('requires kernel guard runner')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def start(self,tail='',timeout=.6):
        master,slave=pty.openpty();original=termios.tcgetattr(slave)
        source="""import sys,json,hashlib,os
sys.path.insert(0,sys.argv[1])
from fast_transfer.mcp_terminal import read_secret,TerminalFailure
try:
 secret=read_secret('SECRET> ',timeout=float(sys.argv[2]))
 print('ACCEPTED',flush=True)
 """+tail+"""
 print('HASH='+hashlib.sha256(secret.encode()).hexdigest(),flush=True)
except TerminalFailure as exc:print('STOP='+exc.args[0],flush=True)
"""
        def attach():fcntl.ioctl(0,termios.TIOCSCTTY,0)
        process=subprocess.Popen([sys.executable,'-I','-S','-B','-c',source,str(ROOT),str(timeout)],
            stdin=slave,stdout=slave,stderr=slave,env={},close_fds=True,start_new_session=True,preexec_fn=attach)
        def cleanup():
            if process.poll() is None:process.kill();process.wait(timeout=3)
            os.close(master);os.close(slave)
        self.addCleanup(cleanup)
        transcript=self.until(master,b'SECRET> ')
        return process,master,slave,original,transcript
    def until(self,fd,marker,timeout=3):
        value=bytearray();deadline=time.monotonic()+timeout
        while marker not in value:
            left=deadline-time.monotonic()
            if left<=0:self.fail('owned PTY marker timeout')
            if not select.select([fd],[],[],left)[0]:self.fail('owned PTY select timeout')
            value.extend(os.read(fd,4096))
        return bytes(value)
    def finish(self,p,master,slave,original,before,marker=b'STOP='):
        transcript=before+self.until(master,marker)
        p.wait(timeout=3)
        self.assertEqual(p.returncode,0)
        self.assertEqual(termios.tcgetattr(slave),original)
        self.assertNotIn(SYNTHETIC,transcript)
        return transcript
    def test_real_pty_input_not_echoed_and_terminal_restored(self):
        p,master,slave,old,trace=self.start()
        self.assertFalse(termios.tcgetattr(slave)[3]&termios.ECHO)
        os.write(master,SYNTHETIC+b'\n')
        transcript=self.finish(p,master,slave,old,trace,marker=b'HASH=')
        self.assertIn(hashlib.sha256(SYNTHETIC).hexdigest().encode(),transcript)
    def test_noninteractive_rejects_without_opening_tty_or_fallback(self):
        with patch.object(os,'isatty',return_value=False),patch.object(os,'open',side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(t.TerminalFailure,'interactive_required'):t.read_secret()
    def test_no_controlling_terminal_rejects_without_echo_fallback(self):
        with patch.object(os,'isatty',return_value=True),patch.object(os,'open',side_effect=OSError('SYNTHETIC_PRIVATE')):
            with self.assertRaisesRegex(t.TerminalFailure,'input_unavailable') as exc:t.read_secret()
        self.assertNotIn('SYNTHETIC_PRIVATE',str(exc.exception))
    def test_cancel_byte_restores_and_flushes_pending_input(self):
        p,master,slave,old,trace=self.start();os.write(master,SYNTHETIC+b'\x03UNCONSUMED\n')
        transcript=self.finish(p,master,slave,old,trace)
        self.assertIn(b'terminal_input_cancelled',transcript);self.assertNotIn(b'UNCONSUMED',transcript)
    def test_eof_byte_restores_without_returning_secret(self):
        p,master,slave,old,trace=self.start();os.write(master,SYNTHETIC+b'\x04')
        self.assertIn(b'terminal_input_eof',self.finish(p,master,slave,old,trace))
    def test_timeout_restores_without_returning_partial_secret(self):
        p,master,slave,old,trace=self.start(timeout=.15);os.write(master,SYNTHETIC)
        self.assertIn(b'terminal_input_timeout',self.finish(p,master,slave,old,trace))
    def test_signal_termination_restores_terminal_and_sanitizes(self):
        p,master,slave,old,trace=self.start();os.write(master,SYNTHETIC);p.send_signal(signal.SIGTERM)
        self.assertIn(b'terminal_input_cancelled',self.finish(p,master,slave,old,trace))
    def test_input_not_in_child_argv_env_no_children_or_persistent_files(self):
        # Hold the secret in the child memory only while parent inspects metadata.
        p,master,slave,old,trace=self.start(tail="import time;time.sleep(.3)\n")
        os.write(master,SYNTHETIC+b'\n');trace+=self.until(master,b'ACCEPTED')
        for filename in ('cmdline','environ'):
            self.assertNotIn(SYNTHETIC,(Path('/proc')/str(p.pid)/filename).read_bytes())
        children=Path('/proc')/str(p.pid)/'task'/str(p.pid)/'children'
        self.assertEqual(children.read_text().strip(),'')
        self.assertEqual(list(self.root.iterdir()),[])
        self.finish(p,master,slave,old,trace,marker=b'HASH=')
    def test_invalid_control_character_refuses_and_restores(self):
        p,master,slave,old,trace=self.start();os.write(master,SYNTHETIC+b'\x1b')
        self.assertIn(b'terminal_input_invalid',self.finish(p,master,slave,old,trace))
    def test_expectation_file_requires_private_regular_owned_file(self):
        path=self.root/'expect.json';path.write_text(json.dumps(asdict(expected())));path.chmod(0o600)
        self.assertEqual(t.load_expected(path),expected())
        path.chmod(0o644)
        with self.assertRaises(t.TerminalFailure):t.load_expected(path)
        link=self.root/'link';link.symlink_to(path)
        with self.assertRaises(OSError):t.load_expected(link)
    def test_parser_never_echoes_unknown_secret_argument(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
            code=t.main(['--token',SYNTHETIC.decode()])
        self.assertEqual(code,1);self.assertNotIn(SYNTHETIC.decode(),output.getvalue())
    def test_confirmation_decline_does_not_ask_for_token_or_network(self):
        output=io.StringIO()
        with patch.object(t,'load_expected',return_value=expected()),patch.object(t,'read_secret',return_value='NO') as read,patch.object(t,'run_readonly',side_effect=AssertionError('no network')),contextlib.redirect_stdout(output):
            code=t.main(['--expectations','synthetic','--read-only'])
        self.assertEqual(code,1);self.assertEqual(read.call_count,1)
    def test_raw_operation_exception_is_private_and_driver_closed(self):
        driver=OfficialHTTPSDriver(access_token=SYNTHETIC.decode());self.addCleanup(driver.close)
        with patch.object(t,'OfficialHTTPSDriver',return_value=driver),patch.object(t._TerminalReadSession,'official_readonly',side_effect=RuntimeError(SYNTHETIC.decode())):
            report=t.run_readonly(expected(),SYNTHETIC.decode())
        self.assertNotIn(SYNTHETIC.decode(),json.dumps(report));self.assertTrue(report['close_confirmed'])
        self.assertIsNone(driver._token);self.assertEqual(driver.trace,[])
    def test_input_does_not_open_real_share_gate_or_write_job(self):
        driver=OfficialHTTPSDriver(access_token=SYNTHETIC.decode());self.addCleanup(driver.close)
        session=t._TerminalReadSession.official_readonly(driver,expected())
        with self.assertRaises(m.Rejected):session.tool('file_sharelink_set',expected().arguments(7,'a1b2'))
        with patch.object(t,'OfficialHTTPSDriver',return_value=driver),patch.object(t._TerminalReadSession,'official_readonly',return_value=session),patch.object(session,'inspect',return_value={'candidate_fields_match':True,'live_authenticated':False,'share_eligible':False}):
            report=t.run_readonly(expected(),SYNTHETIC.decode())
        self.assertFalse(report['share_attempted'] or report['delivery_eligible']);self.assertEqual(list(self.root.iterdir()),[])
    def test_complete_main_two_hidden_prompts_without_token_output(self):
        path=self.root/'expect.json';path.write_text(json.dumps(asdict(expected())));path.chmod(0o600)
        master,slave=pty.openpty();old=termios.tcgetattr(slave)
        source="""import sys
sys.path.insert(0,sys.argv[1])
from fast_transfer import mcp_terminal as t
# Test-only synthetic operation: no subprocess/network callback from production.
def fake(expected,token):
 assert token and expected.fsid=='4004'
 return {'reason':'mcp_share_prerequisites_unproven','share_eligible':False}
t.run_readonly=fake
raise SystemExit(t.main(['--expectations',sys.argv[2],'--read-only']))
"""
        def attach():fcntl.ioctl(0,termios.TIOCSCTTY,0)
        p=subprocess.Popen([sys.executable,'-I','-S','-B','-c',source,str(ROOT),str(path)],
            stdin=slave,stdout=slave,stderr=slave,env={},close_fds=True,start_new_session=True,preexec_fn=attach)
        def cleanup():
            if p.poll() is None:p.kill();p.wait(timeout=3)
            os.close(master);os.close(slave)
        self.addCleanup(cleanup)
        trace=self.until(master,b'Type READ-ONLY')
        # Wait for the complete first prompt, ensuring echo is already disabled.
        if b'(hidden): ' not in trace:trace+=self.until(master,b'(hidden): ')
        os.write(master,b'READ-ONLY\n');trace+=self.until(master,b'Short-lived access_token (hidden): ')
        os.write(master,SYNTHETIC+b'\n');trace+=self.until(master,b'mcp_share_prerequisites_unproven')
        p.wait(timeout=3);self.assertEqual(p.returncode,0)
        self.assertEqual(termios.tcgetattr(slave),old);self.assertNotIn(SYNTHETIC,trace)
        self.assertNotIn(SYNTHETIC,path.read_bytes());self.assertEqual(list(self.root.iterdir()),[path])
    def test_schema_discovery_precedes_exact_account_and_single_file_no_share(self):
        from test_mcp_sse import script,tool
        steps=script()[:5]
        steps[3]=('tools/call','user_info',tool(3,{'uk':'3003'}))
        steps[4]=('tools/call','file_meta',tool(4,{'list':[{'fsid':'4004','path':expected().path,'size':16,'md5':'a'*32}]}))
        driver=OfficialHTTPSDriver(access_token=SYNTHETIC.decode());self.addCleanup(driver.close)
        wire=s.ScriptedHTTP(steps,opening=b'event: endpoint\ndata: /message?sessionId=synthetic\n\n')
        def post(url,raw):
            s.message_endpoint(url,profile='official')
            return wire.post(s.ORIGIN+'/messages?session_id=synthetic',raw)
        with patch.object(t,'OfficialHTTPSDriver',return_value=driver),patch.object(driver,'open',side_effect=wire.open),patch.object(driver,'read',side_effect=wire.read),patch.object(driver,'post',side_effect=post):
            report=t.run_readonly(expected(),SYNTHETIC.decode())
        self.assertTrue(report['candidate_fields_match']);self.assertFalse(report['share_eligible'])
        calls=[v.get('tool') for v in wire.trace if v.get('tool')]
        self.assertEqual(calls,['user_info','file_meta']);self.assertIsNone(driver._token)
    def test_empty_or_unknown_schema_stops_before_account_or_file(self):
        from test_mcp_sse import script,result
        steps=script()[:3];steps[2]=('tools/list',None,result(2,{'tools':[]}))
        driver=OfficialHTTPSDriver(access_token=SYNTHETIC.decode());self.addCleanup(driver.close)
        wire=s.ScriptedHTTP(steps,opening=b'event: endpoint\ndata: /message?sessionId=synthetic\n\n')
        def post(url,raw):return wire.post(s.ORIGIN+'/messages?session_id=synthetic',raw)
        with patch.object(t,'OfficialHTTPSDriver',return_value=driver),patch.object(driver,'open',side_effect=wire.open),patch.object(driver,'read',side_effect=wire.read),patch.object(driver,'post',side_effect=post):
            report=t.run_readonly(expected(),SYNTHETIC.decode())
        self.assertEqual(report['reason'],'mcp_sse_schema_unproven')
        self.assertEqual(report['discovery']['tool_count'],0)
        self.assertFalse(any(v.get('tool') for v in wire.trace));self.assertIsNone(driver._token)
    def test_timeout_one_attempt_and_unconfirmed_close_stays_manual(self):
        driver=OfficialHTTPSDriver(access_token=SYNTHETIC.decode());self.addCleanup(driver.close)
        session=t._TerminalReadSession.official_readonly(driver,expected())
        with patch.object(t,'OfficialHTTPSDriver',return_value=driver),patch.object(t._TerminalReadSession,'official_readonly',return_value=session),patch.object(session,'inspect',side_effect=TimeoutError(SYNTHETIC.decode())) as inspect,patch.object(session,'close',return_value=False):
            report=t.run_readonly(expected(),SYNTHETIC.decode())
        inspect.assert_called_once();self.assertEqual(report['status'],'manual_review')
        self.assertFalse(report['close_confirmed'] or report['automatic_retry_allowed'])
        self.assertNotIn(SYNTHETIC.decode(),json.dumps(report))
    def test_actual_entry_noninteractive_refuses_without_network_or_token(self):
        path=self.root/'expect.json';path.write_text(json.dumps(asdict(expected())));path.chmod(0o600)
        p=subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'tools/mcp_terminal_readonly.py'),
            '--expectations',str(path),'--read-only'],env={},stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,timeout=3)
        self.assertEqual(p.returncode,1);self.assertEqual(p.stderr,b'')
        self.assertIn(b'terminal_interactive_required',p.stdout);self.assertNotIn(SYNTHETIC,p.stdout)
        self.assertEqual(list(self.root.iterdir()),[path])
    def test_terminal_schema_report_never_copies_arbitrary_server_fields(self):
        driver=OfficialHTTPSDriver(access_token=SYNTHETIC.decode());self.addCleanup(driver.close)
        session=t._TerminalReadSession.official_readonly(driver,expected())
        with self.assertRaises(m.Rejected):
            session.review_descriptors({'user_info':{'properties':{SYNTHETIC.decode():{'default':SYNTHETIC.decode()}}}})
        self.assertNotIn(SYNTHETIC.decode(),json.dumps(session.schema_report))
    def test_discovery_mode_needs_no_receipt_and_never_enters_readonly(self):
        output=io.StringIO()
        with patch.object(t,'read_secret',side_effect=['DISCOVER-ONLY',SYNTHETIC.decode()]),patch.object(t,'load_expected',side_effect=AssertionError('no receipt reads')),patch.object(t,'run_readonly',side_effect=AssertionError('no account calls')),patch.object(t,'run_discovery',return_value={'reason':'terminal_discovery_complete'}) as operation,contextlib.redirect_stdout(output):
            code=t.main(['--discover-only'])
        self.assertEqual(code,0);operation.assert_called_once_with(SYNTHETIC.decode())
        self.assertNotIn(SYNTHETIC.decode(),output.getvalue())
    def test_credential_discovery_rpc_and_tool_calls_cannot_access_account(self):
        driver=OfficialHTTPSDriver(access_token=SYNTHETIC.decode());self.addCleanup(driver.close)
        session=t._TerminalDiscoverySession(driver)
        for method in ('tools/call','resources/read'):
            with self.assertRaises(m.Rejected):session.rpc(method)
        with self.assertRaises(m.Rejected):session.tool('user_info',{})
        self.assertEqual(driver.trace,[])
    def test_discovery_mode_full_synthetic_wire_and_no_arbitrary_schema_output(self):
        from test_mcp_sse import script,result
        steps=script()[:3]
        steps[2]=('tools/list',None,result(2,{'tools':[{'name':'user_info','inputSchema':{
            'type':'object','properties':{SYNTHETIC.decode():{'default':SYNTHETIC.decode()}}}}]}))
        driver=OfficialHTTPSDriver(access_token=SYNTHETIC.decode());self.addCleanup(driver.close)
        wire=s.ScriptedHTTP(steps,opening=b'event: endpoint\ndata: /message?sessionId=synthetic\n\n')
        def post(url,raw):return wire.post(s.ORIGIN+'/messages?session_id=synthetic',raw)
        with patch.object(t,'OfficialHTTPSDriver',return_value=driver),patch.object(driver,'open',side_effect=wire.open),patch.object(driver,'read',side_effect=wire.read),patch.object(driver,'post',side_effect=post):
            report=t.run_discovery(SYNTHETIC.decode())
        self.assertEqual(report['reason'],'terminal_discovery_complete')
        self.assertEqual(report['discovery']['tool_count'],1)
        self.assertFalse(report['discovery']['known_tools']['user_info']['candidate_schema_match'])
        self.assertFalse(any(item.get('tool') for item in wire.trace));self.assertIsNone(driver._token)
        self.assertNotIn(SYNTHETIC.decode(),json.dumps(report))

"""Real loopback TCP/TLS tests. Run ONLY with the dedicated local fixture runner."""
import json
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from support.local_sse_server import Case
from test_mcp_share import prepare
from fast_transfer import mcp_http as h, mcp_sse as s, mcp_share as m

FIXTURE_SERVER=None
CERTS=None


class LocalHTTPTests(unittest.TestCase):
    def setUp(self):
        if FIXTURE_SERVER is None:self.skipTest('requires tests/support/run_local_sse.py')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.job=prepare(self.root);self.drivers=[]
        self.addCleanup(self.cleanup)
    def cleanup(self):
        for d in self.drivers:d.close()
        FIXTURE_SERVER.reset(Case())
    def case(self,mode='normal',context=None):
        c=Case(mode,context);FIXTURE_SERVER.reset(c);return c
    def driver(self,trust='good',**kw):
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);ctx.minimum_version=ssl.TLSVersion.TLSv1_2
        if trust:ctx.load_verify_locations(cafile=CERTS[trust][0])
        d=h.LocalHTTPSDriver(FIXTURE_SERVER.server_port,ctx,**kw);self.drivers.append(d);return d
    def exercise(self,mode='normal',**kw):
        c=self.case(mode);d=self.driver(**kw);start=time.monotonic()
        r=s.exercise_local_fixture(self.job,d,pwd='a1b2')
        elapsed=time.monotonic()-start
        self.assertFalse(r['live_connected']);self.assertFalse(r['external_service_connected'])
        self.assertEqual(r['transport_scope'],'local-loopback-tls');self.assertFalse(r['delivery_eligible'])
        self.assertEqual(r['local_tls_connected'],d.tls_version is not None)
        print('LOCAL_SSE_EVIDENCE '+json.dumps({'mode':mode,'elapsed_seconds':elapsed,'TLS':d.tls_version,
            'GETs':c.gets,'POSTs':c.posts,'shares':c.shares,'status':r['status'],'reason':r['reason'],
            'create_attempted':r['create_attempted'],'unknown':r['outcome_unknown'],'closed':r['protocol_closed']}),flush=True)
        return r,d,c,elapsed
    def test_full_real_TLS_HTTP_SSE_handshake_and_single_synthetic_share(self):
        r,d,c,elapsed=self.exercise()
        self.assertEqual(r['status'],'candidate_unverified');self.assertTrue(r['protocol_closed'])
        self.assertIn(d.tls_version,('TLSv1.2','TLSv1.3'));self.assertEqual((c.gets,c.posts,c.shares),(1,6,1))
        self.assertEqual(self.job.view()['phase'],'manual_review')
        d2=self.driver();r2=s.exercise_local_fixture(self.job,d2,pwd='a1b2');self.assertEqual(d2.trace,[])
        self.assertFalse(r2['create_attempted']);self.assertTrue(r2['outcome_unknown']);self.assertEqual(c.shares,1)
    def test_untrusted_certificate_fails_before_HTTP_or_share(self):
        c=self.case();d=self.driver(trust=None)
        r=s.exercise_local_fixture(self.job,d,pwd='a1b2')
        self.assertEqual(r['reason'],'mcp_local_tls_error');self.assertFalse(r['create_attempted'])
        self.assertEqual((c.gets,c.posts,c.shares),(0,0,0))
    def test_hostname_mismatch_fails_with_trusted_but_wrong_SAN(self):
        c=self.case(context=CERTS['wrong'][1]);d=self.driver(trust='wrong')
        r=s.exercise_local_fixture(self.job,d,pwd='a1b2')
        self.assertEqual(r['reason'],'mcp_local_tls_error');self.assertFalse(r['create_attempted']);self.assertEqual(c.gets,0)
    def test_insecure_TLS_context_and_mutation_are_rejected(self):
        c=self.case();ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
        with self.assertRaisesRegex(m.Rejected,'tls_policy'):h.LocalHTTPSDriver(FIXTURE_SERVER.server_port,ctx)
        d=self.driver();d.context.check_hostname=False
        r=s.exercise_local_fixture(self.job,d,pwd='a1b2');self.assertEqual(r['reason'],'mcp_local_tls_policy_rejected')
        self.assertEqual(c.gets,0)
    def test_TLS_key_logging_context_is_rejected_before_network(self):
        c=self.case();ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);ctx.minimum_version=ssl.TLSVersion.TLSv1_2
        ctx.load_verify_locations(cafile=CERTS['good'][0]);ctx.keylog_filename=str(self.root/'synthetic-keylog')
        with self.assertRaisesRegex(m.Rejected,'tls_policy'):h.LocalHTTPSDriver(FIXTURE_SERVER.server_port,ctx)
        self.assertEqual(c.gets,0)
    def test_cross_origin_endpoint_over_actual_TLS_is_never_contacted(self):
        r,d,c,_=self.exercise('cross_origin')
        self.assertFalse(r['create_attempted']);self.assertEqual(c.posts,0)
        self.assertEqual(r['reason'],'mcp_sse_endpoint_rejected')
    def test_actual_bad_MIME_or_duplicate_headers_cannot_start_protocol(self):
        for mode in ('wrong_mime','duplicate_type'):
            r,d,c,_=self.exercise(mode)
            self.assertEqual(r['reason'],'mcp_local_headers_rejected');self.assertFalse(r['create_attempted'])
            self.assertEqual(c.posts,0)
    def test_GET_redirect_does_not_follow_or_leak_location(self):
        r,d,c,_=self.exercise('redirect_get')
        self.assertEqual(r['reason'],'mcp_local_status_rejected');self.assertFalse(r['create_attempted'])
        self.assertEqual((c.gets,c.posts),(1,0));self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(r)+json.dumps(d.trace))
    def test_share_redirect_is_unknown_once_and_never_followed_or_retried(self):
        r,d,c,_=self.exercise('redirect_share')
        self.assertTrue(r['create_attempted'] and r['outcome_unknown']);self.assertEqual(c.shares,1)
        self.assertEqual(r['reason'],'mcp_local_status_rejected')
        r2=s.exercise_local_fixture(self.job,self.driver(),pwd='a1b2');self.assertFalse(r2['create_attempted']);self.assertEqual(c.shares,1)
    def test_real_header_idle_timeout_is_bounded_and_closed(self):
        r,d,c,elapsed=self.exercise('stall_headers',io_timeout=.15,budget=1)
        self.assertEqual(r['reason'],'mcp_local_timeout');self.assertFalse(r['create_attempted']);self.assertLess(elapsed,2)
    def test_trickling_headers_interrupted_by_whole_driver_watchdog(self):
        r,d,c,elapsed=self.exercise('trickle_headers',io_timeout=.2,budget=.3)
        self.assertEqual(r['reason'],'mcp_local_deadline');self.assertFalse(r['create_attempted']);self.assertLess(elapsed,2)
    def test_real_TLS_handshake_stall_times_out_and_closes(self):
        r,d,c,elapsed=self.exercise('stall_tls',io_timeout=.15,budget=.6)
        self.assertIn(r['reason'],('mcp_local_timeout','mcp_local_deadline'));self.assertFalse(r['create_attempted'])
        self.assertEqual(c.gets,0);self.assertLess(elapsed,2)
    def test_real_SSE_idle_read_timeout_not_a_success(self):
        r,d,c,elapsed=self.exercise('stall_read',io_timeout=.15,budget=.8)
        self.assertEqual(r['reason'],'mcp_local_timeout');self.assertFalse(r['create_attempted']);self.assertLess(elapsed,2)
    def test_close_interrupts_actual_blocked_TLS_read(self):
        c=self.case('stall_read');d=self.driver(io_timeout=1,budget=3)
        self.assertEqual(d.open(d.endpoint,s.AUTH_SLOT)[0],200);out=[]
        def read():
            try:out.append(d.read(1024))
            except m.Rejected as exc:out.append(exc.args[0])
        thread=threading.Thread(target=read,daemon=True);thread.start();time.sleep(.05)
        self.assertTrue(thread.is_alive());start=time.monotonic();confirmed=d.close();thread.join(2)
        self.assertFalse(thread.is_alive());self.assertTrue(d.close());self.assertLess(time.monotonic()-start,2)
        self.assertFalse(any(type(x) is bytes and x for x in out))
        print('LOCAL_SSE_EVIDENCE '+json.dumps({'mode':'close_blocked_read','elapsed_seconds':time.monotonic()-start,'first_close_confirmed':confirmed,'final_close_confirmed':d.close(),'reader_exited':True}),flush=True)
    def test_peer_EOF_mid_SSE_frame_cannot_create(self):
        r,d,c,_=self.exercise('drop_frame')
        self.assertFalse(r['create_attempted']);self.assertEqual(c.shares,0);self.assertTrue(r['protocol_closed'])
    def test_wire_identity_drift_has_no_share_side_effect(self):
        r,d,c,_=self.exercise('wrong_identity')
        self.assertEqual(r['reason'],'mcp_fixture_identity_mismatch');self.assertEqual(c.shares,0)
    def test_accepted_synthetic_share_then_ACK_timeout_is_unknown_no_replay(self):
        r,d,c,elapsed=self.exercise('share_timeout',io_timeout=.15,budget=2)
        self.assertTrue(r['create_attempted'] and r['outcome_unknown']);self.assertEqual(c.shares,1)
        self.assertEqual(r['reason'],'mcp_local_timeout');posts=c.posts
        d2=self.driver();r2=s.exercise_local_fixture(self.job,d2,pwd='a1b2')
        self.assertEqual(d2.trace,[]);self.assertEqual(c.posts,posts);self.assertTrue(r2['outcome_unknown'])
    def test_corrupt_real_SSE_share_result_is_unknown_not_verified(self):
        r,d,c,_=self.exercise('corrupt_share')
        self.assertTrue(r['outcome_unknown']);self.assertEqual(c.shares,1);self.assertNotEqual(r['status'],'candidate_unverified')
    def test_external_factory_and_production_constructor_still_reject_before_socket(self):
        with patch('socket.socket',side_effect=AssertionError('no new sockets')) as sock:
            with self.assertRaisesRegex(m.Rejected,'external_driver_locked'):h.external_driver(credential_provider=lambda:'MUST_NOT_CALL')
            sock.assert_not_called()
        d=self.driver()
        with self.assertRaisesRegex(m.Rejected,'driver_unavailable'):s.SSEClient(d)
        with self.assertRaisesRegex(m.Rejected,'connection_unavailable'):m.live_connect()
    def test_local_scope_no_arbitrary_destinations_and_TCP_kernel_port_guard(self):
        c=self.case();d=self.driver()
        with self.assertRaises(m.Rejected):d.open(s.ENDPOINT,s.AUTH_SLOT)
        with self.assertRaises(m.Rejected):d.post('https://not-a-real-target.invalid/messages/?session_id=x',b'{}')
        self.assertEqual(c.gets,0)
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
            with self.assertRaises(PermissionError):probe.connect(('127.0.0.1',1))
    def test_logs_and_state_do_not_contain_private_result_or_proxy_values(self):
        with patch.dict('os.environ',{'HTTPS_PROXY':'http://synthetic-invalid-proxy.invalid','SSLKEYLOGFILE':'/nonexistent/synthetic-denied-keylog'}):
            r,d,c,_=self.exercise()
        text=json.dumps(r)+json.dumps(d.trace)+(self.job.root/'state.json').read_text()+repr(d)
        for value in ['synthetic_link','synthetic_short','a1b2','SYNTHETIC_PRIVATE','proxy.invalid','access_token']:
            self.assertNotIn(value,text)

    def test_initialize_POST_TLS_stall_is_distinct_and_not_retried(self):
        case=self.case('stall_post_tls');driver=self.driver(io_timeout=.15,budget=1)
        client=s.SSEClient.for_local_fixture(driver);self.addCleanup(client.close)
        with self.assertRaisesRegex(m.Rejected,'mcp_local_timeout'):client.connect()
        diag=client.protocol_diagnostics();transport=diag['transport']
        self.assertEqual(diag['stage'],'initialize_post');self.assertEqual(diag['http_statuses'],[200])
        self.assertEqual(transport['operation'],'rpc_post');self.assertEqual(transport['phase'],'tls_handshake')
        self.assertEqual(transport['connection'],2);self.assertFalse(transport['phase_completed'])
        self.assertFalse(transport['last_request_send_returned']);self.assertEqual(case.accepts,2)
        self.assertEqual((case.gets,case.posts,case.shares),(1,0,0))
        self.assertEqual(sum(x.get('operation')=='initialize' for x in driver.trace),1)
    def test_initialize_POST_header_stall_reproduces_user_stage_and_200_only(self):
        case=self.case('stall_post_headers');driver=self.driver(io_timeout=.15,budget=1)
        client=s.SSEClient.for_local_fixture(driver);self.addCleanup(client.close)
        with self.assertRaisesRegex(m.Rejected,'mcp_local_timeout'):client.connect()
        diag=client.protocol_diagnostics();transport=diag['transport']
        self.assertEqual(diag['stage'],'initialize_post');self.assertEqual(diag['http_statuses'],[200])
        self.assertEqual(transport['phase'],'response_headers');self.assertFalse(transport['phase_completed'])
        self.assertTrue(transport['last_request_send_returned']);self.assertFalse(transport['last_response_headers_received'])
        self.assertEqual((case.gets,case.posts,case.shares),(1,1,0))
        self.assertEqual(sum(x.get('operation')=='initialize' for x in driver.trace),1)
    def test_exact_81_byte_endpoint_is_consumed_with_zero_pending_buffer(self):
        case=self.case('endpoint_exact81');driver=self.driver()
        client=s.SSEClient.for_local_fixture(driver);self.addCleanup(client.close)
        driver.open(driver.endpoint,s.AUTH_SLOT)
        kind,value=client.event();self.assertEqual(kind,'endpoint')
        diag=client.protocol_diagnostics()
        self.assertEqual((diag['sse_bytes_read'],diag['event_bytes'],diag['event_count']),(81,81,1))
        self.assertEqual(diag['buffered_bytes'],0);self.assertEqual(diag['pending_line_bytes'],0)
        self.assertEqual(diag['line_buffer_high_water_bytes'],81)
        self.assertEqual((case.gets,case.posts,case.shares),(1,0,0))

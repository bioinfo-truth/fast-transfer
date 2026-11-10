"""Device flow: synthetic app secrets/codes only; inherited seccomp denies network."""
import contextlib
import io
import json
import os
import socket
import ssl
import unittest
from unittest.mock import patch,MagicMock

from fast_transfer import device_oauth as d,device_oauth_http as h,device_terminal as t,mcp_share as c

AK='SYNTHETIC_APP_KEY';SK='SYNTHETIC_SECRET_KEY';DC='SYNTHETIC_DEVICE_CODE';UC='SYNTHETIC_USER_CODE';AT='SYNTHETIC_ACCESS_TOKEN'


def device_response(**delta):return {'device_code':DC,'user_code':UC,'verification_url':'https://openapi.baidu.com/device',
    'qrcode_url':'http://openapi.baidu.com/device/qrcode/SYNTHETIC','expires_in':1800,'interval':5,**delta}
def token_response(**delta):return {'access_token':AT,'refresh_token':'SYNTHETIC_REFRESH','session_key':'SYNTHETIC_SESSION',
    'session_secret':'SYNTHETIC_SESSION_SECRET','scope':'basic netdisk','expires_in':60,**delta}


class Clock:
    def __init__(self):self.now=0
    def __call__(self):return self.now
    def advance(self,seconds):self.now+=seconds


class Scripted:
    def __init__(self,replies=None,device=None):self.replies=list(replies or [token_response()]);self.created=0;self.polled=0;self.response=device or device_response()
    def device(self,key,scope):
        assert key==AK and scope==d.SCOPE;self.created+=1
        if isinstance(self.response,Exception):raise self.response
        return dict(self.response)
    def poll(self,key,secret,code):
        assert (key,secret,code)==(AK,SK,DC);self.polled+=1
        value=self.replies.pop(0)
        if isinstance(value,Exception):raise value
        return dict(value)


class DeviceTests(unittest.TestCase):
    def flow(self,transport=None):
        clock=Clock();flow=d.DeviceFlow(AK,clock=clock);self.addCleanup(flow.close)
        transport=transport or Scripted();flow.start(transport);return flow,clock,transport
    def test_same_application_one_device_request_and_user_instructions_private(self):
        flow,clock,transport=self.flow();url,code=flow.private_instructions()
        self.assertEqual(code,UC);self.assertEqual(url,'https://openapi.baidu.com/device')
        self.assertNotIn(DC,repr(flow));self.assertNotIn(AK,repr(flow))
        with self.assertRaises(c.Rejected):flow.start(transport)
        self.assertEqual(transport.created,1)
    def test_poll_interval_strictly_above_five_and_slow_down_backoff(self):
        flow,clock,transport=self.flow(Scripted([{'error':'authorization_pending'},{'error':'slow_down'},token_response()]))
        self.assertEqual(flow.ready(),6)
        with self.assertRaises(c.Rejected):flow.poll_once(transport,SK)
        self.assertEqual(transport.polled,0)
        clock.advance(6);self.assertIsNone(flow.poll_once(transport,SK));self.assertEqual(flow.ready(),6)
        clock.advance(6);self.assertIsNone(flow.poll_once(transport,SK));self.assertEqual(flow.ready(),11)
        clock.advance(11);lease=flow.poll_once(transport,SK);self.addCleanup(lease.close)
        self.assertEqual(transport.polled,3)
    def test_expiry_and_poll_count_caps_stop_without_extra_request(self):
        flow,clock,transport=self.flow();clock.advance(300)
        with self.assertRaises(c.Rejected):flow.poll_once(transport,SK)
        self.assertEqual(transport.polled,0)
        flow,clock,transport=self.flow();flow.polls=d.MAX_POLLS
        with self.assertRaises(c.Rejected):flow.ready()
    def test_unknown_create_outcome_is_not_reissued(self):
        clock=Clock();flow=d.DeviceFlow(AK,clock=clock);transport=Scripted(device=TimeoutError('SYNTHETIC_PRIVATE'))
        with self.assertRaises(TimeoutError):flow.start(transport)
        self.assertEqual(flow.phase,'create_unknown')
        with self.assertRaises(c.Rejected):flow.start(transport)
        self.assertEqual(transport.created,1);flow.close()
    def test_unknown_exchange_is_not_repolled(self):
        flow,clock,transport=self.flow(Scripted([TimeoutError('SYNTHETIC_PRIVATE')]))
        clock.advance(6)
        with self.assertRaises(TimeoutError):flow.poll_once(transport,SK)
        self.assertEqual(flow.phase,'exchange_unknown')
        with self.assertRaises(c.Rejected):flow.poll_once(transport,SK)
        self.assertEqual(transport.polled,1)
    def test_permission_denial_and_unknown_errors_never_retry(self):
        for error in ('authorization_declined','invalid_client','unauthorized_client','invalid_scope','SYNTHETIC_PRIVATE'):
            flow,clock,transport=self.flow(Scripted([{'error':error,'error_description':SK}]))
            clock.advance(6)
            with self.assertRaises(c.Rejected) as raised:flow.poll_once(transport,SK)
            self.assertNotIn(SK,str(raised.exception));self.assertNotIn('SYNTHETIC_PRIVATE',str(raised.exception))
            with self.assertRaises(c.Rejected):flow.ready()
    def test_insecure_or_unreviewed_verification_url_rejected(self):
        for url in ('http://openapi.baidu.com/device','https://evil.invalid/device','https://openapi.baidu.com/device?code=x',
                    'https://pan.baidu.com/','https://user@openapi.baidu.com/device'):
            flow=d.DeviceFlow(AK)
            with self.assertRaises(c.Rejected):flow.start(Scripted(device=device_response(verification_url=url)))
            flow.close()
    def test_scope_type_and_envelope_unknown_never_produce_lease(self):
        for delta in ({'scope':'basic netdisk offline_access'},{'scope':'basic'},{'scope':'basic,netdisk'},
                      {'expires_in':True},{'new_field':'unknown'}):
            flow,clock,transport=self.flow(Scripted([token_response(**delta)]));clock.advance(6)
            with self.assertRaises(c.Rejected):flow.poll_once(transport,SK)
            self.assertEqual(flow.phase,'exchange_unknown')
    def test_token_is_single_take_expiring_and_refresh_not_retained(self):
        flow,clock,transport=self.flow();clock.advance(6);lease=flow.poll_once(transport,SK)
        self.assertNotIn(AT,repr(lease));self.assertIsNone(flow._code)
        self.assertFalse(hasattr(lease,'refresh_token'));self.assertEqual(lease.take(),AT)
        with self.assertRaises(c.Rejected):lease.take()
        flow,clock,transport=self.flow();clock.advance(6);lease=flow.poll_once(transport,SK);clock.advance(60)
        with self.assertRaises(c.Rejected):lease.take()
    def test_http_request_parameters_same_application_and_no_refresh_method(self):
        transport=h.DeviceOAuthHTTP()
        with patch.object(transport,'_get',return_value={}) as get:
            transport.device(AK,d.SCOPE);path,params=get.call_args.args
            self.assertEqual(path,'/oauth/2.0/device/code');self.assertEqual(params['client_id'],AK)
            transport.poll(AK,SK,DC);path,params=get.call_args.args
            self.assertEqual(path,'/oauth/2.0/token');self.assertEqual(params['client_id'],AK)
            self.assertEqual(params['grant_type'],'device_token');self.assertNotIn('refresh_token',params)
        self.assertFalse(hasattr(transport,'refresh'))
    def request(self,status=200,body=None,content_type='application/json'):
        request=h._Request();self.addCleanup(request.close)
        reply=MagicMock();reply.status=status;reply.getheaders.return_value=[('Content-Type',content_type)]
        reply.getheader.side_effect=lambda key,default=None:content_type if key=='Content-Type' else default
        reply.read1.side_effect=[json.dumps(body or device_response()).encode(),b'']
        connection=MagicMock();connection.getresponse.return_value=reply
        answers=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
        return request,reply,connection,answers
    def test_real_http_code_fixed_destination_no_redirect_or_raw_error_body(self):
        request,reply,connection,answers=self.request(status=302)
        with patch.object(socket,'getaddrinfo',return_value=answers),patch.object(h,'_Connection',return_value=connection):
            with self.assertRaisesRegex(c.Rejected,'http_status_rejected'):
                request.request_json('/oauth/2.0/device/code',{'response_type':'device_code','openapi':'xpansdk','client_id':AK,'scope':d.SCOPE})
        self.assertEqual(connection.request.call_count,1);reply.read1.assert_not_called()
    def test_http_get_query_encoded_and_errors_json_safely_returned(self):
        request,reply,connection,answers=self.request(status=400,body={'error':'authorization_pending'})
        with patch.object(socket,'getaddrinfo',return_value=answers),patch.object(h,'_Connection',return_value=connection):
            value=request.request_json('/oauth/2.0/token',{'grant_type':'device_token','openapi':'xpansdk','client_id':AK,'client_secret':SK+'+/=','code':DC})
        self.assertEqual(value,{'error':'authorization_pending'});self.assertEqual(connection.request.call_args.args[0],'GET')
        self.assertIn('client_secret='+SK+'%2B%2F%3D',connection.request.call_args.args[1]);self.assertEqual(request.trace,[])
    def test_private_dns_and_refresh_injection_rejected_before_connect(self):
        request=h._Request();self.addCleanup(request.close)
        with patch.object(socket,'getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]),patch.object(h,'_Connection',side_effect=AssertionError('must not connect')):
            with self.assertRaisesRegex(c.Rejected,'dns_rejected'):
                request.request_json('/oauth/2.0/device/code',{'response_type':'device_code','openapi':'xpansdk','client_id':AK,'scope':d.SCOPE})
        with self.assertRaisesRegex(c.Rejected,'scope_rejected'):
            request.request_json('/oauth/2.0/token',{'grant_type':'refresh_token','openapi':'xpansdk','client_id':AK,'client_secret':SK,'code':DC})
    def test_oauth_connection_uses_official_hostname_and_verified_tls(self):
        request=h._Request();self.addCleanup(request.close);request.address=(socket.AF_INET,('8.8.8.8',443))
        raw=MagicMock();wrapped=MagicMock()
        with patch.object(socket,'socket',return_value=raw),patch.object(ssl.SSLContext,'wrap_socket',return_value=wrapped) as wrap:
            h._Connection(request).connect()
        wrap.assert_called_once_with(raw,server_hostname='openapi.baidu.com',do_handshake_on_connect=False)
        self.assertEqual(request.context.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(request.context.check_hostname)
        self.assertIsNone(request.context.keylog_filename)
    def test_cli_no_action_before_private_input_and_no_secret_in_parser_errors(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(out),patch.object(t,'DeviceOAuthHTTP',side_effect=AssertionError('no request')):
            code=t.main(['--secret',SK])
        self.assertEqual(code,1);self.assertNotIn(SK,out.getvalue())
    def test_user_approval_then_token_stays_memory_only_no_mcp_without_action(self):
        flow=d.DeviceFlow(AK,clock=Clock());clock=flow.clock;transport=Scripted();out=io.StringIO()
        flags=['--scope',d.SCOPE,'--ack-new-user-grant','--ack-query-credential-risk']
        with patch.object(t,'DeviceFlow',return_value=flow),patch.object(t,'DeviceOAuthHTTP',return_value=transport),patch.object(t,'show_private_device') as display,patch.object(t,'read_secret',side_effect=['XTRANSFER-DEVICE-basic,netdisk',AK,'XTRANSFER-APPROVED',SK,'NO']),patch.object(t.time,'sleep',side_effect=clock.advance),patch.object(t,'run_discovery',side_effect=AssertionError('no MCP')),contextlib.redirect_stdout(out):
            code=t.main(flags)
        self.assertEqual(code,0);display.assert_called_once_with('https://openapi.baidu.com/device',UC)
        for value in (AK,SK,DC,UC,AT,'SYNTHETIC_REFRESH'):self.assertNotIn(value,out.getvalue())
        self.assertIsNone(flow._key);self.assertEqual(transport.polled,1)
    def test_separate_user_action_hands_token_only_to_discovery(self):
        flow=d.DeviceFlow(AK,clock=Clock());clock=flow.clock;out=io.StringIO()
        flags=['--scope',d.SCOPE,'--ack-new-user-grant','--ack-query-credential-risk']
        with patch.object(t,'DeviceFlow',return_value=flow),patch.object(t,'DeviceOAuthHTTP',return_value=Scripted()),patch.object(t,'show_private_device'),patch.object(t,'read_secret',side_effect=['XTRANSFER-DEVICE-basic,netdisk',AK,'XTRANSFER-APPROVED',SK,'MCP-DISCOVER']),patch.object(t.time,'sleep',side_effect=clock.advance),patch.object(t,'run_discovery',return_value={'account_verified':False}) as discover,contextlib.redirect_stdout(out):
            code=t.main(flags)
        self.assertEqual(code,0);discover.assert_called_once_with(AT);self.assertNotIn(AT,out.getvalue())
    def test_private_device_display_rejects_non_tty_and_untrusted_urls(self):
        with patch.object(os,'isatty',return_value=False),patch.object(os,'open',side_effect=AssertionError('no terminal')):
            with self.assertRaises(t.TerminalFailure):t.show_private_device('https://openapi.baidu.com/device',UC)
        with self.assertRaises(t.TerminalFailure):t.show_private_device('https://evil.invalid',UC)
    def test_request_timeout_clears_parameter_references_and_closes(self):
        transport=h.DeviceOAuthHTTP();request=MagicMock();request.request_json.side_effect=TimeoutError(SK);request.close.return_value=True
        params={'client_id':AK,'client_secret':SK}
        with patch.object(h,'_Request',return_value=request),self.assertRaises(TimeoutError):transport._get('/oauth/2.0/token',params)
        self.assertEqual(params,{});request.close.assert_called_once()
    def test_close_unconfirmed_never_returns_a_token_response(self):
        request=MagicMock();request.request_json.return_value=token_response();request.close.return_value=False
        with patch.object(h,'_Request',return_value=request),self.assertRaisesRegex(c.Rejected,'close_unconfirmed'):
            h.DeviceOAuthHTTP().poll(AK,SK,DC)
    def test_tls_mutation_rejected_before_socket_and_credential_submission(self):
        request=h._Request();self.addCleanup(request.close);request.address=(socket.AF_INET,('8.8.8.8',443))
        request.context.check_hostname=False
        with patch.object(socket,'socket',side_effect=AssertionError('no socket')):
            with self.assertRaises(c.Rejected):h._Connection(request).connect()
    def test_cli_unknown_exchange_stops_and_never_submits_to_mcp(self):
        flow=d.DeviceFlow(AK,clock=Clock());clock=flow.clock;out=io.StringIO();transport=Scripted([TimeoutError(SK)])
        flags=['--scope',d.SCOPE,'--ack-new-user-grant','--ack-query-credential-risk']
        with patch.object(t,'DeviceFlow',return_value=flow),patch.object(t,'DeviceOAuthHTTP',return_value=transport),patch.object(t,'show_private_device'),patch.object(t,'read_secret',side_effect=['XTRANSFER-DEVICE-basic,netdisk',AK,'XTRANSFER-APPROVED',SK]),patch.object(t.time,'sleep',side_effect=clock.advance),patch.object(t,'run_discovery',side_effect=AssertionError('no MCP')),contextlib.redirect_stdout(out):
            code=t.main(flags)
        self.assertEqual(code,1);self.assertEqual(transport.polled,1)
        report=json.loads(out.getvalue().splitlines()[-1]);self.assertTrue(report['authorization_outcome_unknown'])
        for value in (AK,SK,DC,UC,AT):self.assertNotIn(value,out.getvalue())
    def test_actual_command_noninteractive_has_no_credential_or_authorization_action(self):
        from pathlib import Path
        import subprocess,sys
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'-I','-S','-B',str(root/'tools/xtransfer_device_authorize.py'),
            '--scope',d.SCOPE,'--ack-new-user-grant','--ack-query-credential-risk'],env={},stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3,close_fds=True)
        self.assertEqual(result.returncode,1);self.assertEqual(result.stderr,b'')
        self.assertIn(b'device_terminal_input_stopped',result.stdout);self.assertNotIn(AT.encode(),result.stdout)
    def test_mixed_pending_and_token_response_is_unknown_not_repolled(self):
        flow,clock,transport=self.flow(Scripted([{'error':'authorization_pending','access_token':AT}]))
        clock.advance(6)
        with self.assertRaisesRegex(c.Rejected,'response_unknown'):flow.poll_once(transport,SK)
        self.assertEqual(flow.phase,'exchange_unknown')
        with self.assertRaises(c.Rejected):flow.ready()
        self.assertEqual(transport.polled,1)
    def test_device_success_and_mcp_protocol_failure_have_separate_completion_flags(self):
        flow=d.DeviceFlow(AK,clock=Clock());clock=flow.clock;out=io.StringIO()
        flags=['--scope',d.SCOPE,'--ack-new-user-grant','--ack-query-credential-risk']
        with patch.object(t,'DeviceFlow',return_value=flow),patch.object(t,'DeviceOAuthHTTP',return_value=Scripted()),patch.object(t,'show_private_device'),patch.object(t,'read_secret',side_effect=['XTRANSFER-DEVICE-basic,netdisk',AK,'XTRANSFER-APPROVED',SK,'MCP-DISCOVER']),patch.object(t.time,'sleep',side_effect=clock.advance),patch.object(t,'run_discovery',return_value={'status':'stopped','reason':'mcp_sse_protocol_rejected','close_confirmed':True}),contextlib.redirect_stdout(out):
            code=t.main(flags)
        report=json.loads(out.getvalue().splitlines()[-1])
        self.assertEqual(code,0);self.assertTrue(report['device_authorization_complete'])
        self.assertFalse(report['mcp_discovery_complete']);self.assertFalse(report['authorization_outcome_unknown'])
        self.assertFalse(report['share_attempted']);self.assertEqual(report['poll_requests'],1)

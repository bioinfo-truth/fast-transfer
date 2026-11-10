"""New official-driver checks: synthetic token, no external connection."""
import json
import socket
import ssl
import unittest
from unittest.mock import patch, MagicMock
from fast_transfer import mcp_official_http as h, mcp_share as m, mcp_sse as s


class OfficialDriverTests(unittest.TestCase):
    def driver(self):
        d=h.OfficialHTTPSDriver(access_token='SYNTHETIC_ONLY+/=')
        self.addCleanup(d.close)
        return d

    def test_constructor_no_network_and_explicit_token_only(self):
        with patch('socket.socket', side_effect=AssertionError('no network')):
            d=self.driver()
        self.assertEqual(d.endpoint,s.ENDPOINT)
        self.assertEqual(d.context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(d.context.check_hostname)
        self.assertIsNone(d.context.keylog_filename)
        self.assertNotIn('SYNTHETIC',repr(d))
        self.assertEqual(d.trace,[])

    def test_token_encoded_only_for_open_and_dropped_on_close(self):
        d=self.driver()
        self.assertEqual(d._opening_path(),'/sse?access_token=SYNTHETIC_ONLY%2B%2F%3D')
        d.close()
        self.assertIsNone(d._token)

    def test_invalid_token_rejected_before_network(self):
        for token in (None,'','x\ny','x y',lambda:'secret'):
            with self.assertRaises(m.Rejected):h.OfficialHTTPSDriver(access_token=token)

    def test_separate_factory_does_not_relax_fixture_or_default_types(self):
        d=self.driver()
        client=s.SSEClient.for_official_readonly(d)
        self.assertEqual(client.origin,h.ORIGIN)
        with self.assertRaises(m.Rejected):s.SSEClient(d)
        with self.assertRaises(m.Rejected):s.SSEClient.for_local_fixture(d)

    def test_sharing_and_unreviewed_tools_blocked_before_network(self):
        d=self.driver()
        with patch('socket.socket',side_effect=AssertionError('no network')):
            for tool in ('file_sharelink_set','file_delete','unknown'):
                with self.assertRaisesRegex(m.Rejected,'operation_locked'):
                    d.post(h.ORIGIN+'/messages/?session_id=x',s.encode({'method':'tools/call','params':{'name':tool}}))

    def test_cross_origin_and_auth_query_rejected_before_dns(self):
        d=self.driver()
        with patch('socket.getaddrinfo',side_effect=AssertionError('no DNS')):
            for url in ('https://example.invalid/messages/?session_id=x',h.ORIGIN+'/messages/?access_token=x'):
                with self.assertRaises(m.Rejected):d.post(url,s.encode({'method':'tools/list'}))

    def test_non_public_dns_answers_rejected(self):
        for ip in ('127.0.0.1','10.0.0.1','169.254.169.254','224.0.0.1'):
            d=self.driver()
            with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]):
                with self.assertRaisesRegex(m.Rejected,'dns_rejected'):d._connection()

    def test_dns_fixed_host_and_pinned_once(self):
        d=self.driver()
        with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]) as resolve:
            d._connection();d._connection()
        resolve.assert_called_once_with(h.HOST,443,type=socket.SOCK_STREAM)
        self.assertEqual(d.address,(socket.AF_INET,('8.8.8.8',443)))

    def test_connection_uses_official_SNI_and_pinned_address(self):
        d=self.driver();d.address=(socket.AF_INET,('8.8.8.8',443))
        raw=MagicMock();wrapped=MagicMock();wrapped.version.return_value='TLSv1.3'
        with patch('socket.socket',return_value=raw),patch.object(ssl.SSLContext,'wrap_socket',return_value=wrapped) as tls:
            d._connection().connect()
        raw.connect.assert_called_once_with(('8.8.8.8',443))
        tls.assert_called_once_with(raw,server_hostname=h.HOST,do_handshake_on_connect=False)
        wrapped.do_handshake.assert_called_once()
        self.assertEqual(d.tls_version,'TLSv1.3')

    def test_dns_errors_are_sanitized(self):
        d=self.driver()
        with patch('socket.getaddrinfo',side_effect=OSError('SYNTHETIC_PRIVATE')):
            with self.assertRaisesRegex(m.Rejected,'dns_failed') as err:d._connection()
        self.assertNotIn('SYNTHETIC',str(err.exception))

    def test_open_uses_auth_only_in_fixed_GET_path_without_trace(self):
        d=self.driver();c=MagicMock();response=MagicMock();response.status=200
        response.getheaders.return_value=[('Content-Type','text/event-stream')]
        response.getheader.side_effect=lambda key,default=None: 'text/event-stream' if key=='Content-Type' else default
        c.getresponse.return_value=response
        with patch.object(d,'_connection',return_value=c):
            self.assertEqual(d.open(d.endpoint,s.AUTH_SLOT),(200,'text/event-stream'))
        args=c.request.call_args.args
        self.assertEqual(args[:2],('GET','/sse?access_token=SYNTHETIC_ONLY%2B%2F%3D'))
        self.assertNotIn('SYNTHETIC',json.dumps(d.trace))
        with self.assertRaises(m.Rejected):d.open(d.endpoint,s.AUTH_SLOT)

    def test_redirect_rejected_without_following_or_response_body(self):
        d=self.driver();c=MagicMock();response=MagicMock();response.status=302
        response.getheaders.return_value=[];response.getheader.side_effect=lambda key,default=None:default
        c.getresponse.return_value=response
        with patch.object(d,'_connection',return_value=c):
            with self.assertRaisesRegex(m.Rejected,'status_rejected'):d.open(d.endpoint,s.AUTH_SLOT)
        self.assertEqual(c.request.call_count,1)
        response.read.assert_not_called()

    def test_dns_wait_timeout_sanitized_and_no_connection_started(self):
        import queue
        d=self.driver()
        with patch.object(h.threading,'Thread') as thread,patch.object(h.queue.Queue,'get',side_effect=queue.Empty):
            with self.assertRaisesRegex(m.Rejected,'dns_timeout'):d._connection()
        self.assertIsNone(d.address)
        self.assertEqual(d._connections,[])
        self.assertEqual(thread.call_args.kwargs['target'],h._resolve)
        self.assertEqual(len(thread.call_args.kwargs['args']),1)

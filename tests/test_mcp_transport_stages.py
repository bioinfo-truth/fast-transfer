"""Synthetic transport fault classification; no official traffic or credentials."""
import http.client
import json
import socket
import ssl
import time
import unittest
from unittest.mock import patch,MagicMock
from fast_transfer import mcp_official_http as h,mcp_share as c,mcp_sse as s

PRIVATE='SYNTHETIC_PRIVATE_ERROR'


class TransportStageTests(unittest.TestCase):
    def driver(self,**kwargs):
        d=h.OfficialHTTPSDriver(**kwargs);self.addCleanup(d.close)
        d.address=(socket.AF_INET,('8.8.8.8',443));return d
    def invoke(self,d):return d.post(s.ORIGIN+'/message?sessionId=synthetic',s.encode({'method':'initialize','id':1,'jsonrpc':'2.0'}))
    def assert_private(self,d):self.assertNotIn(PRIVATE,json.dumps(d.io_diagnostics()))
    def test_tcp_timeout_is_not_misreported_as_server_refusal_or_post_ack(self):
        d=self.driver();raw=MagicMock();raw.connect.side_effect=TimeoutError(PRIVATE)
        with patch.object(socket,'socket',return_value=raw):
            with self.assertRaisesRegex(c.Rejected,'mcp_local_timeout'):self.invoke(d)
        diag=d.io_diagnostics();self.assertEqual(diag['phase'],'tcp_connect')
        self.assertFalse(diag['last_request_send_returned']);self.assertFalse(diag['last_response_headers_received'])
        self.assertEqual(d.http_statuses,[]);self.assert_private(d)
    def test_tls_timeout_after_successful_tcp_is_a_distinct_stage(self):
        d=self.driver();raw=MagicMock();wrapped=MagicMock();wrapped.do_handshake.side_effect=TimeoutError(PRIVATE)
        with patch.object(socket,'socket',return_value=raw),patch.object(ssl.SSLContext,'wrap_socket',return_value=wrapped):
            with self.assertRaisesRegex(c.Rejected,'mcp_local_timeout'):self.invoke(d)
        diag=d.io_diagnostics();self.assertEqual(diag['phase'],'tls_handshake')
        self.assertTrue(diag['history'][0]['completed']);self.assertFalse(diag['history'][-1]['completed'])
        self.assertFalse(diag['last_request_send_returned']);self.assert_private(d)
    def test_send_timeout_does_not_claim_send_returned_or_headers_received(self):
        d=self.driver();raw=MagicMock();wrapped=MagicMock()
        with patch.object(socket,'socket',return_value=raw),patch.object(ssl.SSLContext,'wrap_socket',return_value=wrapped),patch.object(h._OfficialConnection,'request',side_effect=TimeoutError(PRIVATE)):
            with self.assertRaisesRegex(c.Rejected,'mcp_local_timeout'):self.invoke(d)
        diag=d.io_diagnostics();self.assertEqual(diag['phase'],'request_send')
        self.assertFalse(diag['last_request_send_returned']);self.assertEqual(len(d.trace),1);self.assert_private(d)
    def test_header_timeout_records_local_send_return_without_server_ack(self):
        d=self.driver();raw=MagicMock();wrapped=MagicMock()
        with patch.object(socket,'socket',return_value=raw),patch.object(ssl.SSLContext,'wrap_socket',return_value=wrapped),patch.object(h._OfficialConnection,'request'),patch.object(h._OfficialConnection,'getresponse',side_effect=TimeoutError(PRIVATE)):
            with self.assertRaisesRegex(c.Rejected,'mcp_local_timeout'):self.invoke(d)
        diag=d.io_diagnostics();self.assertEqual(diag['phase'],'response_headers')
        self.assertTrue(diag['last_request_send_returned']);self.assertFalse(diag['last_response_headers_received'])
        self.assertEqual(d.http_statuses,[]);self.assert_private(d)
    def test_each_phase_refreshes_socket_timeout_against_same_total_deadline(self):
        d=self.driver();deadline=d.deadline;raw=MagicMock();wrapped=MagicMock()
        reply=MagicMock();reply.status=202;reply.getheaders.return_value=[]
        reply.getheader.side_effect=lambda key,default=None:default
        with patch.object(socket,'socket',return_value=raw),patch.object(ssl.SSLContext,'wrap_socket',return_value=wrapped),patch.object(h._OfficialConnection,'request'),patch.object(h._OfficialConnection,'getresponse',return_value=reply):
            self.assertEqual(self.invoke(d),202)
        self.assertEqual(d.deadline,deadline)
        self.assertEqual(wrapped.settimeout.call_count,3)  # TLS, send, headers.
        self.assertTrue(d.io_diagnostics()['last_response_headers_received'])
        self.assertEqual([x['phase'] for x in d.io_diagnostics()['history']],['tcp_connect','tls_handshake','request_send','response_headers'])
    def test_deadline_expiry_is_classified_even_if_watchdog_thread_has_not_fired(self):
        d=self.driver();d._expired=False
        with self.assertRaisesRegex(c.Rejected,'mcp_local_deadline'):
            with d.operation():
                d.deadline=time.monotonic()-1
                raise TimeoutError(PRIVATE)
        self.assertFalse(d._expired);self.assertTrue(d.io_diagnostics()['deadline_reached'])
    def test_new_session_has_fresh_budget_independent_of_previous_driver(self):
        old=self.driver(budget=.1);old.deadline=time.monotonic()-100
        before=time.monotonic();fresh=self.driver(budget=15)
        self.assertTrue(old.deadline_reached());self.assertGreaterEqual(fresh._created,before)
        diag=fresh.io_diagnostics();self.assertEqual(diag['session_budget_ms'],15000)
        self.assertGreater(diag['remaining_ms'],14000);self.assertFalse(diag['deadline_reached'])

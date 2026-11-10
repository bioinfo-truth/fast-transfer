"""Synthetic protocol diagnostics only; no authorization or external requests."""
import json
import unittest
from unittest.mock import patch
from test_mcp_sse import script,result
from fast_transfer import mcp_sse as s,mcp_share as c,mcp_terminal as t
from fast_transfer.mcp_official_http import OfficialHTTPSDriver

PRIVATE='SYNTHETIC_PRIVATE_RESPONSE_OR_TOKEN'


class DiagnosticTests(unittest.TestCase):
    def client(self,reply=None):
        steps=script()[:3]
        if reply is not None:steps[2]=('tools/list',None,reply)
        driver=s.ScriptedHTTP(steps);client=s.SSEClient(driver);self.addCleanup(client.close)
        return client,driver
    def rejected(self,reply,rule,stage='tools_list_reply'):
        client,driver=self.client(reply)
        with self.assertRaises(c.Rejected):client.connect()
        diag=client.protocol_diagnostics()
        self.assertEqual(diag['failure_rule'],rule);self.assertEqual(diag['stage'],stage)
        self.assertEqual(sum(v.get('operation')=='tools/list' for v in driver.trace),1)
        self.assertNotIn(PRIVATE,json.dumps(diag))
        return client,diag
    def test_success_snapshot_has_fixed_nonsecret_fields(self):
        client,driver=self.client();client.connect();diag=client.protocol_diagnostics()
        self.assertEqual(diag['stage'],'connected');self.assertIsNone(diag['failure_rule'])
        self.assertTrue(diag['rpc_id_matches']);self.assertEqual(diag['rpc_sequence'],2)
        self.assertEqual(diag['event_count'],3);self.assertGreater(diag['sse_bytes_read'],0)
    def test_standard_list_result_meta_dictionary_or_null_is_accepted_and_not_exported(self):
        for meta in (None,{'trace':PRIVATE}):
            tools={'tools':[{'name':name,'inputSchema':schema} for name,schema in s.schemas().items()],'_meta':meta}
            client,_=self.client(result(2,tools));client.connect()
            self.assertTrue(client.connected);self.assertNotIn(PRIVATE,json.dumps(client.protocol_diagnostics()))
    def test_non_dictionary_meta_remains_rejected(self):
        self.rejected(result(2,{'tools':[],'_meta':PRIVATE}),'tools_meta_type','tools_list_shape')
    def test_oversized_single_line_retains_limit_and_reports_safe_rule(self):
        raw=b'event: message\ndata: '+b'x'*(s.MAX_EVENT+10)+b'\n\n'
        client,diag=self.rejected(raw,'pending_line_limit')
        self.assertGreater(diag['line_buffer_high_water_bytes'],s.MAX_EVENT)
        self.assertLessEqual(diag['pending_line_bytes'],s.MAX_EVENT)
        self.assertEqual(s.MAX_EVENT,16384)
    def test_multiline_event_size_limit_has_distinct_rule(self):
        raw=b'event: message\n'+(b'data: '+b'x'*800+b'\n')*24+b'\n'
        _,diag=self.rejected(raw,'event_byte_limit');self.assertGreater(diag['event_bytes'],16384)
    def test_eof_and_unsupported_sse_fields_are_distinguished(self):
        self.rejected(b'event: message\ndata: {','stream_eof')
        self.rejected(b'retry: 5000\nevent: message\ndata: {}\n\n','sse_field_unreviewed')
    def test_wrong_response_id_exposes_only_match_boolean_not_actual_id(self):
        _,diag=self.rejected(s.frame({'jsonrpc':'2.0','id':PRIVATE,'result':{}}),'rpc_id_mismatch')
        self.assertFalse(diag['rpc_id_matches']);self.assertEqual(diag['rpc_sequence'],2)
    def test_unreviewed_notification_is_not_silently_ignored_or_retried(self):
        self.rejected(s.frame({'jsonrpc':'2.0','method':PRIVATE,'params':{}}),'rpc_envelope_extra_fields')
    def test_cursor_presence_reported_without_cursor_value_or_pagination_requests(self):
        _,diag=self.rejected(result(2,{'tools':[],'nextCursor':PRIVATE}),'tools_pagination_unreviewed','tools_list_shape')
        self.assertTrue(diag['pagination_present'])
    def test_unknown_result_fields_are_not_logged_or_accepted(self):
        self.rejected(result(2,{'tools':[],PRIVATE:PRIVATE}),'tools_list_extra_fields','tools_list_shape')
    def test_json_profile_limit_preserved_with_separate_failure_label(self):
        tools=[{'name':'tool'+str(i),'inputSchema':{}} for i in range(17)]
        self.rejected(result(2,{'tools':tools}),'json_profile_rejected')
    def test_http_statuses_are_numeric_and_bounded_without_headers(self):
        client,driver=self.client();driver.http_statuses=[200,202,PRIVATE,999,True,202]
        self.assertEqual(client.protocol_diagnostics()['http_statuses'],[200,202,202])
    def test_terminal_result_forwards_diagnostics_without_token_raw_id_or_url(self):
        driver=OfficialHTTPSDriver(access_token=PRIVATE);self.addCleanup(driver.close)
        steps=script()[:3];steps[2]=('tools/list',None,s.frame({'jsonrpc':'2.0','id':PRIVATE,'result':{}}))
        wire=s.ScriptedHTTP(steps,opening=b'event: endpoint\ndata: /message?sessionId=synthetic\n\n')
        def post(url,raw):return wire.post(s.ORIGIN+'/messages?session_id=synthetic',raw)
        with patch.object(t,'OfficialHTTPSDriver',return_value=driver),patch.object(driver,'open',side_effect=wire.open),patch.object(driver,'read',side_effect=wire.read),patch.object(driver,'post',side_effect=post):
            report=t.run_discovery(PRIVATE)
        self.assertEqual(report['reason'],'mcp_sse_protocol_rejected')
        self.assertEqual(report['protocol_diagnostics']['failure_rule'],'rpc_id_mismatch')
        text=json.dumps(report)
        for value in (PRIVATE,'sessionId=','session_id='):self.assertNotIn(value,text)
        self.assertTrue(report['close_confirmed']);self.assertIsNone(driver._token)

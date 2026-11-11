"""Actual SSE byte framing and JSON-RPC session/fault integration; no sockets."""
import json
import time
import unittest
from pathlib import Path

from test_mcp_share import guarded, prepare, fixture
from fast_transfer import mcp_sse as s, mcp_share as m
import tempfile


def result(identifier,value):return s.frame({'jsonrpc':'2.0','id':identifier,'result':value})
def tool(identifier,obj):return result(identifier,{'content':[{'type':'text','text':json.dumps(obj)}]})
def script():
    f=fixture()
    return [
        ('initialize',None,result(1,{'protocolVersion':s.VERSION,'capabilities':{},'serverInfo':{'name':'synthetic','version':'1'}})),
        ('notifications/initialized',None,b''),
        ('tools/list',None,result(2,{'tools':[{'name':k,'inputSchema':v} for k,v in s.schemas().items()]})),
        ('tools/call','user_info',tool(3,json.loads(f._observations['user_info'].raw))),
        ('tools/call','file_meta',tool(4,json.loads(f._observations['file_meta'].raw))),
        ('tools/call','file_sharelink_set',tool(5,json.loads(f._share.raw)))]


class SSETests(unittest.TestCase):
    def setUp(self):
        if not guarded():self.skipTest('requires kernel guard runner')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.job=prepare(self.root)
    def run_flow(self,steps=None,**kw):
        driver=s.ScriptedHTTP(script() if steps is None else steps,**kw)
        r=s.exercise(self.job,driver,pwd='a1b2')
        self.assertFalse(r['delivery_eligible']);self.assertFalse(r['live_connected'])
        return r,driver
    def creates(self,driver):return sum(x.get('tool')=='file_sharelink_set' for x in driver.trace)
    def test_full_wire_handshake_file_binding_and_single_share(self):
        r,d=self.run_flow(chunk_bytes=1)
        self.assertEqual(r['status'],'candidate_unverified');self.assertTrue(r['protocol_closed'])
        self.assertEqual([x['operation'] for x in d.trace],['sse_open','initialize','notifications/initialized','tools/list','tools/call','tools/call','tools/call'])
        self.assertEqual([x['id'] for x in d.trace if x['method']=='POST'],[1,None,2,3,4,5])
        self.assertEqual(self.creates(d),1)
        self.assertEqual(d.trace[-1]['argument_keys'],['fsid_list','period','pwd'])
        self.assertEqual(self.job.view()['phase'],'manual_review')
    def test_crlf_comments_and_fragmented_multiline_data(self):
        steps=script();steps[0]=('initialize',None,steps[0][2].replace(b',"result":',b',\ndata: "result":').replace(b'\n',b'\r\n'))
        r,d=self.run_flow(steps,opening=b': keepalive\r\nevent: endpoint\r\ndata: /messages/?session_id=fixture\r\n\r\n',chunk_bytes=3)
        self.assertEqual(r['status'],'candidate_unverified');self.assertEqual(self.creates(d),1)
    def test_cross_origin_credentials_encoded_and_wrong_path_endpoints_rejected(self):
        for url in ['http://mcp-pan.baidu.com/messages/?session_id=x','https://evil.invalid/messages/?session_id=x',
                    'https://user@mcp-pan.baidu.com/messages/?session_id=x','/other?session_id=x',
                    '/messages/?access_token=SYNTHETIC','/messages/?session_id=%78','/messages/?session_id=x#fragment']:
            with self.subTest(url=url):
                r,d=self.run_flow(opening=b'event: endpoint\ndata: '+url.encode()+b'\n\n')
                self.assertFalse(r['create_attempted']);self.assertEqual(self.creates(d),0)
                self.assertEqual(len(d.trace),1)
    def test_redirect_http_status_and_wrong_content_type_never_followed(self):
        for status,mime in [(302,'text/event-stream'),(307,'text/event-stream'),(200,'text/html'),(500,'text/event-stream')]:
            r,d=self.run_flow(status=status,content_type=mime)
            self.assertFalse(r['create_attempted']);self.assertEqual(len(d.trace),1)
    def test_bad_utf8_duplicate_event_unknown_field_and_partial_eof(self):
        for raw in [b'event: endpoint\ndata: \xff\n\n',b'event: endpoint\nevent: endpoint\ndata: /messages/?session_id=x\n\n',
                    b'retry: 1\nevent: endpoint\ndata: /messages/?session_id=x\n\n',b'event: endpoint\ndata: /messages/?session_id=x']:
            r,d=self.run_flow(opening=raw);self.assertFalse(r['create_attempted']);self.assertEqual(self.creates(d),0)
    def test_oversize_event_and_notification_flood_fail_bounded(self):
        for raw in [b'event: endpoint\ndata: '+b'a'*17000+b'\n\n',b': heartbeat\n'*513]:
            r,d=self.run_flow(opening=raw);self.assertFalse(r['create_attempted'])
    def test_wrong_id_bool_id_duplicate_json_and_rpc_error_are_not_success(self):
        for reply in [s.frame({'jsonrpc':'2.0','id':99,'result':{}}),s.frame({'jsonrpc':'2.0','id':True,'result':{}}),
                      b'event: message\ndata: {"jsonrpc":"2.0","id":1,"id":1,"result":{}}\n\n',
                      s.frame({'jsonrpc':'2.0','id':1,'error':{'code':-32600,'message':'SYNTHETIC_PRIVATE'}})]:
            steps=script();steps[0]=('initialize',None,reply)
            r,d=self.run_flow(steps);self.assertFalse(r['create_attempted']);self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(r))
    def test_unsupported_protocol_and_missing_schema_stop_before_identity(self):
        steps=script();steps[0]=('initialize',None,result(1,{'protocolVersion':'2099-01-01','capabilities':{},'serverInfo':{}}))
        r,d=self.run_flow(steps);self.assertEqual(len(d.trace),2)
        steps=script();steps[2]=('tools/list',None,result(2,{'tools':[]}))
        r,d=self.run_flow(steps);self.assertEqual(r['reason'],'mcp_sse_schema_unproven');self.assertFalse(r['create_attempted'])
    def test_tool_list_pagination_and_extra_required_schema_rejected(self):
        for fields in [{'tools':[],'nextCursor':'unknown'}, {'tools':[{'name':'user_info','inputSchema':{'type':'object','required':['token']}}]}]:
            steps=script();steps[2]=('tools/list',None,result(2,fields))
            r,d=self.run_flow(steps);self.assertFalse(r['create_attempted']);self.assertEqual(self.creates(d),0)
    def test_business_identity_and_object_drift_over_real_wire_decoder(self):
        for index,name,data in [(3,'user_info',{'uk':'9999'}),(4,'file_meta',{'list':[]})]:
            steps=script();steps[index]=('tools/call',name,tool(index,json.loads(json.dumps(data))))
            # response identifiers: script index3->RPC3, index4->RPC4
            r,d=self.run_flow(steps);self.assertFalse(r['create_attempted']);self.assertEqual(self.creates(d),0)
    def test_non_text_multiple_blocks_and_rest_envelope_remain_unknown(self):
        for fields in [{'content':[{'type':'image','data':'SYNTHETIC'}]}, {'content':[]},
                       {'content':[{'type':'text','text':'{}'}]*2}, {'errno':0,'data':{'link':'SYNTHETIC'}}]:
            self.job=prepare(Path(tempfile.mkdtemp(dir=self.root)))
            steps=script();steps[5]=('tools/call','file_sharelink_set',result(5,fields))
            r,d=self.run_flow(steps);self.assertTrue(r['outcome_unknown']);self.assertEqual(self.creates(d),1)
            self.assertNotEqual(r['status'],'candidate_unverified')
    def test_share_tool_error_is_not_mapped_to_permission_errno(self):
        steps=script();steps[5]=('tools/call','file_sharelink_set',result(5,{'isError':True,'content':[{'type':'text','text':'13998 PRIVATE'}]}))
        r,d=self.run_flow(steps);self.assertEqual(r['reason'],'mcp_sse_tool_error');self.assertTrue(r['outcome_unknown'])
        self.assertNotIn('13998',json.dumps(r));self.assertEqual(self.creates(d),1)
    def test_share_timeout_and_new_session_cannot_replay_persisted_intent(self):
        steps=script();steps[5]=('tools/call','file_sharelink_set','timeout')
        r,d=self.run_flow(steps);self.assertTrue(r['create_attempted'] and r['outcome_unknown']);self.assertEqual(self.creates(d),1)
        r2,d2=self.run_flow();self.assertFalse(r2['create_attempted']);self.assertTrue(r2['outcome_unknown']);self.assertEqual(d2.trace,[])
    def test_share_post_unknown_status_not_retried(self):
        class NotAllowed(s.ScriptedHTTP):pass
        with self.assertRaises(m.Rejected):s.SSEClient(NotAllowed(script()))
        blocked=s.exercise(self.job,object(),pwd='a1b2')
        self.assertEqual(blocked['reason'],'mcp_sse_driver_unavailable')
        self.assertFalse(blocked['create_attempted']);self.assertIsNone(blocked['protocol_closed'])
        # Non-success POST at handshake is rejected; no hidden retry/reconnect.
        r,d=self.run_flow(post_status=500);self.assertFalse(r['create_attempted']);self.assertEqual(len(d.trace),2)
        for status in (302,500):
            self.job=prepare(Path(tempfile.mkdtemp(dir=self.root)))
            steps=script();steps[5]=('tools/call','file_sharelink_set',(status,b''))
            r,d=self.run_flow(steps);self.assertTrue(r['create_attempted'] and r['outcome_unknown'])
            self.assertEqual(self.creates(d),1)
            r2,d2=self.run_flow();self.assertEqual(d2.trace,[])
    def test_arguments_cannot_expand_task_or_read_other_objects(self):
        for name,args in [('file_meta',{'fsids':[9999]}),('user_info',{'access_token':'SYNTHETIC'}),
                          ('file_sharelink_set',{'fsid_list':'["9999"]','period':7,'pwd':'a1b2'}),
                          ('file_del',{})]:
            d=s.ScriptedHTTP(script());c=s.SSEClient(d)
            with self.assertRaises(m.Rejected):c.tool(name,args)
            self.assertEqual(d.trace,[]);c.close()
    def test_deadline_and_closed_session_prevent_any_new_io(self):
        driver=s.ScriptedHTTP(script());client=s.SSEClient(driver);client.deadline=0
        with self.assertRaisesRegex(m.Rejected,'deadline'):client.connect()
        self.assertEqual(driver.trace,[]);self.assertTrue(client.close())
        with self.assertRaisesRegex(m.Rejected,'closed'):client.connect()
        self.assertEqual(driver.trace,[])
    def test_close_unconfirmed_never_reports_success_and_logs_no_private_payload(self):
        r,d=self.run_flow(close_ok=False);self.assertEqual(r['reason'],'mcp_sse_stop_unconfirmed')
        self.assertFalse(r['protocol_closed']);self.assertEqual(r['status'],'manual_review')
        text=json.dumps(r)+json.dumps(d.trace)+(self.job.root/'state.json').read_text()+repr(d)
        for secret in ['synthetic_link','synthetic_short','a1b2','access_token','SYNTHETIC_PRIVATE']:self.assertNotIn(secret,text)

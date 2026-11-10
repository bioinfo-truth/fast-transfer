"""Focused production route/discovery safety checks; synthetic wire only."""
import unittest
from unittest.mock import patch
from fast_transfer import mcp_sse as s,mcp_share as m
from fast_transfer.mcp_official_http import OfficialHTTPSDriver
from fast_transfer.mcp_discovery import OfficialDiscoverySession
from test_mcp_sse import script


class OfficialProfileTests(unittest.TestCase):
    def driver(self):
        d=OfficialHTTPSDriver();self.addCleanup(d.close);return d
    def test_profiles_separate_actual_and_legacy_routes(self):
        url=s.message_endpoint('/message?sessionId=synthetic',profile='official')
        self.assertEqual(url,s.ORIGIN+'/message?sessionId=synthetic')
        with self.assertRaises(m.Rejected):s.message_endpoint(url)
        with self.assertRaises(m.Rejected):s.message_endpoint('/messages?session_id=x',profile='official')
    def test_official_profile_rejects_redirect_auth_query_path_and_origin_drift(self):
        for value in ['/message/?sessionId=x','/message?sessionId=x&access_token=y','/message?sessionId=x&sessionId=y',
                      '/message?sessionId=%78','/message?sessionId=x#y','https://evil.invalid/message?sessionId=x',
                      'http://mcp-pan.baidu.com/message?sessionId=x','https://user@mcp-pan.baidu.com/message?sessionId=x',
                      'https://mcp-pan.baidu.com:444/message?sessionId=x','/other?sessionId=x']:
            with self.subTest(value=value),self.assertRaises(m.Rejected):s.message_endpoint(value,profile='official')
    def test_noauth_open_path_and_business_call_blocked(self):
        d=self.driver();self.assertEqual(d._opening_path(),'/sse')
        with self.assertRaisesRegex(m.Rejected,'authentication_required'):
            d.post(s.ORIGIN+'/message?sessionId=synthetic',s.encode({'method':'tools/call','params':{'name':'user_info'}}))
        self.assertEqual(d.trace,[])
    def test_discovery_rejects_real_or_synthetic_credentials(self):
        d=OfficialHTTPSDriver(access_token='SYNTHETIC_ONLY');self.addCleanup(d.close)
        with self.assertRaises(m.Rejected):OfficialDiscoverySession(d)
    def test_discovery_denies_business_directly_and_at_rpc(self):
        client=OfficialDiscoverySession(self.driver())
        for method in ('tools/call','resources/read','unknown'):
            with self.assertRaises(m.Rejected):client.rpc(method)
        with self.assertRaises(m.Rejected):client.tool('user_info',{})
        self.assertEqual(client.driver.trace,[])
    def test_production_factory_full_synthetic_official_profile_discovery(self):
        driver=self.driver();client=OfficialDiscoverySession(driver)
        wire=s.ScriptedHTTP(script()[:3],opening=b'event: endpoint\ndata: /message?sessionId=synthetic\n\n')
        def post(url,raw):
            s.message_endpoint(url,profile='official')
            return wire.post(s.ORIGIN+'/messages/?session_id=synthetic',raw)
        with patch.object(driver,'open',side_effect=wire.open),patch.object(driver,'post',side_effect=post),patch.object(driver,'read',side_effect=wire.read):
            client.connect()
        report=client.summary();self.assertTrue(report['schema_discovery_completed'])
        self.assertFalse(report['live_authenticated']);self.assertEqual(report['tool_count'],3)
        self.assertEqual(report['selected_tool_schemas']['file_meta']['required'],['fsids'])
        self.assertEqual(client.called,set());client.close();self.assertEqual(client.descriptors,{})
    def test_summary_never_copies_descriptions_defaults_or_examples(self):
        client=OfficialDiscoverySession(self.driver());client.descriptors={'user_info':{'type':'object',
            'properties':{'access_token':{'type':'string','default':'SYNTHETIC_PRIVATE','description':'SYNTHETIC_PRIVATE'}},
            'required':['access_token'],'examples':['SYNTHETIC_PRIVATE']}}
        self.assertNotIn('SYNTHETIC_PRIVATE',str(client.summary()))
        self.assertEqual(client.summary()['selected_tool_schemas']['user_info']['required'],['access_token'])
    def test_observed_empty_tool_list_is_discovery_not_authentication(self):
        client=OfficialDiscoverySession(self.driver());client.review_descriptors({});client.connected=True
        report=client.summary()
        self.assertEqual(report['tool_count'],0);self.assertTrue(report['schema_discovery_completed'])
        self.assertFalse(report['selected_tool_schemas']['user_info']['present'])
        self.assertFalse(report['account_verified'] or report['object_verified'] or report['share_eligible'])
    def test_official_http_post_accepts_only_observed_profile(self):
        from unittest.mock import MagicMock
        d=self.driver();connection=MagicMock();reply=MagicMock();reply.status=202
        reply.getheaders.return_value=[];reply.getheader.side_effect=lambda key,default=None:default
        connection.getresponse.return_value=reply
        with patch.object(d,'_connection',return_value=connection):
            status=d.post(s.ORIGIN+'/message?sessionId=synthetic',s.encode({'method':'notifications/initialized'}))
        self.assertEqual(status,202)
        self.assertEqual(connection.request.call_args.args[:2],('POST','/message?sessionId=synthetic'))
        self.assertEqual(d.http_statuses,[202]);self.assertNotIn('sessionId',str(d.trace))
        with self.assertRaises(m.Rejected):d.post(s.ORIGIN+'/messages?session_id=synthetic',s.encode({'method':'tools/list'}))

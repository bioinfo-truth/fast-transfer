"""Non-secret candidate binding tests; no actual official authentication."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_mcp_share import prepare,guarded
from test_mcp_sse import script,tool,result
from fast_transfer import mcp_binding as b,mcp_share as m,mcp_sse as s
from fast_transfer.workflow import Job,digest


def envelope(fields):return {'content':[{'type':'text','text':json.dumps(fields)}]}


class BindingTests(unittest.TestCase):
    def setUp(self):
        if not guarded():self.skipTest('requires kernel guard runner')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        old=prepare(self.root);state=old.read();state['job_id']='synthetic-bound-job'
        state['mapping']['simulated_target']='/apps/Xtransfer/mvp-validation/synthetic-bound-job/fixture.fna'
        new=Job(old.root.parent,state['job_id']);old.root.rename(new.root);new.save(state)
        self.job=new;mapping=state['mapping']
        self.expected=b.ExpectedObject(new.job_id,'3003','Xtransfer','4004',mapping['simulated_target'],
            mapping['size'],mapping['md5'],mapping['sha256'],digest(mapping))
    def steps(self):
        steps=script();steps[3]=('tools/call','user_info',tool(3,{'uk':3003,'avatar_url':'synthetic','vip_type':2}))
        steps[4]=('tools/call','file_meta',tool(4,{'list':[{'fsid':4004,'path':self.expected.path,
            'size':self.expected.size,'md5':self.expected.md5,'filename':'fixture.fna'}]}))
        return steps
    def session(self,steps=None,expected=None):
        obj=b.BoundSession(s.ScriptedHTTP(steps or self.steps()),expected or self.expected)
        self.addCleanup(obj.close);return obj
    def run_stage(self,session=None):
        obj=session or self.session();return b.stage_candidate_share(self.job,obj,pwd='a1b2'),obj
    def test_non_fixture_account_and_object_full_candidate_flow(self):
        report,obj=self.run_stage()
        self.assertEqual(report['status'],'candidate_unverified')
        self.assertTrue(report['create_attempted'] and report['outcome_unknown'])
        self.assertFalse(report['live_authenticated'] or report['mapping_verified'] or report['delivery_eligible'])
        self.assertEqual(obj.driver.trace[-1]['tool'],'file_sharelink_set')
        self.assertEqual(self.job.read()['phase'],'manual_review')
    def test_uk_match_never_proves_application_or_business_envelope(self):
        obj=self.session();report=obj.inspect()
        self.assertTrue(report['candidate_fields_match'])
        self.assertFalse(report['application_proven'] or report['business_envelope_verified'])
        self.assertIn('credential_application_scope',report['missing_evidence'])
    def test_wrong_account_prevents_metadata_and_share(self):
        report,obj=self.run_stage(self.session(expected=replace(self.expected,account='9009')))
        self.assertFalse(report['create_attempted'])
        self.assertEqual(report['reason'],'mcp_binding_account_mismatch')
        self.assertEqual(obj.called,{'user_info'})
    def test_each_exact_object_field_and_duplicates_prevent_share(self):
        for field,value in [('fsid',5005),('size',True),('size',17),('path','/apps/Xtransfer/other'),('md5','0'*32)]:
            with self.subTest(field=field):
                steps=self.steps();item={'fsid':4004,'path':self.expected.path,'size':16,'md5':self.expected.md5}
                item[field]=value;steps[4]=('tools/call','file_meta',tool(4,{'list':[item]}))
                report,obj=self.run_stage(self.session(steps))
                self.assertFalse(report['create_attempted']);self.assertNotIn('file_sharelink_set',obj.called)
        steps=self.steps();steps[4]=('tools/call','file_meta',tool(4,{'list':[{},{}]}))
        self.assertFalse(self.run_stage(self.session(steps))[0]['create_attempted'])
    def test_job_mapping_hash_and_sha256_drift_stop_before_io(self):
        for expected in [replace(self.expected,mapping_sha256='0'*64),replace(self.expected,sha256='0'*64),replace(self.expected,task='other')]:
            report,obj=self.run_stage(self.session(expected=expected))
            self.assertFalse(report['create_attempted']);self.assertEqual(obj.driver.trace,[])
    def test_unknown_business_envelopes_and_error_flags_rejected(self):
        for raw in [{'errno':0,'data':{}},{'content':[]},{'content':[{'type':'text','text':'```json\n{}\n```'}]},
                    {'isError':True,'content':[]},{'isError':1,'content':[]},
                    {'content':[{'type':'text','text':'{"uk":1,"uk":2}'}]}]:
            with self.assertRaises(m.Rejected):b.decode_result(raw)
    def test_unknown_identity_provenance_fields_are_not_invented(self):
        for fields in [{'uk':3003,'app':'Xtransfer'},{'uk':True},{'uk':'03003'},{'errno':0,'uk':3003}]:
            with self.assertRaises(m.Rejected):b.check_identity(fields,self.expected)
    def test_persist_failure_never_dispatches_share(self):
        obj=self.session()
        with patch.object(self.job,'save',side_effect=OSError('SYNTHETIC_PRIVATE')):
            report,_=self.run_stage(obj)
        self.assertFalse(report['create_attempted']);self.assertNotIn('file_sharelink_set',obj.called)
        self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(report))
    def test_share_timeout_consumes_existing_job_across_new_session(self):
        steps=self.steps();steps[5]=('tools/call','file_sharelink_set','timeout')
        report,obj=self.run_stage(self.session(steps))
        self.assertTrue(report['create_attempted'] and report['outcome_unknown'])
        reopened=Job(self.job.root.parent,self.job.job_id)
        fresh=self.session();r=b.stage_candidate_share(reopened,fresh,pwd='a1b2')
        self.assertFalse(r['create_attempted']);self.assertTrue(r['outcome_unknown']);self.assertEqual(fresh.driver.trace,[])
    def test_share_malformed_response_remains_unknown_and_not_deliverable(self):
        steps=self.steps();steps[5]=('tools/call','file_sharelink_set',tool(5,{'errno':0,'link':'SYNTHETIC_PRIVATE'}))
        report,_=self.run_stage(self.session(steps))
        self.assertTrue(report['outcome_unknown']);self.assertFalse(report['delivery_eligible'])
    def test_state_and_repr_do_not_persist_private_bindings_or_result(self):
        report,obj=self.run_stage()
        text=(self.job.root/'state.json').read_text()+json.dumps(report)+repr(self.expected)+repr(obj)
        for secret in ('synthetic_link','synthetic_short','a1b2','3003','4004'):self.assertNotIn(secret,text)
    def test_bad_expectation_and_arbitrary_object_request_rejected(self):
        for delta in [{'size':True},{'path':'/apps/Other/x'},{'fsid':'0'},{'account':True},{'md5':'X'*32}]:
            with self.assertRaises(m.Rejected):replace(self.expected,**delta)
        obj=self.session()
        with self.assertRaises(m.Rejected):obj.tool('file_meta',{'fsids':[4005]})
        self.assertEqual(obj.driver.trace,[])
    def test_official_readonly_scope_rejected_before_state_or_share(self):
        from fast_transfer.mcp_official_http import OfficialHTTPSDriver
        driver=OfficialHTTPSDriver(access_token='SYNTHETIC_ONLY');self.addCleanup(driver.close)
        obj=b.BoundSession.official_readonly(driver,self.expected)
        with patch.object(self.job,'read',side_effect=AssertionError('no state read')):
            report,_=self.run_stage(obj)
        self.assertEqual(report['reason'],'mcp_official_operation_locked')
        self.assertEqual(driver.trace,[])
        with self.assertRaises(m.Rejected):obj.tool('file_sharelink_set',self.expected.arguments(7,'a1b2'))

    def test_official_factory_reads_only_bound_id_using_synthetic_wire(self):
        from fast_transfer.mcp_official_http import OfficialHTTPSDriver
        driver=OfficialHTTPSDriver(access_token='SYNTHETIC_ONLY');self.addCleanup(driver.close)
        obj=s.SSEClient.for_official_readonly(driver,expected=self.expected);self.addCleanup(obj.close)
        steps=self.steps()[:5]
        steps[2]=('tools/list',None,result(2,{'tools':[{'name':name,'inputSchema':s.schemas()[name]}
            for name in ('user_info','file_meta')]}))
        wire=s.ScriptedHTTP(steps)
        with patch.object(driver,'open',side_effect=wire.open),patch.object(driver,'post',side_effect=wire.post),patch.object(driver,'read',side_effect=wire.read):
            report=obj.inspect()
        self.assertTrue(report['candidate_fields_match']);self.assertFalse(report['live_authenticated'])
        self.assertEqual(obj.called,{'user_info','file_meta'})
        self.assertFalse(any(x.get('tool')=='file_sharelink_set' for x in wire.trace))

    def test_fresh_process_sees_consumed_intent_and_sends_no_requests(self):
        import subprocess,sys
        steps=self.steps();steps[5]=('tools/call','file_sharelink_set','timeout')
        self.run_stage(self.session(steps))
        source="""import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from fast_transfer.mcp_binding import ExpectedObject,BoundSession,stage_candidate_share
from fast_transfer.mcp_sse import ScriptedHTTP
from fast_transfer.workflow import Job,digest
job=Job(Path(sys.argv[2]),'synthetic-bound-job');v=job.read()['mapping']
e=ExpectedObject(job.job_id,'3003','Xtransfer','4004',v['simulated_target'],v['size'],v['md5'],v['sha256'],digest(v))
session=BoundSession(ScriptedHTTP([]),e)
r=stage_candidate_share(job,session,pwd='a1b2')
assert r['outcome_unknown'] and not r['create_attempted'] and not session.driver.trace
print('consumed_no_requests')
"""
        p=subprocess.run([sys.executable,'-I','-S','-B','-c',source,str(Path(__file__).resolve().parents[1]),str(self.job.root.parent)],
            env={},stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr.decode());self.assertEqual(p.stdout,b'consumed_no_requests\n')

    def test_existing_job_lock_blocks_parallel_candidate_before_dispatch(self):
        obj=self.session()
        with self.job.locked():report,_=self.run_stage(obj)
        self.assertFalse(report['create_attempted']);self.assertEqual(obj.driver.trace,[])

    def test_unconfirmed_protocol_close_cannot_look_finished(self):
        obj=self.session();obj.driver.close_ok=False
        report,_=self.run_stage(obj)
        self.assertEqual(report['status'],'manual_review');self.assertFalse(report['protocol_closed'])

"""MCP document-field candidates only; never a server session or wire fixture."""
import contextlib
from dataclasses import replace
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from fast_transfer import mcp_share as m
from fast_transfer.workflow import Job


def guarded():
    try:s=socket.socket()
    except OSError as exc:return exc.errno==errno.EPERM
    s.close();return False


def observation(obj, **kw):return m.Observation(json.dumps(obj).encode(), **kw)


def fixture():
    return m.FixtureTransport(observation({'uk':m.FIXTURE_UK}),
        observation({'list':[{'fsid':m.FIXTURE_FSID,'path':m.FIXTURE_PATH,
                              'size':16,'md5':hashlib.md5(m.FIXTURE_DATA).hexdigest()}]}),
        observation({'link':'https://pan.baidu.com/s/synthetic_link',
                     'short_url':'https://pan.baidu.com/s/synthetic_short','period':7,'pwd':'a1b2'}))


def prepare(root):
    for name in ('jobs','source','backend'):(root/name).mkdir()
    manifest=json.loads((REPO/'examples/ncbi-ecoli/manifest.json').read_text())
    e=manifest['files'][0];e.update(name='fixture.fna',size=16,md5=hashlib.md5(m.FIXTURE_DATA).hexdigest())
    (root/'source/fixture.fna').write_bytes(m.FIXTURE_DATA)
    (root/'source/.receipts').mkdir()
    (root/'source/.receipts/0.json').write_text(json.dumps({'file':'fixture.fna','status':'source_verified','bytes':16,
        'md5':e['md5'],'sha256':hashlib.sha256(m.FIXTURE_DATA).hexdigest()}))
    job=Job(root/'jobs',m.FIXTURE_TASK);job.create(manifest)
    assert job.simulate(manifest,root/'source',root/'backend')['phase']=='simulated_cloud_verified'
    return job


class MCPShareTests(unittest.TestCase):
    def setUp(self):
        if not guarded():self.skipTest('requires kernel guard runner')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def job(self):
        root=Path(tempfile.mkdtemp(dir=self.root));return prepare(root)
    def attempt(self,job=None,transport=None,**kw):
        return m.exercise_share(job or self.job(),transport or fixture(),pwd=kw.pop('pwd','a1b2'),**kw)
    def assert_closed(self,r):
        for k in ('mapping_verified','live_authenticated','share_eligible','delivery_eligible','automatic_retry_allowed'):
            self.assertIs(r[k],False)
    def test_minimal_arguments_use_json_string_array_and_explicit_local_period(self):
        args=m.ShareArguments(m.FIXTURE_FSID,7,'a1b2')
        raw=args.fixture_arguments()
        self.assertEqual(set(raw),{'fsid_list','period','pwd'})
        self.assertIs(type(raw['fsid_list']),str);self.assertEqual(json.loads(raw['fsid_list']),[m.FIXTURE_FSID])
        self.assertEqual(raw['period'],7);self.assertEqual(raw['pwd'],'a1b2')
        self.assertNotIn('a1b2',repr(args))
    def test_valid_candidate_stays_unverified_without_invented_share_mapping(self):
        job=self.job();t=fixture();r=self.attempt(job,t)
        self.assertEqual(r['status'],'candidate_unverified');self.assertEqual(r['reason'],'mcp_share_mapping_unproven')
        self.assertTrue(r['create_attempted'] and r['outcome_unknown']);self.assert_closed(r)
        self.assertEqual(t.calls,['user_info','file_meta','file_sharelink_set'])
        state=job.view();self.assertEqual(state['phase'],'manual_review');self.assertFalse(state['delivery_eligible'])
        self.assertNotIn('share',state)
    def test_identity_mismatch_or_missing_identity_prevents_create(self):
        for obj in ({'uk':'9999'},{},{'uk':1001},{'uk':True},{'uk':m.FIXTURE_UK,'verified':True}):
            t=fixture();t._observations['user_info']=observation(obj)
            r=self.attempt(transport=t);self.assertFalse(r['create_attempted']);self.assert_closed(r)
            self.assertNotIn('file_sharelink_set',t.calls)
    def test_app_session_account_or_task_drift_never_becomes_authentication(self):
        for op in ('user_info','file_meta'):
            for key in ('app','session','account','task'):
                t=fixture();t._observations[op]=replace(t._observations[op],**{key:'other'})
                r=self.attempt(transport=t)
                self.assertEqual(r['reason'],'mcp_fixture_scope_mismatch');self.assertFalse(r['create_attempted'])
    def test_return_provenance_drift_after_create_is_unknown_and_consumed(self):
        job=self.job();t=fixture();t._share=replace(t._share,app='other')
        r=self.attempt(job,t);self.assertTrue(r['create_attempted'] and r['outcome_unknown'])
        fresh=fixture();self.attempt(job,fresh);self.assertEqual(fresh.calls,[])
    def test_object_fsid_path_size_hash_and_duplicates_prevent_create(self):
        for key,value in [('fsid','9999'),('fsid',2001),('path',m.FIXTURE_PATH+'-other'),('size',True),('size',17),('md5','0'*32)]:
            t=fixture();obj=json.loads(t._observations['file_meta'].raw);obj['list'][0][key]=value
            t._observations['file_meta']=observation(obj)
            self.assertFalse(self.attempt(transport=t)['create_attempted'])
        t=fixture();obj=json.loads(t._observations['file_meta'].raw);obj['list']*=2
        t._observations['file_meta']=observation(obj);self.assertFalse(self.attempt(transport=t)['create_attempted'])
    def test_job_scope_and_pending_workflow_do_not_dispatch(self):
        job=self.job();job.manual('verify_source');t=fixture()
        self.assertFalse(self.attempt(job,t)['create_attempted']);self.assertEqual(t.calls,[])
        job=self.job();state=job.read();state['mapping']['md5']='0'*32
        with job.locked():job.save(state)
        t=fixture();self.assertFalse(self.attempt(job,t)['create_attempted']);self.assertEqual(t.calls,[])
    def test_explicit_normalized_permission_denial_is_not_an_official_error_code(self):
        for op in ('user_info','file_meta','share'):
            t=fixture()
            if op=='share':t._share=replace(t._share,status='permission_denied')
            else:t._observations[op]=replace(t._observations[op],status='permission_denied')
            r=self.attempt(transport=t)
            self.assertEqual(r['reason'],'mcp_fixture_permission_denied');self.assert_closed(r)
            self.assertEqual(r['create_attempted'],op=='share')
    def test_unknown_status_or_rest_cookie_envelopes_are_not_mcp_success(self):
        for obj in ({'errno':0,'data':{'link':'synthetic'}},{'isError':False,'content':[]},{'code':13998}):
            t=fixture();t._share=observation(obj)
            r=self.attempt(transport=t);self.assertTrue(r['outcome_unknown']);self.assertNotEqual(r['status'],'candidate_unverified')
        t=fixture();t._share=replace(t._share,status='success')
        self.assertEqual(self.attempt(transport=t)['reason'],'mcp_response_contract_unknown')
    def test_missing_or_malformed_fields_do_not_create_verified_link(self):
        for key in ('link','short_url','period','pwd'):
            t=fixture();obj=json.loads(t._share.raw);del obj[key];t._share=observation(obj)
            r=self.attempt(transport=t);self.assertTrue(r['outcome_unknown']);self.assert_closed(r)
        for delta in ({'period':True},{'period':30},{'pwd':'zzzz'},{'short_url':123},{'owner':m.FIXTURE_UK}):
            t=fixture();t._share=observation({**json.loads(t._share.raw),**delta})
            self.assertNotEqual(self.attempt(transport=t)['status'],'candidate_unverified')
    def test_illegal_urls_rejected_after_intent_without_retries(self):
        for value in ('javascript:alert(1)','http://pan.baidu.com/s/abcdef','https://pan.baidu.com.evil/s/abcdef',
                      'https://user@pan.baidu.com/s/abcdef','https://pan.baidu.com/s/abcdef?pwd=SECRET',
                      'https://pan.baidu.com/s/abcdef#secret','https://pan.baidu.com/s/%61bcdef'):
            job=self.job();t=fixture();t._share=observation({**json.loads(t._share.raw),'link':value})
            r=self.attempt(job,t);self.assertEqual(r['reason'],'mcp_candidate_url_invalid')
            other=fixture();self.attempt(job,other);self.assertEqual(other.calls,[])
    def test_bad_argument_types_and_extra_credentials_cannot_enter_tool_arguments(self):
        for period,pwd in [(True,'a1b2'),(0,'a1b2'),(30,'a1b2'),(7,'ABCD'),(7,'abcd?'),(7,1234)]:
            t=fixture();r=self.attempt(transport=t,period=period,pwd=pwd)
            self.assertFalse(r['create_attempted']);self.assertNotIn('file_sharelink_set',t.calls)
        with self.assertRaises(TypeError):m.ShareArguments(m.FIXTURE_FSID,7,'a1b2',access_token='SYNTHETIC')
    def test_timeout_has_persisted_intent_and_fresh_process_cannot_resend(self):
        job=self.job();t=fixture();t._share='timeout'
        r=self.attempt(job,t);self.assertEqual(r['reason'],'mcp_fixture_create_outcome_unknown')
        self.assertEqual(t.calls.count('file_sharelink_set'),1)
        home=self.root/'home';home.mkdir()
        p=subprocess.Popen([sys.executable,'-I','-S','-B',__file__,'reopen',str(job.root.parent)],
            env={'HOME':str(home),'XDG_CONFIG_HOME':str(home/'config'),'TMPDIR':str(self.root)},
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,cwd=self.root)
        try:out,err=p.communicate(timeout=10)
        finally:
            if p.poll() is None:p.kill();p.communicate(timeout=3)
        self.assertEqual(p.returncode,0,err.decode());self.assertEqual(err,b'')
        fresh=json.loads(out);self.assertEqual(fresh['calls'],[]);self.assertFalse(fresh['result']['create_attempted'])
        self.assertTrue(fresh['result']['outcome_unknown'])
        self.assertEqual(job.view()['phase'],'manual_review')
    def test_persist_failure_prevents_fixture_dispatch(self):
        for error in (OSError('SYNTHETIC_PRIVATE_ERROR'),TimeoutError('SYNTHETIC_PRIVATE_ERROR')):
            job=self.job();t=fixture()
            with patch.object(job,'save',side_effect=error):r=self.attempt(job,t)
            self.assertFalse(r['create_attempted']);self.assertFalse(r['outcome_unknown'])
            self.assertNotIn('file_sharelink_set',t.calls)
            self.assertEqual(r['reason'],'mcp_fixture_input_or_state_invalid')
            self.assertNotIn('SYNTHETIC_PRIVATE_ERROR',json.dumps(r))
    def test_duplicate_json_invalid_encoding_depth_and_oversize_are_rejected(self):
        for raw in (b'{"uk":"1001","uk":"1001"}',b'\xff',b'[]',b'{} {}',b'{"x":NaN}',
                    b'{' + b' ' * 16384 + b'}',b'{"a":'+b'['*10+b'0'+b']'*10+b'}'):
            t=fixture();t._observations['user_info']=m.Observation(raw)
            self.assertFalse(self.attempt(transport=t)['create_attempted'])
    def test_private_values_not_in_results_state_output_or_repr(self):
        job=self.job();t=fixture();stream=io.StringIO()
        with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):r=self.attempt(job,t)
        text=json.dumps(r)+(job.root/'state.json').read_text()+repr(t)+repr(t._share)+stream.getvalue()
        for secret in ('synthetic_link','synthetic_short','a1b2'):self.assertNotIn(secret,text)
        with patch.object(job,'read',side_effect=m.Rejected('SYNTHETIC_SECRET')):r=self.attempt(job,fixture())
        self.assertNotIn('SYNTHETIC_SECRET',json.dumps(r))
    def test_live_connection_and_custom_transport_remain_closed(self):
        with self.assertRaisesRegex(m.Rejected,'mcp_live_connection_unavailable'):m.live_connect()
        job=self.job();r=m.exercise_share(job,object(),pwd='a1b2')
        self.assertEqual(r['reason'],'mcp_fixture_transport_required');self.assertFalse(r['create_attempted'])
        class Subclass(m.FixtureTransport):pass
        t=fixture();sub=Subclass(t._observations['user_info'],t._observations['file_meta'],t._share)
        self.assertFalse(self.attempt(job,sub)['create_attempted'])


if __name__=='__main__' and len(sys.argv)>1 and sys.argv[1]=='reopen':
    assert guarded() and not list(Path(os.environ['HOME']).iterdir())
    t=fixture();r=m.exercise_share(Job(Path(sys.argv[2]),m.FIXTURE_TASK),t,pwd='a1b2')
    print(json.dumps({'result':r,'calls':t.calls}))

"""Actual SDK encoding plus a stateful synthetic service; no real cloud calls."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
import urllib.parse

from fast_transfer.baidu_http import HTTPReply, RuntimeGrant
from fast_transfer.sdk_codec import SDKRequestEncoder
from fast_transfer.task import Task, read_json
from fast_transfer.task_upload import run_next, TaskProtocol, TaskHTTP, main
from fast_transfer.upload_stage import StageFailure
from test_sdk_codec import HELPER, GUARD, sha
from test_baidu_protocol import ACCOUNT


def reply(obj):
    body=obj if type(obj) is bytes else json.dumps(obj).encode()
    stream=io.BytesIO(body)
    return HTTPReply(200,[],stream.read1,stream.close,time.monotonic()+120)


class Cloud:
    def __init__(self, data):
        self.data=data;self.rows={};self.by_path={};self.sessions={};self.events=[]
        self.next_id=10;self.drop_locate=False;self.drop_commit=False
        self.corrupt_readback=False;self.required=None;self.stop_ok=True;self.free=100_000_000_000
    def add(self,path,size,isdir,data=b''):
        self.next_id+=1;fid=self.next_id
        self.rows[fid]={'fs_id':fid,'path':path,'size':size,'isdir':isdir,'data':data}
        self.by_path[path]=fid;return fid


class MemoryAPI:
    mode='fake-http'
    def __init__(self, cloud):self.cloud=cloud;self.stopped=False
    def exchange(self,req):
        req.validate();c=self.cloud
        p=req.params;method=p.get('method');form={}
        if req.purpose=='control' and req.body:form=dict(urllib.parse.parse_qsl(req.body.decode('ascii')))
        if req.purpose=='readback':
            c.events.append('readback');fid=int(req.url.rsplit('/',1)[1]);data=c.rows[fid]['data']
            return reply(data if not c.corrupt_readback else b'X'*len(data))
        if method=='uinfo':return reply({'errno':0,'uk':42,'vip_type':2})
        if req.url.endswith('/api/quota'):return reply({'errno':0,'total':c.free,'used':0,'expire':False})
        if method=='create' and form.get('isdir')=='1':
            c.events.append('directory')
            if form['path'] in c.by_path:return reply({'errno':-8})
            fid=c.add(form['path'],0,1)
            return reply({'errno':0,'fs_id':fid,'path':form['path'],'isdir':1})
        if method=='filemetas':
            rows=[]
            for fid in json.loads(p['fsids']):
                row=c.rows[fid];public={k:v for k,v in row.items() if k!='data'}
                if not row['isdir']:public['dlink']='https://d.pcs.baidu.com/readback/'+str(fid)
                rows.append(public)
            return reply({'errno':0,'list':rows})
        if method=='precreate':
            c.events.append('precreate');hashes=json.loads(form['block_list']);session='SYNTHETIC-'+str(len(c.sessions))
            required=list(range(len(hashes))) if c.required is None else c.required
            parts={};data=c.data[Path(form['path']).name]
            for i in set(range(len(hashes)))-set(required):parts[i]=data[i*4*1024**2:(i+1)*4*1024**2]
            c.sessions[session]={'path':form['path'],'size':int(form['size']),'hashes':hashes,'parts':parts}
            # Official SDK response shape: no required path field.
            return reply({'errno':0,'return_type':1,'uploadid':session,'block_list':required})
        if method=='locateupload':
            c.events.append('locate')
            if c.drop_locate:c.drop_locate=False;raise StageFailure('http_io_failure')
            return reply({'error_code':0,'servers':[{'server':'https://c.pcs.baidu.com'}]})
        if req.purpose=='upload':
            part=int(p['partseq']);c.events.append('part:'+str(part))
            data=req.body.split(b'\r\n\r\n',1)[1].rsplit(b'\r\n--',1)[0]
            c.sessions[p['uploadid']]['parts'][part]=data
            return reply({'md5':hashlib.md5(data).hexdigest()})
        if method=='create':
            c.events.append('commit');s=c.sessions[form['uploadid']]
            if json.loads(form['block_list'])!=s['hashes']:raise AssertionError('not all original hashes committed')
            data=b''.join(s['parts'][i] for i in range(len(s['hashes'])))
            if len(data)!=s['size']:raise AssertionError('commit wrong size')
            fid=c.add(s['path'],len(data),0,data)
            if c.drop_commit:c.drop_commit=False;raise StageFailure('http_io_failure')
            return reply({'errno':0,'fs_id':fid,'path':s['path'],'size':len(data),'isdir':0})
        raise AssertionError('unexpected operation')
    def stop(self):self.stopped=True;return self.cloud.stop_ok


class TaskUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HELPER.is_file():raise unittest.SkipTest('Build the actual SDK encoder first')
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.guard=self.root/'guard.py';self.guard.write_bytes(GUARD.read_bytes());self.guard.chmod(0o600)
        self.codec=SDKRequestEncoder(HELPER,sha(HELPER),self.guard,sha(self.guard))
        self.manifest=json.loads((Path(__file__).resolve().parents[1]/'examples/ncbi-ecoli/manifest.json').read_text())
        self.data={'fixture.fna':b'ACGT'*1024}
        self.configure()
    def configure(self):
        base=json.loads(json.dumps(self.manifest['files'][0]));entries=[]
        for name,data in self.data.items():
            e=json.loads(json.dumps(base));e.update(name=name,size=len(data),md5=hashlib.md5(data).hexdigest());e.pop('sha256',None);entries.append(e)
        self.manifest={'schema_version':1,'files':entries}
        self.task=Task.create(self.root,self.manifest);self.cloud=Cloud(self.data);self.factory_calls=0;self.last=None
    def download(self,entry,path,*a,**kw):
        data=self.data[entry['name']];fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(data)
        return {'bytes':len(data),'md5':hashlib.md5(data).hexdigest(),'sha256':hashlib.sha256(data).hexdigest()}
    def prepare(self):self.task.next_source(downloader=self.download)
    def factory(self,target,identity,limits,app_name):
        self.factory_calls+=1
        self.last=TaskProtocol(MemoryAPI(self.cloud),app_name,target,ACCOUNT,limits,self.codec,test_mode=True)
        return self.last
    def run_upload(self,**kwargs):return run_next(self.task,self.factory,ACCOUNT,**kwargs)
    def count(self,name):return self.cloud.events.count(name)

    def test_full_sdk_task_flow_is_verified_but_fixture_is_never_real(self):
        self.prepare();r=self.run_upload()
        self.assertEqual(r['status'],'test_cloud_verified');self.assertFalse(r['cloud_verified']);self.assertFalse(r['delivered'])
        self.assertEqual(self.cloud.events,['directory','precreate','locate','part:0','commit','readback'])
        view=self.task.view();self.assertEqual(view['upload_backend'],'test-fixture');self.assertFalse(view['cloud_backend_connected'])
        self.assertEqual(view['files'][0]['phase'],'test_cloud_verified')
        self.assertEqual(self.run_upload()['status'],'no_pending_upload')
        self.assertEqual(self.count('commit'),1)

    def test_precreate_receipt_survives_node_lookup_failure(self):
        self.prepare();self.cloud.drop_locate=True
        with self.assertRaisesRegex(StageFailure,'http_io_failure'):self.run_upload()
        self.assertEqual(self.task.view()['unknown_operations'],0)
        self.assertEqual(self.count('precreate'),1)
        self.run_upload();self.assertEqual(self.count('precreate'),1);self.assertEqual(self.count('directory'),1)

    def test_resume_skips_confirmed_parts_and_commits_all_original_hashes(self):
        self.data={'fixture.fna':b'A'*(4*1024**2)+b'C'*123};self.configure();self.prepare()
        def stop(operation,part):
            if operation=='part' and part==0:raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.run_upload(checkpoint_hook=stop)
        self.assertEqual(self.count('part:0'),1);self.assertEqual(self.count('commit'),0)
        self.assertTrue(self.last.client.stopped)
        self.task=Task(self.root,self.task.job_id)
        self.run_upload();self.assertEqual(self.count('part:0'),1);self.assertEqual(self.count('part:1'),1);self.assertEqual(self.count('precreate'),1)

    def test_server_required_subset_does_not_shrink_commit_hash_list(self):
        self.data={'fixture.fna':b'A'*(4*1024**2)+b'C'*123};self.configure();self.cloud.required=[1];self.prepare()
        self.run_upload();self.assertEqual(self.count('part:0'),0);self.assertEqual(self.count('part:1'),1);self.assertEqual(self.count('commit'),1)

    def test_commit_confirmation_survives_readback_failure_without_reupload(self):
        self.prepare();self.cloud.corrupt_readback=True
        with self.assertRaisesRegex(StageFailure,'readback_hash'):self.run_upload()
        self.assertEqual(self.task.view()['files'][0]['phase'],'uploading');self.assertEqual(self.task.view()['unknown_operations'],0)
        self.cloud.corrupt_readback=False;self.run_upload()
        self.assertEqual(self.count('commit'),1);self.assertEqual(self.count('precreate'),1);self.assertEqual(self.count('part:0'),1);self.assertEqual(self.count('readback'),2)

    def test_unknown_commit_blocks_factory_and_never_retries(self):
        self.prepare();self.cloud.drop_commit=True
        with self.assertRaisesRegex(StageFailure,'http_io'):self.run_upload()
        self.assertEqual(self.task.view()['unknown_operations'],1);calls=self.factory_calls
        with self.assertRaisesRegex(Exception,'unknown_operation'):self.run_upload()
        self.assertEqual(self.factory_calls,calls);self.assertEqual(self.count('commit'),1)

    def test_two_files_share_one_directory_and_remain_separate(self):
        self.data={'fixture.fna':b'AAAA','second.fna':b'CCCC'};self.configure()
        self.prepare();self.run_upload();self.prepare();self.run_upload()
        self.assertEqual(self.count('directory'),1);self.assertEqual(self.count('commit'),2)
        self.assertEqual([r['phase'] for r in self.task.view()['files']],['test_cloud_verified']*2)

    def test_source_change_stops_before_factory_or_cloud_calls(self):
        self.prepare();path=self.task.source_path(0,self.manifest['files'][0]);path.write_bytes(b'X'*len(self.data['fixture.fna']))
        with self.assertRaises(Exception):self.run_upload()
        self.assertEqual(self.factory_calls,0);self.assertFalse(self.cloud.events)

    def test_false_stop_does_not_grant_verification(self):
        self.prepare();self.cloud.stop_ok=False
        with self.assertRaisesRegex(StageFailure,'stop_unconfirmed'):self.run_upload()
        self.assertEqual(self.task.view()['files'][0]['phase'],'uploading')
        self.cloud.stop_ok=True;self.run_upload();self.assertEqual(self.count('commit'),1)

    def test_fixture_history_cannot_be_promoted_to_real_before_credentials(self):
        self.prepare();self.cloud.drop_locate=True
        with self.assertRaises(StageFailure):self.run_upload()
        provider=Mock(side_effect=AssertionError('no credential access'))
        def live(target,identity,limits,app_name):
            grant=RuntimeGrant(True,target,ACCOUNT,identity['sha256'],'synthetic-test-scope',time.monotonic()+600)
            return TaskProtocol(TaskHTTP(grant=grant,credential_provider=provider),app_name,target,ACCOUNT,limits,self.codec)
        with self.assertRaisesRegex(StageFailure,'identity_changed'):run_next(self.task,live,ACCOUNT)
        provider.assert_not_called()

    def test_quota_rejects_before_any_mutation(self):
        self.prepare();self.cloud.free=0
        with self.assertRaisesRegex(StageFailure,'quota_insufficient'):self.run_upload()
        self.assertFalse(self.cloud.events);self.assertEqual(self.task.view()['unknown_operations'],0)

    def test_identical_restored_source_can_resume_after_stamp_change(self):
        self.prepare();self.cloud.drop_locate=True
        with self.assertRaises(StageFailure):self.run_upload()
        path=self.task.source_path(0,self.manifest['files'][0]);data=path.read_bytes()
        path.unlink();path.write_bytes(data);path.chmod(0o600)
        self.run_upload();self.assertEqual(self.count('precreate'),1)

    def test_approval_hash_is_rechecked_under_task_lock(self):
        self.prepare()
        with self.assertRaisesRegex(StageFailure,'scope_invalid'):
            self.run_upload(approved_task_spec_sha256='0'*64)
        self.assertEqual(self.factory_calls,0);self.assertFalse(self.cloud.events)

    def test_scope_http_requires_one_exact_armed_request_before_credentials(self):
        from fast_transfer.baidu_http import HTTPRequest
        provider=Mock(side_effect=AssertionError('not reached'))
        resolver=Mock(side_effect=AssertionError('no network'))
        target='/apps/Xtransfer/mvp-validation/'+self.task.job_id+'/fixture.fna'
        grant=RuntimeGrant(True,target,ACCOUNT,'a'*64,'synthetic-test-scope',time.monotonic()+600)
        client=TaskHTTP(grant=grant,credential_provider=provider,resolver=resolver)
        req=HTTPRequest('POST','https://pan.baidu.com/rest/2.0/xpan/file',target,params={'method':'create'},body=b'path=synthetic-only')
        with self.assertRaisesRegex(StageFailure,'not_journaled'):client.exchange(req)
        client.arm(req)
        changed=HTTPRequest('POST',req.url,target,params=req.params,body=b'path=changed')
        with self.assertRaisesRegex(StageFailure,'not_journaled'):client.exchange(changed)
        provider.assert_not_called();resolver.assert_not_called()

    def test_cli_requires_matching_approval_before_auth_file_access(self):
        import contextlib
        out=io.StringIO()
        args=['--tasks-dir',str(self.root),self.task.job_id,'--approve-job',self.task.job_id,
              '--approved-task-sha256','0'*64,'--authorization',str(self.root/'never-read.json'),
              '--expected-account-sha256',ACCOUNT,'--sdk-helper',str(HELPER),'--sdk-helper-sha256',sha(HELPER),
              '--sdk-guard',str(self.guard),'--sdk-guard-sha256',sha(self.guard)]
        with patch('fast_transfer.task_upload.access_token_first_field') as token,contextlib.redirect_stdout(out):
            self.assertEqual(main(args),2)
        token.assert_not_called();self.assertEqual(json.loads(out.getvalue())['reason'],'task_upload_scope_invalid')

    def test_bad_saved_session_never_reprecreates_or_sends_parts(self):
        self.prepare();self.cloud.drop_locate=True
        with self.assertRaises(StageFailure):self.run_upload()
        with self.task.locked() as db:
            row=db.execute("SELECT receipt FROM operations WHERE operation='precreate'").fetchone()
            receipt=json.loads(row['receipt']);receipt['hashes']=['0'*32]
            with db:db.execute("UPDATE operations SET receipt=? WHERE operation='precreate'",(json.dumps(receipt),))
        with self.assertRaisesRegex(StageFailure,'state_invalid'):self.run_upload()
        self.assertEqual(self.count('precreate'),1);self.assertEqual(self.count('part:0'),0)

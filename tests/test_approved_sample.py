import io
import json
import os
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import Mock,patch

from fast_transfer.approved_sample import (SampleHTTP,ApprovedSample,APPROVAL_REF,NAME,SIZE,MD5,SHA256,
                                          access_token_first_field)
from fast_transfer.baidu_http import HTTPRequest,RuntimeGrant,PinnedBaiduHTTPClient
from fast_transfer.upload_stage import StageFailure,TransferLimits
from test_baidu_protocol import ACCOUNT

TARGET='/apps/Xtransfer/mvp-validation/job-'+('a'*32)+'/'+NAME


class ApprovedTests(unittest.TestCase):
    def grant(self):return RuntimeGrant(True,TARGET,ACCOUNT,SHA256,APPROVAL_REF,time.monotonic()+60)

    def request(self,method,form):
        return HTTPRequest('POST','https://pan.baidu.com/rest/2.0/xpan/file',TARGET,
                           params={'method':method},body=urllib.parse.urlencode(form).encode())

    def test_default_clients_and_bare_sample_client_do_not_load_credentials(self):
        for cls in (PinnedBaiduHTTPClient,SampleHTTP):
            provider,resolver=Mock(),Mock();client=cls(credential_provider=provider,resolver=resolver)
            with self.assertRaisesRegex(StageFailure,'runtime_locked'):
                client.exchange(HTTPRequest('GET','https://pan.baidu.com/api/quota',TARGET))
            provider.assert_not_called();resolver.assert_not_called()

    def test_single_directory_intent_and_exact_scope_before_auth_or_dns(self):
        provider,resolver=Mock(return_value=None),Mock()
        client=SampleHTTP(grant=self.grant(),credential_provider=provider,resolver=resolver)
        wrong=self.request('create',{'path':'/apps/Xtransfer/old','isdir':1,'rtype':0})
        with self.assertRaisesRegex(StageFailure,'scope_invalid'):client.exchange(wrong)
        provider.assert_not_called();resolver.assert_not_called()
        req=self.request('create',{'path':TARGET.rsplit('/',1)[0],'isdir':1,'rtype':0})
        with self.assertRaisesRegex(StageFailure,'auth_missing'):client.exchange(req)
        # Intent is consumed before an I/O uncertainty; no second dispatch.
        with self.assertRaisesRegex(StageFailure,'replay'):client.exchange(req)
        self.assertEqual(provider.call_count,1);resolver.assert_not_called()

    def test_overwrite_revision_wrong_hash_and_cross_sample_are_rejected(self):
        client=SampleHTTP(grant=self.grant())
        client.attempts={'directory'}
        base={'path':TARGET,'size':SIZE,'isdir':0,'rtype':1,'block_list':json.dumps([MD5],separators=(',',':')),'autoinit':1}
        for delta in ({'rtype':3},{'is_revision':1},{'path':TARGET+'-other'},{'size':SIZE+1},{'block_list':'["bad"]'}):
            with self.subTest(delta=delta),self.assertRaisesRegex(StageFailure,'scope_invalid'):
                client.authorize_write(self.request('precreate',{**base,**delta}))
        client.authorize_write(self.request('precreate',base))
        req=HTTPRequest('POST','https://c.pcs.baidu.com/rest/2.0/pcs/superfile2',TARGET,'upload',
            {'method':'upload','type':'tmpfile','path':TARGET,'uploadid':'fixture','partseq':0},b'bad')
        with self.assertRaisesRegex(StageFailure,'scope_invalid'):client.authorize_write(req)
        with self.assertRaises(StageFailure):
            ApprovedSample(PinnedBaiduHTTPClient(),ACCOUNT,TransferLimits(4*1024**2,16*1024**2,1024))

    def test_sample_specific_adapter_requires_matching_account_and_entry(self):
        client=SampleHTTP(grant=self.grant())
        transport=ApprovedSample(client,ACCOUNT,TransferLimits(4*1024**2,16*1024**2,1024))
        self.assertEqual(transport.mode,'approved-live-sample')
        entry={'name':NAME,'size':SIZE,'md5':MD5,'sha256':SHA256}
        transport.validate_scope(entry,'job-'+('a'*32),'Xtransfer')
        with self.assertRaises(StageFailure):transport.validate_scope({**entry,'md5':'0'*32},'job-'+('a'*32),'Xtransfer')
        self.assertTrue(transport.stop());self.assertIsNone(client._credential)

    def test_token_loader_stops_before_any_later_field_and_rejects_other_layout(self):
        class Counted(io.BytesIO):
            def fileno(self):return 123
        data=b'{"access_token":"symbolic-test-only","refresh_token":"NEVER_READ"}'
        stream=Counted(data)
        end=data.index(b',')
        class Context:
            def __enter__(self):return stream
            def __exit__(self,*args):self.position=stream.tell()
        ctx=Context()
        fake=Mock(st_mode=0o100600,st_nlink=1)
        with patch('os.open',return_value=123),patch('os.fdopen',return_value=ctx),patch('os.fstat',return_value=fake):
            self.assertEqual(access_token_first_field('/unused'),'symbolic-test-only')
        self.assertEqual(ctx.position,end)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'auth.json';p.write_text('{"refresh_token":null,"access_token":null}');os.chmod(p,0o600)
            with self.assertRaisesRegex(StageFailure,'token_layout'):access_token_first_field(p)

    def test_explicit_lane_with_injected_fake_http_and_public_simulator_rejects_it(self):
        import hashlib
        from fast_transfer.approved_sample import run_approved_sample
        from fast_transfer.upload_stage import run_simulated_upload
        from fast_transfer.space import BackendNeeds
        from test_baidu_protocol import FakeHTTP
        data=b'ACGTACGT';md5=hashlib.md5(data).hexdigest();sha=hashlib.sha256(data).hexdigest()
        net=patch('socket.create_connection',side_effect=AssertionError('No network'))
        with net as socket_mock, patch('fast_transfer.approved_sample.SIZE',len(data)), patch('fast_transfer.approved_sample.MD5',md5), patch('fast_transfer.approved_sample.SHA256',sha), tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'source';src.mkdir();(src/'.receipts').mkdir();backend=root/'backend';backend.mkdir()
            manifest=json.loads((Path(__file__).resolve().parents[1]/'examples/ncbi-ecoli/manifest.json').read_text())
            entry=manifest['files'][0];entry.update(size=len(data),md5=md5,sha256=sha)
            (src/NAME).write_bytes(data)
            receipt=src/'.receipts/0.json';receipt.write_text(json.dumps({'file':NAME,'status':'source_verified','bytes':len(data),'md5':md5,'sha256':sha}))
            grant=RuntimeGrant(True,TARGET,ACCOUNT,sha,APPROVAL_REF,time.monotonic()+60)
            client=SampleHTTP(grant=grant)
            fake=FakeHTTP(data)
            def fault(req,obj):
                if req.params.get('method')=='filemetas':
                    row=obj['list'][0]
                    if json.loads(req.params['fsids'])==[7]:row.update(fs_id=7,path=TARGET.rsplit('/',1)[0],isdir=1)
                    else:row['path']=TARGET
                return obj
            fake.fault=fault
            client.exchange=fake.exchange  # Deliberate unit-only injection; no actual account claim.
            transport=ApprovedSample(client,ACCOUNT,TransferLimits(4*1024**2,16*1024**2,1024))
            needs=BackendNeeds('direct-api',65536,262144,262144,'stream')
            denied=run_simulated_upload(entry,src/NAME,receipt,backend,'job-'+('a'*32),'Xtransfer',transport,needs,transport.limits)
            self.assertEqual(denied['reason'],'transport_mode_or_app_mismatch');self.assertFalse(fake.calls)
            result=run_approved_sample(entry,src/NAME,receipt,backend,'job-'+('a'*32),transport,needs,transport.limits)
            self.assertEqual(result['status'],'verified_live_sample')
            self.assertTrue(result['cloud_verified']);self.assertFalse(result['delivery_eligible'])
            self.assertFalse(result['simulated_delivery_eligible']);socket_mock.assert_not_called()

    def test_precommit_recovery_rechecks_directory_and_never_recreates_it(self):
        from test_baidu_protocol import FakeHTTP,reply
        for mode in ('empty','nonempty','identity_drift','old_commit'):
            with self.subTest(mode=mode):
                client=SampleHTTP(grant=self.grant());fake=FakeHTTP()
                def exchange(req):
                    if req.params.get('method')=='list':
                        fake.calls.append(req)
                        return reply(json.dumps({'errno':0,'list':[] if mode=='empty' else [{'fs_id':99}]}).encode())
                    return fake.exchange(req)
                def fault(req,obj):
                    if req.params.get('method')=='filemetas':
                        obj['list'][0].update(fs_id=8 if mode=='identity_drift' else 7,path=TARGET.rsplit('/',1)[0],isdir=1)
                    return obj
                fake.fault=fault;client.exchange=exchange
                t=ApprovedSample(client,ACCOUNT,TransferLimits(4*1024**2,16*1024**2,1024))
                proof={'target':TARGET,'prior_commit_attempted':mode=='old_commit','prior_payload_sent':0,'directory_id':7}
                if mode=='empty':
                    t.inspect_empty_precommit_directory(proof)
                    t.reserve_new(TARGET.rsplit('/',1)[0])
                    self.assertEqual(t.phase,'reserved');self.assertEqual(client.attempts,{'directory'})
                else:
                    with self.assertRaises(StageFailure):t.inspect_empty_precommit_directory(proof)
                self.assertFalse(any(r.method=='POST' for r in fake.calls))

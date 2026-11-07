import hashlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fast_transfer.acceptance import (audit,check_file,prepare,write_new,digest,main,FLAGS)
from fast_transfer.intake import InputProblem
from fast_transfer.space import RESERVE


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        data=b'ACGT'*128;self.file=self.root/'fixture.fna';self.file.write_bytes(data)
        t=int(time.time())-10
        self.spec={'schema_version':1,'kind':'receipt_expectation','job_id':'job-receipt',
                   'manifest_sha256':'1'*64,'mapping_sha256':'2'*64,'source_version_sha256':'3'*64,
                   'origin':'simulation','file':{'name':'fixture.fna','bytes':len(data),'md5':hashlib.md5(data).hexdigest(),'sha256':hashlib.sha256(data).hexdigest()},
                   'upstream':{stage:{'kind':'simulation','record_sha256':str(i+4)*64,'completed_at':t+i,'outcome':'completed'} for i,stage in enumerate(('source','upload_readback','share'))},
                   'share_expires_at':t+1000}
        self.obs={'schema_version':1,'kind':'receipt_observation','job_id':'job-receipt','attempt_id':'attempt-1',
                  'spec_sha256':digest(self.spec),'mapping_sha256':self.spec['mapping_sha256'],
                  'device_ref_sha256':'a'*64,'location_claim':'mainland_cn','location_evidence_sha256':None,
                  'acquisition':{'kind':'simulation','method':'local_copy','started_at':t+3,'finished_at':t+4,'outcome':'completed'},
                  'observations':{'elapsed_ms':1000,'network_received_bytes':None,'minimum_free_bytes':RESERVE,'manual_steps':2}}
        for attr in ('socket','create_connection'):
            p=patch('socket.'+attr,side_effect=AssertionError('No sockets'));m=p.start();self.addCleanup(p.stop);self.addCleanup(m.assert_not_called)

    def bind(self):self.obs['spec_sha256']=digest(self.spec)

    def receipt(self):return check_file(self.spec,self.obs,self.file)

    def test_local_match_is_not_location_upload_share_or_delivery_evidence(self):
        r=self.receipt();self.assertTrue(r['file_check']['matches_expected'])
        for key in FLAGS:self.assertIs(r[key],False)
        self.assertIn('receiver_location_not_verified',r['review_reasons'])
        self.assertIn('real_upstream_evidence_not_verified',r['review_reasons'])
        self.assertNotIn(str(self.file),json.dumps(r))
        # Roundtrip sorted JSON must not reorder timeline semantics.
        spec=json.loads(json.dumps(self.spec,sort_keys=True))
        result=audit(spec,[r]);self.assertNotIn('time_order_invalid',result['review_reasons'])
        self.assertFalse(result['delivered'])

    def test_wrong_task_mapping_spec_and_filename_fail(self):
        for key,value in [('job_id','wrong'),('mapping_sha256','0'*64),('spec_sha256','0'*64)]:
            with self.subTest(key=key):
                old=self.obs[key];self.obs[key]=value
                with self.assertRaisesRegex(InputProblem,'wrong_mapping'):self.receipt()
                self.obs[key]=old
        other=self.root/'wrong.fna';other.write_bytes(self.file.read_bytes())
        with self.assertRaisesRegex(InputProblem,'wrong_filename'):check_file(self.spec,self.obs,other)

    def test_bytes_md5_and_sha256_must_each_match(self):
        self.file.write_bytes(b'X')
        with self.assertRaisesRegex(InputProblem,'length_mismatch'):self.receipt()
        self.file.write_bytes(b'ACGT'*128)
        for field,width in [('md5',32),('sha256',64)]:
            old=self.spec['file'][field];self.spec['file'][field]='0'*width;self.bind()
            r=self.receipt();self.assertFalse(r['file_check']['matches_expected'])
            self.assertEqual(r['status'],'manual_review');self.assertFalse(r['delivered'])
            self.spec['file'][field]=old;self.bind()

    def test_missing_unknown_prior_evidence_time_order_and_expiry_remain_review(self):
        self.spec['upstream']['upload_readback'].update(kind='missing',record_sha256=None,completed_at=None,outcome='unknown')
        self.spec['share_expires_at']=0;self.bind()
        self.obs['acquisition']['finished_at']=0
        reasons=self.receipt()['review_reasons']
        for code in ('upload_readback_evidence_missing','upload_readback_outcome_not_completed','upload_readback_time_missing','time_order_invalid','share_expired_before_receipt'):
            self.assertIn(code,reasons)
        self.obs['acquisition']['outcome']='unknown'
        self.assertIn('receipt_outcome_not_completed',self.receipt()['review_reasons'])

    def test_duplicate_and_forged_real_receipts_or_json_true_never_grant_eligibility(self):
        r=self.receipt()
        with self.assertRaisesRegex(InputProblem,'duplicate_attempt'):audit(self.spec,[r,r])
        for flag in FLAGS:
            changed={**r,flag:True}
            with self.assertRaisesRegex(InputProblem,'untrusted_real_claim'):audit(self.spec,[changed])
        self.obs['acquisition']['kind']='real'
        with self.assertRaisesRegex(InputProblem,'untrusted_real_claim'):self.receipt()
        self.obs['acquisition']['kind']='operator_claim'
        for stage in self.spec['upstream'].values():stage['kind']='operator_claim'
        self.spec['origin']='unverified_operator_record';self.bind()
        r=self.receipt();self.assertFalse(audit(self.spec,[r])['delivery_eligible'])

    def test_missing_fields_secrets_symlinks_and_overwrite_are_rejected(self):
        self.obs['access_token']='NEVER_ECHO'
        with self.assertRaises(InputProblem) as caught:self.receipt()
        self.assertNotIn('NEVER_ECHO',str(caught.exception));del self.obs['access_token']
        link=self.root/'linked';link.mkdir();(link/'fixture.fna').symlink_to(self.file)
        with self.assertRaises(OSError):check_file(self.spec,self.obs,link/'fixture.fna')
        out=self.root/'receipt.json';write_new(out,self.receipt())
        before=out.read_bytes()
        with self.assertRaises(FileExistsError):write_new(out,self.receipt())
        self.assertEqual(before,out.read_bytes())

    def test_prepare_binds_workflow_without_upgrading_simulation_claims(self):
        class FakeJob:
            def view(inner):return {'phase':'simulated_cloud_verified','job_id':'job-receipt','manifest_sha256':'1'*64,'mapping_sha256':'2'*64,
                'mapping':{'name':'fixture.fna','size':512,'md5':self.spec['file']['md5'],'sha256':self.spec['file']['sha256'],
                           'source':{'version_sha256':'3'*64},'simulated_target':'synthetic-target'}}
        s=prepare(FakeJob());self.assertEqual(s['file'],self.spec['file'])
        self.assertEqual(s['upstream']['share']['kind'],'missing')
        self.assertIsNone(s['upstream']['source']['completed_at'])
        self.assertEqual(s['origin'],'simulation')
        examples=Path(__file__).resolve().parents[1]/'examples/m6'
        example_spec=json.loads((examples/'expectation.synthetic.json').read_text())
        example_obs=json.loads((examples/'observation.template.json').read_text())
        self.assertTrue(check_file(example_spec,example_obs,self.file)['file_check']['matches_expected'])
        del s['source_version_sha256']
        with self.assertRaises(InputProblem):check_file(s,self.obs,self.file)

    def test_cli_structural_audit_does_not_claim_rehashed_file_or_actual_receipt(self):
        spec=self.root/'spec.json';spec.write_text(json.dumps(self.spec))
        receipts=self.root/'receipts.json';receipts.write_text(json.dumps([self.receipt()]))
        stream=io.StringIO()
        with patch('sys.argv',['acceptance','audit',str(spec),str(receipts)]),patch('sys.stdout',stream):self.assertEqual(main(),0)
        result=json.loads(stream.getvalue());self.assertEqual(result['status'],'unverified_records_reviewed')
        self.assertFalse(result['delivered'])

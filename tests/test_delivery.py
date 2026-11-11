"""Offline import/receipt tests; all cloud records and shares are synthetic."""
import copy
import json
import time
import unittest

from fast_transfer.delivery import load_handoff, record_delivery, main
from fast_transfer.intake import InputProblem
from fast_transfer.task import encoded
from fast_transfer.task_handoff import export_handoff
import test_task_handoff as fixture


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        fixture.HandoffTests.setUp(self)
        self.digest=export_handoff(self.task,self.output)['handoff_sha256']
        self.doc=load_handoff(self.output,self.digest,'b'*64)
        now=int(time.time())
        self.observed={'schema':'fast-transfer-human-observation-v1','job_id':self.doc['job_id'],
                       'task_spec_sha256':self.doc['task_spec_sha256'],
                       'metadata':[{k:x[k] for k in ('index','path','fs_id','bytes','md5')} for x in self.doc['files']],
                       'share':{'url':'https://pan.baidu.com/s/SYNTHETIC_TEST_LINK','code':'a1B2','created_at':now-10,'expires_at':now+86000},
                       'recipient':{'status':'confirmed','logged_out':True,'downloaded':True,'confirmed_at':now}}
        self.observation=self.root/'observation.json';self.receipt=self.root/'receipt.json'
        self.save()

    def save(self):
        self.observation.write_text(encoded(self.observed));self.observation.chmod(0o600)

    def run_record(self):
        return record_delivery(self.output,self.digest,'b'*64,self.observation,self.receipt)

    def test_confirmed_is_human_attestation_and_private(self):
        result=self.run_record();self.assertTrue(result['delivered']);self.assertFalse(result['network_actions'])
        self.assertNotIn('SYNTHETIC_TEST_LINK',json.dumps(result))
        record=json.loads(self.receipt.read_text())
        self.assertEqual(record['evidence'],'operator-attestation-not-independent-verification')
        self.assertEqual(self.receipt.stat().st_mode & 0o777,0o600)
        with self.assertRaises(FileExistsError):self.run_record()

    def test_pending_and_failed_are_not_delivery(self):
        for status in ('pending','failed'):
            self.observed['recipient']={'status':status,'logged_out':False,'downloaded':False,'confirmed_at':None}
            self.save();self.receipt=self.root/(status+'.json')
            self.assertFalse(self.run_record()['delivered'])

    def test_handoff_digest_and_account_required(self):
        for digest,account in [('a'*64,'b'*64),(self.digest,'c'*64)]:
            with self.assertRaises(InputProblem):load_handoff(self.output,digest,account)

    def test_observation_other_object_or_scope_refused(self):
        original=copy.deepcopy(self.observed)
        for key in ('fs_id','bytes','md5','path'):
            self.observed=copy.deepcopy(original);self.observed['metadata'][0][key]='different';self.save()
            with self.assertRaises(InputProblem):self.run_record()
        self.observed=copy.deepcopy(original);self.observed['task_spec_sha256']='f'*64;self.save()
        with self.assertRaises(InputProblem):self.run_record()
        self.assertFalse(self.receipt.exists())

    def test_no_claim_without_logged_out_download_and_valid_time(self):
        original=copy.deepcopy(self.observed)
        for field,value in [('logged_out',False),('downloaded',False),('confirmed_at',None),('confirmed_at',int(time.time())+999999)]:
            self.observed=copy.deepcopy(original);self.observed['recipient'][field]=value;self.save()
            with self.assertRaises(InputProblem):self.run_record()

    def test_bad_share_or_extra_credential_refused(self):
        original=copy.deepcopy(self.observed)
        for url in ('http://pan.baidu.com/s/EXAMPLE','https://pan.baidu.com.evil/s/EXAMPLE','https://pan.baidu.com/s/EXAMPLE?secret=x'):
            self.observed=copy.deepcopy(original);self.observed['share']['url']=url;self.save()
            with self.assertRaises(InputProblem):self.run_record()
        self.observed=copy.deepcopy(original);self.observed['token']='NEVER';self.save()
        with self.assertRaises(InputProblem):self.run_record()

    def test_public_observation_refused(self):
        self.observation.chmod(0o644)
        with self.assertRaises(InputProblem):self.run_record()

"""Provenance and task association using synthetic private receipts only."""
import copy
import hashlib
import json
import unittest

import test_delivery as fixture
from fast_transfer.delivery import record_delivery, validate_handoff
from fast_transfer.intake import InputProblem
from fast_transfer.task import encoded
from fast_transfer.task_delivery import attach_receipt


class TaskDeliveryTests(unittest.TestCase):
    save = fixture.DeliveryTests.save
    def setUp(self):
        fixture.DeliveryTests.setUp(self)
        self.result=record_delivery(self.output,self.digest,'b'*64,self.observation,self.receipt)

    def attach(self):
        return attach_receipt(self.task,self.receipt,self.result['receipt_sha256'])

    def test_confirmation_attaches_and_reopening_view_retains_evidence(self):
        self.assertTrue(self.attach()['delivered'])
        view=self.task.view();self.assertTrue(view['delivered'])
        self.assertEqual(view['delivery_evidence'],'operator-attestation')
        self.assertEqual(view['recovery']['action'],'delivery_recorded')
        self.assertNotIn('SYNTHETIC_TEST_LINK',json.dumps(view))
        self.assertEqual(self.attach()['status'],'receipt_already_attached')
        with self.task.locked() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0],1)

    def test_pending_then_confirmed_no_upload_or_regression(self):
        self.observed['recipient']={'status':'pending','logged_out':False,'downloaded':False,'confirmed_at':None}
        self.observation.write_text(encoded(self.observed));pending=self.root/'pending.json'
        result=record_delivery(self.output,self.digest,'b'*64,self.observation,pending)
        self.assertFalse(attach_receipt(self.task,pending,result['receipt_sha256'])['delivered'])
        self.assertFalse(self.task.view()['delivered'])
        self.assertEqual(self.task.view()['recovery']['action'],'await_recipient')
        self.attach()
        # A different failed receipt cannot erase a prior confirmed delivery.
        self.observed['recipient']['status']='failed';self.observation.write_text(encoded(self.observed))
        failed=self.root/'failed.json';result=record_delivery(self.output,self.digest,'b'*64,self.observation,failed)
        with self.assertRaises(InputProblem):attach_receipt(self.task,failed,result['receipt_sha256'])
        self.assertTrue(self.task.view()['delivered'])

    def test_changed_receipt_and_scope_cannot_attach(self):
        original=json.loads(self.receipt.read_text())
        with self.assertRaises(InputProblem):attach_receipt(self.task,self.receipt,'a'*64)
        for field,value in [('task_spec_sha256','f'*64),('job_id','job-'+'0'*32)]:
            changed=copy.deepcopy(original);changed['handoff'][field]=value
            raw=(encoded(changed)+'\n').encode();self.receipt.write_bytes(raw)
            with self.assertRaises(InputProblem):attach_receipt(self.task,self.receipt,hashlib.sha256(raw).hexdigest())
        self.assertFalse(self.task.view()['delivered'])

    def test_provenance_source_checksum_and_query_secret_refused(self):
        for mutate in ('checksum','version','query','extra'):
            doc=copy.deepcopy(self.doc)
            if mutate=='checksum':doc['manifest']['files'][0]['md5']='0'*32
            if mutate=='version':doc['manifest']['files'][0]['source']['version']='another version'
            if mutate=='query':doc['manifest']['files'][0]['url']+='?token=SECRET'
            if mutate=='extra':doc['manifest']['files'][0]['source']['token']='SECRET'
            with self.assertRaises(InputProblem):validate_handoff(doc,'b'*64)

    def test_real_verification_and_unknown_intent_are_required(self):
        with self.task.locked() as db:
            with db:db.execute("UPDATE files SET phase='uploading'")
        with self.assertRaises(InputProblem):self.attach()
        with self.task.locked() as db:
            with db:
                db.execute("UPDATE files SET phase='cloud_verified'")
                db.execute("INSERT INTO operations VALUES(0,'commit',-1,?,'unknown',NULL,1)",('a'*64,))
        with self.assertRaises(InputProblem):self.attach()

    def test_source_policy_and_attribution_are_in_private_receipt(self):
        doc=json.loads(self.receipt.read_text())
        source=doc['handoff']['manifest']['files'][0]['source']
        self.assertEqual(source['access'],'public')
        self.assertEqual(source['redistribution']['status'],'reviewed')
        self.assertIn('record_url',source)

    def test_claim_flag_cannot_bypass_observation(self):
        doc=json.loads(self.receipt.read_text());doc['human_observation']['recipient']['downloaded']=False
        raw=(encoded(doc)+'\n').encode();self.receipt.write_bytes(raw)
        with self.assertRaises(InputProblem):attach_receipt(self.task,self.receipt,hashlib.sha256(raw).hexdigest())

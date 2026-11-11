"""One explicit replay, actual SDK encoding and synthetic lost responses."""
import json
import unittest
from unittest.mock import patch

import test_task_upload as fixture
from fast_transfer.task_retry import retry_unknown_part
from fast_transfer.task import Task
from fast_transfer.upload_stage import StageFailure


class PartRetryTests(unittest.TestCase):
    setUpClass=classmethod(lambda cls:fixture.TaskUploadTests.setUpClass())
    configure=fixture.TaskUploadTests.configure
    download=fixture.TaskUploadTests.download
    prepare=fixture.TaskUploadTests.prepare
    factory=fixture.TaskUploadTests.factory
    run_upload=fixture.TaskUploadTests.run_upload
    count=fixture.TaskUploadTests.count
    def setUp(self):
        fixture.TaskUploadTests.setUp(self)
        self.data={'fixture.fna':b'A'*(4*1024**2)+b'C'*123};self.configure();self.prepare()
    def lose_part_response(self,part=0):
        exchange=fixture.MemoryAPI.exchange
        def lose(client,req):
            reply=exchange(client,req)
            if req.purpose=='upload' and int(req.params['partseq'])==part:raise StageFailure('http_io_failure')
            return reply
        with patch.object(fixture.MemoryAPI,'exchange',lose):
            with self.assertRaisesRegex(StageFailure,'http_io_failure'):self.run_upload()
        self.assertEqual(self.task.view()['unknown_operations'],1)
    def retry(self,part=0,**kw):
        return retry_unknown_part(self.task,self.factory,fixture.ACCOUNT,part,
            approved_task_spec_sha256=self.task.view()['task_spec_sha256'],**kw)
    def test_one_replay_preserves_original_unknown_then_normal_resume(self):
        self.lose_part_response();sessions=list(self.cloud.sessions)
        result=self.retry();self.assertEqual(result['status'],'part_retry_confirmed')
        self.assertFalse(result['cloud_verified']);self.assertEqual(self.task.view()['unknown_operations'],0)
        self.assertEqual(list(self.cloud.sessions),sessions)
        with self.task.locked() as db:
            row=db.execute('SELECT * FROM part_retry_attempts').fetchone()
            original=json.loads(row['original_unknown'])
            self.assertEqual(original['outcome'],'unknown');self.assertIsNone(original['receipt'])
            self.assertEqual(row['outcome'],'confirmed');self.assertEqual(json.loads(row['receipt'])['part'],0)
        self.assertEqual(self.count('part:0'),2);self.assertEqual(self.count('commit'),0)
        self.task=Task(self.root,self.task.job_id);self.run_upload()
        self.assertEqual(self.count('part:0'),2);self.assertEqual(self.count('part:1'),1)
        self.assertEqual(self.count('directory'),1);self.assertEqual(self.count('precreate'),1)
        self.assertEqual(self.count('commit'),1)
        calls=self.factory_calls
        with self.assertRaisesRegex(StageFailure,'requires_one_unknown'):self.retry()
        self.assertEqual(self.factory_calls,calls)
    def test_failed_retry_is_consumed_and_never_loops(self):
        self.lose_part_response();exchange=fixture.MemoryAPI.exchange
        def lose_again(client,req):
            reply=exchange(client,req)
            if req.purpose=='upload':raise StageFailure('http_io_failure')
            return reply
        with patch.object(fixture.MemoryAPI,'exchange',lose_again):
            with self.assertRaisesRegex(StageFailure,'http_io_failure'):self.retry()
        calls=self.factory_calls
        with self.assertRaisesRegex(StageFailure,'already_attempted'):self.retry()
        self.assertEqual(self.factory_calls,calls);self.assertEqual(self.count('part:0'),2)
        self.assertEqual(self.task.view()['unknown_operations'],1)
        with self.task.locked() as db:
            self.assertEqual(db.execute('SELECT outcome FROM part_retry_attempts').fetchone()[0],'unknown')
    def test_final_part_is_rejected_before_factory(self):
        self.lose_part_response(1);calls=self.factory_calls
        with self.assertRaisesRegex(StageFailure,'nonfinal'):self.retry(1)
        self.assertEqual(self.factory_calls,calls)
    def test_commit_unknown_is_never_replayed(self):
        self.cloud.drop_commit=True
        with self.assertRaises(StageFailure):self.run_upload()
        calls=self.factory_calls
        with self.assertRaisesRegex(StageFailure,'requires_one_unknown'):self.retry()
        self.assertEqual(self.factory_calls,calls);self.assertEqual(self.count('commit'),1)
    def test_changed_source_rejected_before_factory(self):
        self.lose_part_response();calls=self.factory_calls
        self.task.source_path(0,self.manifest['files'][0]).write_bytes(b'X'*len(self.data['fixture.fna']))
        with self.assertRaisesRegex(StageFailure,'source_changed'):self.retry()
        self.assertEqual(self.factory_calls,calls);self.assertEqual(self.count('part:0'),1)
    def test_wrong_scope_or_account_never_reaches_factory(self):
        self.lose_part_response();calls=self.factory_calls
        with self.assertRaisesRegex(StageFailure,'scope_invalid'):
            retry_unknown_part(self.task,self.factory,fixture.ACCOUNT,0,approved_task_spec_sha256='0'*64)
        with self.assertRaisesRegex(StageFailure,'identity_changed'):
            retry_unknown_part(self.task,self.factory,'0'*64,0,approved_task_spec_sha256=self.task.view()['task_spec_sha256'])
        self.assertEqual(self.factory_calls,calls)

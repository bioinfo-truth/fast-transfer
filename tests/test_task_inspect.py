"""Unknown-commit reconciliation with actual SDK and synthetic cloud only."""
import json
import unittest
from unittest.mock import Mock

import test_task_upload as fixture
from fast_transfer.task_inspect import inspect_commit
from fast_transfer.task import encoded
from fast_transfer.intake import InputProblem
from fast_transfer.upload_stage import StageFailure
from fast_transfer.baidu_http import HTTPRequest, RuntimeGrant
from fast_transfer.task_upload import TaskHTTP
import time


class InspectionTests(unittest.TestCase):
    setUpClass=classmethod(lambda cls:fixture.TaskUploadTests.setUpClass())
    configure=fixture.TaskUploadTests.configure
    download=fixture.TaskUploadTests.download
    prepare=fixture.TaskUploadTests.prepare
    factory=fixture.TaskUploadTests.factory
    run_upload=fixture.TaskUploadTests.run_upload
    count=fixture.TaskUploadTests.count

    def setUp(self):
        fixture.TaskUploadTests.setUp(self);self.prepare();self.cloud.drop_commit=True
        with self.assertRaises(StageFailure):self.run_upload()
        self.spec=self.task.view()['task_spec_sha256']
        path=next(path for path,fid in self.cloud.by_path.items() if not self.cloud.rows[fid]['isdir'])
        self.proof={'job_id':self.task.job_id,'task_spec_sha256':self.spec,'path':path,
                    'fs_id':self.cloud.by_path[path],'bytes':len(self.data['fixture.fna'])}
        self.proof_path=self.root/'proof.json';self.save()

    def save(self):self.proof_path.write_text(encoded(self.proof));self.proof_path.chmod(0o600)
    def inspect(self):
        return inspect_commit(self.task,self.factory,fixture.ACCOUNT,self.proof_path,approved_task_spec_sha256=self.spec)

    def test_unknown_commit_reconciles_by_full_readback_without_repeating_mutation(self):
        before=list(self.cloud.events);result=self.inspect()
        self.assertFalse(result['remote_mutations']);self.assertFalse(result['cloud_verified'])
        self.assertEqual(self.cloud.events,before+['readback'])
        self.assertEqual(self.task.view()['unknown_operations'],0)
        self.assertEqual(self.task.view()['files'][0]['phase'],'test_cloud_verified')
        self.assertEqual(self.run_upload()['status'],'no_pending_upload');self.assertEqual(self.count('commit'),1)

    def test_corrupt_object_remains_unknown_and_can_be_reinspected(self):
        self.cloud.corrupt_readback=True
        with self.assertRaisesRegex(InputProblem,'readback_hash'):self.inspect()
        self.assertEqual(self.task.view()['unknown_operations'],1)
        self.assertTrue(self.last.client.stopped)
        self.cloud.corrupt_readback=False;self.inspect();self.assertEqual(self.count('commit'),1)

    def test_locator_or_scope_mismatch_before_factory(self):
        calls=self.factory_calls
        self.proof['path']+='.wrong';self.save()
        with self.assertRaises(InputProblem):self.inspect()
        self.assertEqual(self.factory_calls,calls)

    def test_wrong_object_id_or_metadata_never_resolves(self):
        self.proof['fs_id']=next(fid for fid,row in self.cloud.rows.items() if row['isdir']);self.save()
        with self.assertRaises(StageFailure):self.inspect()
        self.assertEqual(self.task.view()['unknown_operations'],1)

    def test_false_stop_and_changed_source_preserve_unknown(self):
        self.cloud.stop_ok=False
        with self.assertRaisesRegex(InputProblem,'stop_unconfirmed'):self.inspect()
        self.assertEqual(self.task.view()['unknown_operations'],1)
        self.cloud.stop_ok=True;calls=self.factory_calls
        self.task.source_path(0,self.manifest['files'][0]).write_bytes(b'X'*len(self.data['fixture.fna']))
        with self.assertRaisesRegex(InputProblem,'source_changed'):self.inspect()
        self.assertEqual(self.factory_calls,calls)

    def test_read_only_http_denies_post_before_credentials(self):
        provider=Mock(side_effect=AssertionError('no credentials'))
        client=TaskHTTP(grant=RuntimeGrant(True,self.proof['path'],fixture.ACCOUNT,'a'*64,'synthetic-test',time.monotonic()+30),credential_provider=provider)
        client.read_only=True
        with self.assertRaisesRegex(StageFailure,'inspection_read_only'):
            client.exchange(HTTPRequest('POST','https://pan.baidu.com/rest/2.0/xpan/file',self.proof['path'],'control',{'method':'create'},b''))
        provider.assert_not_called()

    def test_only_unknown_commit_accepted_and_no_unknown_replay(self):
        with self.task.locked() as db:
            with db:db.execute("UPDATE operations SET operation='precreate',part=99 WHERE outcome='unknown'")
        calls=self.factory_calls
        with self.assertRaisesRegex(InputProblem,'commit_only'):self.inspect()
        self.assertEqual(self.factory_calls,calls)

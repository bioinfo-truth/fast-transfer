"""Real exec/SIGKILL/re-exec recovery using synthetic durable cloud state."""
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import unittest

import test_task_upload as fixture
from fast_transfer.task import Task, encoded
# This helper module contains no top-level execution.
sys.path.insert(0,str(Path(__file__).resolve().parent/'support'))
from task_upload_process_worker import save_cloud, load_cloud


class UploadProcessTests(unittest.TestCase):
    setUpClass=classmethod(lambda cls:fixture.TaskUploadTests.setUpClass())
    configure=fixture.TaskUploadTests.configure
    download=fixture.TaskUploadTests.download
    prepare=fixture.TaskUploadTests.prepare

    def setUp(self):
        fixture.TaskUploadTests.setUp(self)
        self.worker=Path(__file__).resolve().parent/'support/task_upload_process_worker.py'
        self.snapshot=self.root/'cloud.json';self.result=self.root/'result.json';self.proof=self.root/'proof.json'

    def start(self,checkpoint):
        return subprocess.Popen([sys.executable,'-I','-S','-B',str(self.worker),str(self.root),self.task.job_id,
                                 str(self.guard),str(self.snapshot),checkpoint,str(self.result),str(self.proof)],
                                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                env={'PYTHONDONTWRITEBYTECODE':'1'},start_new_session=True)

    def kill_at(self,checkpoint):
        process=self.start(checkpoint)
        try:
            ready,_,_=select.select([process.stdout],[],[],20)
            self.assertTrue(ready,'worker did not reach checkpoint')
            marker=process.stdout.readline()
            if marker!=b'READY\n':
                out,err=process.communicate(timeout=10)
                self.fail('worker checkpoint failed: '+repr((marker,out,err)))
            self.assertIsNone(process.poll())
            os.kill(process.pid,signal.SIGKILL);process.wait(timeout=10)
            self.assertEqual(process.returncode,-signal.SIGKILL)
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
            process.stdout.close();process.stderr.close()

    def finish(self,mode='resume'):
        process=self.start(mode)
        try:
            out,err=process.communicate(timeout=30)
            self.assertEqual(process.returncode,0,repr((out,err)))
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
        result=json.loads(self.result.read_text());self.assertFalse(result['cloud_verified'])
        return load_cloud(self.snapshot)

    def test_kill_after_session_part_and_commit_confirmation_then_fresh_exec_resume(self):
        self.data={'fixture.fna':b'A'*(4*1024**2)+b'G'*123}
        for checkpoint in ('precreate:-1','part:0','commit:-1'):
            with self.subTest(checkpoint=checkpoint):
                self.configure();self.prepare();save_cloud(self.cloud,self.snapshot)
                self.kill_at(checkpoint)
                reopened=Task(self.root,self.task.job_id)
                self.assertEqual(reopened.view()['unknown_operations'],0)
                cloud=self.finish()
                for operation in ('directory','precreate','part:0','part:1','commit'):
                    self.assertEqual(cloud.events.count(operation),1,(checkpoint,cloud.events))
                self.assertEqual(reopened.view()['files'][0]['phase'],'test_cloud_verified')

    def test_kill_after_remote_commit_before_response_requires_read_only_inspection(self):
        self.prepare();save_cloud(self.cloud,self.snapshot);self.kill_at('unknown-commit')
        reopened=Task(self.root,self.task.job_id)
        self.assertEqual(reopened.view()['unknown_operations'],1)
        # Ordinary resume must stop without making another synthetic cloud call.
        process=self.start('resume')
        try:
            out,err=process.communicate(timeout=20)
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
        self.assertNotEqual(process.returncode,0)
        self.assertIn(b'task_unknown_operation_requires_inspection',err)
        cloud=load_cloud(self.snapshot)
        path=next(path for path,fid in cloud.by_path.items() if not cloud.rows[fid]['isdir'])
        self.proof.write_text(encoded({'job_id':self.task.job_id,'task_spec_sha256':reopened.view()['task_spec_sha256'],
                                      'path':path,'fs_id':cloud.by_path[path],'bytes':len(self.data['fixture.fna'])}))
        self.proof.chmod(0o600)
        cloud=self.finish('inspect')
        self.assertEqual(cloud.events.count('commit'),1);self.assertEqual(cloud.events.count('part:0'),1)
        self.assertEqual(cloud.events.count('readback'),1)
        self.assertEqual(reopened.view()['unknown_operations'],0)

"""Local deletion tests use only synthetic temporary files/records."""
import hashlib
import json
import os
import signal
import select
from pathlib import Path
import tempfile
import unittest

from fast_transfer.intake import InputProblem
from fast_transfer.task import Task, encoded
from fast_transfer.task_cleanup import cleanup_file
from fast_transfer.task_handoff import export_handoff
from fast_transfer.upload_stage import StageFailure


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        manifest=json.loads((Path(__file__).resolve().parents[1]/'examples/ncbi-ecoli/manifest.json').read_text())
        self.data=b'synthetic source';entry=manifest['files'][0];entry['size']=len(self.data)
        entry['md5']=hashlib.md5(self.data).hexdigest();entry['sha256']=hashlib.sha256(self.data).hexdigest()
        self.task=Task.create(self.root,manifest);self.task.file_root(0).mkdir(mode=0o700)
        self.path=self.task.source_path(0,entry);self.path.write_bytes(self.data)
        self.other=self.task.file_root(0)/'keep-receipt';self.other.write_bytes(b'keep')
        receipt={'path':'/apps/Xtransfer/mvp-validation/'+self.task.job_id+'/'+entry['name'],
                 'fs_id':123,'bytes':entry['size'],'md5':entry['md5'],'sha256':entry['sha256']}
        with self.task.locked() as db:
            db.executescript('CREATE TABLE upload_context(id INTEGER PRIMARY KEY,kind TEXT,account_sha256 TEXT);'
                             'CREATE TABLE verifications(idx INTEGER PRIMARY KEY,kind TEXT,receipt TEXT,completed INTEGER);')
            with db:
                db.execute('INSERT INTO upload_context VALUES(1,?,?)',('official-api','a'*64))
                db.execute('INSERT INTO verifications VALUES(0,?,?,1)',('official-api',encoded(receipt)))
                db.execute("UPDATE files SET phase='cloud_verified',source_receipt=?",(encoded({k:receipt[k] for k in ('bytes','md5','sha256')}),))

    def test_cleanup_retains_records_and_handoff_then_idempotent(self):
        result=cleanup_file(self.task,0)
        self.assertFalse(self.path.exists());self.assertFalse(result['cloud_deleted'])
        self.assertEqual(self.other.read_bytes(),b'keep')
        self.assertEqual(self.task.view()['files'][0]['phase'],'cleaned')
        export_handoff(self.task,self.root/'handoff.json')
        self.assertEqual(cleanup_file(self.task,0)['status'],'cleaned')

    def test_after_unlink_interruption_recovers(self):
        def stop(stage):
            if stage=='payload_removed':raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):cleanup_file(self.task,0,checkpoint_hook=stop)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.task.view()['files'][0]['phase'],'cloud_verified')
        self.assertEqual(cleanup_file(self.task,0)['status'],'cleaned')

    def test_before_unlink_interruption_recovers(self):
        def stop(stage):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):cleanup_file(self.task,0,checkpoint_hook=stop)
        self.assertTrue(self.path.exists());cleanup_file(self.task,0)

    def test_changed_payload_or_hardlink_preserved(self):
        self.path.write_bytes(b'X'*len(self.data))
        with self.assertRaises((InputProblem,StageFailure)):cleanup_file(self.task,0)
        self.assertTrue(self.path.exists())
        self.path.write_bytes(self.data);os.link(self.path,self.root/'hardlink')
        with self.assertRaises(InputProblem):cleanup_file(self.task,0)
        self.assertTrue(self.path.exists())

    def test_fixture_unknown_and_unverified_refused(self):
        for kind,phase in [('test-fixture','test_cloud_verified'),('official-api','uploading')]:
            with self.task.locked() as db:
                with db:
                    db.execute('UPDATE upload_context SET kind=?',(kind,))
                    db.execute('UPDATE files SET phase=?',(phase,))
            with self.assertRaises(InputProblem):cleanup_file(self.task,0)
            self.assertTrue(self.path.exists())
        with self.task.locked() as db:
            with db:
                db.execute("UPDATE files SET phase='cloud_verified'")
                db.execute("INSERT INTO operations VALUES(0,'commit',-1,?,'unknown',NULL,1)",('a'*64,))
        with self.assertRaises(InputProblem):cleanup_file(self.task,0)
        self.assertTrue(self.path.exists())

    def test_missing_without_intent_and_reappeared_payload_refused(self):
        self.path.unlink()
        with self.assertRaises(InputProblem):cleanup_file(self.task,0)
        self.path.write_bytes(self.data);cleanup_file(self.task,0)
        self.path.write_bytes(self.data)
        with self.assertRaises(InputProblem):cleanup_file(self.task,0)
        self.assertTrue(self.path.exists())

    def test_payload_swap_after_intent_preserved(self):
        def swap(stage):
            if stage=='intent_saved':
                self.path.rename(self.root/'original')
                self.path.write_bytes(self.data)
        with self.assertRaises(InputProblem):cleanup_file(self.task,0,checkpoint_hook=swap)
        self.assertEqual(self.path.read_bytes(),self.data)

    def test_sigkill_after_unlink_reopens_and_finishes_without_deleting_other_file(self):
        read_fd,write_fd=os.pipe()
        child=os.fork()
        if child==0:
            os.close(read_fd)
            def pause(stage):
                if stage=='payload_removed':
                    os.write(write_fd,b'R')
                    while True:signal.pause()
            try:cleanup_file(self.task,0,checkpoint_hook=pause)
            finally:os._exit(3)
        os.close(write_fd)
        try:
            ready,_,_=select.select([read_fd],[],[],10)
            self.assertTrue(ready,'child did not reach unlink checkpoint')
            self.assertEqual(os.read(read_fd,1),b'R')
            os.kill(child,signal.SIGKILL)
            _,status=os.waitpid(child,0);child=None
            self.assertTrue(os.WIFSIGNALED(status))
            reopened=Task(self.root,self.task.job_id)
            self.assertEqual(cleanup_file(reopened,0)['status'],'cleaned')
            self.assertEqual(self.other.read_bytes(),b'keep')
        finally:
            os.close(read_fd)
            if child is not None:
                try:os.kill(child,signal.SIGKILL)
                except ProcessLookupError:pass
                os.waitpid(child,0)

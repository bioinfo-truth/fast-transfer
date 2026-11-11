import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fast_transfer.intake import InputProblem
from fast_transfer.space import RESERVE, MARGIN, Volume
from fast_transfer.task import Task, main


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.data = b'ACGT'*256
        self.manifest = json.loads((Path(__file__).resolve().parents[1]/'examples/ncbi-ecoli/manifest.json').read_text())
        e = self.manifest['files'][0]
        e.update(name='fixture.fna',size=len(self.data),md5=hashlib.md5(self.data).hexdigest())
        e.pop('sha256',None)
        self.task = Task.create(self.parent,self.manifest)

    def downloader(self, entry, path, max_bytes, **kwargs):
        kwargs['space_guard'].check('download')
        fd = os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as f:f.write(self.data)
        return {'bytes':len(self.data),'md5':hashlib.md5(self.data).hexdigest(),
                'sha256':hashlib.sha256(self.data).hexdigest()}

    def prepared(self):
        self.task.next_source(downloader=self.downloader)
        return self.task

    def test_create_snapshots_multiple_inputs_and_private_records(self):
        second = json.loads(json.dumps(self.manifest['files'][0]));second['name']='second.fna'
        self.manifest['files'].append(second)
        job = Task.create(self.parent,self.manifest)
        self.manifest['files'][0]['name']='mutated.fna'
        self.assertEqual([r['name'] for r in job.view()['files']],['fixture.fna','second.fna'])
        self.assertEqual((job.root/'task.sqlite3').stat().st_mode&0o777,0o600)
        self.assertEqual(job.root.stat().st_mode&0o777,0o700)
        self.assertFalse(job.view()['cloud_backend_connected'])
        self.assertFalse(job.view()['delivered'])

    def test_download_next_uses_guard_and_does_not_prefetch(self):
        self.prepared()
        self.assertEqual(self.task.view()['files'][0]['phase'],'source_verified')
        with self.assertRaisesRegex(InputProblem,'recovery_or_upload'):
            self.task.next_source(downloader=lambda *a,**k:self.fail('prefetched'))
        with self.task.locked() as db:
            receipt=json.loads(db.execute('SELECT source_receipt FROM files').fetchone()[0])
        self.assertEqual(receipt['sha256'],hashlib.sha256(self.data).hexdigest())

    def test_lost_download_reply_can_recover_complete_source_without_network(self):
        def interrupted(*args,**kwargs):
            self.downloader(*args,**kwargs)
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.task.next_source(downloader=interrupted)
        self.assertEqual(self.task.view()['files'][0]['phase'],'downloading')
        reopened=Task(self.parent,self.task.job_id)
        result=reopened.recover_source(0)
        self.assertFalse(result['network_repeated'])
        self.assertEqual(reopened.view()['files'][0]['phase'],'source_verified')

    def test_partial_source_requires_explicit_local_restart(self):
        def partial(entry,path,*a,**kw):
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as f:f.write(b'part')
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.task.next_source(downloader=partial)
        with self.assertRaises(Exception):self.task.recover_source(0)
        self.assertEqual(self.task.reset_incomplete_source(0)['status'],'pending')
        self.task.next_source(downloader=self.downloader)
        self.assertEqual(self.task.view()['files'][0]['phase'],'source_verified')

    def test_durable_unknown_prevents_new_writes_and_restart_after_reopen(self):
        self.prepared()
        token=self.task.begin_operation(0,'directory',{'path':'synthetic-only'})
        reopened=Task(self.parent,self.task.job_id)
        self.assertEqual(reopened.view()['unknown_operations'],1)
        with self.assertRaisesRegex(InputProblem,'consumed'):
            reopened.begin_operation(0,'directory',{'path':'synthetic-only'})
        with self.assertRaisesRegex(InputProblem,'unknown_operation'):
            reopened.begin_operation(0,'precreate',{'path':'synthetic-only'})
        with self.assertRaisesRegex(InputProblem,'restart_rejected'):reopened.reset_incomplete_source(0)
        reopened.finish_operation(0,'directory',token,{'fs_id':123,'path':'/apps/Xtransfer/mvp-validation/'+self.task.job_id})
        self.assertEqual(reopened.view()['unknown_operations'],0)
        with self.assertRaisesRegex(InputProblem,'consumed'):
            reopened.begin_operation(0,'directory',{'path':'synthetic-only'})

    def test_receipt_binding_and_credential_fields_rejected(self):
        self.prepared();token=self.task.begin_operation(0,'commit',{'path':'synthetic-only'})
        good={'fs_id':123,'path':'/apps/Xtransfer/mvp-validation/'+self.task.job_id+'/fixture.fna','size':len(self.data),'md5':hashlib.md5(self.data).hexdigest()}
        with self.assertRaisesRegex(InputProblem,'receipt_mismatch'):
            self.task.finish_operation(0,'commit','0'*64,good)
        with self.assertRaisesRegex(InputProblem,'receipt_invalid'):
            self.task.finish_operation(0,'commit',token,{**good,'access_token':'SYNTHETIC_SECRET_ONLY'})
        self.assertNotIn('SYNTHETIC_SECRET_ONLY',(self.task.root/'task.sqlite3').read_bytes().decode(errors='ignore'))
        self.assertEqual(self.task.view()['unknown_operations'],1)
        self.task.finish_operation(0,'commit',token,good)
        self.assertFalse(self.task.view()['delivered'])

    def test_lock_and_unsafe_files(self):
        with self.task.locked():
            with self.assertRaisesRegex(InputProblem,'task_busy'):self.task.view()
        db=self.task.root/'task.sqlite3';db.chmod(0o644)
        with self.assertRaisesRegex(InputProblem,'private_file'):self.task.view()
        db.chmod(0o600);db.rename(self.task.root/'saved.sqlite3');db.symlink_to(self.task.root/'saved.sqlite3')
        with self.assertRaisesRegex(InputProblem,'private_file'):self.task.view()

    def test_manifest_change_and_corrupt_db_never_promote(self):
        with self.task.locked() as db:
            with db:db.execute("UPDATE meta SET manifest_sha256=?",('0'*64,))
        with self.assertRaisesRegex(InputProblem,'manifest_changed'):self.task.view()

    def test_space_rejected_before_downloader_and_no_remote_intent(self):
        with patch('fast_transfer.space.DiskProbe.directory',return_value=Volume(1,1,RESERVE+MARGIN,4096)):
            with self.assertRaises(InputProblem):self.task.next_source(downloader=lambda *a,**k:self.fail('download called'))
        self.assertEqual(self.task.view()['files'][0]['phase'],'source_failed')
        self.assertEqual(self.task.view()['unknown_operations'],0)

    def test_empty_workspace_from_pre_intent_crash_is_reused(self):
        self.task.file_root(0).mkdir(mode=0o700)
        self.task.next_source(downloader=self.downloader)
        self.assertEqual(self.task.view()['files'][0]['phase'],'source_verified')

    def test_restart_after_deleted_folder_crash_and_unknown_file_retention(self):
        with self.task.locked() as db:
            with db:db.execute("UPDATE files SET phase='downloading'")
        self.assertEqual(self.task.reset_incomplete_source(0)['status'],'pending')
        def fail_download(entry,path,*a,**kw):
            (path.parent/'unknown.txt').write_text('keep')
            raise OSError()
        with self.assertRaises(OSError):self.task.next_source(downloader=fail_download)
        with self.assertRaisesRegex(InputProblem,'unknown_source_files'):self.task.reset_incomplete_source(0)
        self.assertTrue((self.task.file_root(0)/'unknown.txt').exists())

    def test_cli_create_show_never_reads_config_and_has_no_cloud_entry(self):
        file=self.parent/'manifest.json';file.write_text(json.dumps(self.manifest))
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['--tasks-dir',str(self.parent),'create',str(file)]),0)
        result=json.loads(out.getvalue());self.assertFalse(result['cloud_backend_connected'])
        out=io.StringIO()
        with contextlib.redirect_stdout(out):self.assertEqual(main(['--tasks-dir',str(self.parent),'show',result['job_id']]),0)
        self.assertFalse(json.loads(out.getvalue())['delivered'])

    def test_file_limit_and_public_parent_rejected_before_task_creation(self):
        count=len(list(self.parent.iterdir()))
        with self.assertRaisesRegex(InputProblem,'transfer_limits'):Task.create(self.parent,self.manifest,max_file_bytes=1)
        self.assertEqual(len(list(self.parent.iterdir())),count)
        self.parent.chmod(0o755)
        with self.assertRaisesRegex(InputProblem,'private_directory'):Task.create(self.parent,self.manifest)
        self.parent.chmod(0o700)

    def test_unknown_commit_cannot_be_replayed_from_a_fresh_process(self):
        self.prepared();self.task.begin_operation(0,'commit',{'path':'synthetic-only'})
        repo=Path(__file__).resolve().parents[1]
        script="""import sys
sys.path.insert(0,sys.argv[1])
from fast_transfer.task import Task
from fast_transfer.intake import InputProblem
try: Task(sys.argv[2],sys.argv[3]).begin_operation(0,'commit',{'path':'synthetic-only'})
except InputProblem as e:
 assert e.code=='task_operation_already_consumed'
 print('unknown_not_replayed')
else: raise SystemExit(1)
"""
        r=subprocess.run([sys.executable,'-I','-S','-B','-c',script,str(repo),str(self.parent),self.task.job_id],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'unknown_not_replayed')
        self.assertEqual(self.task.view()['unknown_operations'],1)

    def test_sigkill_after_source_write_recovers_without_downloading_again(self):
        repo=Path(__file__).resolve().parents[1]
        script="""import os,sys,hashlib
sys.path.insert(0,sys.argv[1])
from fast_transfer.task import Task
def download(entry,path,*args,**kw):
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'wb') as f:
  f.write(b'ACGT'*256);f.flush();os.fsync(f.fileno())
 print('source_written',flush=True)
 os.read(0,1)
Task(sys.argv[2],sys.argv[3]).next_source(downloader=download)
"""
        child=subprocess.Popen([sys.executable,'-I','-S','-B','-c',script,str(repo),str(self.parent),self.task.job_id],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            import select
            self.assertTrue(select.select([child.stdout],[],[],10)[0])
            self.assertEqual(child.stdout.readline().strip(),'source_written')
            child.kill();child.communicate(timeout=10)
            self.assertEqual(self.task.view()['files'][0]['phase'],'downloading')
            self.assertFalse(self.task.recover_source(0)['network_repeated'])
        finally:
            if child.poll() is None:child.kill();child.communicate(timeout=10)

    def test_real_source_downloader_is_used_with_bounded_fake_http(self):
        from email.message import Message
        from fast_transfer.download import download_verified
        class Response:
            def __init__(inner):
                inner.headers=Message();inner.headers['Content-Length']=str(len(self.data));inner.body=io.BytesIO(self.data)
            def getheader(inner,name,default=None):return inner.headers.get(name,default)
            def read1(inner,n):return inner.body.read(n)
            def close(inner):inner.body.close()
        class Connection:
            sock=None
            def close(inner):pass
        with patch('fast_transfer.download.open_public',return_value=(Response(),Connection(),0)) as opened:
            result=self.task.next_source()
        self.assertEqual(result['status'],'source_verified');opened.assert_called_once()
        self.assertEqual(self.task.source_path(0,self.manifest['files'][0]).read_bytes(),self.data)

    def test_all_1024_hashes_fit_private_session_receipt(self):
        manifest=json.loads(json.dumps(self.manifest));entry=manifest['files'][0]
        entry['size']=1024*4*1024**2
        job=Task.create(self.parent,manifest,max_file_bytes=entry['size'])
        with job.locked() as db:
            with db:db.execute("UPDATE files SET phase='source_verified'")
        token=job.begin_operation(0,'precreate',{'synthetic_fixture':True})
        receipt={'uploadid':'SYNTHETIC_ONLY','required':list(range(1024)),
                 'hashes':['a'*32]*1024,'path':'/apps/Xtransfer/mvp-validation/'+job.job_id+'/'+entry['name'],
                 'size':entry['size'],'host':'d.pcs.baidu.com','directory_id':123}
        job.finish_operation(0,'precreate',token,receipt)
        self.assertEqual(job.view()['unknown_operations'],0)

    def test_nested_credential_receipt_is_rejected_without_persistence(self):
        self.prepared();token=self.task.begin_operation(0,'part',{'synthetic_fixture':True},part=0)
        with self.assertRaisesRegex(InputProblem,'receipt_invalid'):
            self.task.finish_operation(0,'part',token,{'part':0,'bytes':len(self.data),'md5':{'access_token':'SYNTHETIC_ONLY'}},part=0)
        self.assertEqual(self.task.view()['unknown_operations'],1)

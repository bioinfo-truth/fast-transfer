"""Synthetic private records exercise export admission; no cloud verification claim."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from fast_transfer.intake import InputProblem
from fast_transfer.task import Task, encoded
from fast_transfer.task_handoff import export_handoff


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        manifest=json.loads((Path(__file__).resolve().parents[1]/'examples/ncbi-ecoli/manifest.json').read_text())
        self.task=Task.create(self.root,manifest)
        entry=manifest['files'][0]
        self.receipt={'path':'/apps/Xtransfer/mvp-validation/'+self.task.job_id+'/'+entry['name'],
                      'fs_id':123,'bytes':entry['size'],'md5':entry['md5'],'sha256':'a'*64}
        with self.task.locked() as db:
            db.executescript('CREATE TABLE upload_context(id INTEGER PRIMARY KEY,kind TEXT,account_sha256 TEXT);'
                             'CREATE TABLE verifications(idx INTEGER PRIMARY KEY,kind TEXT,receipt TEXT,completed INTEGER);')
            with db:
                db.execute('INSERT INTO upload_context VALUES(1,?,?)',('official-api','b'*64))
                db.execute('INSERT INTO verifications VALUES(0,?,?,1)',('official-api',encoded(self.receipt)))
                db.execute('UPDATE files SET phase=?,source_receipt=? WHERE idx=0',('cloud_verified',encoded({k:self.receipt[k] for k in ('bytes','md5','sha256')})))
        self.output=self.root/'handoff.json'

    def test_whitelist_private_export_and_digest(self):
        result=export_handoff(self.task,self.output)
        raw=self.output.read_bytes();doc=json.loads(raw)
        self.assertEqual(result['handoff_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.output.stat().st_mode & 0o777,0o600)
        self.assertFalse(doc['delivered']);self.assertEqual(doc['files'][0]['fs_id'],123)
        self.assertEqual(set(doc['files'][0]),{'index','name','path','fs_id','bytes','md5','sha256'})
        for word in ('uploadid','token','cookie','url'):self.assertNotIn(word,raw.decode().lower())

    def test_fixture_and_incomplete_refused(self):
        for kind,phase in [('test-fixture','test_cloud_verified'),('official-api','uploading')]:
            with self.task.locked() as db:
                with db:
                    db.execute('UPDATE upload_context SET kind=?',(kind,))
                    db.execute('UPDATE files SET phase=?',(phase,))
            with self.assertRaises(InputProblem):export_handoff(self.task,self.output)
            self.assertFalse(self.output.exists())

    def test_unknown_effect_refused(self):
        with self.task.locked() as db:
            with db:db.execute("INSERT INTO operations VALUES(0,'commit',-1,?,'unknown',NULL,1)",('a'*64,))
        with self.assertRaises(InputProblem):export_handoff(self.task,self.output)
        self.assertFalse(self.output.exists())

    def test_changed_receipt_refused(self):
        for key,value in [('path','/other'),('bytes',0),('fs_id',True),('sha256','b'*64),('token','PRIVATE')]:
            changed=dict(self.receipt);changed[key]=value
            with self.task.locked() as db:
                with db:db.execute('UPDATE verifications SET receipt=?',(encoded(changed),))
            with self.assertRaises(InputProblem):export_handoff(self.task,self.output)
            self.assertFalse(self.output.exists())

    def test_existing_file_and_symlink_never_overwritten(self):
        self.output.write_text('preserve')
        with self.assertRaises(FileExistsError):export_handoff(self.task,self.output)
        self.assertEqual(self.output.read_text(),'preserve')
        link=self.root/'link';link.symlink_to(self.output)
        with self.assertRaises(FileExistsError):export_handoff(self.task,link)
        self.assertEqual(self.output.read_text(),'preserve')

    def test_public_directory_refused(self):
        public=self.root/'public';public.mkdir(mode=0o755)
        with self.assertRaises(InputProblem):export_handoff(self.task,public/'handoff.json')

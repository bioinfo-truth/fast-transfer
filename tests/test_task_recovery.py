"""Advisory diagnostics on synthetic generic Tasks; no network or credentials."""
import contextlib
import hashlib
import io
import json
import unittest
from unittest.mock import patch

import test_stability as fixture
import test_task_upload as upload_fixture
from fast_transfer.task import Task, main
from fast_transfer.task_retry import retry_unknown_part
from fast_transfer.upload_stage import StageFailure


class RecoveryTests(unittest.TestCase):
    setUp = fixture.StabilityTests.setUp
    configure = fixture.StabilityTests.configure
    download = fixture.StabilityTests.download
    prepare = fixture.StabilityTests.prepare
    factory = fixture.StabilityTests.factory
    run_upload = fixture.StabilityTests.run_upload
    count = fixture.StabilityTests.count

    def plan(self): return self.task.view()['recovery']

    def test_source_phases_have_distinct_offline_advice(self):
        for phase, action in [('pending','download_next'),('downloading','recover_source'),
                              ('source_failed','recover_source'),('source_verified','resume_upload'),
                              ('manual_review','manual_review')]:
            with self.subTest(phase=phase):
                with self.task.locked() as db:
                    with db: db.execute('UPDATE files SET phase=?',(phase,))
                before = hashlib.sha256((self.task.root/'task.sqlite3').read_bytes()).hexdigest()
                plan = self.plan()
                self.assertEqual(plan['action'],action)
                self.assertTrue(plan['advisory_only']); self.assertFalse(plan['automatic_action'])
                self.assertEqual(before,hashlib.sha256((self.task.root/'task.sqlite3').read_bytes()).hexdigest())
                self.assertEqual(self.factory_calls,0)

    def test_confirmed_commit_advises_readback_not_reupload(self):
        self.cloud.corrupt_readback = True
        with self.assertRaises(StageFailure): self.run_upload()
        before = list(self.cloud.events)
        self.assertEqual(self.plan()['action'],'readback_only')
        self.assertEqual(self.cloud.events,before)
        self.cloud.corrupt_readback = False; self.run_upload(readback_only=True)
        self.assertEqual(self.plan()['action'],'synthetic_only')
        self.assertFalse(self.task.view()['delivered']); self.assertEqual(self.count('commit'),1)

    def test_unknown_commit_classification_overrides_error_code(self):
        self.cloud.drop_commit = True
        with self.assertRaises(StageFailure): self.run_upload()
        for reason in ('http_rate_limited','http_auth_rejected','http_timeout',None):
            with self.subTest(reason=reason):
                with self.task.locked() as db:
                    with db: db.execute('UPDATE files SET reason=?',(reason,))
                plan = self.plan()
                self.assertEqual(plan['action'],'inspect_commit_proof')
                self.assertEqual(plan['unknown'],[{'index':0,'operation':'commit','part':-1}])
                self.assertEqual(self.task.view()['unknown_operations'],1)
        self.assertEqual(self.count('commit'),1)

    def test_unknown_directory_and_multiple_unknowns_stay_manual(self):
        self.task.begin_operation(0,'directory',{'synthetic':'private-intent'})
        self.assertEqual(self.plan()['action'],'manual_review')
        with self.task.locked() as db:
            with db: db.execute("INSERT INTO operations VALUES(0,'commit',-1,?,'unknown',NULL,1)",('a'*64,))
        self.assertEqual(self.plan()['action'],'manual_review')
        self.assertEqual(len(self.plan()['unknown']),2)
        self.assertEqual(self.factory_calls,0)

    def lose_part(self,part):
        exchange = upload_fixture.MemoryAPI.exchange
        def drop(client,req):
            response = exchange(client,req)
            if req.purpose=='upload' and int(req.params['partseq'])==part:
                response.close(); raise StageFailure('http_timeout')
            return response
        return patch.object(upload_fixture.MemoryAPI,'exchange',drop)

    def test_final_unknown_part_never_suggests_retry(self):
        with self.lose_part(1):
            with self.assertRaises(StageFailure): self.run_upload()
        self.assertEqual(self.plan()['action'],'manual_review')
        self.assertEqual(self.plan()['unknown'][0]['part'],1)

    def test_once_retry_advice_disappears_after_consumed_failed_attempt(self):
        with self.lose_part(0):
            with self.assertRaises(StageFailure): self.run_upload()
        self.assertEqual(self.plan()['action'],'review_one_time_part_retry')
        with self.lose_part(0):
            with self.assertRaises(StageFailure):
                retry_unknown_part(self.task,self.factory,upload_fixture.ACCOUNT,0,
                    approved_task_spec_sha256=self.task.view()['task_spec_sha256'])
        self.task = Task(self.root,self.task.job_id)
        self.assertEqual(self.plan()['action'],'manual_review')
        self.assertEqual(self.task.view()['unknown_operations'],1)
        self.assertEqual(self.count('part:0'),2); self.assertEqual(self.count('commit'),0)

    def test_handoff_not_assumed_exported_and_pending_is_not_delivery(self):
        # Synthetic DB projection solely to exercise summary branches; no real-cloud claim.
        with self.task.locked() as db:
            with db:
                db.execute("UPDATE files SET phase='cloud_verified'")
                db.execute('CREATE TABLE upload_context(id INTEGER PRIMARY KEY,kind TEXT,account_sha256 TEXT)')
                db.execute("INSERT INTO upload_context VALUES(1,'official-api',?)",('a'*64,))
                db.execute('CREATE TABLE deliveries(receipt_sha256 TEXT PRIMARY KEY,status TEXT,receipt TEXT,attached INTEGER)')
        self.assertEqual(self.plan()['action'],'export_or_check_handoff')
        for i,(status,action) in enumerate([('pending','await_recipient'),('failed','review_recipient_failure')]):
            with self.task.locked() as db:
                with db: db.execute('INSERT INTO deliveries VALUES(?,?,?,?)',(str(i),status,'SYNTHETIC_PRIVATE_RECEIPT',i+1))
            self.assertEqual(self.plan()['action'],action)
            self.assertFalse(self.task.view()['delivered'])
        self.assertEqual(self.factory_calls,0)

    def test_show_cli_emits_advice_without_changing_database(self):
        before = (self.task.root/'task.sqlite3').read_bytes(); out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = main(['--tasks-dir',str(self.root),'show',self.task.job_id])
        self.assertEqual(result,0)
        view = json.loads(out.getvalue())
        self.assertEqual(view['recovery']['action'],'resume_upload')
        self.assertFalse(view['recovery']['automatic_action'])
        self.assertEqual((self.task.root/'task.sqlite3').read_bytes(),before)
        self.assertEqual(self.factory_calls,0)

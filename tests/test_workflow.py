import json
import hashlib
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fast_transfer.intake import InputProblem
from fast_transfer.workflow import Job, digest, main, MAX_STATE
from fast_transfer.space import RESERVE, MARGIN


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.jobs=self.root/'jobs';self.jobs.mkdir()
        self.source=self.root/'source';self.source.mkdir();(self.source/'.receipts').mkdir()
        self.backend=self.root/'backend';self.backend.mkdir()
        self.manifest=json.loads((Path(__file__).resolve().parents[1]/'examples/ncbi-ecoli/manifest.json').read_text())
        data=b'ACGT'*256
        e=self.manifest['files'][0];e.update(name='fixture.fna',size=len(data),md5=hashlib.md5(data).hexdigest())
        (self.source/e['name']).write_bytes(data)
        (self.source/'.receipts/0.json').write_text(json.dumps({'file':e['name'],'status':'source_verified','bytes':len(data),'md5':e['md5'],'sha256':hashlib.sha256(data).hexdigest()}))
        self.job=Job(self.jobs,'job-workflow')
        net=patch('socket.socket',side_effect=AssertionError('No socket'));sock=net.start();self.addCleanup(net.stop);self.addCleanup(sock.assert_not_called)
        n=patch('socket.create_connection',side_effect=AssertionError('No network'));m=n.start();self.addCleanup(n.stop);self.addCleanup(m.assert_not_called)

    def run_simulation(self):
        self.job.create(self.manifest)
        return self.job.simulate(self.manifest,self.source,self.backend)

    def form(self):
        return {'job_id':'job-workflow','mapping_sha256':self.job.view()['mapping_sha256'],
                'link':'https://share.invalid/s/synthetic-only','expires_at':int(time.time())+3600,
                'authorization_ref':'synthetic-operator-declaration','scope':'simulation-only'}

    def test_simulated_chain_draft_and_expiry_never_grant_real_delivery(self):
        s=self.run_simulation();self.assertEqual(s['phase'],'simulated_cloud_verified')
        form=self.form();self.job.share_draft(form)
        view=self.job.view();self.assertEqual(view['phase'],'share_draft')
        self.assertEqual(view['share_current_status'],'unverified')
        self.assertEqual(self.job.view(form['expires_at'])['share_current_status'],'expired')
        for k in ('cloud_verified','share_verified','delivery_eligible','delivered'):self.assertIs(view[k],False)
        raw=(self.job.root/'state.json').read_text()
        self.assertNotIn(form['link'],raw);self.assertNotIn('extraction_code',raw)
        self.assertEqual(os.stat(self.job.root/'state.json').st_mode & 0o777,0o600)

    def test_wrong_mapping_scope_secret_fields_and_bad_expiry_are_rejected(self):
        self.run_simulation()
        for changes in ({'job_id':'other'},{'mapping_sha256':'0'*64},{'scope':'real-share'},
                        {'expires_at':0},{'expires_at':True},{'expires_at':int(time.time())+31*86400},
                        {'link':'https://pan.baidu.com/s/example?pwd=secret'}, {'password':'secret'}):
            with self.subTest(changes=changes),self.assertRaises(InputProblem):self.job.share_draft({**self.form(),**changes})
        self.assertEqual(self.job.view()['phase'],'simulated_cloud_verified')

    def test_duplicate_start_and_duplicate_share_cannot_overwrite_or_redeliver(self):
        self.run_simulation();state=(self.job.root/'state.json').read_bytes()
        with self.assertRaises(InputProblem):self.job.create(self.manifest)
        with self.assertRaises(InputProblem):self.job.simulate(self.manifest,self.source,self.backend)
        self.assertEqual(state,(self.job.root/'state.json').read_bytes())
        form=self.form();self.job.share_draft(form)
        with self.assertRaises(InputProblem):self.job.share_draft(form)

    def test_interrupted_intent_and_unknown_commit_require_manual_resolution(self):
        self.job.create(self.manifest)
        with patch('fast_transfer.workflow.run_simulated_upload',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.job.simulate(self.manifest,self.source,self.backend)
        self.assertEqual(self.job.view()['phase'],'simulation_running')
        with self.assertRaises(InputProblem):self.job.simulate(self.manifest,self.source,self.backend)
        self.job.manual('inspect_commit_outcome')
        with self.assertRaises(InputProblem):self.job.simulate(self.manifest,self.source,self.backend)
        self.assertEqual(self.job.view()['manual_action'],'inspect_commit_outcome')
        other=Job(self.jobs,'job-unknown');other.create(self.manifest)
        with patch('fast_transfer.workflow.run_simulated_upload',return_value={'mutation_outcome_unknown':True,'reason':'http_io_failure'}):
            self.assertEqual(other.simulate(self.manifest,self.source,self.backend)['phase'],'manual_review')
        self.assertTrue(other.view()['mutation_outcome_unknown'])

    def test_missing_source_mismatched_manifest_and_cancel_do_not_advance(self):
        self.job.create(self.manifest)
        changed=json.loads(json.dumps(self.manifest));changed['files'][0]['name']='other.fna'
        with self.assertRaises(InputProblem):self.job.simulate(changed,self.source,self.backend)
        (self.source/'fixture.fna').unlink()
        self.assertEqual(self.job.simulate(self.manifest,self.source,self.backend)['phase'],'manual_review')
        self.job.manual('cancel');self.assertEqual(self.job.view()['phase'],'cancelled')
        with self.assertRaises(InputProblem):self.job.share_draft(self.form())

    def test_state_true_flags_do_not_grant_rights_and_unknown_fields_are_not_echoed(self):
        self.run_simulation();p=self.job.root/'state.json';s=json.loads(p.read_text())
        s.update(cloud_verified=True,share_verified=True,delivery_eligible=True,delivered=True)
        p.write_text(json.dumps(s))
        self.assertFalse(self.job.view()['delivery_eligible'])
        self.assertFalse(self.job.view()['cloud_verified'])
        s['access_token']='MUST_NOT_ECHO';p.write_text(json.dumps(s))
        with self.assertRaises(InputProblem) as caught:self.job.view()
        self.assertNotIn('MUST_NOT_ECHO',str(caught.exception))

    def test_lock_space_limit_and_symlink_fail_closed(self):
        self.job.create(self.manifest)
        with self.job.locked():
            with self.assertRaisesRegex(InputProblem,'busy'):self.job.manual('verify_source')
        from fast_transfer.space import Volume
        with patch('fast_transfer.workflow.DiskProbe.directory',return_value=Volume(1,1,RESERVE+MARGIN,4096)):
            with self.assertRaisesRegex(InputProblem,'space_reserve'):self.job.manual('verify_source')
        p=self.job.root/'state.json';p.write_bytes(b'X'*(MAX_STATE+1))
        with self.assertRaisesRegex(InputProblem,'record_limit'):self.job.view()
        p.unlink();p.symlink_to(self.source/'fixture.fna')
        with self.assertRaises(OSError):self.job.view()

    def test_cli_create_show_and_invalid_form_have_safe_machine_output(self):
        import io
        mf=self.root/'manifest.json';mf.write_text(json.dumps(self.manifest))
        base=['workflow','--jobs-dir',str(self.jobs),'--job-id','job-cli']
        for args in (['create',str(mf)],['show']):
            stream=io.StringIO()
            with patch('sys.argv',base+args),patch('sys.stdout',stream):self.assertEqual(main(),0)
            self.assertFalse(json.loads(stream.getvalue())['delivery_eligible'])
        form=self.root/'bad-form.json';form.write_text(json.dumps({'access_token':'NEVER_ECHO'}))
        stream=io.StringIO()
        with patch('sys.argv',base+['record-share',str(form)]),patch('sys.stdout',stream):self.assertEqual(main(),2)
        self.assertNotIn('NEVER_ECHO',stream.getvalue())

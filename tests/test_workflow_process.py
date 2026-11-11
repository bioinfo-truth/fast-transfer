"""Real child SIGKILL/reopen and deterministic local persistence fault injection."""
import errno
import hashlib
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import sys
import tempfile
import unittest

from fast_transfer.workflow import Job

REPO=Path(__file__).resolve().parents[1]
WORKER=REPO/'tests/support/workflow_process_worker.py'


class WorkflowProcessTests(unittest.TestCase):
    def setUp(self):
        # Mandatory guard, not a Python socket mock. Do not run this module directly.
        try:probe=socket.socket()
        except OSError as exc:self.assertEqual(exc.errno,errno.EPERM)
        else:
            probe.close()
            self.skipTest('requires tests/support/run_workflow_isolated.py kernel guard')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in ('jobs','source','backend'): (self.root/name).mkdir()
        manifest=json.loads((REPO/'examples/ncbi-ecoli/manifest.json').read_text())
        data=b'ACGT'*256
        manifest['files'][0].update(name='fixture.fna',size=len(data),md5=hashlib.md5(data).hexdigest())
        (self.root/'manifest.json').write_text(json.dumps(manifest))
        (self.root/'source/fixture.fna').write_bytes(data)
        self.children=[];self.addCleanup(self.stop_children)
        self.job=Job(self.root/'jobs','job-process')
        self.run_worker('create')
        self.initial=(self.job.root/'state.json').read_bytes()

    def stop_children(self):
        for p in self.children:
            if p.poll() is None:p.kill()
            p.communicate(timeout=5)

    def spawn(self,mode):
        home=self.root/('home-'+str(len(self.children)));home.mkdir()
        p=subprocess.Popen([sys.executable,'-I','-S','-B',str(WORKER),str(self.root),mode],
            env={'HOME':str(home),'XDG_CONFIG_HOME':str(home/'config'),'TMPDIR':str(self.root)},
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,cwd=self.root)
        self.children.append(p);return p

    def run_worker(self,mode):
        p=self.spawn(mode);out,err=p.communicate(timeout=10)
        self.assertEqual(p.returncode,0,err.decode());self.assertEqual(err,b'')
        return json.loads(out) if out else None

    def paused(self,mode):
        p=self.spawn(mode)
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout,selectors.EVENT_READ)
            self.assertTrue(sel.select(timeout=10),'worker barrier timeout')
        self.assertEqual(p.stdout.readline(),b'READY\n')
        return p

    def kill(self,p):
        p.kill();out,err=p.communicate(timeout=5)
        self.assertEqual(p.returncode,-9);self.assertEqual(err,b'')

    def calls(self):
        p=self.root/'backend-calls'
        return p.read_bytes().count(b'call\n') if p.exists() else 0

    def assert_diagnosis(self,reason):
        before={p.name:p.read_bytes() for p in self.job.root.iterdir() if p.is_file()}
        d=self.run_worker('diagnose')
        self.assertEqual(d['reason'],reason);self.assertFalse(d['delivery_eligible'])
        self.assertFalse(d['automatic_retry_allowed'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.job.root.iterdir() if p.is_file()})
        return d

    def test_kill_before_intent_has_no_backend_action(self):
        self.kill(self.paused('before_intent'))
        self.assertEqual(self.calls(),0)
        self.assertEqual((self.job.root/'state.json').read_bytes(),self.initial)
        self.assert_diagnosis('workflow_record_readable')
        # No backend was invoked; a fresh invocation may consume the first intent.
        self.run_worker('normal');self.assertEqual(self.calls(),1)
        self.run_worker('normal');self.assertEqual(self.calls(),1)

    def test_kill_during_new_file_retains_prior_state_and_blocks_backend(self):
        self.kill(self.paused('during_new'))
        self.assertTrue((self.job.root/'state.new').exists())
        self.assertEqual((self.job.root/'state.json').read_bytes(),self.initial)
        self.assert_diagnosis('workflow_pending_state_file')
        self.run_worker('normal');self.assertEqual(self.calls(),0)

    def test_kill_after_replace_before_directory_fsync_blocks_replay(self):
        self.kill(self.paused('after_replace'))
        self.assert_diagnosis('workflow_incomplete_or_unknown_outcome')
        self.run_worker('normal');self.assertEqual(self.calls(),0)

    def test_kill_after_durable_intent_before_backend_effect_blocks_replay(self):
        # save() returns after file + directory fsync, before backend invocation.
        self.kill(self.paused('after_intent'))
        self.assertEqual(self.calls(),0)
        self.assert_diagnosis('workflow_incomplete_or_unknown_outcome')
        self.run_worker('normal');self.assertEqual(self.calls(),0)

    def test_kill_during_backend_and_competing_start_do_not_repeat_action(self):
        p=self.paused('during_backend')
        self.assertEqual(self.calls(),1)
        self.assertEqual(self.run_worker('normal')['reason'],'workflow_busy')
        self.kill(p)
        self.assert_diagnosis('workflow_incomplete_or_unknown_outcome')
        self.run_worker('normal');self.assertEqual(self.calls(),1)

    def test_directory_fsync_failure_retains_intent_and_blocks_replay(self):
        self.run_worker('directory_fsync_failure')
        self.assert_diagnosis('workflow_incomplete_or_unknown_outcome')
        self.run_worker('normal');self.assertEqual(self.calls(),0)

    def test_terminal_persistence_failure_preserves_unknown_intent(self):
        self.run_worker('terminal_fsync_failure')
        self.assertEqual(self.calls(),1)
        self.assert_diagnosis('workflow_pending_state_file')
        self.run_worker('normal');self.assertEqual(self.calls(),1)
        self.assertEqual(self.job.view()['phase'],'simulation_running')
        self.assertFalse(self.job.view()['delivery_eligible'])

    def test_kill_after_backend_return_before_terminal_save_blocks_replay(self):
        self.kill(self.paused('after_backend'))
        self.assertEqual(self.calls(),1)
        self.assert_diagnosis('workflow_incomplete_or_unknown_outcome')
        self.run_worker('normal');self.assertEqual(self.calls(),1)
        view=self.job.view()
        for key in ('cloud_verified','share_verified','delivery_eligible','delivered'):self.assertFalse(view[key])

    def test_fsync_enospc_leaves_residue_no_backend_or_overwrite(self):
        self.run_worker('write_failure')
        self.assertEqual((self.job.root/'state.json').read_bytes(),self.initial)
        self.assert_diagnosis('workflow_pending_state_file')
        self.run_worker('normal');self.assertEqual(self.calls(),0)
        self.assertEqual((self.job.root/'state.json').read_bytes(),self.initial)

    def test_replace_eio_leaves_residue_no_backend_or_overwrite(self):
        self.run_worker('replace_failure')
        self.assertEqual((self.job.root/'state.json').read_bytes(),self.initial)
        self.assert_diagnosis('workflow_pending_state_file')
        self.run_worker('normal');self.assertEqual(self.calls(),0)

    def test_two_process_lock_competition_then_kernel_release(self):
        holder=self.paused('hold_lock')
        self.assert_diagnosis('workflow_busy')
        out=self.run_worker('normal');self.assertEqual(out['reason'],'workflow_busy')
        self.assertEqual(self.calls(),0)
        self.kill(holder)
        self.assert_diagnosis('workflow_record_readable')
        self.run_worker('normal');self.run_worker('normal');self.assertEqual(self.calls(),1)

    def test_corrupt_missing_and_partial_state_are_readonly_diagnosed(self):
        path=self.job.root/'state.json'
        for raw in (b'{"secret":"SYNTHETIC_NEVER_ECHO"',b'[]',b'{"schema_version":1}'):
            path.write_bytes(raw)
            d=self.assert_diagnosis('workflow_state_unreadable_or_invalid')
            self.assertNotIn('SYNTHETIC_NEVER_ECHO',json.dumps(d))
            self.run_worker('normal');self.assertEqual(self.calls(),0)
        path.unlink()
        self.assert_diagnosis('workflow_state_missing')
        (self.job.root/'state.new').write_bytes(b'partial')
        self.assert_diagnosis('workflow_pending_state_file')

    def test_diagnose_does_not_follow_pending_file_symlink(self):
        sentinel=self.root/'synthetic-sentinel';sentinel.write_bytes(b'UNCHANGED')
        (self.job.root/'state.new').symlink_to(sentinel)
        d=self.run_worker('diagnose');self.assertEqual(d['reason'],'workflow_pending_state_file')
        self.run_worker('normal');self.assertEqual(self.calls(),0)
        self.assertEqual(sentinel.read_bytes(),b'UNCHANGED')

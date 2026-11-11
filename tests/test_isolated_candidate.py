import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_baidu_protocol import FakeHTTP, TARGET, ACCOUNT, LIMITS
from fast_transfer.baidu_http import PinnedBaiduHTTPClient
from fast_transfer.isolated_candidate import IsolatedBaiduCandidate
from fast_transfer.space import BackendNeeds
from fast_transfer.upload_stage import StageFailure, run_simulated_upload


class CandidateHTTP(FakeHTTP):
    def exchange(self, req):
        if req.params.get('method') == 'filemetas' and json.loads(req.params['fsids']) == [7]:
            from test_baidu_protocol import reply
            self.calls.append(req)
            row = {'fs_id': 7, 'path': str(Path(TARGET).parent), 'isdir': 1}
            obj = {'errno': 0, 'list': [row]}
            if self.fault: obj = self.fault(req, obj)
            out = reply(json.dumps(obj).encode()); self.replies.append(out)
            return out
        return super().exchange(req)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.http = CandidateHTTP()
        self.adapter = IsolatedBaiduCandidate(self.http, 'Xtransfer', TARGET, ACCOUNT, LIMITS)
        self.net = patch('socket.create_connection', side_effect=AssertionError('No network'))
        n = self.net.start(); self.addCleanup(self.net.stop); self.addCleanup(n.assert_not_called)

    def begin(self):
        self.adapter.reserve_new(str(Path(TARGET).parent))
        data = self.http.data
        return self.adapter.begin_new(TARGET, len(data), [hashlib.md5(data).hexdigest()])

    def uploaded(self):
        s = self.begin(); self.adapter.put_part(s, 0, self.http.data); return s

    def terminal(self, action):
        before = len(self.http.calls)
        with self.assertRaises(StageFailure): action()
        self.assertEqual(before, len(self.http.calls))
        self.assertFalse(self.adapter.evidence()['delivery_eligible'])

    def test_fake_only_and_directory_identity_checked_before_file_mutations(self):
        with self.assertRaisesRegex(StageFailure, 'fake_only'):
            IsolatedBaiduCandidate(PinnedBaiduHTTPClient(), 'Xtransfer', TARGET, ACCOUNT, LIMITS)
        s = self.uploaded(); self.adapter.commit_new(s)
        directory_reads = [r for r in self.http.calls if r.params.get('fsids') == '[7]']
        self.assertEqual(len(directory_reads), 3)
        self.terminal(lambda: self.adapter.commit_new(s))
        self.assertFalse(self.adapter.evidence()['cloud_verified'])

    def test_existing_directory_or_file_and_racing_rename_never_deliver_or_retry(self):
        for stage in ('directory', 'precreate', 'commit'):
            with self.subTest(stage=stage):
                self.setUp()
                def fault(req, obj):
                    method = req.params.get('method')
                    if stage == 'directory' and method == 'create' and b'isdir=1' in req.body:
                        return {'errno': -8}
                    if stage == 'precreate' and method == 'precreate':return {**obj, 'path': TARGET+'-renamed'}
                    if stage == 'commit' and method == 'create' and b'isdir=0' in req.body:
                        return {**obj, 'path': TARGET+'-renamed'}
                    return obj
                self.http.fault = fault
                with self.assertRaises(StageFailure):
                    s = self.uploaded(); self.adapter.commit_new(s)
                self.assertTrue(self.adapter.uncertain_objects)
                self.terminal(lambda: self.adapter.reserve_new(str(Path(TARGET).parent)))
                self.assertFalse(any(r.params.get('method') in ('delete','filemanager') for r in self.http.calls))

    def test_directory_race_fsid_or_path_drift_stops_before_precreate(self):
        self.adapter.reserve_new(str(Path(TARGET).parent))
        self.http.fault = lambda r,o: {**o, 'list':[{'fs_id':8,'path':TARGET,'isdir':1}]} if r.params.get('fsids') == '[7]' else o
        with self.assertRaises(StageFailure):self.adapter.begin_new(TARGET, 8, [hashlib.md5(self.http.data).hexdigest()])
        self.assertFalse(any(r.params.get('method') == 'precreate' for r in self.http.calls))
        self.terminal(lambda:self.adapter.begin_new(TARGET, 8, []))

    def test_commit_timeout_is_unknown_and_cannot_replay_even_if_server_created_it(self):
        s = self.uploaded()
        exchange = self.http.exchange
        def timeout(req):
            out = exchange(req)
            if req.params.get('method') == 'create' and b'isdir=0' in req.body:
                out.close(); raise TimeoutError('private-response')
            return out
        self.http.exchange = timeout
        with self.assertRaisesRegex(StageFailure, 'http_io_failure'):self.adapter.commit_new(s)
        self.assertTrue(self.adapter.commit_attempted and self.adapter.uncertain_objects)
        self.assertEqual(self.adapter.objects, {})
        self.terminal(lambda:self.adapter.commit_new(s))
        self.assertNotIn('private-response', json.dumps(self.adapter.evidence()))
        # The existing task recorder must retain uncertainty without exception text.
        self.setUp()
        exchange2 = self.http.exchange
        def lost_response(req):
            out = exchange2(req)
            if req.params.get('method') == 'create' and b'isdir=0' in req.body:
                out.close(); raise TimeoutError('private-response')
            return out
        self.http.exchange = lost_response
        with tempfile.TemporaryDirectory() as d:
            result = self.run_job(Path(d))
            self.assertTrue(result['mutation_outcome_unknown'] and result['commit_attempted'])
            self.assertFalse(result['simulated_delivery_eligible'])
            state = (Path(d)/'backend/job-http/state.json').read_text()
            self.assertNotIn('private-response', state)
            self.assertTrue(json.loads(state)['mutation_outcome_unknown'])

    def test_expired_replayed_and_tampered_sessions_are_terminal(self):
        for mode in ('expiry','tamper','duplicate'):
            with self.subTest(mode=mode):
                self.setUp();s=self.begin()
                if mode=='expiry':self.adapter.deadline=time.monotonic()-1
                elif mode=='tamper':s.path=TARGET+'-other'
                else:self.adapter.put_part(s,0,self.http.data)
                with self.assertRaises(StageFailure):self.adapter.put_part(s,0,self.http.data)
                self.terminal(lambda:self.adapter.commit_new(s))

    def run_job(self, root):
        src=root/'source';src.mkdir(exist_ok=True);(src/'.receipts').mkdir(exist_ok=True)
        backend=root/'backend';backend.mkdir(exist_ok=True)
        data=b'ACGTACGT';(src/'test.fna').write_bytes(data)
        entry=json.loads((Path(__file__).resolve().parents[1]/'examples/ncbi-ecoli/manifest.json').read_text())['files'][0]
        entry.update(name='test.fna',size=len(data),md5=hashlib.md5(data).hexdigest())
        receipt=src/'.receipts/0.json';receipt.write_text(json.dumps({'file':'test.fna','status':'source_verified','bytes':len(data),'md5':entry['md5'],'sha256':hashlib.sha256(data).hexdigest()}))
        return run_simulated_upload(entry,src/'test.fna',receipt,backend,'job-http','Xtransfer',self.adapter,
                                    BackendNeeds('direct-api',65536,262144,262144,'stream'),LIMITS)

    def test_joint_hash_length_and_stop_failures_and_persistent_duplicate_start(self):
        for mode in ('success','corrupt','short','stop'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                self.setUp()
                if mode=='corrupt':self.http.data=b'TCGTACGT'
                if mode=='short':self.http.data=b'ACGT'
                if mode=='stop':self.http.stop=lambda:False
                r=self.run_job(Path(d))
                self.assertEqual(r['simulated_delivery_eligible'],mode=='success')
                self.assertFalse(r['cloud_verified'] or r['delivery_eligible'])
                if mode=='corrupt':self.assertEqual(r['reason'],'readback_hash_or_length_mismatch')
                if mode=='stop':self.assertEqual(r['reason'],'adapter_stop_unconfirmed')
                before=len(self.http.calls)
                r2=self.run_job(Path(d))
                self.assertFalse(r2['simulated_delivery_eligible']);self.assertEqual(len(self.http.calls),before)

    def test_space_checkpoint_failure_terminates_candidate_without_more_writes(self):
        s=self.uploaded()
        class Context:
            def checkpoint(self):raise StageFailure('disk_budget_exceeded')
        self.adapter.attach(Context())
        before=len(self.http.calls)
        with self.assertRaisesRegex(StageFailure,'disk_budget_exceeded'):self.adapter.commit_new(s)
        self.assertEqual(len(self.http.calls),before)
        self.adapter.context=None
        self.terminal(lambda:self.adapter.commit_new(s))

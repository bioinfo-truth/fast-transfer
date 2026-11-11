import hashlib
import json
import tempfile
import io
import sys
import os
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fast_transfer.simulated_cloud import MemoryCloud
from fast_transfer.space import BackendNeeds, DiskProbe, RESERVE, MARGIN
from fast_transfer.upload_stage import run_simulated_upload, TransferLimits, StageFailure
from fast_transfer.intake import InputProblem
from fast_transfer import m3


class Volumes(DiskProbe):
    def __init__(self, source, backend, split):
        self.source, self.backend, self.split = source, backend, split
        self.free = {0: 64*1024**3, 1: 64*1024**3, 2: 64*1024**3}

    def device(self, path):
        if not self.split:
            return 0
        if path.is_relative_to(self.source):
            return 1
        if path.is_relative_to(self.backend):
            return 2
        return 0

    def directory(self, path, writable=False):
        v = super().directory(path, writable)
        device = self.device(path)
        return replace(v, device=device, free=self.free[device])

    def file(self, path):
        a = super().file(path)
        return None if a is None else replace(a, device=self.device(path))


class UploadStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source, self.backend = root/'source', root/'backend'
        self.source.mkdir(); self.backend.mkdir(); (self.source/'.receipts').mkdir()
        self.data = b'ACGT'*2048
        self.entry = json.loads((Path(__file__).resolve().parents[1]/'examples/ncbi-ecoli/manifest.json').read_text())['files'][0]
        self.entry.update(name='test.fna', size=len(self.data), md5=hashlib.md5(self.data).hexdigest())
        self.path = self.source/self.entry['name']; self.path.write_bytes(self.data)
        self.receipt = self.source/'.receipts/0.json'
        self.receipt.write_text(json.dumps({'status': 'source_verified', 'file': self.entry['name'],
                                          'bytes': len(self.data), 'md5': self.entry['md5'],
                                          'sha256': hashlib.sha256(self.data).hexdigest()}))
        self.needs = BackendNeeds('direct-api', 65536, 262144, 262144, 'stream')
        self.limits = TransferLimits(1024, 16384, 32, 512)
        self.cloud = MemoryCloud()
        self.probe = Volumes(self.source, self.backend, False)

    def run_job(self, cloud=None, **kw):
        with patch('socket.create_connection', side_effect=AssertionError('No sockets allowed')) as net:
            result = run_simulated_upload(self.entry, self.path, self.receipt, self.backend,
                                          kw.pop('job_id', 'job-01'), 'Xtransfer', cloud or self.cloud,
                                          kw.pop('needs', self.needs), kw.pop('limits', self.limits),
                                          probe=self.probe, **kw)
            net.assert_not_called()
        return result

    def test_success_checks_source_parts_metadata_and_full_readback_on_both_layouts(self):
        for split in (False, True):
            with self.subTest(split=split):
                self.probe.split = split
                cloud = MemoryCloud()
                r = self.run_job(cloud, job_id='job-split' if split else 'job-same',
                                 expected_layout='separate' if split else 'same')
                self.assertEqual(r['status'], 'verified_simulation')
                self.assertTrue(r['verification_complete'] and r['simulated_delivery_eligible'])
                self.assertFalse(r['delivery_eligible'] or r['cloud_verified'])
                self.assertEqual(r['source'], r['readback'])
                self.assertEqual(r['confirmed_parts'], list(range(8)))
                self.assertEqual(r['requested_payload_bytes'], len(self.data))
                self.assertTrue(r['stop_confirmed'] and r['state_persisted'])
                self.assertEqual(cloud.objects[r['target']], self.data)
                files = list((self.backend/r['job_id']).iterdir())
                self.assertEqual([x.name for x in files], ['state.json'])
                self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)

    def test_source_receipt_or_hash_failure_prevents_remote_operations(self):
        self.path.write_bytes(b'X'*len(self.data))
        r = self.run_job()
        self.assertEqual(r['reason'], 'source_receipt_mismatch')
        self.assertEqual(self.cloud.operations, [])
        self.assertFalse(r['simulated_delivery_eligible'])

    def test_manifest_checksum_is_checked_independently_of_source_receipt(self):
        self.entry['md5'] = '0'*32
        r = self.run_job()
        self.assertEqual(r['reason'], 'source_checksum_mismatch')
        self.assertEqual(self.cloud.operations, [])

    def test_source_size_and_oversize_receipt_refuse_before_upload(self):
        self.path.write_bytes(self.data[:-1])
        self.assertEqual(self.run_job()['reason'], 'source_size_mismatch')
        self.path.write_bytes(self.data)
        self.receipt.write_bytes(b'X'*16385)
        self.assertEqual(self.run_job(job_id='large-receipt')['reason'], 'source_receipt_limit')
        self.assertEqual(self.cloud.operations, [])

    def test_failed_source_receipt_is_not_an_upload_authorization(self):
        r = json.loads(self.receipt.read_text()); r['status'] = 'failed'
        self.receipt.write_text(json.dumps(r))
        result = self.run_job()
        self.assertEqual(result['reason'], 'source_receipt_mismatch')
        self.assertEqual(self.cloud.operations, [])

    def test_part_receipt_mismatch_stops_without_commit(self):
        class BadPart(MemoryCloud):
            def put_part(self, session, index, data):
                super().put_part(session, index, data)
                return '0'*32
        cloud = BadPart(); r = self.run_job(cloud)
        self.assertEqual(r['reason'], 'part_receipt_mismatch')
        self.assertNotIn('commit', cloud.operations)
        self.assertTrue(cloud.stopped)

    def test_remote_size_mismatch_prevents_readback_and_delivery(self):
        class BadSize(MemoryCloud):
            def metadata(self, path): return {'size': 1}
        cloud = BadSize(); r = self.run_job(cloud)
        self.assertEqual(r['reason'], 'remote_size_mismatch')
        self.assertNotIn('readback', cloud.operations)
        self.assertFalse(r['simulated_delivery_eligible'])

    def test_corrupt_truncated_and_excessive_readback_never_qualify(self):
        for mode in ('corrupt', 'truncate', 'extra'):
            class BadBack(MemoryCloud):
                def readback(inner, path, chunk_bytes):
                    data = inner.objects[path]
                    data = b'X'+data[1:] if mode == 'corrupt' else data[:-1] if mode == 'truncate' else data+b'X'
                    for i in range(0, len(data), chunk_bytes): yield data[i:i+chunk_bytes]
            r = self.run_job(BadBack(), job_id='bad-'+mode)
            self.assertFalse(r['verification_complete'] or r['simulated_delivery_eligible'])
            self.assertIn(r['reason'], ('readback_hash_or_length_mismatch', 'readback_size_exceeded'))

    def test_duplicate_start_preserves_existing_record_and_sends_nothing(self):
        self.assertTrue(self.run_job()['simulated_delivery_eligible'])
        state = self.backend/'job-01/state.json'; before = state.read_bytes()
        cloud = MemoryCloud(); r = self.run_job(cloud)
        self.assertEqual(r['reason'], 'duplicate_job')
        self.assertEqual(cloud.operations, [])
        self.assertEqual(state.read_bytes(), before)

    def test_remote_namespace_collision_does_not_overwrite_old_object(self):
        directory = '/apps/Xtransfer/mvp-validation/job-01'
        self.cloud.directories.add(directory)
        self.cloud.objects[directory+'/test.fna'] = b'old'
        r = self.run_job()
        self.assertEqual(r['reason'], 'remote_target_exists')
        self.assertEqual(self.cloud.objects[directory+'/test.fna'], b'old')
        self.assertNotIn('begin', self.cloud.operations)

    def test_unknown_overhead_and_missing_limits_stop_before_transport(self):
        r = self.run_job(needs=BackendNeeds('direct-api'))
        self.assertEqual(r['reason'], 'unknown_source_overhead')
        self.assertEqual(list(self.backend.iterdir()), [])
        r = self.run_job(limits=TransferLimits(1024, None, 32))
        self.assertEqual(r['reason'], 'unknown_or_invalid_transfer_limits')
        self.assertEqual(self.cloud.operations, [])

    def test_source_changes_after_validation_are_not_uploaded(self):
        path, data = self.path, self.data
        class Mutating(MemoryCloud):
            def reserve_new(inner, target):
                super().reserve_new(target); path.write_bytes(b'X'*len(data))
        cloud = Mutating(); r = self.run_job(cloud)
        self.assertEqual(r['reason'], 'source_changed')
        self.assertFalse(any(x.startswith('part:') for x in cloud.operations))

    def test_exception_messages_are_redacted_and_adapter_is_stopped(self):
        class Error(MemoryCloud):
            def put_part(self, *args): raise RuntimeError('SECRET_TOKEN https://signed.example/?secret')
        cloud = Error(); r = self.run_job(cloud)
        self.assertEqual(r['reason'], 'adapter_or_local_io_failure')
        self.assertNotIn('SECRET', json.dumps(r))
        self.assertNotIn('signed.example', (self.backend/'job-01/state.json').read_text())
        self.assertTrue(cloud.stopped)

    def test_injected_error_codes_cannot_smuggle_sensitive_text(self):
        for index, error in enumerate((StageFailure('SECRET_TOKEN'), InputProblem('secret_account_token'))):
            class Spoofed(MemoryCloud):
                def put_part(self, *args): raise error
            r = self.run_job(Spoofed(), job_id='spoof-'+str(index))
            self.assertEqual(r['reason'], 'adapter_or_local_io_failure')
            self.assertNotIn('SECRET', json.dumps(r))
            self.assertNotIn('secret_account_token', json.dumps(r))

    def test_unconfirmed_stop_revokes_simulated_delivery(self):
        class Unstopped(MemoryCloud):
            def stop(self): return False
        r = self.run_job(Unstopped())
        self.assertTrue(r['verification_complete'])
        self.assertEqual(r['reason'], 'adapter_stop_unconfirmed')
        self.assertFalse(r['simulated_delivery_eligible'])

    def test_space_falls_before_second_part_no_further_payload_is_stored(self):
        for split in (False, True):
            self.probe = Volumes(self.source, self.backend, split)
            probe = self.probe
            class Drop(MemoryCloud):
                def put_part(inner, session, index, data):
                    if index == 1: probe.free[2 if split else 0] = RESERVE+MARGIN-1
                    return super().put_part(session, index, data)
            cloud = Drop(); r = self.run_job(cloud, job_id='drop-split' if split else 'drop-same')
            self.assertEqual(r['reason'], 'disk_budget_exceeded')
            self.assertEqual(r['confirmed_parts'], [0])
            self.assertEqual([x for x in cloud.operations if x.startswith('part:')], ['part:0'])
            self.assertTrue(cloud.stopped)
            self.assertFalse(r['state_persisted'] or r['simulated_delivery_eligible'])
            self.assertEqual(self.path.read_bytes(), self.data)

    def test_readback_phase_cap_and_dynamic_space_loss_stop_safely(self):
        r = self.run_job(needs=BackendNeeds('direct-api', 65536, 262144, 0, 'stream'))
        self.assertEqual(r['reason'], 'temporary_overhead_exceeds_plan')
        self.assertNotIn('readback', self.cloud.operations)
        probe = self.probe
        class DropBack(MemoryCloud):
            def readback(inner, path, chunk_bytes):
                probe.free[0] = RESERVE+MARGIN-1
                yield inner.objects[path][:chunk_bytes]
        cloud = DropBack(); r = self.run_job(cloud, job_id='drop-back')
        self.assertEqual(r['reason'], 'disk_budget_exceeded')
        self.assertFalse(r['simulated_delivery_eligible'])
        self.assertEqual(len(cloud.objects), 1)  # No remote cleanup/deletion.

    def test_temporary_files_are_registered_and_checked_before_write(self):
        class Temp(MemoryCloud):
            def attach(inner, context):
                super().attach(context)
                inner.temp = context.register_temporary('scratch.bin')
            def put_part(inner, *args):
                if not inner.temp.exists():
                    inner.context.before_temporary_write(300000)
                    inner.temp.write_bytes(b'X'*300000)
                return super().put_part(*args)
        cloud = Temp(); r = self.run_job(cloud)
        self.assertEqual(r['reason'], 'temporary_overhead_exceeds_plan')
        self.assertFalse((self.backend/'job-01/scratch.bin').exists())
        self.assertNotIn('part:0', cloud.operations)

    def test_registered_temporary_file_survives_upload_to_readback_transition(self):
        class Temp(MemoryCloud):
            def attach(inner, context):
                super().attach(context)
                inner.temp = context.register_temporary('scratch.bin')
            def put_part(inner, *args):
                if not inner.temp.exists():
                    inner.context.before_temporary_write(4096)
                    fd = os.open(inner.temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(fd, 'wb') as f: f.write(b'X'*128)
                    inner.context.checkpoint()
                return super().put_part(*args)
        r = self.run_job(Temp())
        self.assertTrue(r['simulated_delivery_eligible'])
        self.assertEqual((self.backend/'job-01/scratch.bin').read_bytes(), b'X'*128)

    def test_limits_and_system_floor_fail_before_new_task_or_transport(self):
        r = self.run_job(limits=TransferLimits(1024, 16384, 1))
        self.assertEqual(r['reason'], 'file_exceeds_transfer_limits')
        self.probe.free[0] = RESERVE+MARGIN-1
        self.assertEqual(self.run_job()['reason'], 'space_workspace_reserve')
        self.assertEqual(list(self.backend.iterdir()), [])
        self.assertEqual(self.cloud.operations, [])

    def test_cli_is_explicitly_offline_and_returns_machine_readable_state(self):
        manifest = self.source/'manifest.json'
        manifest.write_text(json.dumps({'schema_version': 1, 'files': [self.entry]}))
        args = ['m3', '--simulate', str(manifest), '--source-dir', str(self.source),
                '--backend-dir', str(self.backend), '--job-id', 'cli-job']
        stdout = io.StringIO()
        with patch.object(sys, 'argv', args), patch.object(sys, 'stdout', stdout), patch('socket.create_connection', side_effect=AssertionError('No network')) as net:
            self.assertEqual(m3.main(), 0)
            net.assert_not_called()
        r = json.loads(stdout.getvalue())
        self.assertTrue(r['simulated_delivery_eligible'])
        self.assertFalse(r['delivery_eligible'] or r['cloud_verified'])

    def test_cli_requires_simulate_flag_and_has_no_live_fallback(self):
        stderr = io.StringIO()
        with patch.object(sys, 'argv', ['m3']), patch.object(sys, 'stderr', stderr):
            with self.assertRaises(SystemExit) as caught: m3.main()
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.cloud.operations, [])

    def test_live_transport_bad_task_paths_and_source_symlinks_are_refused(self):
        self.cloud.mode = 'live'
        self.assertEqual(self.run_job()['reason'], 'transport_mode_or_app_mismatch')
        self.cloud.mode = 'simulation'
        self.assertEqual(self.run_job(job_id='../escape')['reason'], 'invalid_task_or_app_name')
        self.path.unlink(); self.path.symlink_to(self.receipt)
        self.assertFalse(self.run_job()['simulated_delivery_eligible'])
        self.assertEqual(self.cloud.operations, [])

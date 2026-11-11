"""Synthetic generic task faults only; run with inherited kernel network denial."""
import io
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fast_transfer.baidu_http import HTTPReply, HTTPRequest, PinnedBaiduHTTPClient, RuntimeGrant
from fast_transfer.sdk_codec import SDKRequestEncoder
from fast_transfer.space import DiskProbe, Volume
from fast_transfer.task import Task
from fast_transfer.upload_stage import StageFailure
from test_sdk_codec import HELPER, GUARD, sha
import test_task_upload as fixtures


class StabilityTests(unittest.TestCase):
    configure = fixtures.TaskUploadTests.configure
    download = fixtures.TaskUploadTests.download
    prepare = fixtures.TaskUploadTests.prepare
    factory = fixtures.TaskUploadTests.factory
    run_upload = fixtures.TaskUploadTests.run_upload
    count = fixtures.TaskUploadTests.count

    def setUp(self):
        if not HELPER.is_file(): self.skipTest('Build actual SDK encoder first')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.guard = self.root/'guard.py'; self.guard.write_bytes(GUARD.read_bytes()); self.guard.chmod(0o600)
        self.codec = SDKRequestEncoder(HELPER, sha(HELPER), self.guard, sha(self.guard))
        self.manifest = {'files': [{'name':'sample.bin','url':'https://example.org/sample.bin',
            'source':{'access':'public','record_url':'https://example.org/record','version':'synthetic-v1',
                'checksum_url':'https://example.org/checksums', 'redistribution':{'status':'reviewed',
                    'basis_url':'https://example.org/terms','note':'Synthetic fixture; never fetch.'}}}]}
        self.data = {'sample.bin': b'A'*(4*1024**2)+b'B'*1024}
        self.configure(); self.prepare()

    def test_probe_status_stops_once_persists_reason_and_never_writes(self):
        for status, reason in ((429,'http_rate_limited'), (401,'http_auth_rejected'), (403,'http_access_denied')):
            with self.subTest(status=status):
                calls = []; replies = []
                def deny(client, req):
                    calls.append(req)
                    stream = io.BytesIO(b'private error text must not be recorded')
                    out = HTTPReply(status, [], stream.read1, stream.close, time.monotonic()+10)
                    replies.append(out); return out
                with patch.object(fixtures.MemoryAPI,'exchange',deny):
                    with self.assertRaisesRegex(StageFailure,reason): self.run_upload()
                self.assertEqual(len(calls),1); self.assertTrue(replies[0].closed)
                view = self.task.view()
                self.assertEqual(view['files'][0]['reason'],reason)
                self.assertEqual(view['unknown_operations'],0); self.assertFalse(self.cloud.events)
                self.assertTrue(self.last.client.stopped)
        self.task = Task(self.root,self.task.job_id)
        self.run_upload()
        self.assertEqual(self.count('commit'),1)

    def test_timeout_after_part_effect_is_unknown_and_restart_does_not_replay(self):
        exchange = fixtures.MemoryAPI.exchange
        def drop(client,req):
            out = exchange(client,req)
            if req.purpose == 'upload':
                out.close(); raise StageFailure('http_timeout')
            return out
        with patch.object(fixtures.MemoryAPI,'exchange',drop):
            with self.assertRaisesRegex(StageFailure,'http_timeout'): self.run_upload()
        self.assertEqual(self.task.view()['unknown_operations'],1)
        self.assertEqual(self.task.view()['files'][0]['reason'],'http_timeout')
        before = list(self.cloud.events); calls = self.factory_calls
        self.task = Task(self.root,self.task.job_id)
        with self.assertRaisesRegex(StageFailure,'unknown_operation'): self.run_upload()
        self.assertEqual(self.factory_calls,calls); self.assertEqual(self.cloud.events,before)
        self.assertEqual(self.count('commit'),0)

    def test_space_drop_after_confirmed_part_stops_and_resume_skips_it(self):
        original = DiskProbe.directory; low = [False]
        def directory(probe,path,writable=False):
            volume = original(probe,path,writable)
            return Volume(volume.device,volume.inode,0,volume.quantum) if low[0] else volume
        def boundary(operation,part):
            if operation == 'part' and part == 0: low[0] = True
        with patch.object(DiskProbe,'directory',directory):
            with self.assertRaisesRegex(Exception,'disk_budget_exceeded'):
                self.run_upload(checkpoint_hook=boundary)
        self.assertTrue(self.last.client.stopped)
        self.assertEqual(self.count('part:0'),1); self.assertEqual(self.count('part:1'),0)
        self.assertEqual(self.count('commit'),0)
        self.assertEqual(self.task.view()['unknown_operations'],0)
        self.assertEqual(self.task.view()['files'][0]['phase'],'uploading')
        low[0] = False; self.task = Task(self.root,self.task.job_id); self.run_upload()
        self.assertEqual(self.count('part:0'),1); self.assertEqual(self.count('part:1'),1)
        self.assertEqual(self.count('commit'),1)

    def test_reply_socket_timeout_closes_without_leaking_exception(self):
        closed = []
        def reader(n): raise TimeoutError('synthetic private request text')
        reply = HTTPReply(200,[],reader,lambda:closed.append(True),time.monotonic()+10)
        with self.assertRaisesRegex(StageFailure,'^http_timeout$'):
            list(reply.chunks(100,16))
        self.assertEqual(closed,[True]); self.assertTrue(reply.closed)

    def test_readback_rate_limit_recovers_with_get_only_without_recommit(self):
        exchange = fixtures.MemoryAPI.exchange
        replies = []
        def deny_readback(client,req):
            if req.purpose == 'readback':
                stream = io.BytesIO(b'')
                out = HTTPReply(429,[],stream.read1,stream.close,time.monotonic()+10)
                replies.append(out); return out
            return exchange(client,req)
        with patch.object(fixtures.MemoryAPI,'exchange',deny_readback):
            with self.assertRaisesRegex(StageFailure,'http_rate_limited'): self.run_upload()
        self.assertEqual(len(replies),1); self.assertTrue(replies[0].closed)
        self.assertEqual(self.task.view()['unknown_operations'],0)
        self.assertEqual(self.task.view()['files'][0]['reason'],'http_rate_limited')
        self.assertEqual(self.count('commit'),1)
        self.task = Task(self.root,self.task.job_id)
        def only_get(client,req):
            self.assertEqual(req.method,'GET'); return exchange(client,req)
        with patch.object(fixtures.MemoryAPI,'exchange',only_get):
            result = self.run_upload(readback_only=True)
        self.assertEqual(result['status'],'test_cloud_verified')
        self.assertFalse(result['delivered']); self.assertFalse(result['cloud_verified'])
        self.assertEqual(self.count('commit'),1)

    def test_request_socket_timeout_closes_connection_without_retry(self):
        target = '/apps/Xtransfer/mvp-validation/job-synthetic/sample.bin'
        grant = RuntimeGrant(True,target,'a'*64,'b'*64,'synthetic-only',time.monotonic()+60)
        connection = Mock(); connection.getresponse.side_effect = TimeoutError('private synthetic detail')
        factory = Mock(return_value=connection)
        client = PinnedBaiduHTTPClient(grant=grant,resolver=lambda _:['8.8.8.8'],connection_factory=factory)
        request = HTTPRequest('GET','https://d.pcs.baidu.com/data',target,'readback',auth=False)
        with self.assertRaisesRegex(StageFailure,'^http_timeout$'): client.exchange(request)
        factory.assert_called_once(); connection.request.assert_called_once(); connection.close.assert_called_once()
        self.assertTrue(client.stop())

    def test_sqlite_full_before_receipt_keeps_part_or_commit_unknown(self):
        # Real SQLITE_FULL in a temporary test database via page cap; no disk filling.
        original = Task.finish_operation
        for operation in ('part','commit'):
            with self.subTest(operation=operation):
                self.configure(); self.prepare()
                def full(task,index,op,fingerprint,receipt,*,part=-1,_db=None):
                    if op == operation:
                        _db.execute('CREATE TABLE synthetic_capacity_probe(payload BLOB)')
                        _db.commit()
                        pages = _db.execute('PRAGMA page_count').fetchone()[0]
                        _db.execute('PRAGMA max_page_count='+str(pages))
                        with _db:
                            _db.execute('INSERT INTO synthetic_capacity_probe VALUES(zeroblob(1048576))')
                        raise AssertionError('Expected bounded SQLite capacity failure')
                    return original(task,index,op,fingerprint,receipt,part=part,_db=_db)
                with patch.object(Task,'finish_operation',full):
                    with self.assertRaises(sqlite3.OperationalError) as caught:
                        self.run_upload()
                self.assertEqual(caught.exception.sqlite_errorcode,sqlite3.SQLITE_FULL)
                self.assertTrue(self.last.client.stopped)
                view = self.task.view()
                self.assertEqual(view['unknown_operations'],1)
                self.assertFalse(view['delivered'])
                self.assertEqual(view['files'][0]['phase'],'uploading')
                with self.task.locked() as db:
                    row = db.execute("SELECT operation,receipt FROM operations WHERE outcome='unknown'").fetchone()
                    self.assertEqual(row['operation'],operation); self.assertIsNone(row['receipt'])
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM verifications').fetchone()[0],0)
                calls = self.factory_calls; events = list(self.cloud.events)
                self.task = Task(self.root,self.task.job_id)
                with self.assertRaisesRegex(StageFailure,'unknown_operation'): self.run_upload()
                self.assertEqual(self.factory_calls,calls); self.assertEqual(self.cloud.events,events)
                self.assertEqual(self.count('part:0'),1)
                self.assertEqual(self.count('commit'),1 if operation=='commit' else 0)

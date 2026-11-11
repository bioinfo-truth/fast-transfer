"""Private, durable multi-file MVP tasks and the real source-download stage.

Cloud operations are journaled here but this CLI does not yet invoke an upload
backend. A manifest or a saved receipt is never an authentication grant.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time
from uuid import uuid4

from .download import download_verified
from .intake import InputProblem, load_manifest, require_accepted
from .space import DiskProbe, SpaceGuard, BackendNeeds, preflight_workspace
from .upload_stage import open_regular, source_identity, StageFailure, safe_reason
from .workflow import digest
from .resources import ResourceSamples

MAX_JSON = 1024 * 1024
MAX_RECEIPT = 64 * 1024
SOURCE_PHASES = ('pending', 'downloading', 'source_verified', 'source_failed')
OPERATIONS = frozenset(('directory', 'precreate', 'part', 'commit'))
PHASES = frozenset((*SOURCE_PHASES, 'uploading', 'cloud_verified', 'test_cloud_verified', 'cleaned', 'manual_review'))


def fail(code):
    raise InputProblem(code, 'manual_review')


def private_directory(path):
    path = Path(path).absolute()
    DiskProbe().directory(path, writable=True)
    info = path.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        fail('task_private_directory_required')
    return path


def private_file(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077 or info.st_nlink != 1):
        fail('task_private_file_required')


def encoded(value, limit=MAX_JSON):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(raw.encode()) > limit:
        fail('task_record_limit')
    return raw


def read_json(raw):
    if type(raw) is not str or len(raw.encode()) > MAX_JSON:
        fail('task_record_invalid')
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                fail('task_record_invalid')
            out[k] = v
        return out
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: fail('task_record_invalid'))
    except (ValueError, TypeError):
        fail('task_record_invalid')


class Task:
    """One operator/worker at a time, SQLite FULL transactions, private records.

    Unknown remote writes are never reset by reopening the task. SQLite is used
    for transactions, not as proof of remote success or account permission.
    """
    def __init__(self, parent, job_id):
        if type(job_id) is not str or not re.fullmatch(r'job-[0-9a-f]{32}', job_id):
            fail('task_id_invalid')
        self.root = Path(parent).absolute() / job_id
        self.job_id = job_id

    @classmethod
    def create(cls, parent, manifest, *, app_name='Xtransfer',
               max_file_bytes=1024**3, part_bytes=4*1024**2):
        entries = require_accepted(manifest)
        # Copy the reviewed snapshot; later caller mutations cannot change it.
        snapshot = read_json(encoded(manifest))
        if (type(max_file_bytes) is not int or not 0 < max_file_bytes <= 20*1000**3
                or type(part_bytes) is not int or not 4*1024**2 <= part_bytes <= 32*1024**2
                or any(e['size'] > max_file_bytes or (e['size']+part_bytes-1)//part_bytes > 1024 for e in entries)
                or type(app_name) is not str or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', app_name)):
            fail('task_transfer_limits_invalid')
        parent = private_directory(parent)
        preflight_workspace(parent)
        task = cls(parent, 'job-'+uuid4().hex)
        task.root.mkdir(mode=0o700)
        (task.root/'files').mkdir(mode=0o700)
        fd = os.open(task.root/'lock', os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
        os.close(fd)
        fd = os.open(task.root/'task.sqlite3', os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
        os.close(fd)
        with task.locked(initializing=True) as db:
            db.executescript('''
                CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1), snapshot TEXT NOT NULL,
                  manifest_sha256 TEXT NOT NULL, settings TEXT NOT NULL, created INTEGER NOT NULL);
                CREATE TABLE files (idx INTEGER PRIMARY KEY, phase TEXT NOT NULL,
                  source_receipt TEXT, source_stamp TEXT, reason TEXT);
                CREATE TABLE operations (idx INTEGER NOT NULL, operation TEXT NOT NULL,
                  part INTEGER NOT NULL, intent_sha256 TEXT NOT NULL,
                  outcome TEXT NOT NULL, receipt TEXT, started INTEGER NOT NULL,
                  PRIMARY KEY(idx, operation, part));
                PRAGMA user_version=1;
            ''')
            settings = {'app_name': app_name, 'max_file_bytes': max_file_bytes,
                        'part_bytes': part_bytes, 'source_admission': 'source-only'}
            with db:
                db.execute('INSERT INTO meta VALUES(1,?,?,?,?)',
                           (encoded(snapshot), digest(snapshot), encoded(settings), int(time.time())))
                db.executemany('INSERT INTO files VALUES(?,?,NULL,NULL,NULL)',
                               [(i, 'pending') for i in range(len(entries))])
        task.sync_directory()
        return task

    def sync_directory(self):
        fd = os.open(self.root, os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def locked(self, *, initializing=False):
        private_directory(self.root)
        private_file(self.root/'lock')
        lock = os.open(self.root/'lock', os.O_RDWR|os.O_NOFOLLOW)
        db = None
        try:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                fail('task_busy')
            private_file(self.root/'task.sqlite3')
            for name in ('task.sqlite3-journal', 'task.sqlite3-wal', 'task.sqlite3-shm'):
                if os.path.lexists(self.root/name):
                    private_file(self.root/name)
            db = sqlite3.connect((self.root/'task.sqlite3').as_uri()+'?mode=rw',
                                 uri=True, timeout=0)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA synchronous=FULL')
            if not initializing:
                if db.execute('PRAGMA user_version').fetchone()[0] != 1:
                    fail('task_schema_invalid')
                self.context(db)
            yield db
        finally:
            if db is not None:
                db.close()
            os.close(lock)

    @contextlib.contextmanager
    def _using_db(self, db=None):
        """Internal worker reuse while its outer task lock remains held."""
        if db is not None:
            self.context(db)
            yield db
        else:
            with self.locked() as connection:
                yield connection

    def context(self, db):
        row = db.execute('SELECT * FROM meta WHERE id=1').fetchone()
        if row is None:
            fail('task_record_invalid')
        manifest, settings = read_json(row['snapshot']), read_json(row['settings'])
        entries = require_accepted(manifest)
        if digest(manifest) != row['manifest_sha256']:
            fail('task_manifest_changed')
        if (type(settings) is not dict or set(settings) != {'app_name','max_file_bytes','part_bytes','source_admission'}
                or settings['source_admission'] != 'source-only'
                or type(settings['app_name']) is not str
                or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', settings['app_name'])
                or type(settings['max_file_bytes']) is not int or not 0 < settings['max_file_bytes'] <= 20*1000**3
                or type(settings['part_bytes']) is not int or not 4*1024**2 <= settings['part_bytes'] <= 32*1024**2):
            fail('task_record_invalid')
        rows = list(db.execute('SELECT * FROM files ORDER BY idx'))
        if (len(rows) != len(entries) or any(r['idx'] != i or r['phase'] not in PHASES
                or entries[i]['size'] > settings['max_file_bytes']
                or (entries[i]['size']+settings['part_bytes']-1)//settings['part_bytes'] > 1024
                for i, r in enumerate(rows))):
            fail('task_record_invalid')
        return manifest, settings, rows

    def spec_digest(self, manifest, settings):
        return digest({'job_id':self.job_id,'manifest_sha256':digest(manifest),'settings':settings})

    def _recovery(self, db, rows, settings, backend, delivered):
        """Advisory local state only: never execute or grant the suggested action."""
        unknown = list(db.execute("SELECT idx,operation,part FROM operations WHERE outcome='unknown' ORDER BY idx,operation,part"))
        detail = []
        for op in unknown:
            if (type(op['idx']) is not int or not 0 <= op['idx'] < len(rows)
                    or op['operation'] not in OPERATIONS or type(op['part']) is not int
                    or (op['operation'] != 'part' and op['part'] != -1)
                    or (op['operation'] == 'part' and not 0 <= op['part'] < 1024)):
                fail('task_record_invalid')
            detail.append({'index':op['idx'],'operation':op['operation'],'part':op['part']})
        result = {'advisory_only':True,'automatic_action':False,'unknown':detail,
                  'index':None,'action':'manual_review'}
        if unknown:
            if len(unknown) == 1:
                op = unknown[0]; result['index'] = op['idx']
                if op['operation'] == 'commit':result['action'] = 'inspect_commit_proof'
                elif op['operation'] == 'part':
                    manifest, _, _ = self.context(db)
                    count = (manifest['files'][op['idx']]['size']+settings['part_bytes']-1)//settings['part_bytes']
                    attempted = False
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name='part_retry_attempts' AND type='table'").fetchone():
                        attempted = db.execute('SELECT 1 FROM part_retry_attempts WHERE idx=? AND part=?',
                                               (op['idx'],op['part'])).fetchone() is not None
                    if op['part'] < count-1 and not attempted:
                        result['action'] = 'review_one_time_part_retry'
            return result
        if delivered:
            result['action'] = 'delivery_recorded'; return result
        row = next((r for r in rows if r['phase'] not in ('cloud_verified','test_cloud_verified','cleaned')),None)
        if row is not None:
            result['index'] = row['idx']
            phase = row['phase']
            result['action'] = {'pending':'download_next','downloading':'recover_source',
                                'source_failed':'recover_source','source_verified':'resume_upload'}.get(phase,'manual_review')
            if phase == 'uploading':
                commit = db.execute("SELECT 1 FROM operations WHERE idx=? AND operation='commit' AND outcome='confirmed'",
                                    (row['idx'],)).fetchone()
                result['action'] = 'readback_only' if commit else 'resume_upload'
            return result
        if backend != 'official-api' or any(r['phase']=='test_cloud_verified' for r in rows):
            result['action'] = 'synthetic_only'; return result
        result['action'] = 'export_or_check_handoff'
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='deliveries' AND type='table'").fetchone():
            last = db.execute('SELECT status FROM deliveries ORDER BY attached DESC,rowid DESC LIMIT 1').fetchone()
            if last is not None:
                result['action'] = 'await_recipient' if last['status']=='pending' else 'review_recipient_failure'
        return result

    def view(self):
        with self.locked() as db:
            manifest, settings, rows = self.context(db)
            unknown = db.execute("SELECT COUNT(*) FROM operations WHERE outcome='unknown'").fetchone()[0]
            backend = None
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='upload_context'").fetchone():
                row = db.execute('SELECT kind FROM upload_context WHERE id=1').fetchone()
                if row is not None:
                    if row['kind'] not in ('official-api','test-fixture'):fail('task_record_invalid')
                    backend = row['kind']
            delivered = False
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='deliveries'").fetchone():
                delivered = db.execute("SELECT 1 FROM deliveries WHERE status='confirmed'").fetchone() is not None
            return {'job_id': self.job_id, 'manifest_sha256': digest(manifest),
                    'task_spec_sha256': self.spec_digest(manifest,settings),
                    'files': [{'index': r['idx'], 'name': manifest['files'][r['idx']]['name'],
                               'size': manifest['files'][r['idx']]['size'], 'phase': r['phase'],
                               'reason':safe_reason(r['reason']) if r['reason'] is not None else None}
                              for r in rows], 'unknown_operations': unknown,
                    'cloud_backend_connected': backend == 'official-api', 'upload_backend': backend, 'delivered': delivered,
                    'delivery_evidence': 'operator-attestation' if delivered else None,
                    'source_admission': settings['source_admission'],
                    'recovery':self._recovery(db,rows,settings,backend,delivered)}

    def file_root(self, index):
        return self.root/'files'/str(index)

    def source_path(self, index, entry):
        return self.file_root(index)/entry['name']

    def next_source(self, *, downloader=None, timeout=1800):
        """Download at most one file; unfinished previous file blocks prefetch.

        downloader injection is a test/application dependency, never a manifest
        field. This stage grants no upload admission or remote write permission.
        """
        if type(timeout) not in (int, float) or not 0 < timeout <= 86400:
            fail('task_source_timeout_invalid')
        downloader = downloader or download_verified
        with self.locked() as db:
            manifest, settings, rows = self.context(db)
            pending = next((r for r in rows if r['phase'] not in ('cloud_verified', 'test_cloud_verified', 'cleaned')), None)
            if pending is None:
                return {'status': 'no_pending_source'}
            index = pending['idx']
            if pending['phase'] != 'pending':
                fail('task_source_recovery_or_upload_required')
            entry = manifest['files'][index]
            folder = self.file_root(index)
            if os.path.lexists(folder):
                private_directory(folder)
                if any(folder.iterdir()):
                    fail('task_source_workspace_exists')
            else:
                folder.mkdir(mode=0o700)
            with db:
                db.execute("UPDATE files SET phase='downloading', reason=NULL WHERE idx=?", (index,))
            try:
                path = self.source_path(index, entry)
                guard = SpaceGuard({entry['name']: entry['size']}, folder, BackendNeeds.source_only())
                guard.check('download')
                result = downloader(entry, path, settings['max_file_bytes'], space_guard=guard, timeout=timeout)
                receipt, stamp = self.verify_source(entry, path, settings['part_bytes'])
                if any(result.get(k) != receipt[k] for k in ('bytes','md5','sha256')):
                    fail('task_source_receipt_mismatch')
                with db:
                    db.execute("UPDATE files SET phase='source_verified',source_receipt=?,source_stamp=?,reason=NULL WHERE idx=?",
                               (encoded(receipt, MAX_RECEIPT), encoded(stamp), index))
                return {'status': 'source_verified', 'index': index, 'bytes': receipt['bytes']}
            except Exception as exc:
                # KeyboardInterrupt/SIGKILL leave downloading as a durable intent.
                reason = exc.code if isinstance(exc, (InputProblem, StageFailure)) else 'task_source_io_failure'
                with db:
                    db.execute("UPDATE files SET phase='source_failed', reason=? WHERE idx=?", (reason, index))
                raise

    @staticmethod
    def verify_source(entry, path, part_bytes):
        with open_regular(path) as stream:
            identity, _, stamp = source_identity(stream, lambda: None, part_bytes, entry['size'])
        if any(entry.get(k) and entry[k].lower() != identity[k] for k in ('md5','sha256')):
            fail('task_source_checksum_mismatch')
        return {'status': 'source_verified', 'file': entry['name'], **identity}, list(stamp)

    def recover_source(self, index):
        """Reuse a complete source after interruption, never repeat network blindly."""
        with self.locked() as db:
            manifest, settings, _ = self.context(db)
            row = self.file_row(db, index)
            if row['phase'] not in ('downloading', 'source_failed'):
                fail('task_source_not_recoverable')
            receipt, stamp = self.verify_source(manifest['files'][index],
                         self.source_path(index, manifest['files'][index]), settings['part_bytes'])
            with db:
                db.execute("UPDATE files SET phase='source_verified',source_receipt=?,source_stamp=?,reason=NULL WHERE idx=?",
                           (encoded(receipt, MAX_RECEIPT), encoded(stamp), index))
            return {'status': 'source_verified', 'index': index, 'network_repeated': False}

    def reset_incomplete_source(self, index):
        """Explicit local restart only; never allowed after a remote intent exists."""
        with self.locked() as db:
            manifest, _, _ = self.context(db)
            row = self.file_row(db, index)
            if (row['phase'] not in ('downloading','source_failed')
                    or db.execute('SELECT 1 FROM operations WHERE idx=?', (index,)).fetchone()):
                fail('task_source_restart_rejected')
            entry = manifest['files'][index]
            folder = self.file_root(index)
            if not os.path.lexists(folder):
                with db:
                    db.execute("UPDATE files SET phase='pending',reason=NULL WHERE idx=?", (index,))
                return {'status': 'pending', 'index': index}
            private_directory(folder)
            path = self.source_path(index, entry)
            if any(p.name != entry['name'] for p in folder.iterdir()):
                fail('task_unknown_source_files_retained')
            # A complete verified file should be recovered, not discarded.
            if os.path.lexists(path):
                private_file(path)
                if path.stat().st_size == entry['size']:
                    fail('task_complete_source_requires_inspection')
                path.unlink()
            if any(folder.iterdir()):
                fail('task_unknown_source_files_retained')
            folder.rmdir()
            with db:
                db.execute("UPDATE files SET phase='pending',reason=NULL WHERE idx=?", (index,))
            return {'status': 'pending', 'index': index}

    @staticmethod
    def file_row(db, index):
        if type(index) is not int or index < 0:
            fail('task_file_index_invalid')
        row = db.execute('SELECT * FROM files WHERE idx=?', (index,)).fetchone()
        if row is None:
            fail('task_file_index_invalid')
        return row

    def begin_operation(self, index, operation, intent, *, part=-1, _db=None):
        """Commit an intent before a backend call. Existing keys never replay.

        The caller must independently enforce scope, payload and live permission.
        This method does not invoke a backend or mark a file cloud-verified.
        """
        if (operation not in OPERATIONS or type(part) is not int
                or (operation == 'part' and not 0 <= part < 1024)
                or (operation != 'part' and part != -1)
                or type(intent) is not dict):
            fail('task_operation_invalid')
        fingerprint = digest(read_json(encoded(intent, MAX_RECEIPT)))
        with self._using_db(_db) as db:
            row = self.file_row(db, index)
            if row['phase'] not in ('source_verified','uploading'):
                fail('task_source_not_verified')
            if db.execute('SELECT 1 FROM operations WHERE idx=? AND operation=? AND part=?',
                          (index, operation, part)).fetchone():
                fail('task_operation_already_consumed')
            if db.execute("SELECT 1 FROM operations WHERE idx=? AND outcome='unknown'", (index,)).fetchone():
                fail('task_unknown_operation_requires_inspection')
            with db:
                db.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?)',
                           (index, operation, part, fingerprint, 'unknown', None, int(time.time())))
                db.execute("UPDATE files SET phase='uploading' WHERE idx=?", (index,))
        return fingerprint

    def finish_operation(self, index, operation, fingerprint, receipt, *, part=-1, _db=None):
        """Save a private receipt, not a real-cloud success assertion.

        Never persist credentials. The typed backend must restrict receipt fields
        before calling this primitive. The task summary never emits receipts.
        """
        if (operation not in OPERATIONS or type(part) is not int
                or type(fingerprint) is not str or not re.fullmatch('[0-9a-f]{64}', fingerprint)
                or type(receipt) is not dict):
            fail('task_operation_invalid')
        allowed = {'directory': {'fs_id', 'path'},
                   'precreate': {'uploadid', 'required', 'path', 'size', 'hashes', 'host', 'directory_id'},
                   'part': {'part', 'md5', 'bytes'},
                   'commit': {'fs_id', 'path', 'size'}}[operation]
        if operation == 'commit' and set(receipt) == allowed|{'md5'}:
            allowed = allowed|{'md5'}  # Legacy private receipts; new commits need no invented hash.
        if set(receipt) != allowed:
            fail('task_operation_receipt_invalid')
        with self._using_db(_db) as db:
            manifest, settings, _ = self.context(db)
            row = self.file_row(db, index)
            entry = manifest['files'][index]
            directory = '/apps/'+settings['app_name']+'/mvp-validation/'+self.job_id
            target = directory+'/'+entry['name']
            number = lambda x: type(x) is int and 0 < x < 2**63
            md5 = lambda x: type(x) is str and re.fullmatch('[0-9a-f]{32}', x)
            if 'path' in receipt and receipt['path'] != (directory if operation == 'directory' else target):
                fail('task_operation_receipt_invalid')
            if ('fs_id' in receipt and not number(receipt['fs_id'])
                    or 'size' in receipt and (type(receipt['size']) is not int or receipt['size'] != entry['size'])
                    or 'md5' in receipt and not md5(receipt['md5'])):
                fail('task_operation_receipt_invalid')
            if operation == 'part':
                expected = min(settings['part_bytes'], entry['size']-part*settings['part_bytes'])
                if (type(receipt['part']) is not int or receipt['part'] != part or expected <= 0
                        or type(receipt['bytes']) is not int or receipt['bytes'] != expected):
                    fail('task_operation_receipt_invalid')
            if operation == 'precreate':
                count = (entry['size']+settings['part_bytes']-1)//settings['part_bytes']
                if (type(receipt['uploadid']) is not str or not re.fullmatch('[A-Za-z0-9._=-]{1,4096}', receipt['uploadid'])
                        or type(receipt['required']) is not list
                        or any(type(i) is not int or not 0 <= i < count for i in receipt['required'])
                        or len(set(receipt['required'])) != len(receipt['required'])
                        or type(receipt['hashes']) is not list or len(receipt['hashes']) != count
                        or any(not md5(h) for h in receipt['hashes'])
                        or type(receipt['host']) is not str
                        or not re.fullmatch('[a-z0-9-]+(?:[.][a-z0-9-]+)*[.](?:baidu[.]com|baidupcs[.]com)', receipt['host'])
                        or not number(receipt['directory_id'])):
                    fail('task_operation_receipt_invalid')
            raw = encoded(receipt, MAX_RECEIPT)
            with db:
                cur = db.execute("UPDATE operations SET outcome='confirmed',receipt=? WHERE idx=? AND operation=? AND part=? AND intent_sha256=? AND outcome='unknown'",
                                 (raw, index, operation, part, fingerprint))
                if cur.rowcount != 1:
                    fail('task_operation_receipt_mismatch')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Private MVP tasks; source stage only, no cloud calls.')
    parser.add_argument('--tasks-dir', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create');create.add_argument('manifest', type=Path)
    create.add_argument('--max-file-bytes', type=int, default=1024**3)
    create.add_argument('--part-bytes', type=int, default=4*1024**2)
    for name in ('show','download-next','recover-source','restart-incomplete-source'):
        command = sub.add_parser(name);command.add_argument('job_id')
        if name == 'download-next':
            command.add_argument('--timeout', type=float, default=1800)
        if name in ('recover-source','restart-incomplete-source'):
            command.add_argument('--index', type=int, required=True)
    args = parser.parse_args(argv)
    samples = None
    try:
        if args.command == 'create':
            task = Task.create(args.tasks_dir, load_manifest(args.manifest),
                               max_file_bytes=args.max_file_bytes, part_bytes=args.part_bytes)
            result = task.view()
        else:
            task = Task(args.tasks_dir, args.job_id)
            if args.command == 'show':result = task.view()
            elif args.command == 'download-next':
                with ResourceSamples(task.root) as samples:
                    result = task.next_source(timeout=args.timeout)
                result['resource_samples'] = samples.summary()
            elif args.command == 'recover-source':result = task.recover_source(args.index)
            else:result = task.reset_incomplete_source(args.index)
        print(json.dumps(result, sort_keys=True));return 0
    except InputProblem as exc:
        print(json.dumps({'status':exc.status,'reason':exc.code,
                          'resource_samples':samples.summary() if samples is not None else None}));return 2
    except Exception:
        print(json.dumps({'status':'manual_review','reason':'task_local_failure',
                          'resource_samples':samples.summary() if samples is not None else None}));return 2


if __name__ == '__main__':
    sys.exit(main())

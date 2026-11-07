"""Fake-only, one-attempt isolated non-overwrite policy candidate.

This is not live authorization or proof of server atomicity. Local job-directory
exclusivity belongs to the existing M3 runner, not this in-memory adapter.
"""
import time
from functools import wraps
from pathlib import PurePosixPath

from .baidu_http import fail
from .upload_stage import StageFailure
from .baidu_protocol import BaiduProtocol, METAS


def mutation(expected, success):
    def decorate(method):
        @wraps(method)
        def once(self, *args):
            self.checkpoint()
            if self.phase not in expected or self.busy:
                self.phase = 'failed'
                fail('candidate_replay_rejected')
            self.busy = True
            self.write_attempted = False
            try:
                result = method(self, *args)
                self.phase = success
                return result
            except BaseException as exc:
                self.uncertain_objects |= self.write_attempted
                self.phase = 'failed'
                if isinstance(exc, Exception) and not isinstance(exc, StageFailure):
                    fail('http_io_failure')
                raise
            finally:
                self.busy = False
        return once
    return decorate


def new_candidate_job_id():
    # Randomness reduces accidental collisions; exclusive mkdir remains decisive.
    from uuid import uuid4
    return 'job-'+uuid4().hex


class IsolatedBaiduCandidate(BaiduProtocol):
    """rtype=0 directory, rtype=1 file; fail terminally and retain all objects."""
    def __init__(self, client, app_name, target, expected_account_sha256, limits):
        if client.mode != 'fake-http':
            fail('candidate_fake_only')
        super().__init__(client, app_name, target, expected_account_sha256, limits,
                         diagnostic_rename_policy=True)
        self.phase, self.busy = 'new', False
        self.deadline = time.monotonic()+900
        self.directory = str(PurePosixPath(target).parent)
        self.directory_id = None
        self.write_attempted = self.uncertain_objects = False
        self.commit_attempted = False

    def checkpoint(self):
        try:
            super().checkpoint()
        except BaseException:
            self.phase = 'failed'
            raise
        if self.phase == 'failed':
            fail('candidate_terminal')
        if time.monotonic() >= self.deadline:
            self.phase = 'failed'
            fail('candidate_expired')

    def request(self, method, url, params, form=None, **kwargs):
        if method == 'POST':
            self.write_attempted = True
        obj = super().request(method, url, params, form, **kwargs)
        if method == 'POST' and form and form.get('isdir') == 1:
            if type(obj.get('fs_id')) is not int or obj['fs_id'] <= 0:
                fail('protocol_shape_invalid')
            self.directory_id = obj['fs_id']
        return obj

    def verify_directory(self):
        import json
        obj = self.request('GET', METAS, {'method': 'filemetas',
                                        'fsids': json.dumps([self.directory_id])})
        rows = obj.get('list')
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            fail('protocol_shape_invalid')
        row = rows[0]
        if (type(row.get('errno', 0)) is not int or row.get('errno', 0) != 0
                or type(row.get('fs_id')) is not int or row['fs_id'] != self.directory_id
                or row.get('path') != self.directory or type(row.get('isdir')) is not int or row['isdir'] != 1):
            fail('protocol_path_changed')

    @mutation(('new',), 'reserved')
    def reserve_new(self, path):
        super().reserve_new(path)
        self.verify_directory()

    @mutation(('reserved',), 'uploading')
    def begin_new(self, path, size, hashes):
        self.verify_directory()
        return super().begin_new(path, size, hashes)

    @mutation(('uploading',), 'uploading')
    def put_part(self, session, index, data):
        return super().put_part(session, index, data)

    @mutation(('uploading',), 'committed')
    def commit_new(self, session):
        self.verify_directory()
        self.commit_attempted = True
        return super().commit_new(session)

    def evidence(self):
        return {'policy': 'isolated-rename-reject-candidate', 'phase': self.phase,
                'commit_attempted': self.commit_attempted,
                'uncertain_objects_retained': self.uncertain_objects,
                'automatic_write_retry': False, 'automatic_delete': False,
                'cloud_verified': False, 'delivery_eligible': False}

"""Official REST bindings, dependency-injected HTTP. Strict live writes stay closed."""
import hashlib
import json
import os
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .baidu_http import HTTPRequest, JSON_LIMIT, destination, response_headers, fail
from .upload_stage import TransferLimits

FILE = 'https://pan.baidu.com/rest/2.0/xpan/file'
NAS = 'https://pan.baidu.com/rest/2.0/xpan/nas'
METAS = 'https://pan.baidu.com/rest/2.0/xpan/multimedia'
QUOTA = 'https://pan.baidu.com/api/quota'
LOCATE = 'https://d.pcs.baidu.com/rest/2.0/pcs/file'


@dataclass(repr=False)
class UploadSession:
    path: str
    size: int
    hashes: tuple
    uploadid: str
    host: str
    required: tuple
    confirmed: dict = field(default_factory=dict)
    committed: bool = False


class BaiduProtocol:
    """Full protocol in fake-HTTP diagnostics; no undocumented precreate rtype=0.

    diagnostic_rename_policy is accepted ONLY with a fake-http client. It uses
    documented rtype=1 consistently and rejects any server path change. It is
    not the strict conflict-fail guarantee required for real MVP admission.
    """
    def __init__(self, client, app_name, target, expected_account_sha256, limits,
                 *, diagnostic_rename_policy=False):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', app_name):
            fail('protocol_shape_invalid')
        pattern = re.escape('/apps/'+app_name+'/mvp-validation/')+r'[a-z0-9][a-z0-9-]{0,63}/[A-Za-z0-9][A-Za-z0-9._-]{0,179}'
        if not re.fullmatch(pattern, target) or not re.fullmatch(r'[0-9a-f]{64}', expected_account_sha256):
            fail('protocol_shape_invalid')
        if diagnostic_rename_policy and client.mode != 'fake-http':
            fail('protocol_strict_conflict_unproven')
        if not isinstance(limits, TransferLimits):
            fail('protocol_account_limits_unknown')
        self.client, self.app_name, self.target = client, app_name, target
        self.account, self.limits = expected_account_sha256, limits
        self.diagnostic = diagnostic_rename_policy
        self.mode = 'simulation' if client.mode == 'fake-http' else 'http-live-locked'
        self.context, self.facts, self.reserved, self.closed = None, None, False, False
        self.sessions, self.objects = [], {}
        self.session_bindings = {}
        self.confirmations, self.committed = {}, set()

    def attach(self, context):
        self.context = context

    def checkpoint(self):
        if self.closed:
            fail('http_stopped')
        if self.context is not None:
            self.context.checkpoint()

    def request(self, method, url, params, form=None, *, body=None, content_type=None, purpose='control'):
        self.checkpoint()
        if form is not None:
            body = urllib.parse.urlencode(form).encode()
        req = HTTPRequest(method, url, self.target, purpose, params, body or b'',
                          content_type or 'application/x-www-form-urlencoded')
        req.validate()
        reply = self.client.exchange(req)
        try:
            self.checkpoint()
            if reply.status in (301, 302, 303, 307, 308):
                fail('http_redirect_rejected')
            if reply.status != 200:
                fail('http_status_rejected')
            length = response_headers(reply)
            if length is not None and length > JSON_LIMIT:
                fail('http_limit_exceeded')
            raw = b''.join(reply.chunks(JSON_LIMIT, min(65536, JSON_LIMIT)))
            def unique(pairs):
                out = {}
                for key, value in pairs:
                    if key in out: fail('protocol_json_invalid')
                    out[key] = value
                return out
            obj = json.loads(raw, object_pairs_hook=unique)
            if not isinstance(obj, dict):
                fail('protocol_json_invalid')
            if 'errno' not in obj:
                if purpose != 'upload' or not isinstance(obj.get('md5'), str) or not re.fullmatch(r'[0-9a-f]{32}', obj['md5']):
                    fail('protocol_json_invalid')
            elif type(obj['errno']) is not int or obj['errno'] != 0:
                fail('protocol_conflict' if obj.get('errno') == -8 else 'protocol_api_error')
            if 'error_code' in obj and (type(obj['error_code']) is not int or obj['error_code'] != 0):
                fail('protocol_api_error')
            return obj
        except (ValueError, UnicodeError):
            fail('protocol_json_invalid')
        finally:
            reply.close()

    def probe(self):
        user = self.request('GET', NAS, {'method': 'uinfo', 'vip_version': 'v2'})
        if type(user.get('uk')) is not int or user['uk'] <= 0:
            fail('protocol_shape_invalid')
        fingerprint = hashlib.sha256(str(user['uk']).encode()).hexdigest()
        if fingerprint != self.account:
            fail('protocol_identity_mismatch')
        vip = user.get('vip_type')
        if type(vip) is not int or vip not in (0, 1, 2):
            fail('protocol_account_limits_unknown')
        quota = self.request('GET', QUOTA, {'checkfree': 1, 'checkexpire': 1})
        if (any(type(quota.get(k)) is not int or quota[k] < 0 for k in ('total', 'used'))
                or quota['used'] > quota['total'] or quota.get('expire') is not False):
            fail('protocol_account_limits_unknown')
        # Documentation-derived ceilings, NOT an entitlement/permission probe.
        file_gb, part_mb = ((4, 4), (10, 16), (20, 32))[vip]
        self.facts = {'account_sha256': fingerprint, 'vip_type': vip,
                      'quota_available': quota['total']-quota['used'],
                      'documented_file_bytes': file_gb*1000**3,
                      'documented_part_bytes': part_mb*1000**2,
                      'limits_basis': 'public-docs-conservative-decimal-not-live',
                      'upload_permission': 'unverified', 'live_verified': False}
        return dict(self.facts)

    def write_gate(self):
        self.checkpoint()
        if not self.diagnostic or self.client.mode != 'fake-http':
            fail('protocol_strict_conflict_unproven')
        if self.facts is None:
            self.probe()

    def reserve_new(self, path):
        self.write_gate()
        if path != str(PurePosixPath(self.target).parent) or self.reserved:
            fail('protocol_path_changed')
        obj = self.request('POST', FILE, {'method': 'create'}, {'path': path, 'isdir': 1, 'rtype': 0})
        if obj.get('path') != path or type(obj.get('isdir')) is not int or obj['isdir'] != 1:
            fail('protocol_path_changed')
        self.reserved = True

    def begin_new(self, path, size, hashes):
        self.write_gate()
        if type(size) is not int or size <= 0 or not isinstance(hashes, (list, tuple)):
            fail('protocol_shape_invalid')
        self.limits.validate(size)
        if not self.reserved or path != self.target or self.sessions:
            fail('protocol_not_ready')
        if (size > self.facts['quota_available'] or size > self.facts['documented_file_bytes']):
            fail('protocol_quota_insufficient')
        if (self.limits.part_bytes < 4*1024**2
                or min(size, self.limits.part_bytes) > self.facts['documented_part_bytes']):
            fail('protocol_account_limits_unknown')
        count = (size+self.limits.part_bytes-1)//self.limits.part_bytes
        if len(hashes) != count or any(not isinstance(h, str) or not re.fullmatch(r'[0-9a-f]{32}', h) for h in hashes):
            fail('protocol_shape_invalid')
        obj = self.request('POST', FILE, {'method': 'precreate'},
                           {'path': path, 'size': size, 'isdir': 0, 'autoinit': 1, 'rtype': 1,
                            'block_list': json.dumps(hashes, separators=(',', ':'))})
        required = obj.get('block_list')
        if required == [] and count == 1:
            required = [0]  # Explicit special case on the official precreate page.
        if obj.get('path') != path:
            fail('protocol_path_changed')
        if (type(obj.get('return_type')) is not int or obj['return_type'] != 1
                or not isinstance(obj.get('uploadid'), str) or not 1 <= len(obj['uploadid']) <= 512
                or not isinstance(required, list) or any(type(i) is not int or not 0 <= i < count for i in required)
                or len(set(required)) != len(required)):
            fail('protocol_shape_invalid')
        located = self.request('GET', LOCATE, {'method': 'locateupload', 'appid': 250528,
                                              'path': path, 'uploadid': obj['uploadid'], 'upload_version': '2.0'})
        servers = located.get('servers')
        if not isinstance(servers, list) or not servers or not isinstance(servers[0], dict):
            fail('protocol_shape_invalid')
        host = servers[0].get('server')
        u = destination(host, 'readback')
        if u.path not in ('', '/') or u.query:
            fail('http_url_rejected')
        session = UploadSession(path, size, tuple(hashes), obj['uploadid'],
                                urllib.parse.urlunsplit(('https', u.netloc, '', '', '')), tuple(required))
        self.sessions.append(session)
        self.confirmations[id(session)] = {}
        self.session_bindings[id(session)] = (path, size, session.hashes, session.uploadid, session.host, session.required)
        return session

    def required_parts(self, session):
        self.session(session)
        return session.required

    def session(self, session):
        if not any(s is session for s in self.sessions) or id(session) in self.committed or session.committed:
            fail('protocol_session_invalid')
        if self.session_bindings[id(session)] != (session.path, session.size, session.hashes, session.uploadid, session.host, session.required):
            fail('protocol_session_invalid')

    def put_part(self, session, index, data):
        self.write_gate(); self.session(session)
        if type(index) is not int or index not in session.required or index in self.confirmations[id(session)]:
            fail('protocol_part_mismatch')
        expected = min(self.limits.part_bytes, session.size-index*self.limits.part_bytes)
        if type(data) is not bytes or len(data) != expected or hashlib.md5(data).hexdigest() != session.hashes[index]:
            fail('protocol_part_mismatch')
        boundary = 'fasttransfer-'+os.urandom(16).hex()
        body = (('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="part"\r\n'
                 'Content-Type: application/octet-stream\r\n\r\n').encode()+data+('\r\n--'+boundary+'--\r\n').encode())
        obj = self.request('POST', session.host+'/rest/2.0/pcs/superfile2',
                           {'method': 'upload', 'type': 'tmpfile', 'path': session.path,
                            'uploadid': session.uploadid, 'partseq': index}, body=body,
                           content_type='multipart/form-data; boundary='+boundary, purpose='upload')
        if obj.get('md5') != session.hashes[index]:
            fail('protocol_part_mismatch')
        self.confirmations[id(session)][index] = obj['md5']
        return obj['md5']

    def commit_new(self, session):
        self.write_gate(); self.session(session)
        if set(self.confirmations[id(session)]) != set(session.required):
            fail('protocol_part_mismatch')
        obj = self.request('POST', FILE, {'method': 'create'},
                           {'path': session.path, 'size': session.size, 'isdir': 0, 'rtype': 1,
                            'is_revision': 0, 'uploadid': session.uploadid,
                            'block_list': json.dumps(session.hashes, separators=(',', ':'))})
        if (obj.get('path') != session.path or type(obj.get('size')) is not int or obj['size'] != session.size
                or type(obj.get('fs_id')) is not int or obj['fs_id'] <= 0
                or type(obj.get('isdir')) is not int or obj['isdir'] != 0):
            fail('protocol_path_changed')
        session.committed = True
        self.committed.add(id(session))
        self.objects[session.path] = (obj['fs_id'], session.size)

    def metadata(self, path):
        if path not in self.objects:
            fail('protocol_not_ready')
        fs_id, size = self.objects[path]
        obj = self.request('GET', METAS, {'method': 'filemetas', 'fsids': json.dumps([fs_id]), 'dlink': 1})
        rows = obj.get('list')
        if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
                or type(rows[0].get('errno', 0)) is not int or rows[0].get('errno', 0) != 0 or rows[0].get('path') != path
                or type(rows[0].get('size')) is not int or rows[0]['size'] != size
                or type(rows[0].get('fs_id')) is not int or rows[0]['fs_id'] != fs_id
                or type(rows[0].get('isdir')) is not int or rows[0]['isdir'] != 0):
            fail('protocol_shape_invalid')
        destination(rows[0].get('dlink'), 'readback')
        return {'size': size, 'dlink': rows[0]['dlink']}

    def readback(self, path, chunk_bytes):
        if type(chunk_bytes) is not int or not 1 <= chunk_bytes <= 1024**2:
            fail('http_limit_exceeded')
        meta = self.metadata(path)
        url, seen, auth = meta['dlink'], set(), True
        for hop in range(4):
            self.checkpoint(); destination(url, 'readback')
            if url in seen: fail('http_redirect_rejected')
            seen.add(url)
            req = HTTPRequest('GET', url, self.target, 'readback', auth=auth)
            req.validate()
            reply = self.client.exchange(req)
            try:
                if reply.status in (301, 302, 303, 307, 308):
                    location = reply.header('location')
                    if (hop == 3 or not isinstance(location, str) or len(location) > 8192
                            or any(ord(c) <= 32 or ord(c) >= 127 for c in location) or '\\' in location):
                        fail('http_redirect_rejected')
                    url = urllib.parse.urljoin(url, location)  # Unauthenticated base: never forward a token.
                    destination(url, 'readback'); auth = False
                    continue
                if reply.status != 200: fail('http_status_rejected')
                length = response_headers(reply)
                if length is not None and length != meta['size']: fail('protocol_readback_mismatch')
                total = 0
                for data in reply.chunks(meta['size'], chunk_bytes):
                    self.checkpoint(); total += len(data)
                    yield data
                if total != meta['size']: fail('protocol_readback_mismatch')
                return
            finally:
                reply.close()
        fail('http_redirect_rejected')

    def stop(self):
        self.closed = True
        try:
            return self.client.stop() is True
        except Exception:
            return False

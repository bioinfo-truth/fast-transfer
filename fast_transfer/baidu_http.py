"""Bounded HTTPS channel. Runtime gate defaults closed; no credential discovery."""
import ipaddress
import socket
import time
import urllib.parse
from dataclasses import dataclass, field

from .safe_http import PinnedHTTPSConnection, public_addresses
from .upload_stage import StageFailure

IO_TIMEOUT = 30
REQUEST_BUDGET = 120
JSON_LIMIT = 256 * 1024
PART_LIMIT = 32 * 1024**2
AUTH_SLOT = object()  # Fake clients see this symbol, never a credential value.


def fail(code):
    raise StageFailure(code) from None


def destination(url, purpose):
    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) <= 32 or ord(c) >= 127 for c in url) or '\\' in url:
        fail('http_url_rejected')
    try:
        u = urllib.parse.urlsplit(url)
        if u.scheme != 'https' or not u.hostname or u.username is not None or u.password is not None or u.fragment or u.port not in (None, 443):
            fail('http_url_rejected')
        host = u.hostname
        if not host.endswith(('.baidu.com', '.baidupcs.com')) or host.endswith('.') or '%' in host:
            fail('http_url_rejected')
        keys = [k.casefold() for k, _ in urllib.parse.parse_qsl(u.query, keep_blank_values=True)]
        if any(k in ('access_token', 'refresh_token', 'cookie', 'bduss', 'authorization', 'client_secret', 'password', 'token') for k in keys):
            fail('http_url_rejected')
        if purpose == 'control':
            allowed = {('pan.baidu.com', '/rest/2.0/xpan/file'), ('pan.baidu.com', '/rest/2.0/xpan/nas'),
                       ('pan.baidu.com', '/rest/2.0/xpan/multimedia'), ('pan.baidu.com', '/api/quota'),
                       ('d.pcs.baidu.com', '/rest/2.0/pcs/file')}
            if (host, u.path) not in allowed or u.query:
                fail('http_url_rejected')
        elif purpose == 'upload':
            if u.path != '/rest/2.0/pcs/superfile2' or u.query:
                fail('http_url_rejected')
        elif purpose != 'readback':
            fail('http_url_rejected')
        return u
    except ValueError:
        fail('http_url_rejected')


@dataclass(frozen=True, repr=False)
class HTTPRequest:
    method: str
    url: str
    binding: str
    purpose: str = 'control'
    params: dict = field(default_factory=dict)
    body: bytes = b''
    content_type: str = 'application/x-www-form-urlencoded'
    auth: bool = True

    def validate(self):
        import re
        if any(type(x) is not str for x in (self.method, self.url, self.binding, self.purpose, self.content_type)) or type(self.auth) is not bool:
            fail('http_header_rejected')
        u = destination(self.url, self.purpose)
        if self.method not in ('GET', 'POST') or type(self.body) is not bytes or len(self.body) > PART_LIMIT+4096:
            fail('http_limit_exceeded')
        if self.content_type != 'application/x-www-form-urlencoded' and not re.fullmatch(r'multipart/form-data; boundary=fasttransfer-[0-9a-f]{32}', self.content_type):
            fail('http_header_rejected')
        if self.purpose != 'upload' and len(self.body) > JSON_LIMIT:
            fail('http_limit_exceeded')
        if not isinstance(self.params, dict) or any(type(k) is not str or type(v) not in (str, int) for k, v in self.params.items()):
            fail('http_url_rejected')
        if self.purpose != 'readback' and not self.auth:
            fail('http_auth_missing')
        if any(k.casefold() in ('access_token', 'refresh_token', 'cookie', 'bduss', 'client_secret') for k in self.params):
            fail('http_url_rejected')
        if self.method == 'GET' and self.body:
            fail('http_header_rejected')
        if self.purpose == 'control':
            methods = {'/rest/2.0/xpan/file': ('meta', 'create', 'precreate'),
                       '/rest/2.0/xpan/nas': ('uinfo',), '/rest/2.0/xpan/multimedia': ('filemetas',),
                       '/rest/2.0/pcs/file': ('locateupload',), '/api/quota': (None,)}
            method = self.params.get('method')
            if method not in methods[u.path] or (self.method == 'POST') != (method in ('precreate', 'create')):
                fail('http_url_rejected')
        elif self.purpose == 'upload':
            if self.method != 'POST' or self.params.get('method') != 'upload' or self.params.get('type') != 'tmpfile':
                fail('http_url_rejected')
        elif self.method != 'GET' or self.params:
            fail('http_url_rejected')
        if 'path' in self.params and self.params['path'] != self.binding:
            fail('http_scope_invalid')


@dataclass(frozen=True)
class RuntimeGrant:
    enabled: bool = False
    target: str = ''
    account_sha256: str = ''
    source_sha256: str = ''
    approval_ref: str = ''
    expires_monotonic: float = 0

    def check(self, binding):
        import re
        if self.enabled is not True:
            fail('http_runtime_locked')
        if (any(type(x) is not str for x in (binding, self.target, self.account_sha256, self.source_sha256, self.approval_ref))
                or type(self.expires_monotonic) not in (int, float)):
            fail('http_scope_invalid')
        if (binding != self.target or not re.fullmatch(r'/apps/[A-Za-z][A-Za-z0-9_-]{0,63}/mvp-validation/[a-z0-9][a-z0-9-]{0,63}/[A-Za-z0-9][A-Za-z0-9._-]{0,179}', self.target)
                or not re.fullmatch(r'[0-9a-f]{64}', self.account_sha256)
                or not re.fullmatch(r'[0-9a-f]{64}', self.source_sha256) or not re.fullmatch(r'[A-Za-z0-9:_-]{1,128}', self.approval_ref)
                or not 0 < self.expires_monotonic-time.monotonic() <= 900):
            fail('http_scope_invalid')


class HTTPReply:
    """Owns only this request's connection; never logs headers/URLs."""
    def __init__(self, status, headers, reader, close, deadline):
        self.status, self.headers, self.reader = status, headers, reader
        self._close, self.deadline, self.closed = close, deadline, False

    def values(self, name):
        return [v for k, v in self.headers if k.lower() == name]

    def header(self, name):
        values = self.values(name)
        if len(values) > 1:
            fail('http_header_rejected')
        return values[0] if values else None

    def chunks(self, limit, chunk_bytes):
        if type(limit) is not int or limit < 0 or type(chunk_bytes) is not int or not 1 <= chunk_bytes <= 1024**2:
            self.close()
            fail('http_limit_exceeded')
        total = 0
        try:
            while True:
                if self.closed:
                    fail('http_stopped')
                if time.monotonic() >= self.deadline:
                    fail('http_deadline')
                data = self.reader(min(chunk_bytes, limit-total+1))
                if self.closed or time.monotonic() >= self.deadline:
                    fail('http_deadline')
                if not data:
                    break
                if type(data) is not bytes or len(data) > chunk_bytes:
                    fail('http_limit_exceeded')
                total += len(data)
                if total > limit:
                    fail('http_limit_exceeded')
                yield data
        except StageFailure:
            raise
        except Exception:
            fail('http_io_failure')
        finally:
            self.close()

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self._close()
            except Exception:
                fail('http_io_failure')


def response_headers(reply):
    length = reply.header('content-length')
    if length is not None and (len(length) > 20 or not length.isascii() or not length.isdigit()):
        fail('http_header_rejected')
    if length is not None and reply.header('transfer-encoding'):
        fail('http_header_rejected')
    if reply.header('content-encoding') not in (None, 'identity'):
        fail('http_header_rejected')
    return None if length is None else int(length)


class PinnedBaiduHTTPClient:
    mode = 'live-http-locked'

    def __init__(self, *, grant=None, credential_provider=None,
                 resolver=public_addresses, connection_factory=PinnedHTTPSConnection):
        self.grant = grant or RuntimeGrant()
        self.provider, self.resolver, self.factory = credential_provider, resolver, connection_factory
        self.active, self.reply, self.stopped = None, None, False
        self._credential = None
        self._close_failed = False

    def _discard(self, response, connection):
        for resource in (response, connection):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    self._close_failed = True
        self.active, self.reply = None, None

    def exchange(self, req):
        # Gate BEFORE credential callback, DNS or connection construction.
        self.grant.check(req.binding)
        if self.stopped:
            fail('http_stopped')
        req.validate()
        if req.method != 'GET' or req.purpose == 'upload':
            # Precreate does not document conflict-fail 0 consistently with create.
            # No live write is enabled merely by opening the authorization gate.
            fail('protocol_strict_conflict_unproven')
        u = destination(req.url, req.purpose)
        if self.active is not None:
            fail('http_concurrent_request')
        connection = response = None
        try:
            params = dict(req.params)
            if req.auth:
                if self._credential is None:
                    if self.provider is None:
                        fail('http_auth_missing')
                    credential = self.provider()
                    if not isinstance(credential, str) or not credential or len(credential) > 4096:
                        fail('http_auth_missing')
                    self._credential = credential
                params['access_token'] = self._credential
            addresses = self.resolver(u.hostname)
            if not addresses or any(not ipaddress.ip_address(x).is_global or ipaddress.ip_address(x).is_multicast for x in addresses):
                fail('http_url_rejected')
            self.grant.check(req.binding)
            if self.stopped:
                fail('http_stopped')
            connection = self.factory(u.hostname, addresses[0], IO_TIMEOUT)
            if hasattr(connection, 'set_debuglevel'):
                connection.set_debuglevel(0)
            deadline = min(time.monotonic()+REQUEST_BUDGET, self.grant.expires_monotonic)
            query = u.query
            if params:
                query += ('&' if query else '')+urllib.parse.urlencode(params)
            path = urllib.parse.urlunsplit(('', '', u.path or '/', query, ''))
            if len(path.encode()) > 16384:
                fail('http_limit_exceeded')
            self.active = connection
            connection.request(req.method, path, body=req.body or None,
                               headers={'User-Agent': 'pan.baidu.com', 'Accept-Encoding': 'identity',
                                        'Content-Type': req.content_type})
            response = connection.getresponse()
            def close():
                try:
                    try:
                        response.close()
                    finally:
                        connection.close()
                except Exception:
                    self._close_failed = True
                    raise
                finally:
                    if self.active is connection:
                        self.active = None
                        self.reply = None
            def read(n):
                if self.stopped:
                    fail('http_stopped')
                if connection.sock:
                    connection.sock.settimeout(min(IO_TIMEOUT, max(.001, deadline-time.monotonic())))
                return response.read1(n)
            reply = HTTPReply(response.status, response.getheaders(), read, close, deadline)
            self.reply = reply
            response_headers(reply)
            return reply
        except StageFailure:
            self._discard(response, connection)
            raise
        except Exception:
            self._discard(response, connection)
            fail('http_io_failure')

    def stop(self):
        self.stopped = True
        self._credential = None  # Release this job's reference; not a secure-erasure claim.
        connection, self.active = self.active, None
        if connection is not None:
            try:
                if connection.sock:
                    connection.sock.shutdown(socket.SHUT_RDWR)
            finally:
                if self.reply is not None:
                    self.reply.close()
                else:
                    connection.close()
        self.reply = None
        return not self._close_failed

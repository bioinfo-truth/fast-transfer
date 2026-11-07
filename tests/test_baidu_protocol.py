import hashlib
import io
import json
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import Mock, patch

from fast_transfer.baidu_http import (AUTH_SLOT, HTTPReply, HTTPRequest, PinnedBaiduHTTPClient,
                                     RuntimeGrant, destination, IO_TIMEOUT, JSON_LIMIT)
from fast_transfer.baidu_protocol import BaiduProtocol, FILE
from fast_transfer.space import BackendNeeds
from fast_transfer.upload_stage import TransferLimits, StageFailure, run_simulated_upload

TARGET = '/apps/Xtransfer/mvp-validation/job-http/test.fna'
ACCOUNT = hashlib.sha256(b'42').hexdigest()
LIMITS = TransferLimits(4*1024**2, 16*1024**2, 1024)


def reply(data, status=200, headers=()):
    stream = io.BytesIO(data)
    return HTTPReply(status, list(headers), stream.read1, stream.close, time.monotonic()+120)


class FakeHTTP:
    mode = 'fake-http'

    def __init__(self, data=b'ACGTACGT'):
        self.data, self.calls, self.symbolic_auth, self.replies = data, [], [], []
        self.fault = None
        self.redirects, self.required = [], None
        self.stopped = False

    def exchange(self, req):
        req.validate()
        if self.stopped: raise StageFailure('http_stopped')
        self.calls.append(req)
        params = dict(req.params)
        if req.auth: params['access_token'] = AUTH_SLOT
        self.symbolic_auth.append(params)
        form = dict(urllib.parse.parse_qsl(req.body.decode())) if req.purpose == 'control' else {}
        method = params.get('method')
        if req.purpose == 'readback':
            if self.redirects:
                status, headers, data = self.redirects.pop(0)
                out = reply(data, status, headers)
            else: out = reply(self.data, headers=[('Content-Length', str(len(self.data)))])
            self.replies.append(out); return out
        if method == 'uinfo': obj = {'errno': 0, 'uk': 42, 'vip_type': 2}
        elif req.url.endswith('/api/quota'): obj = {'errno': 0, 'total': 100_000_000_000, 'used': 0, 'free': 0, 'expire': False}
        elif method == 'create' and form['isdir'] == '1': obj = {'errno': 0, 'path': form['path'], 'isdir': 1, 'fs_id': 7}
        elif method == 'precreate':
            blocks = json.loads(form['block_list'])
            obj = {'errno': 0, 'path': form['path'], 'uploadid': 'fixture-session', 'return_type': 1,
                   'block_list': list(range(len(blocks))) if self.required is None else self.required}
        elif method == 'locateupload': obj = {'errno': 0, 'servers': [{'server': 'https://c.pcs.baidu.com'}]}
        elif req.purpose == 'upload':
            data = req.body.split(b'\r\n\r\n', 1)[1].rsplit(b'\r\n--', 1)[0]
            obj = {'md5': hashlib.md5(data).hexdigest()}  # Part success need not include errno.
        elif method == 'create': obj = {'errno': 0, 'path': form['path'], 'size': int(form['size']), 'isdir': 0, 'fs_id': 9}
        elif method == 'filemetas': obj = {'errno': 0, 'list': [{'fs_id': 9, 'size': len(self.data), 'isdir': 0,
                                                               'path': TARGET, 'dlink': 'https://d.pcs.baidu.com/data?sign=fixture'}]}
        else: raise AssertionError('Unexpected protocol operation')
        if self.fault: obj = self.fault(req, obj)
        raw = obj if type(obj) is bytes else json.dumps(obj).encode()
        out = reply(raw); self.replies.append(out); return out

    def stop(self):
        self.stopped = True
        for out in self.replies: out.close()
        return True


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.http = FakeHTTP()
        self.transport = BaiduProtocol(self.http, 'Xtransfer', TARGET, ACCOUNT, LIMITS,
                                       diagnostic_rename_policy=True)
        self.network = patch('socket.create_connection', side_effect=AssertionError('No real requests'))
        self.network_mock = self.network.start()
        self.addCleanup(self.network.stop)
        self.addCleanup(lambda: self.network_mock.assert_not_called())

    def begin(self):
        self.transport.reserve_new(str(Path(TARGET).parent))
        data = self.http.data
        blocks = tuple(hashlib.md5(data[i:i+LIMITS.part_bytes]).hexdigest() for i in range(0, len(data), LIMITS.part_bytes))
        return self.transport.begin_new(TARGET, len(data), blocks)

    def commit(self):
        session = self.begin()
        for i in session.required:
            self.transport.put_part(session, i, self.http.data[i*LIMITS.part_bytes:(i+1)*LIMITS.part_bytes])
        self.transport.commit_new(session)
        return session

    def test_documented_sequence_encoding_and_full_stream(self):
        self.commit()
        self.assertEqual(b''.join(self.transport.readback(TARGET, 3)), self.http.data)
        forms = [(r.params.get('method'), dict(urllib.parse.parse_qsl(r.body.decode())))
                 for r in self.http.calls if r.purpose == 'control' and r.method == 'POST']
        self.assertEqual([f.get('rtype') for _, f in forms], ['0', '1', '1'])
        self.assertEqual(forms[-1][1]['is_revision'], '0')
        self.assertEqual(forms[1][1]['block_list'], forms[-1][1]['block_list'])
        self.assertTrue(all(p.get('access_token') is AUTH_SLOT for p in self.http.symbolic_auth))
        upload = next(r for r in self.http.calls if r.purpose == 'upload')
        self.assertEqual(upload.url, 'https://c.pcs.baidu.com/rest/2.0/pcs/superfile2')
        self.assertEqual(upload.params['partseq'], 0)
        self.assertNotIn('fixture-session', repr(upload))
        self.assertTrue(all(r.closed for r in self.http.replies))

    def test_strict_default_does_not_assume_precreate_supports_conflict_fail(self):
        strict = BaiduProtocol(self.http, 'Xtransfer', TARGET, ACCOUNT, LIMITS)
        with self.assertRaisesRegex(StageFailure, 'strict_conflict_unproven'):
            strict.reserve_new(str(Path(TARGET).parent))
        self.assertEqual(self.http.calls, [])
        with self.assertRaises(StageFailure):
            BaiduProtocol(PinnedBaiduHTTPClient(), 'Xtransfer', TARGET, ACCOUNT, LIMITS,
                          diagnostic_rename_policy=True)

    def test_identity_unknown_tier_quota_and_permission_are_not_guessed(self):
        self.http.fault = lambda req, obj: {**obj, 'uk': 99} if req.params.get('method') == 'uinfo' else obj
        with self.assertRaisesRegex(StageFailure, 'identity_mismatch'): self.transport.probe()
        self.http.fault = lambda req, obj: {**obj, 'vip_type': 3} if req.params.get('method') == 'uinfo' else obj
        with self.assertRaisesRegex(StageFailure, 'limits_unknown'): self.transport.probe()
        self.http.fault = None
        facts = self.transport.probe()
        self.assertFalse(facts['live_verified'])
        self.assertEqual(facts['upload_permission'], 'unverified')
        self.assertEqual(facts['quota_available'], 100_000_000_000)
        self.http.fault = lambda req, obj: {**obj, 'total': 10, 'used': 9, 'free': 10**15} if req.url.endswith('/api/quota') else obj
        self.transport.probe()
        with self.assertRaisesRegex(StageFailure, 'quota_insufficient'): self.begin()

    def test_errno_missing_boolean_duplicate_json_and_raw_errors_are_rejected(self):
        for raw in (b'{"errno":-8,"errno":0}', b'{"errno":false}', b'{"message":"SECRET"}', b'not-json SECRET'):
            self.http.fault = lambda req, obj: raw
            with self.assertRaises(StageFailure) as caught: self.transport.probe()
            self.assertNotIn('SECRET', str(caught.exception))

    def test_response_bytes_are_bounded_and_redirects_not_followed_for_control(self):
        self.http.fault = lambda req, obj: b'X'*(JSON_LIMIT+1)
        with self.assertRaisesRegex(StageFailure, 'limit_exceeded'): self.transport.probe()
        self.assertTrue(self.http.replies[-1].closed)
        class Redirect(FakeHTTP):
            def exchange(self, req): return reply(b'', 302, [('Location', 'https://evil.example/')])
        t = BaiduProtocol(Redirect(), 'Xtransfer', TARGET, ACCOUNT, LIMITS)
        with self.assertRaisesRegex(StageFailure, 'redirect_rejected'): t.probe()

    def test_precreate_indices_and_empty_single_block_special_case(self):
        for required in ([True], [1], [0, 0], '0'):
            self.http.required = required
            self.transport.reserved = False; self.transport.sessions = []
            with self.assertRaisesRegex(StageFailure, 'shape_invalid'): self.begin()
        self.http.required = []; self.transport.reserved = False
        self.assertEqual(self.begin().required, (0,))

    def test_incomplete_parts_duplicate_parts_and_session_tampering_stop_commit(self):
        s = self.begin()
        with self.assertRaisesRegex(StageFailure, 'part_mismatch'): self.transport.commit_new(s)
        self.transport.put_part(s, 0, self.http.data)
        with self.assertRaises(StageFailure): self.transport.put_part(s, 0, self.http.data)
        s.path = '/apps/Xtransfer/other'
        with self.assertRaisesRegex(StageFailure, 'session_invalid'): self.transport.commit_new(s)

    def test_conflicts_and_renamed_paths_fail_without_followup_upload(self):
        self.http.fault = lambda req, obj: {'errno': -8, 'errmsg': 'SECRET'} if req.params.get('method') == 'create' else obj
        with self.assertRaisesRegex(StageFailure, 'protocol_conflict'): self.begin()
        self.http.fault = lambda req, obj: {**obj, 'path': TARGET+'-renamed'} if req.params.get('method') == 'precreate' else obj
        with self.assertRaisesRegex(StageFailure, 'path_changed'): self.begin()
        self.assertFalse(any(r.purpose == 'upload' for r in self.http.calls))

    def test_create_path_and_metadata_identity_cannot_drift(self):
        self.http.fault = lambda req, obj: {**obj, 'path': TARGET+'-other'} if req.params.get('method') == 'create' and b'isdir=0' in req.body else obj
        with self.assertRaisesRegex(StageFailure, 'path_changed'): self.commit()
        self.http = FakeHTTP(); self.transport = BaiduProtocol(self.http, 'Xtransfer', TARGET, ACCOUNT, LIMITS, diagnostic_rename_policy=True)
        self.commit()
        self.http.fault = lambda req, obj: {**obj, 'list': [{**obj['list'][0], 'fs_id': 10}]} if req.params.get('method') == 'filemetas' else obj
        with self.assertRaisesRegex(StageFailure, 'shape_invalid'): self.transport.metadata(TARGET)

    def test_upload_endpoint_and_download_destinations_are_https_allowlisted(self):
        self.http.fault = lambda req, obj: {'errno': 0, 'servers': [{'server': 'http://c.pcs.baidu.com'}]} if req.params.get('method') == 'locateupload' else obj
        with self.assertRaisesRegex(StageFailure, 'url_rejected'): self.begin()
        for url in ('https://baidu.com.evil.example/file', 'https://127.0.0.1/file', 'https://a.baidu.com:444/file',
                    'https://u:p@a.baidu.com/file', 'https://a.baidu.com/file?access_token=SECRET', 'https://a.baidu.com/file#fragment'):
            with self.assertRaises(StageFailure): destination(url, 'readback')

    def test_readback_redirects_drop_auth_and_reject_credential_propagation(self):
        self.commit()
        self.http.redirects = [(302, [('Location', 'https://c.pcs.baidu.com/file?sign=fixture')], b''),
                               (200, [], self.http.data)]
        self.assertEqual(b''.join(self.transport.readback(TARGET, 4)), self.http.data)
        calls = [r for r in self.http.calls if r.purpose == 'readback']
        self.assertEqual([r.auth for r in calls], [True, False])
        self.assertNotIn('access_token', self.http.symbolic_auth[-1])
        self.http.redirects = [(302, [('Location', 'https://c.pcs.baidu.com/file?access_token=SECRET')], b'')]
        with self.assertRaisesRegex(StageFailure, 'url_rejected'): list(self.transport.readback(TARGET, 4))

    def test_download_loop_length_chunk_and_header_errors(self):
        self.commit()
        for responses in ([(302, [('Location', 'https://d.pcs.baidu.com/data?sign=fixture')], b'')],
                          [(200, [('Content-Length', '9')], self.http.data)],
                          [(200, [('Content-Encoding', 'gzip')], self.http.data)],
                          [(200, [], self.http.data[:-1])], [(200, [], self.http.data+b'X')]):
            self.http.redirects = list(responses)
            with self.assertRaises(StageFailure): list(self.transport.readback(TARGET, 3))

    def test_protocol_binding_plugs_into_m3_and_honors_required_parts(self):
        data = b'A'*LIMITS.part_bytes+b'BC'  # Tiny compared with GB benchmarks; never networked.
        self.http = FakeHTTP(data); self.http.required = [1]
        self.transport = BaiduProtocol(self.http, 'Xtransfer', TARGET, ACCOUNT, LIMITS, diagnostic_rename_policy=True)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root/'source'; source.mkdir(); (source/'.receipts').mkdir(); backend = root/'backend'; backend.mkdir()
            entry = json.loads((Path(__file__).resolve().parents[1]/'examples/ncbi-ecoli/manifest.json').read_text())['files'][0]
            entry.update(name='test.fna', size=len(data), md5=hashlib.md5(data).hexdigest())
            (source/'test.fna').write_bytes(data)
            receipt = {'file': 'test.fna', 'status': 'source_verified', 'bytes': len(data), 'md5': entry['md5'], 'sha256': hashlib.sha256(data).hexdigest()}
            path = source/'.receipts/0.json'; path.write_text(json.dumps(receipt))
            r = run_simulated_upload(entry, source/'test.fna', path, backend, 'job-http', 'Xtransfer', self.transport,
                                     BackendNeeds('direct-api', 65536, 262144, 262144, 'stream'), LIMITS)
            self.assertEqual(r['status'], 'verified_simulation')
            self.assertEqual(r['confirmed_parts'], [1]); self.assertEqual(r['requested_payload_bytes'], 2)
            self.assertFalse(r['cloud_verified'] or r['delivery_eligible'])


class ChannelTests(unittest.TestCase):
    def grant(self):
        return RuntimeGrant(True, TARGET, ACCOUNT, 'b'*64, 'test-only-no-credentials', time.monotonic()+60)

    def test_default_gate_prevents_credential_callback_dns_and_connection(self):
        provider, resolver, factory = Mock(), Mock(), Mock()
        c = PinnedBaiduHTTPClient(credential_provider=provider, resolver=resolver, connection_factory=factory)
        with self.assertRaisesRegex(StageFailure, 'runtime_locked'):
            c.exchange(HTTPRequest('GET', FILE, TARGET, params={'method': 'meta'}))
        provider.assert_not_called(); resolver.assert_not_called(); factory.assert_not_called()

    def test_concrete_live_writes_stay_closed_even_with_an_explicit_grant(self):
        provider, resolver = Mock(), Mock()
        c = PinnedBaiduHTTPClient(grant=self.grant(), credential_provider=provider, resolver=resolver)
        with self.assertRaisesRegex(StageFailure, 'strict_conflict_unproven'):
            c.exchange(HTTPRequest('POST', FILE, TARGET, params={'method': 'create'}, body=b'isdir=1'))
        provider.assert_not_called(); resolver.assert_not_called()

    def test_anonymous_redirect_wire_with_fake_connector_has_fixed_timeout_and_stops(self):
        raw = Mock(status=200); raw.getheaders.return_value = [('Content-Length', '8')]
        stream = io.BytesIO(b'ACGTACGT'); raw.read1.side_effect = stream.read1
        conn = Mock(); conn.getresponse.return_value = raw
        factory = Mock(return_value=conn); provider = Mock()
        c = PinnedBaiduHTTPClient(grant=self.grant(), credential_provider=provider,
                                 resolver=lambda _: ['8.8.8.8'], connection_factory=factory)
        req = HTTPRequest('GET', 'https://d.pcs.baidu.com/data', TARGET, 'readback', auth=False)
        out = c.exchange(req)
        factory.assert_called_once_with('d.pcs.baidu.com', '8.8.8.8', IO_TIMEOUT)
        conn.set_debuglevel.assert_called_once_with(0); provider.assert_not_called()
        headers = conn.request.call_args.kwargs['headers']
        self.assertNotIn('Authorization', headers); self.assertNotIn('Cookie', headers)
        with self.assertRaisesRegex(StageFailure, 'concurrent_request'): c.exchange(req)
        self.assertIs(c.active, conn)
        self.assertTrue(c.stop()); self.assertTrue(out.closed)
        conn.sock.shutdown.assert_called_once()
        with self.assertRaises(StageFailure): list(out.chunks(8, 4))

    def test_private_dns_and_scope_fail_before_fake_connector(self):
        factory = Mock()
        c = PinnedBaiduHTTPClient(grant=self.grant(), resolver=lambda _: ['127.0.0.1'], connection_factory=factory)
        with self.assertRaisesRegex(StageFailure, 'url_rejected'):
            c.exchange(HTTPRequest('GET', 'https://d.pcs.baidu.com/data', TARGET, 'readback', auth=False))
        with self.assertRaisesRegex(StageFailure, 'scope_invalid'):
            c.exchange(HTTPRequest('GET', 'https://d.pcs.baidu.com/data', TARGET+'-other', 'readback', auth=False))
        factory.assert_not_called()

    def test_expired_or_non_boolean_grant_cannot_reach_provider(self):
        from dataclasses import replace
        provider, resolver = Mock(), Mock()
        for grant in (replace(self.grant(), enabled='False'), replace(self.grant(), expires_monotonic=0),
                      replace(self.grant(), account_sha256=True)):
            client = PinnedBaiduHTTPClient(grant=grant, credential_provider=provider, resolver=resolver)
            with self.assertRaises(StageFailure):
                client.exchange(HTTPRequest('GET', FILE, TARGET, params={'method': 'meta'}))
        provider.assert_not_called(); resolver.assert_not_called()

    def test_absent_injected_credential_stops_before_any_dns_or_connection(self):
        provider, resolver, factory = Mock(return_value=None), Mock(), Mock()
        client = PinnedBaiduHTTPClient(grant=self.grant(), credential_provider=provider,
                                       resolver=resolver, connection_factory=factory)
        with self.assertRaisesRegex(StageFailure, 'auth_missing'):
            client.exchange(HTTPRequest('GET', FILE, TARGET, params={'method': 'meta'}))
        resolver.assert_not_called(); factory.assert_not_called()

    def test_deadline_and_response_headers_close_stream(self):
        out = reply(b'data'); out.deadline = 0
        with self.assertRaisesRegex(StageFailure, 'http_deadline'): list(out.chunks(4, 2))
        self.assertTrue(out.closed)
        for headers in ([('Content-Length', '4'), ('Content-Length', '4')],
                        [('Content-Length', '4'), ('Transfer-Encoding', 'chunked')]):
            from fast_transfer.baidu_http import response_headers
            out = reply(b'data', headers=headers)
            with self.assertRaises(StageFailure): response_headers(out)
            out.close()

    def test_io_and_cleanup_exceptions_do_not_leak_or_claim_stop(self):
        conn = Mock()
        conn.getresponse.side_effect = RuntimeError('SECRET_SIGNED_URL')
        conn.close.side_effect = RuntimeError('SECRET_CLOSE')
        client = PinnedBaiduHTTPClient(grant=self.grant(), resolver=lambda _: ['8.8.8.8'],
                                       connection_factory=lambda *args: conn)
        with self.assertRaises(StageFailure) as caught:
            client.exchange(HTTPRequest('GET', 'https://d.pcs.baidu.com/data', TARGET, 'readback', auth=False))
        self.assertEqual(str(caught.exception), 'http_io_failure')
        self.assertFalse(client.stop())

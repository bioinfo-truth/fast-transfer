import hashlib
import io
import json
import sys
import socket
import tempfile
import time
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

from fast_transfer import download as app
from fast_transfer import safe_http as net
from fast_transfer.intake import InputProblem
from fast_transfer.space import BackendNeeds, SpaceGuard, RESERVE, MARGIN, rounded


class Response(io.BytesIO):
    def __init__(self, data=b'', status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v

    def getheader(self, name, default=None):
        return self.headers.get(name, default)


class SafeHTTPTests(unittest.TestCase):
    def test_mixed_private_public_dns_is_rejected_before_connection(self):
        rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))
                for ip in ('8.8.8.8', '127.0.0.1')]
        with patch.object(net.socket, 'getaddrinfo', return_value=rows), patch.object(net, 'PinnedHTTPSConnection') as connect:
            with self.assertRaisesRegex(InputProblem, 'nonpublic_dns'):
                net.open_public('https://example.org/a', time.monotonic()+60)
            connect.assert_not_called()

    def test_connection_pins_address_but_keeps_original_tls_hostname(self):
        c = net.PinnedHTTPSConnection('example.org', '8.8.8.8', 1)
        sock, context = MagicMock(), MagicMock()
        c._context = context
        with patch.object(net.socket, 'create_connection', return_value=sock) as connect:
            c.connect()
        connect.assert_called_once_with(('8.8.8.8', 443), 1)
        context.wrap_socket.assert_called_once_with(sock, server_hostname='example.org')

    def test_redirect_private_dns_downgrade_and_signed_url_are_refused(self):
        for target in ('https://127.0.0.1/a', 'http://example.org/a',
                       'https://example.org/a?secret=DO_NOT_LOG', 'https://private.example.org/a',
                       'https://example.org/a\nDO_NOT_LOG'):
            response = Response(status=302, headers={'Location': target})
            connection = MagicMock()
            connection.getresponse.return_value = response
            with patch.object(net, 'public_addresses', side_effect=[['8.8.8.8'], InputProblem('nonpublic_dns_result')]), patch.object(net, 'PinnedHTTPSConnection', return_value=connection) as factory:
                with self.assertRaises(InputProblem) as caught:
                    net.open_public('https://example.org/start', time.monotonic()+60)
                self.assertNotIn('DO_NOT_LOG', str(caught.exception))
                self.assertEqual(factory.call_count, 1)
                connection.close.assert_called()

    def test_public_cross_host_redirect_resolves_each_hop(self):
        connections = [MagicMock(), MagicMock()]
        connections[0].getresponse.return_value = Response(status=302, headers={'Location': 'https://other.example.org/file'})
        connections[1].getresponse.return_value = Response(b'ok')
        with patch.object(net, 'public_addresses', side_effect=[['8.8.8.8'], ['1.1.1.1']]) as dns, patch.object(net, 'PinnedHTTPSConnection', side_effect=connections):
            response, connection, hops = net.open_public('https://example.org/file', time.monotonic()+60)
            self.assertEqual(hops, 1)
            self.assertEqual([x.args[0] for x in dns.call_args_list], ['example.org', 'other.example.org'])
            self.assertEqual(response.read(), b'ok')
            response.close(); connection.close()

    def test_redirect_loop_and_access_denied_states(self):
        for status, headers, code in [(302, {'Location': '/a'}, 'redirect_loop'),
                                     (401, {}, 'source_access_denied'), (403, {}, 'source_access_denied')]:
            response = Response(status=status, headers=headers)
            c = MagicMock(); c.getresponse.return_value = response
            with patch.object(net, 'public_addresses', return_value=['8.8.8.8']), patch.object(net, 'PinnedHTTPSConnection', return_value=c):
                with self.assertRaisesRegex(InputProblem, code):
                    net.open_public('https://example.org/a', time.monotonic()+60)
                self.assertTrue(response.closed)

    def test_redirect_count_limit(self):
        connections = [MagicMock(), MagicMock()]
        for index, c in enumerate(connections):
            c.getresponse.return_value = Response(status=302, headers={'Location': '/next'+str(index)})
        with patch.object(net, 'public_addresses', return_value=['8.8.8.8']), patch.object(net, 'PinnedHTTPSConnection', side_effect=connections) as factory:
            with self.assertRaisesRegex(InputProblem, 'too_many_redirects'):
                net.open_public('https://example.org/start', time.monotonic()+60, max_redirects=1)
            self.assertEqual(factory.call_count, 2)

    def test_expired_deadline_prevents_dns_and_socket(self):
        with patch.object(net, 'public_addresses') as dns:
            with self.assertRaisesRegex(InputProblem, 'download_deadline'):
                net.open_public('https://example.org/a', time.monotonic()-1)
            dns.assert_not_called()


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.data = b'public biological fixture\n' * 50
        self.entry = json.loads((Path(__file__).resolve().parents[1] / 'examples/ncbi-ecoli/manifest.json').read_text())['files'][0]
        self.entry.update(size=len(self.data), md5=hashlib.md5(self.data).hexdigest(), sha256=hashlib.sha256(self.data).hexdigest())
        self.space = MagicMock(free=20*1024**3)

    def run_download(self, path, data=None, headers=None):
        response = Response(self.data if data is None else data, headers=headers)
        with patch.object(app, 'open_public', return_value=(response, MagicMock(), 0)), patch('fast_transfer.space.shutil.disk_usage', return_value=self.space):
            return app.download_verified(self.entry, path, 4096)

    def test_success_without_content_length_still_checks_size_and_both_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'file'
            result = self.run_download(p)
            self.assertEqual(result['status'], 'source_verified')
            self.assertEqual(p.read_bytes(), self.data)
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_mismatch_truncation_and_overrun_remove_only_new_partial_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'file'
            for data in (self.data[:-1], self.data+b'x', b'x'*len(self.data)):
                with self.subTest(size=len(data)), self.assertRaises(InputProblem):
                    self.run_download(p, data)
                self.assertFalse(p.exists())

    def test_existing_file_and_symlink_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            original, target = Path(d)/'original', Path(d)/'target'
            original.write_bytes(b'existing')
            target.symlink_to(original)
            with self.assertRaises(InputProblem):
                self.run_download(target)
            self.assertEqual(original.read_bytes(), b'existing')
            self.assertTrue(target.is_symlink())

    def test_size_or_disk_budget_prevents_any_request(self):
        with tempfile.TemporaryDirectory() as d, patch.object(app, 'open_public') as fetch, patch('fast_transfer.space.shutil.disk_usage', return_value=MagicMock(free=app.RESERVE)):
            with self.assertRaisesRegex(InputProblem, 'disk_budget'):
                app.download_verified(self.entry, Path(d)/'file', 4096)
            with self.assertRaisesRegex(InputProblem, 'file_budget'):
                app.download_verified(self.entry, Path(d)/'file', 1)
            fetch.assert_not_called()

    def test_disk_reserve_drop_during_stream_stops_and_removes_partial(self):
        response = Response(self.data)
        original_read = response.read1
        def drop(n):
            self.space.free = app.RESERVE
            return original_read(n)
        response.read1 = drop
        with tempfile.TemporaryDirectory() as d, patch.object(app, 'open_public', return_value=(response, MagicMock(), 0)), patch('fast_transfer.space.shutil.disk_usage', return_value=self.space):
            p = Path(d)/'file'
            with self.assertRaisesRegex(InputProblem, 'disk_budget'):
                app.download_verified(self.entry, p, 4096)
            self.assertFalse(p.exists())

    def test_invalid_or_conflicting_response_headers(self):
        for headers in ({'Content-Length':'bad'}, {'Content-Length':'1'}, {'Content-Length':'9'*5000},
                        {'Content-Encoding':'gzip'}, {'Content-Length':str(len(self.data)), 'Transfer-Encoding':'chunked'}):
            with tempfile.TemporaryDirectory() as d, self.subTest(headers=headers), self.assertRaises(InputProblem):
                self.run_download(Path(d)/'file', headers=headers)

    def test_unreviewed_input_stops_before_network(self):
        del self.entry['size']
        with tempfile.TemporaryDirectory() as d, patch.object(app, 'open_public') as fetch:
            with self.assertRaisesRegex(InputProblem, 'intake_manual_review'):
                app.download_verified(self.entry, Path(d)/'file', 4096)
            fetch.assert_not_called()

    def test_read_failure_removes_only_new_partial_and_closes_connection(self):
        response, connection = Response(self.data), MagicMock()
        response.read1 = MagicMock(side_effect=OSError('DO_NOT_LOG'))
        with tempfile.TemporaryDirectory() as d, patch.object(app, 'open_public', return_value=(response, connection, 0)), patch('fast_transfer.space.shutil.disk_usage', return_value=self.space):
            p = Path(d)/'file'
            with self.assertRaises(OSError):
                app.download_verified(self.entry, p, 4096)
            self.assertFalse(p.exists())
            self.assertTrue(response.closed)
            connection.close.assert_called_once()

    def test_future_openlist_cache_budget_blocks_download_before_network(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); target = root/'file'
            import os
            quantum = os.statvfs(root).f_frsize
            self.space.free = RESERVE + MARGIN + rounded(len(self.data), quantum)
            needs = BackendNeeds('openlist', 0, 0, 0, 'stream')
            with patch('fast_transfer.space.shutil.disk_usage', return_value=self.space), patch.object(app, 'open_public') as fetch:
                guard = SpaceGuard({'file': len(self.data)}, root, needs, root)
                with self.assertRaisesRegex(InputProblem, 'disk_budget'):
                    app.download_verified(self.entry, target, 4096, space_guard=guard)
                fetch.assert_not_called()
                self.assertFalse(target.exists())

    def test_backend_budget_is_rechecked_during_download_and_old_files_survive(self):
        response = Response(self.data)
        original_read = response.read1
        def drop(n):
            self.space.free = RESERVE + MARGIN
            return original_read(n)
        response.read1 = drop
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); old = root/'old'; old.write_bytes(b'preserve')
            needs = BackendNeeds('openlist', 0, 0, 0, 'stream')
            with patch('fast_transfer.space.shutil.disk_usage', return_value=self.space), patch.object(app, 'open_public', return_value=(response, MagicMock(), 0)):
                guard = SpaceGuard({'file': len(self.data)}, root, needs, root)
                with self.assertRaisesRegex(InputProblem, 'disk_budget'):
                    app.download_verified(self.entry, root/'file', 4096, space_guard=guard)
            self.assertEqual(old.read_bytes(), b'preserve')
            self.assertFalse((root/'file').exists())

    def test_cli_backend_admission_and_receipt_are_offline_and_separate_from_upload(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); manifest = root/'manifest.json'
            manifest.write_text(json.dumps({'schema_version': 1, 'files': [self.entry]}))
            backend = root/'backend'; backend.mkdir()
            output = root/'new'
            args = ['download', str(manifest), '--output-dir', str(output), '--backend', 'openlist',
                    '--backend-dir', str(backend), '--source-overhead-bytes', '1048576',
                    '--upload-temp-bytes', '65536', '--readback-temp-bytes', '65536',
                    '--readback-mode', 'stream', '--expected-layout', 'same']
            stdout = io.StringIO()
            with patch.object(sys, 'argv', args), patch.object(sys, 'stdout', stdout), patch('fast_transfer.space.shutil.disk_usage', return_value=self.space), patch.object(app, 'open_public', return_value=(Response(self.data), MagicMock(), 0)) as source:
                self.assertEqual(app.main(), 0)
            rows = [json.loads(line) for line in stdout.getvalue().splitlines()]
            self.assertEqual(rows[0]['event'], 'space_admission')
            self.assertEqual(rows[0]['planned_stages'], ['download', 'upload', 'readback'])
            self.assertEqual(rows[0]['requirements']['upload_temp_bytes'], 65536)
            self.assertEqual(rows[1]['status'], 'source_verified')
            self.assertEqual((output/self.entry['name']).read_bytes(), self.data)
            self.assertEqual(list(backend.iterdir()), [])
            self.assertEqual(json.loads((output/'.receipts/0.json').read_text())['status'], 'source_verified')
            self.assertEqual(source.call_count, 1)  # Mocked public-source GET only.

    def test_cli_unknown_backend_cost_does_not_create_files_or_request_data(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); manifest = root/'manifest.json'
            manifest.write_text(json.dumps({'schema_version': 1, 'files': [self.entry]}))
            output = root/'new'; stdout = io.StringIO()
            args = ['download', str(manifest), '--output-dir', str(output), '--backend', 'openlist',
                    '--source-overhead-bytes', '0']
            with patch.object(sys, 'argv', args), patch.object(sys, 'stdout', stdout), patch.object(app, 'open_public') as source:
                self.assertEqual(app.main(), 2)
            self.assertEqual(json.loads(stdout.getvalue())['reason'], 'unknown_backend_overhead')
            self.assertFalse(output.exists())
            source.assert_not_called()

    def test_cli_low_space_stops_before_creating_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); manifest = root/'manifest.json'
            manifest.write_text(json.dumps({'schema_version': 1, 'files': [self.entry]}))
            output = root/'new'; stdout = io.StringIO()
            self.space.free = RESERVE + MARGIN - 1
            args = ['download', str(manifest), '--output-dir', str(output)]
            with patch.object(sys, 'argv', args), patch.object(sys, 'stdout', stdout), patch('fast_transfer.space.shutil.disk_usage', return_value=self.space), patch.object(app, 'open_public') as source:
                self.assertEqual(app.main(), 2)
            self.assertEqual(json.loads(stdout.getvalue())['reason'], 'space_workspace_reserve')
            self.assertFalse(output.exists())
            source.assert_not_called()

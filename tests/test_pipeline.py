import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fast_transfer import __main__ as app


class Source:
    def __init__(self, data):
        self.data = data
        self.headers = {'Content-Length': str(len(data))}
        self.offset = 0
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, n):
        result = self.data[self.offset:self.offset+n]
        self.offset += len(result)
        return result


class PipelineTests(unittest.TestCase):
    def test_download_and_hash(self):
        data = b'public data' * 100
        with tempfile.TemporaryDirectory() as d, patch.object(app.urllib.request, 'urlopen', return_value=Source(data)):
            target = Path(d) / 'file'
            self.assertEqual(app.download({'url': 'https://example.org/file', 'size': len(data)}, target, 4096, 0), len(data))
            self.assertEqual(app.hashes(target)[1], hashlib.md5(data).hexdigest())

    def test_limit_rejects_large_source(self):
        with tempfile.TemporaryDirectory() as d, patch.object(app.urllib.request, 'urlopen', return_value=Source(b'12345')):
            with self.assertRaisesRegex(ValueError, 'limit'):
                app.download({'url': 'https://example.org/file'}, Path(d) / 'file', 4, 0)

    def test_upload_precreate_chunks_and_create(self):
        data = b'abcdef'
        md5 = hashlib.md5(data).hexdigest()
        calls = []
        def fake_json(url, data=None, headers=None):
            if 'locateupload' in url:
                return {'servers': [{'server': 'https://upload.example'}]}
            calls.append(url)
            return {'md5': md5}
        def fake_form(url, values):
            if 'precreate' in url:
                self.assertEqual(json.loads(values['block_list']), [md5])
                return {'uploadid': 'id', 'block_list': [0]}
            self.assertEqual(values['uploadid'], 'id')
            return {'size': len(data), 'path': '/apps/test/file', 'fs_id': 42}
        with tempfile.TemporaryDirectory() as d, patch.object(app, 'json_request', side_effect=fake_json), patch.object(app, 'post_form', side_effect=fake_form):
            path = Path(d) / 'file'
            path.write_bytes(data)
            result = app.upload(path, '/apps/test/file', 'token')
            self.assertEqual(result['md5'], md5)
            self.assertEqual(len(calls), 1)

    def test_names_cannot_escape_work_directory(self):
        for name in ('../x', '/tmp/x', '.', 'a\\b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                app.safe_name(name)


if __name__ == '__main__': unittest.main()

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fast_transfer.intake import assess, load_manifest, InputProblem, public_url

FIXTURE = Path(__file__).resolve().parents[1] / 'examples/ncbi-ecoli/manifest.json'


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(FIXTURE.read_text())
        self.file = self.manifest['files'][0]

    def codes(self):
        return {r['code'] for x in assess(self.manifest)['files'] for r in x['reasons']}

    def test_real_fixture_and_official_checksum_snapshot(self):
        self.assertEqual(assess(self.manifest)['status'], 'accepted')
        checksums = (FIXTURE.parent / 'md5checksums.txt').read_text()
        self.assertIn(self.file['md5'] + '  ./' + self.file['name'], checksums)

    def test_source_metadata_snapshot_bytes_match_record(self):
        record = json.loads((FIXTURE.parent / 'source-record.json').read_text())
        for name, expected in record['snapshots'].items():
            self.assertEqual(hashlib.sha256((FIXTURE.parent / name).read_bytes()).hexdigest(), expected)

    def test_unknown_size_or_no_source_checksum_requires_manual_review(self):
        del self.file['size']
        del self.file['md5']
        self.assertEqual(assess(self.manifest)['status'], 'manual_review')
        self.assertEqual(self.codes(), {'size_required', 'source_checksum_required'})

    def test_missing_provenance_is_not_implicitly_public(self):
        del self.file['source']
        self.assertEqual(assess(self.manifest)['status'], 'manual_review')

    def test_controlled_access_and_prohibited_distribution_rejected(self):
        self.file['source']['access'] = 'controlled'
        self.file['source']['redistribution']['status'] = 'prohibited'
        self.assertEqual(assess(self.manifest)['status'], 'rejected')
        self.assertIn('controlled_access_not_supported', self.codes())
        self.assertIn('redistribution_prohibited', self.codes())

    def test_unreviewed_rights_require_manual_review(self):
        self.file['source']['redistribution']['status'] = 'unknown'
        self.assertEqual(assess(self.manifest)['status'], 'manual_review')

    def test_unsafe_names_rejected(self):
        for name in ('../x', '/tmp/x', 'a\\b', 'a\nlog', 'a%2fb', '..', 'CON.txt', 'a.', '数据.gz', 'x'*181):
            with self.subTest(name=name):
                self.file['name'] = name
                self.assertIn('invalid_filename', self.codes())

    def test_duplicate_names_are_case_insensitive(self):
        duplicate = copy.deepcopy(self.file)
        duplicate['name'] = self.file['name'].upper()
        self.manifest['files'].append(duplicate)
        self.assertIn('duplicate_filename', self.codes())

    def test_invalid_sizes_hashes_unknown_fields_and_schema(self):
        for size in (True, -1, 0, '12'):
            self.file['size'] = size
            self.assertIn('invalid_size', self.codes())
        self.file['size'] = 123
        self.file['md5'] = 'not-md5'
        self.file['Authorization'] = 'DO_NOT_LOG'
        report = assess(self.manifest)
        self.assertIn('invalid_md5', self.codes())
        self.assertNotIn('DO_NOT_LOG', json.dumps(report))
        self.manifest['schema_version'] = True
        self.assertEqual(assess(self.manifest)['status'], 'rejected')

    def test_credential_query_private_and_unsafe_urls(self):
        for url in ('http://example.org/a', 'https://user:SECRET@example.org/a',
                    'https://example.org/a?token=SECRET', 'https://127.0.0.1/a',
                    'https://[::1]/a', 'https://169.254.169.254/a', 'https://localhost/a',
                    'https://a.local/a', 'https://example.org:444/a', 'https://example.org/\nSECRET'):
            with self.subTest(url=url), self.assertRaises(InputProblem) as caught:
                public_url(url)
            self.assertNotIn('SECRET', str(caught.exception))

    def test_duplicate_json_keys_and_oversize_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'm.json'
            p.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaisesRegex(InputProblem, 'duplicate_json_key'):
                load_manifest(p)
            p.write_bytes(b' ' * (1024**2 + 1))
            with self.assertRaisesRegex(InputProblem, 'manifest_too_large'):
                load_manifest(p)

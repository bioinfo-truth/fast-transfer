"""Synthetic mixed OAuth JSON only. No real credentials or external service."""
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from fast_transfer import auth_metadata as m

NOW=dt.datetime(2026,11,10,14,tzinfo=dt.timezone.utc)
SECRET='SYNTHETIC_SECRET_VALUE_NOT_FOR_OUTPUT'


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'synthetic.json'
    def read(self,obj):
        self.path.write_text(json.dumps(obj));self.path.chmod(0o600)
        value=m.read_authorization_metadata(self.path,NOW)
        self.assertNotIn(SECRET,json.dumps(value));return value
    def test_scope_and_expiry_return_only_fixed_safe_metadata(self):
        value=self.read({'access_token':SECRET,'refresh_token':SECRET,'app_name':'Xtransfer','scope':'basic netdisk',
            'issued_at':'2026-11-01T00:00:00Z','expires_in':2592000})
        self.assertEqual(value['scope']['value'],'basic netdisk')
        self.assertEqual(value['expiry']['utc'],'2026-12-01T00:00:00+00:00')
        self.assertEqual(value['local_expiry_assessment'],'not_past_recorded_expiry')
        self.assertFalse(value['official_live_validity_verified'])
    def test_duration_alone_and_created_time_are_not_used_as_issuance(self):
        value=self.read({'access_token':SECRET,'expires_in':2592000,'created_at':'2026-11-01T00:00:00Z'})
        self.assertEqual(value['issuance']['status'],'missing');self.assertEqual(value['local_expiry_assessment'],'unknown')
    def test_file_mtime_does_not_supply_missing_metadata(self):
        value=self.read({'access_token':SECRET})
        self.assertEqual(value['scope']['status'],'missing');self.assertEqual(value['local_expiry_assessment'],'unknown')
    def test_opaque_values_in_white_fields_are_not_reflected(self):
        value=self.read({'access_token':SECRET,'scope':SECRET,'app_name':SECRET,'expires_at':SECRET,'app_id':123456789})
        self.assertNotIn('123456789',json.dumps(value));self.assertEqual(value['scope']['status'],'unsupported_or_redacted')
    def test_secret_duplicated_in_allowed_scope_is_tainted(self):
        value=self.read({'access_token':'basic netdisk','scope':'basic netdisk'})
        self.assertEqual(value['scope']['status'],'unsupported_or_redacted')
    def test_conflicts_and_naive_time_do_not_become_expiry(self):
        value=self.read({'scope':'basic netdisk','metadata':{'scope':'basic'},'issued_at':'2026-11-01T00:00:00','expires_in':5})
        self.assertEqual(value['scope']['status'],'conflicting_records');self.assertEqual(value['local_expiry_assessment'],'unknown')
    def test_absolute_timestamp_and_milliseconds_normalized(self):
        value=self.read({'expires_at':1793491200000})
        self.assertEqual(value['expiry']['conversion'],['unix_milliseconds'])
        self.assertEqual(value['local_expiry_assessment'],'past_recorded_expiry')
    def test_unknown_containers_and_secret_keys_are_not_exported(self):
        value=self.read({'other':{'scope':SECRET},'client_secret':SECRET,'metadata':{'scope':'basic,netdisk'}})
        self.assertEqual(value['scope']['value'],'basic netdisk');self.assertNotIn('client_secret',json.dumps(value))
    def test_bad_file_modes_symlinks_duplicates_and_oversize_fail_without_raw_errors(self):
        self.path.write_text('{"scope":"basic","scope":"'+SECRET+'"}');self.path.chmod(0o600)
        self.assertEqual(m.read_authorization_metadata(self.path)['status'],'metadata_unavailable_or_rejected')
        self.path.write_text('x'*65537)
        self.assertEqual(m.read_authorization_metadata(self.path)['status'],'metadata_unavailable_or_rejected')
        self.path.write_text('{}');self.path.chmod(0o644)
        self.assertEqual(m.read_authorization_metadata(self.path)['status'],'metadata_unavailable_or_rejected')
        link=Path(self.tmp.name)/'link';link.symlink_to(self.path)
        self.assertEqual(m.read_authorization_metadata(link)['status'],'metadata_unavailable_or_rejected')
    def test_unbounded_or_mistyped_metadata_does_not_escape(self):
        value=self.read({'expires_in':True,'scope':{'secret':SECRET},'metadata':{'issued_at':-1}})
        self.assertEqual(value['expires_in']['status'],'unusable_or_conflicting')
        self.assertEqual(value['local_expiry_assessment'],'unknown')

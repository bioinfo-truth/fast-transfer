"""Synthetic original receipt joins and hash-bound identity; no external I/O."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fast_transfer import original_sample as o, mcp_binding as b, mcp_share as c


class OriginalSampleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.job='job-'+'a'*32
        self.target='/apps/Xtransfer/mvp-validation/'+self.job+'/'+o.NAME
        self.account=hashlib.sha256(b'3003').hexdigest()
        self.records={
          'result.json':{'job_id':self.job,'target':self.target,'commit_attempted':False,'requested_payload_bytes':0},
          'precommit-inspection.json':{'job_id':self.job,'target':self.target,'directory_id':4,
            'prior_commit_attempted':False,'prior_payload_sent':0},
          'recovery-result.json':{'job_id':self.job,'target':self.target,'verified_object_id':5,
            'readback':{'bytes':o.SIZE,'md5':o.MD5,'sha256':o.SHA256},'cloud_verified':True,
            'verification_complete':True,'same_cloud_directory':True},
          'recovered-session.private.json':{'path':self.target,'account_sha256':self.account,'directory_id':4,
            'size':o.SIZE,'block_md5':[o.MD5],'source_sha256':o.SHA256,'approval_ref':o.APPROVAL_REF,'uploadid':'synthetic_private_session'},
          'source/.receipts/0.json':{'file':o.NAME,'status':'source_verified','bytes':o.SIZE,'md5':o.MD5,'sha256':o.SHA256}}
        self.write()
    def write(self):
        for name,record in self.records.items():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(record));p.chmod(0o600)
    def test_join_mapping_and_no_exported_session(self):
        e=o.load_original(self.root)
        self.assertEqual(e.account,'sha256:'+self.account);self.assertEqual(e.fsid,'5')
        self.assertNotIn('synthetic_private_session',repr(e)+json.dumps(e.__dict__))
        changed=replace(e,fsid='6');self.assertNotEqual(e.mapping_sha256,o.digest({k:v for k,v in changed.__dict__.items() if k!='mapping_sha256'}))
    def test_each_cross_record_drift_rejected(self):
        for file,key in [('precommit-inspection.json','job_id'),('recovery-result.json','target'),
                         ('recovered-session.private.json','source_sha256'),('recovered-session.private.json','directory_id'),
                         ('source/.receipts/0.json','md5')]:
            prev=self.records[file][key];self.records[file][key]='synthetic_mismatch';self.write()
            with self.assertRaises(o.BindingFailure):o.load_original(self.root)
            self.records[file][key]=prev
    def test_private_permissions_duplicates_and_symlinks_rejected(self):
        p=self.root/'result.json';p.chmod(0o644)
        with self.assertRaises(o.BindingFailure):o.load_original(self.root)
        self.write();p.write_text('{"x":1,"x":2}')
        with self.assertRaises(o.BindingFailure):o.load_original(self.root)
        self.write();p.unlink();p.symlink_to(self.root/'recovery-result.json')
        with self.assertRaises(o.BindingFailure):o.load_original(self.root)
    def test_hash_identity_matching_and_mismatch(self):
        e=o.load_original(self.root);b.check_identity({'uk':3003},e)
        for uk in (3004,True,'03003'):
            with self.assertRaises(c.Rejected):b.check_identity({'uk':uk},e)
    def test_account_hash_never_passed_as_raw_id(self):
        e=o.load_original(self.root)
        with self.assertRaises(c.Rejected):replace(e,account=self.account)
    def native(self,user,meta=None):
        e=o.load_original(self.root);calls=[]
        def req(_self,method,url,params):
            calls.append((url,params));return user if len(calls)==1 else meta
        with patch.object(o._Probe,'request',req):result=o.native_readonly(e,lambda:self.fail('no network credential loading'))
        return result,calls
    def test_native_wrong_account_prevents_object(self):
        r,calls=self.native({'uk':3004});self.assertFalse(r['metadata_request_attempted']);self.assertEqual(len(calls),1)
    def test_native_exact_object_no_download(self):
        row={'fs_id':5,'path':self.target,'size':o.SIZE,'md5':o.MD5,'isdir':0}
        r,calls=self.native({'uk':3003},{'list':[row]})
        self.assertTrue(r['native_object_matches'] and r['closed']);self.assertEqual(len(calls),2)
        self.assertEqual(calls[1][1]['dlink'],0)
    def test_obfuscated_md5_matches_without_new_content_read(self):
        raw=o.MD5[8:16]+o.MD5[:8]+o.MD5[24:]+o.MD5[16:24]
        encoded=''.join(format(int(c,16)^(i&15),'x') for i,c in enumerate(raw))
        encoded=encoded[:9]+chr(ord('g')+int(encoded[9],16))+encoded[10:]
        row={'fs_id':5,'path':self.target,'size':o.SIZE,'md5':encoded,'isdir':0}
        r,calls=self.native({'uk':3003},{'list':[row]})
        self.assertTrue(r['native_object_matches']);self.assertEqual(len(calls),2)
        self.assertFalse(r['metadata_comparison']['md5_matches'])
        self.assertTrue(r['metadata_comparison']['md5_normalized_matches'])
        e=o.load_original(self.root)
        b.check_metadata({'list':[{'fsid':5,'path':self.target,'size':o.SIZE,'md5':encoded}]},e)
    def test_close_failure_does_not_report_finished(self):
        e=o.load_original(self.root)
        with patch.object(o._Probe,'request',return_value={'uk':3004}),patch.object(o.PinnedBaiduHTTPClient,'stop',side_effect=OSError('synthetic_private')):
            r=o.native_readonly(e,lambda:None)
        self.assertFalse(r['closed']);self.assertEqual(r['status'],'manual_review_close_unconfirmed')
        self.assertNotIn('synthetic_private',json.dumps(r))
    def test_native_each_mismatch_and_raw_failure_suppressed(self):
        row={'fs_id':5,'path':self.target,'size':o.SIZE,'md5':o.MD5,'isdir':0}
        for field in row:
            bad=dict(row);bad[field]='synthetic_private_mismatch'
            r,_=self.native({'uk':3003},{'list':[bad]});self.assertFalse(r['native_object_matches'])
        e=o.load_original(self.root)
        with patch.object(o._Probe,'request',side_effect=ValueError('synthetic_private_exception')):
            r=o.native_readonly(e,lambda:None)
        self.assertNotIn('synthetic_private',json.dumps(r))

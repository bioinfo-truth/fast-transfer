"""Actual pinned SDK encoder subprocess tests; all payloads/auth are synthetic."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fast_transfer.baidu_http import HTTPRequest
from fast_transfer.baidu_protocol import BaiduProtocol, FILE
from fast_transfer.sdk_codec import SDKRequestEncoder
from fast_transfer.upload_stage import StageFailure, TransferLimits
from test_baidu_protocol import FakeHTTP, ACCOUNT

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT/'scratch/official-sdk-reuse-20261111/ft-sdk-codec'
GUARD = ROOT/'scripts/baidu-sdk-codec-guard.py'
TARGET = '/apps/Xtransfer/mvp-validation/job-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/fixture.fna'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class SDKCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HELPER.is_file():
            raise unittest.SkipTest('Build integrations/baidu-sdk-go/cmd/ft-sdk-codec first; this suite requires the actual SDK artifact')

    def setUp(self):
        tmp = tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.guard = Path(tmp.name)/'guard.py'
        shutil.copyfile(GUARD,self.guard);self.guard.chmod(0o600)
        self.codec = SDKRequestEncoder(HELPER,sha(HELPER),self.guard,sha(self.guard))

    def form(self, operation):
        if operation == 'directory':return {'path':TARGET.rsplit('/',1)[0],'isdir':1,'rtype':0}
        f={'path':TARGET,'size':3,'isdir':0,'rtype':1,'block_list':json.dumps([hashlib.md5(b'abc').hexdigest()],separators=(',',':'))}
        if operation == 'precreate':f['autoinit']=1
        else:f.update(uploadid='SYNTHETIC_ONLY',is_revision=0)
        return f

    def test_actual_sdk_encodes_all_control_requests(self):
        for operation in ('directory','precreate','commit'):
            method='precreate' if operation=='precreate' else 'create'
            req=self.codec.control(FILE,TARGET,{'method':method},self.form(operation))
            self.assertEqual(req.url,FILE);self.assertEqual(req.binding,TARGET)
            self.assertNotIn(b'access_token',req.body)

    def test_actual_sdk_encodes_exact_binary_part_from_sealed_memfd(self):
        data=b'\x00\xffabc\r\n--SYNTHETIC\x00'*100
        req=self.codec.part(TARGET,'https://c.pcs.baidu.com','SYNTHETIC_ONLY',2,data)
        self.assertEqual(req.params['partseq'],'2')
        self.assertEqual(req.params['path'],TARGET)
        req.validate()
        self.assertIn(data,req.body)

    def test_full_existing_protocol_uses_sdk_for_four_writes_and_strict_parser(self):
        data=b'ACGT'*256;http=FakeHTTP(data)
        limits=TransferLimits(4*1024**2,16*1024**2,1024)
        protocol=BaiduProtocol(http,'Xtransfer',TARGET,ACCOUNT,limits,diagnostic_rename_policy=True,request_encoder=self.codec)
        with patch('test_baidu_protocol.TARGET',TARGET),patch.object(self.codec,'_run',wraps=self.codec._run) as runs:
            protocol.reserve_new(TARGET.rsplit('/',1)[0])
            session=protocol.begin_new(TARGET,len(data),[hashlib.md5(data).hexdigest()])
            protocol.put_part(session,0,data);protocol.commit_new(session)
            meta=protocol.metadata(TARGET)
            self.assertEqual(b''.join(protocol.readback(TARGET,1024)),data)
        self.assertEqual(runs.call_count,4)
        self.assertTrue(protocol.stop())

    def test_default_live_write_gate_remains_closed_with_encoder(self):
        http=FakeHTTP();protocol=BaiduProtocol(http,'Xtransfer',TARGET,ACCOUNT,TransferLimits(4*1024**2,16*1024**2,1024),request_encoder=self.codec)
        with self.assertRaisesRegex(StageFailure,'strict_conflict'):protocol.reserve_new(TARGET.rsplit('/',1)[0])
        self.assertFalse(http.calls)

    def test_source_part_hash_mismatch_does_not_create_encoded_request(self):
        fd=os.memfd_create('synthetic-only',os.MFD_CLOEXEC)
        try:
            os.write(fd,b'abc');os.lseek(fd,0,os.SEEK_SET)
            with self.assertRaisesRegex(StageFailure,'sdk_codec_failed'):
                self.codec._run({'operation':'part','target':TARGET,'uploadid':'SYNTHETIC_ONLY','source_fd':fd,'part_bytes':3,'part_md5':'0'*32},fd)
        finally:os.close(fd)

    def test_wrong_artifact_hash_and_writable_artifact_rejected(self):
        with self.assertRaisesRegex(StageFailure,'artifact_rejected'):SDKRequestEncoder(HELPER,'0'*64,self.guard,sha(self.guard))
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'helper';p.write_bytes(b'fake');p.chmod(0o777)
            with self.assertRaisesRegex(StageFailure,'artifact_rejected'):SDKRequestEncoder(p,sha(p),self.guard,sha(self.guard))

    def test_unexpected_encoded_target_or_fields_never_reach_transport(self):
        obj={'method':'POST','url':FILE,'params':{'method':'create'},'body':b'', 'content_type':'application/x-www-form-urlencoded'}
        with patch.object(self.codec,'_run',return_value={**obj,'url':'https://example.org/'}):
            with self.assertRaisesRegex(StageFailure,'binding_mismatch'):
                self.codec.control(FILE,TARGET,{'method':'create'},self.form('directory'))
        with self.assertRaisesRegex(StageFailure,'input_rejected'):
            self.codec.control(FILE,TARGET,{'method':'create'},{**self.form('directory'),'access_token':'SYNTHETIC_ONLY'})

    def test_oversized_payload_is_rejected_before_helper(self):
        with patch('fast_transfer.sdk_codec.PART_LIMIT',4),patch.object(self.codec,'_run') as run:
            with self.assertRaisesRegex(StageFailure,'input_rejected'):self.codec.part(TARGET,'https://c.pcs.baidu.com','SYNTHETIC_ONLY',0,b'12345')
            run.assert_not_called()

    def fake_helper(self,folder,code):
        p=Path(folder)/'fake-helper';p.write_text('#!/usr/bin/python3 -I\n'+code);p.chmod(0o700)
        return p

    def test_guard_network_denial_survives_exec(self):
        with tempfile.TemporaryDirectory() as folder:
            p=self.fake_helper(folder,'import socket,errno\ntry: socket.socket()\nexcept OSError as e:\n assert e.errno==errno.EPERM\n print("network_denied")\nelse: raise SystemExit(1)\n')
            r=subprocess.run(['/usr/bin/python3','-I','-S','-B',str(self.guard),str(p)],capture_output=True,text=True,env={},timeout=5)
            self.assertEqual(r.returncode,0);self.assertEqual(r.stdout.strip(),'network_denied')

    def test_watchdog_kills_hung_helper(self):
        with tempfile.TemporaryDirectory() as folder:
            p=self.fake_helper(folder,'import time\ntime.sleep(10)\n')
            codec=SDKRequestEncoder(p,sha(p),self.guard,sha(self.guard),timeout=.1)
            with self.assertRaisesRegex(StageFailure,'deadline'):codec._run({'operation':'directory','target':TARGET})

    def test_output_limit_stops_bad_helper(self):
        with tempfile.TemporaryDirectory() as folder:
            p=self.fake_helper(folder,'import sys\nsys.stdout.write("x"*4096)\n')
            codec=SDKRequestEncoder(p,sha(p),self.guard,sha(self.guard))
            with patch('fast_transfer.sdk_codec.MAX_OUTPUT',128):
                with self.assertRaisesRegex(StageFailure,'output_rejected'):codec._run({'operation':'directory','target':TARGET})

    def test_memory_pressure_stops_before_helper_or_memfd(self):
        with patch.object(self.codec,'available_memory',return_value=0),patch.object(self.codec,'_run') as run,patch('os.memfd_create') as allocate:
            with self.assertRaisesRegex(StageFailure,'memory_budget'):
                self.codec.part(TARGET,'https://c.pcs.baidu.com','SYNTHETIC_ONLY',0,b'abc')
            run.assert_not_called();allocate.assert_not_called()

    def test_encoder_cannot_turn_get_form_into_a_mutation(self):
        http=FakeHTTP();protocol=BaiduProtocol(http,'Xtransfer',TARGET,ACCOUNT,TransferLimits(4*1024**2,16*1024**2,1024),diagnostic_rename_policy=True,request_encoder=self.codec)
        with patch.object(self.codec,'_run') as run:
            with self.assertRaisesRegex(StageFailure,'scope_invalid'):
                protocol.request('GET',FILE,{'method':'create'},self.form('directory'))
            run.assert_not_called()
        self.assertFalse(http.calls)

    def test_maximum_part_size_is_not_truncated_by_process_protocol(self):
        data=b'X'*(32*1024**2)
        req=self.codec.part(TARGET,'https://c.pcs.baidu.com','SYNTHETIC_MAX_ONLY',0,data)
        self.assertGreater(len(req.body),len(data))
        self.assertLessEqual(len(req.body),len(data)+4096)
        self.assertEqual(req.params['uploadid'],'SYNTHETIC_MAX_ONLY')

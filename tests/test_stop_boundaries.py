"""Bounded synthetic stop experiments in kernel-network-denied child processes."""
import errno
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from fast_transfer.upload_stage import TransferControl, TransferLimits, run_simulated_upload, StageFailure
from fast_transfer.simulated_cloud import MemoryCloud
from fast_transfer.space import BackendNeeds, DiskProbe, Volume, RESERVE, MARGIN
from fast_transfer.baidu_http import PinnedBaiduHTTPClient, HTTPRequest, RuntimeGrant


def guarded():
    try:p=socket.socket()
    except OSError as exc:return exc.errno==errno.EPERM
    p.close();return False


def upload_scenario(root,mode):
    data=b'ACGT'*4
    source=root/'source';source.mkdir();(source/'.receipts').mkdir()
    backend=root/'backend';backend.mkdir()
    entry=json.loads((REPO/'examples/ncbi-ecoli/manifest.json').read_text())['files'][0]
    entry.update(name='fixture.fna',size=len(data),md5=hashlib.md5(data).hexdigest())
    (source/'fixture.fna').write_bytes(data)
    receipt=source/'.receipts/0.json';receipt.write_text(json.dumps({'file':'fixture.fna','status':'source_verified','bytes':len(data),'md5':entry['md5'],'sha256':hashlib.sha256(data).hexdigest()}))
    control=TransferControl(deadline=time.monotonic()+5)
    entered=threading.Event();release=threading.Event();events=[];dropped=False
    class Probe(DiskProbe):
        def directory(self,path,writable=False):
            v=super().directory(path,writable)
            return Volume(v.device,v.inode,RESERVE+MARGIN-1,v.quantum) if dropped else v
    class Cloud(MemoryCloud):
        def put_part(self,session,index,part):
            nonlocal dropped
            if mode in ('cooperative_put','uncooperative_put','never_returns','low_space_stalled_put') and index==0:
                entered.set();release.wait()
                if mode=='uncooperative_put':
                    # A single bounded fake write after cancellation; deliberately ignores checkpoint.
                    events.append(len(part))
                    (root/'late-write').write_bytes(part)
                    session.parts[index]=part
                    self.operations.append('part:'+str(index))
                    return hashlib.md5(part).hexdigest()
            out=super().put_part(session,index,part);events.append(len(part))
            if mode=='cancel_before_commit' and index==3:control.cancel()
            if mode=='low_space_after_part':dropped=True
            return out
        def commit_new(self,session):
            super().commit_new(session)
            if mode=='cancel_after_commit':control.cancel()
        def readback(self,path,n):
            if mode=='stalled_readback':entered.set();release.wait()
            for part in super().readback(path,n):
                if mode=='cancel_readback':control.cancel()
                yield part
        def stop(self):
            if mode=='never_stop':entered.set();release.wait()
            out=super().stop()
            if mode=='cancel_during_stop':control.cancel()
            if mode=='stop_false':return False
            if mode=='stop_raises':raise RuntimeError('SYNTHETIC_NEVER_ECHO')
            return out
    cloud=Cloud();needs=BackendNeeds('direct-api',65536,262144,262144,'stream')
    limits=TransferLimits(4,16,4,4)
    results=[]
    def run():results.append(run_simulated_upload(entry,source/'fixture.fna',receipt,backend,'job-stop','Xtransfer',cloud,needs,limits,probe=Probe(),control=control))
    if mode=='already_cancelled':control.cancel()
    if mode=='expired':control=TransferControl(deadline=time.monotonic()-1)
    thread=threading.Thread(target=run,daemon=True);thread.start()
    report={}
    if mode in ('cooperative_put','uncooperative_put','never_returns','never_stop','stalled_readback','low_space_stalled_put'):
        assert entered.wait(3)
        start=time.monotonic()
        if mode=='low_space_stalled_put':dropped=True
        else:control.cancel()
        time.sleep(.03)
        report.update(blocked_after_signal=thread.is_alive(),observation_seconds=time.monotonic()-start,bytes_before_release=sum(events))
        if mode in ('never_returns','never_stop'):
            # Existing duplicate-job claim prevents another run, even while first is stuck.
            duplicate=run_simulated_upload(entry,source/'fixture.fna',receipt,backend,'job-stop','Xtransfer',Cloud(),needs,limits)
            report.update(result_available=bool(results),duplicate_reason=duplicate['reason'],bytes_after_result_unavailable=sum(events))
            return report  # daemon thread terminated only when this owned subprocess exits
        released_at=time.monotonic();release.set();thread.join(3)
        report['signal_to_return_seconds']=time.monotonic()-start
        report['release_to_return_seconds']=time.monotonic()-released_at
    else:thread.join(3)
    assert not thread.is_alive() and len(results)==1
    r=results[0];before=sum(events);time.sleep(.03)
    report.update(result=r,operations=cloud.operations,accepted_payload_bytes=sum(events),bytes_written_after_result=sum(events)-before,
                  max_part_bytes=max(events,default=0),late_file_bytes=(root/'late-write').stat().st_size if (root/'late-write').exists() else 0)
    return report


def http_scenario(root,mode):
    entered=threading.Event();release=threading.Event();calls=[];timeouts=[];read_sizes=[]
    cooperative=mode.startswith('cooperative_')
    point=mode.split('_',1)[1] if cooperative else mode
    class Sock:
        def settimeout(self,n):timeouts.append(n)
        def shutdown(self,how):
            if cooperative:release.set()
    class Response:
        status=200
        def getheaders(self):return [('Content-Length','4')]
        def read1(self,n):
            read_sizes.append(n)
            if point=='read':entered.set();release.wait()
            return b'ACGT'[:n]
        def close(self):
            if cooperative:release.set()
    response=Response()
    class Connection:
        sock=Sock()
        def set_debuglevel(self,n):assert n==0
        def request(self,*args,**kw):
            calls.append('request')
            if point in ('request','deadline'):entered.set();release.wait()
        def getresponse(self):
            calls.append('headers')
            if point=='headers':entered.set();release.wait()
            return response
        def close(self):
            if point=='close':entered.set();release.wait()
            if cooperative:release.set()
    target='/apps/Xtransfer/mvp-validation/job-stop/fixture.fna'
    grant=RuntimeGrant(True,target,'0'*64,'1'*64,'synthetic-only',time.monotonic()+60)
    client=PinnedBaiduHTTPClient(grant=grant,resolver=lambda _:['8.8.8.8'],connection_factory=lambda *args:Connection())
    request=HTTPRequest('GET','https://d.pcs.baidu.com/synthetic',target,'readback',auth=False)
    outcome=[]
    if mode=='headers_stop':
        stop_results=[]
        def headers():
            stop_results.append(client.stop())
            return [('Content-Length','4')]
        response.getheaders=headers
        try:client.exchange(request)
        except StageFailure as exc:outcome.append(exc.code)
        else:outcome.append('unexpected_success')
        return {'stop_results':stop_results,'outcome':outcome,'final_stop_confirmed':client.stop(),'reply_released':client.reply is None}
    if mode=='close':
        client.exchange(request)
        thread=threading.Thread(target=lambda:outcome.append(client.stop()),daemon=True)
        thread.start();assert entered.wait(3)
        second=client.stop()
        blocked=thread.is_alive();release.set();thread.join(3)
        assert not thread.is_alive()
        return {'second_stop_confirmed':second,'first_still_blocked':blocked,'first_stop_result':outcome,'final_stop_confirmed':client.stop()}
    def run():
        try:
            reply=client.exchange(request)
            if point=='read':list(reply.chunks(4,4))
            outcome.append('unexpected_success')
        except StageFailure as exc:outcome.append(exc.code)
    with patch('fast_transfer.baidu_http.REQUEST_BUDGET',.01 if mode=='deadline' else 120):
        thread=threading.Thread(target=run,daemon=True);thread.start();assert entered.wait(3)
        start=time.monotonic()
        if mode=='deadline':
            time.sleep(.03);first=None
        else:first=client.stop()
        stop_call_seconds=time.monotonic()-start if mode!='deadline' else None
        time.sleep(.03)
        blocked=thread.is_alive()
        release.set();thread.join(3);assert not thread.is_alive()
        final=client.stop()
    return {'first_stop_confirmed':first,'first_stop_call_seconds':stop_call_seconds,'blocked_after_stop':blocked,'outcome':outcome,'calls':calls,'final_stop_confirmed':final,'elapsed_seconds':time.monotonic()-start,'read_timeouts':timeouts,'requested_read_sizes':read_sizes}


class StopBoundaryTests(unittest.TestCase):
    def setUp(self):
        if not guarded():self.skipTest('requires kernel guard runner')
    def scenario(self,kind,mode):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);home=root/'home';home.mkdir()
            p=subprocess.Popen([sys.executable,'-I','-S','-B',__file__,'worker',kind,mode,tmp],env={'HOME':str(home),'XDG_CONFIG_HOME':str(home/'config'),'TMPDIR':tmp},stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,cwd=tmp)
            try:out,err=p.communicate(timeout=10)
            finally:
                if p.poll() is None:p.kill();p.communicate(timeout=3)
            self.assertEqual(p.returncode,0,err.decode());self.assertEqual(err,b'')
            result=json.loads(out)
            print('FT_STOP_EVIDENCE '+json.dumps({'kind':kind,'mode':mode,**result}),flush=True)
            return result
    def rejected(self,d):
        r=d['result'];self.assertEqual(r['status'],'manual_review')
        for k in ('simulated_delivery_eligible','delivery_eligible','cloud_verified'):self.assertFalse(r[k])
        self.assertEqual(d['bytes_written_after_result'],0)
        self.assertLessEqual(d['max_part_bytes'],4)
        return r
    def test_cancel_during_cooperative_stalled_part(self):
        d=self.scenario('upload','cooperative_put');r=self.rejected(d)
        self.assertTrue(d['blocked_after_signal']);self.assertEqual(d['bytes_before_release'],0)
        self.assertEqual(d['accepted_payload_bytes'],0);self.assertEqual(r['reason'],'transfer_cancelled')
    def test_cancel_cannot_interrupt_uncooperative_part_one_late_payload(self):
        d=self.scenario('upload','uncooperative_put');self.rejected(d)
        self.assertTrue(d['blocked_after_signal']);self.assertEqual(d['late_file_bytes'],4)
        self.assertEqual(d['accepted_payload_bytes'],4);self.assertNotIn('commit',d['operations'])
    def test_never_returning_call_has_no_stop_result_or_second_backend(self):
        d=self.scenario('upload','never_returns')
        self.assertTrue(d['blocked_after_signal']);self.assertFalse(d['result_available'])
        self.assertEqual(d['duplicate_reason'],'duplicate_job');self.assertEqual(d['bytes_after_result_unavailable'],0)
    def test_stalled_stop_has_no_confirmed_result(self):
        d=self.scenario('upload','never_stop')
        self.assertTrue(d['blocked_after_signal']);self.assertFalse(d['result_available'])
        self.assertEqual(d['duplicate_reason'],'duplicate_job')
        self.assertEqual(d['bytes_after_result_unavailable'],16)
    def test_cancel_while_readback_is_stalled(self):
        d=self.scenario('upload','stalled_readback');r=self.rejected(d)
        self.assertTrue(d['blocked_after_signal']);self.assertEqual(r['reason'],'transfer_cancelled')
        self.assertFalse(r['verification_complete'])
    def test_cancel_before_commit(self):
        d=self.scenario('upload','cancel_before_commit');self.rejected(d);self.assertNotIn('commit',d['operations'])
    def test_cancel_after_commit(self):
        d=self.scenario('upload','cancel_after_commit');self.rejected(d)
        self.assertIn('commit',d['operations']);self.assertNotIn('metadata',d['operations'])
    def test_cancel_during_readback(self):
        d=self.scenario('upload','cancel_readback');r=self.rejected(d)
        self.assertEqual(r['reason'],'transfer_cancelled');self.assertFalse(r['verification_complete'])
    def test_low_space_during_stalled_part_rejects_payload_on_release(self):
        d=self.scenario('upload','low_space_stalled_put');self.rejected(d)
        self.assertTrue(d['blocked_after_signal']);self.assertEqual(d['accepted_payload_bytes'],0)
        self.assertNotIn('commit',d['operations'])
    def test_low_space_after_one_part_rejects_new_payload(self):
        d=self.scenario('upload','low_space_after_part');self.rejected(d)
        self.assertEqual(d['accepted_payload_bytes'],4);self.assertNotIn('commit',d['operations'])
    def test_stop_false_or_exception_cannot_claim_success(self):
        for mode in ('stop_false','stop_raises'):
            d=self.scenario('upload',mode);r=self.rejected(d);self.assertIs(r['stop_confirmed'],False)
            self.assertTrue(r['verification_complete']);self.assertEqual(r['reason'],'adapter_stop_unconfirmed')
    def test_cancel_before_start_and_expired_deadline_have_no_payload(self):
        for mode,reason in [('already_cancelled','transfer_cancelled'),('expired','transfer_deadline')]:
            d=self.scenario('upload',mode);r=self.rejected(d)
            self.assertEqual(r['reason'],reason);self.assertEqual(d['operations'],[])
    def test_cancel_during_stop_revokes_verification(self):
        d=self.scenario('upload','cancel_during_stop');r=self.rejected(d);self.assertFalse(r['verification_complete'])
    def test_stop_during_header_validation_rejects_and_releases_reply(self):
        d=self.scenario('http','headers_stop');self.assertEqual(d['stop_results'],[False])
        self.assertEqual(d['outcome'],['http_stopped']);self.assertTrue(d['reply_released'])
        self.assertTrue(d['final_stop_confirmed'])
    def test_http_stalled_request_stop_is_unconfirmed_until_unwind(self):
        d=self.scenario('http','request');self.assertFalse(d['first_stop_confirmed'])
        self.assertTrue(d['blocked_after_stop']);self.assertTrue(d['final_stop_confirmed'])
        self.assertEqual(d['outcome'],['http_stopped']);self.assertNotIn('headers',d['calls'])
    def test_http_stalled_headers_stop_is_unconfirmed_until_unwind(self):
        d=self.scenario('http','headers');self.assertFalse(d['first_stop_confirmed'])
        self.assertTrue(d['blocked_after_stop']);self.assertEqual(d['outcome'],['http_stopped'])
    def test_http_stalled_read_stop_is_unconfirmed_until_unwind(self):
        d=self.scenario('http','read');self.assertFalse(d['first_stop_confirmed'])
        self.assertTrue(d['blocked_after_stop']);self.assertNotEqual(d['outcome'],['unexpected_success'])
        self.assertTrue(d['final_stop_confirmed']);self.assertTrue(0<d['read_timeouts'][0]<=30)
        self.assertEqual(d['requested_read_sizes'],[4])
    def test_cooperative_close_unblocks_header_and_reader(self):
        for mode in ('cooperative_headers','cooperative_read'):
            d=self.scenario('http',mode);self.assertFalse(d['blocked_after_stop'])
            self.assertNotEqual(d['outcome'],['unexpected_success']);self.assertTrue(d['final_stop_confirmed'])
    def test_concurrent_stop_does_not_confirm_while_close_is_blocked(self):
        d=self.scenario('http','close');self.assertFalse(d['second_stop_confirmed'])
        self.assertTrue(d['first_still_blocked']);self.assertEqual(d['first_stop_result'],[True])
        self.assertTrue(d['final_stop_confirmed'])
    def test_deadline_checked_after_stalled_request_returns(self):
        d=self.scenario('http','deadline');self.assertTrue(d['blocked_after_stop'])
        self.assertEqual(d['outcome'],['http_deadline']);self.assertNotIn('headers',d['calls'])


if __name__=='__main__' and len(sys.argv)>1 and sys.argv[1]=='worker':
    assert guarded()
    assert not list(Path(os.environ['HOME']).iterdir())
    kind,mode,root=sys.argv[2:]
    out=upload_scenario(Path(root),mode) if kind=='upload' else http_scenario(Path(root),mode)
    print(json.dumps(out),flush=True)

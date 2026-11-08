"""Explicit one-approval launcher. Existing token only, no generic live service."""
import argparse
import json
import os
import shutil
import signal
import sys
import threading
import time
from pathlib import Path

from .approved_sample import (APPROVAL_REF,NAME,SIZE,MD5,SHA256,SampleHTTP,
                             ApprovedSample,access_token_first_field,run_approved_sample)
from .baidu_http import RuntimeGrant
from .intake import load_manifest
from .isolated_candidate import new_candidate_job_id
from .space import BackendNeeds,DiskProbe,RESERVE,MARGIN
from .upload_stage import TransferLimits,StageFailure,safe_reason
from .workflow import bounded_json

RUN_NAME='approved-ncbi-20261108-once'


def net_bytes():
    rx=tx=0
    for line in Path('/proc/net/dev').read_text().splitlines()[2:]:
        interface,values=line.split(':');parts=values.split()
        if interface.strip()!='lo':rx+=int(parts[0]);tx+=int(parts[8])
    return rx,tx


class Samples:
    def __init__(self,root):
        self.root=root;self.minimum=None;self.peak_rss_kib=0;self.count=0
        self.event=threading.Event();self.thread=threading.Thread(target=self.loop,daemon=True)
    def sample(self):
        free=shutil.disk_usage(self.root).free
        self.minimum=free if self.minimum is None else min(self.minimum,free)
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith('VmRSS:'):self.peak_rss_kib=max(self.peak_rss_kib,int(line.split()[1]))
        self.count+=1
    def loop(self):
        while not self.event.wait(.02):
            try:self.sample()
            except OSError:pass
    def start(self):self.sample();self.thread.start()
    def stop(self):self.event.set();self.thread.join(1);self.sample()


def save(path,data):
    raw=json.dumps(data,sort_keys=True).encode()
    if len(raw)>65536:raise StageFailure('job_record_limit')
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())


def main():
    p=argparse.ArgumentParser(description='One explicitly approved NCBI upload/readback only; no sharing bypass.')
    p.add_argument('--approved',required=True,choices=[APPROVAL_REF])
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--authorization',type=Path,required=True)
    p.add_argument('--account-sha256',required=True)
    a=p.parse_args();os.umask(0o077)
    root=a.workspace/RUN_NAME
    client=sample=None
    result={'mode':'approved-live-sample','status':'manual_review','cloud_verified':False,
            'delivery_eligible':False,'share_status':'pending_app_permission_or_manual_client',
            'share_attempted':False,'share_link_created':False,'m6_domestic_receipt':False}
    started=time.monotonic();net0=net_bytes()
    try:
        DiskProbe().directory(a.workspace.absolute(),writable=True)
        # Durable approval-consumption marker. Never select another root after failure.
        root.mkdir(mode=0o700)
        save(root/'intent.json',{'approval_ref':APPROVAL_REF,'sample_sha256':SHA256,'started_utc':time.time(),'pid':os.getpid()})
        sample=Samples(root);sample.start()
        if shutil.disk_usage(root).free<RESERVE+MARGIN+SIZE+1024**2:raise StageFailure('disk_budget_exceeded')
        source=root/'source';source.mkdir();(source/'.receipts').mkdir();backend=root/'backend';backend.mkdir()
        receipt=bounded_json(a.receipt)
        expected={'file':NAME,'status':'source_verified','bytes':SIZE,'md5':MD5,'sha256':SHA256}
        if any(receipt.get(k)!=v for k,v in expected.items()):raise StageFailure('source_receipt_mismatch')
        save(source/'.receipts/0.json',expected)
        shutil.copyfile(a.source,source/NAME)
        job=new_candidate_job_id();target='/apps/Xtransfer/mvp-validation/'+job+'/'+NAME
        limits=TransferLimits(4*1024**2,16*1024**2,1024)
        grant=RuntimeGrant(True,target,a.account_sha256,SHA256,APPROVAL_REF,time.monotonic()+600)
        client=SampleHTTP(grant=grant,credential_provider=lambda:access_token_first_field(a.authorization))
        transport=ApprovedSample(client,a.account_sha256,limits,session_store=lambda record:save(root/'precreated-session.private.json',record))
        result=run_approved_sample(load_manifest(a.manifest)['files'][0],source/NAME,source/'.receipts/0.json',
            backend,job,transport,BackendNeeds('direct-api',65536,262144,262144,'stream'),limits)
        result.update(share_status='pending_app_permission_or_manual_client',share_attempted=False,
                      share_link_created=False,m6_domestic_receipt=False,approval_ref=APPROVAL_REF)
        if transport.facts is not None:
            result['account_probe']={k:v for k,v in transport.facts.items() if k!='account_sha256'}
        # IDs only for the verified exact object; no URL or auth body is persisted.
        result['identity_verified_on_request']=transport.facts is not None
        result['upload_observed_on_sample']=result['cloud_verified']
        if result['cloud_verified']:
            result['verified_object_id']=transport.objects[target][0]
        result['http_timings']=client.timings
        result['protocol_diagnostics']=transport.protocol_diagnostics
    except FileExistsError:
        # Existing marker means outcome must be inspected, never run again.
        print(json.dumps({'status':'manual_review','reason':'approval_already_consumed','cloud_verified':False}))
        return 2
    except Exception as exc:
        result['reason']=safe_reason(exc.code) if isinstance(exc,StageFailure) else 'approved_sample_local_failure'
    finally:
        if client is not None:
            try:result['client_stopped']=client.stop() is True
            except Exception:result['client_stopped']=False
            result['credential_reference_released']=client._credential is None
        if sample is not None:
            sample.stop()
            result.update(minimum_sampled_free_bytes=sample.minimum,space_sample_count=sample.count,
                          peak_rss_kib=sample.peak_rss_kib,sampler_stopped=not sample.thread.is_alive())
        if (sample is not None and sample.minimum<RESERVE) or result.get('client_stopped') is False or result.get('sampler_stopped') is False:
            result.update(cloud_verified=False,status='manual_review',reason='disk_budget_exceeded' if sample is not None and sample.minimum<RESERVE else 'adapter_stop_unconfirmed')
        net1=net_bytes()
        result.update(elapsed_seconds=round(time.monotonic()-started,6),
                      host_network_received_bytes=net1[0]-net0[0],host_network_sent_bytes=net1[1]-net0[1],
                      new_credential_files=0,existing_authorization_retained=True)
    save(root/'result.json',result)
    print(json.dumps(result))
    return 0 if result.get('cloud_verified') is True else 2


if __name__=='__main__':
    def stop(signum,frame):raise InterruptedError()
    signal.signal(signal.SIGTERM,stop)
    sys.exit(main())

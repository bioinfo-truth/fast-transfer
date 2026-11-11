"""Narrow recovery of the one known precommit failure; no new cloud directory."""
import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

from .approved_sample import (APPROVAL_REF,NAME,SHA256,SampleHTTP,ApprovedSample,
                             access_token_first_field,run_approved_sample)
from .baidu_http import RuntimeGrant
from .intake import load_manifest
from .sample_run import RUN_NAME,save,Samples,net_bytes
from .space import BackendNeeds,DiskProbe,RESERVE
from .upload_stage import TransferLimits,StageFailure,safe_reason
from .workflow import bounded_json


def main():
    p=argparse.ArgumentParser(description='Continue the approved sample in the verified same empty directory.')
    p.add_argument('--approved',required=True,choices=[APPROVAL_REF]);p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True)
    p.add_argument('--account-sha256',required=True)
    a=p.parse_args();os.umask(0o077);root=a.workspace/RUN_NAME
    client=sample=None;began=time.monotonic();net0=net_bytes()
    r={'mode':'approved-live-sample','status':'manual_review','cloud_verified':False,'delivery_eligible':False,
       'share_attempted':False,'share_link_created':False,'m6_domestic_receipt':False}
    try:
        DiskProbe().directory(root.absolute(),writable=True)
        old=bounded_json(root/'result.json');proof=bounded_json(root/'precommit-inspection.json')
        if (old.get('reason')!='protocol_json_invalid' or old.get('commit_attempted') is not False
                or type(old.get('requested_payload_bytes')) is not int or old['requested_payload_bytes']!=0
                or old.get('target')!=proof.get('target') or old.get('job_id')!=proof.get('job_id')
                or old.get('http_timings',[])[-1].get('operation')!='locateupload'):
            raise StageFailure('approved_sample_scope_invalid')
        save(root/'recovery-intent.json',{'approval_ref':APPROVAL_REF,'prior_commit_attempted':False,
             'purpose':'new precreate in same verified empty directory; old session not reused','started_utc':time.time(),'pid':os.getpid()})
        sample=Samples(root);sample.start()
        backend=root/'recovery-backend';backend.mkdir()
        source=root/'source';target=old['target'];limits=TransferLimits(4*1024**2,16*1024**2,1024)
        client=SampleHTTP(grant=RuntimeGrant(True,target,a.account_sha256,SHA256,APPROVAL_REF,time.monotonic()+600),
                          credential_provider=lambda:access_token_first_field(a.authorization))
        t=ApprovedSample(client,a.account_sha256,limits,session_store=lambda record:save(root/'recovered-session.private.json',record))
        t.inspect_empty_precommit_directory(proof)
        r=run_approved_sample(load_manifest(a.manifest)['files'][0],source/NAME,source/'.receipts/0.json',
                             backend,old['job_id'],t,BackendNeeds('direct-api',65536,262144,262144,'stream'),limits)
        r.update(same_cloud_directory=True,old_uploadid_reused=False,precommit_recovery=True,
                 share_attempted=False,share_link_created=False,m6_domestic_receipt=False,
                 share_status='pending_existing_app_share_capability_or_manual_client')
        if r['cloud_verified']:r['verified_object_id']=t.objects[target][0]
        if t.facts is not None:r['account_probe']={k:v for k,v in t.facts.items() if k!='account_sha256'}
        r.update(http_timings=client.timings,protocol_diagnostics=t.protocol_diagnostics)
    except FileExistsError:
        print(json.dumps({'status':'manual_review','reason':'recovery_intent_already_consumed','cloud_verified':False}));return 2
    except Exception as exc:r['reason']=safe_reason(exc.code) if isinstance(exc,StageFailure) else 'approved_recovery_local_failure'
    finally:
        if client is not None:
            try:r['client_stopped']=client.stop() is True
            except Exception:r['client_stopped']=False
            r['credential_reference_released']=client._credential is None
        if sample is not None:
            sample.stop();r.update(minimum_sampled_free_bytes=sample.minimum,space_sample_count=sample.count,
                                  peak_rss_kib=sample.peak_rss_kib,sampler_stopped=not sample.thread.is_alive())
        if (sample is not None and sample.minimum<RESERVE) or r.get('client_stopped') is False or r.get('sampler_stopped') is False:
            r.update(cloud_verified=False,status='manual_review',reason='adapter_stop_unconfirmed')
        net1=net_bytes();r.update(elapsed_seconds=round(time.monotonic()-began,6),new_credential_files=0,
                                 host_network_received_bytes=net1[0]-net0[0],host_network_sent_bytes=net1[1]-net0[1])
    save(root/'recovery-result.json',r);print(json.dumps(r));return 0 if r.get('cloud_verified') is True else 2


if __name__=='__main__':
    def stop(signum,frame):raise InterruptedError()
    signal.signal(signal.SIGTERM,stop);sys.exit(main())

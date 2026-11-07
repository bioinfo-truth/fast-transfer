"""M6 local-file checks and untrusted receipt review. No network or delivery gate."""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

from .intake import safe_name
from .workflow import Job, bounded_json, digest, fail, MAX_STATE
from .space import DiskProbe, RESERVE, MARGIN

FLAGS = ('cloud_verified','share_verified','location_verified','delivery_eligible','delivered')


def keys(obj, fields):
    if not isinstance(obj,dict) or set(obj)!=set(fields.split()):fail('acceptance_schema_invalid')


def number(value, nullable=False):
    if value is None and nullable:return
    if type(value) is not int or not 0<=value<=2**63-1:fail('acceptance_number_invalid')


def sha(value, nullable=False):
    if value is None and nullable:return
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):fail('acceptance_hash_invalid')


def label(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}',value):fail('acceptance_label_invalid')


def schema(obj, kind):
    if type(obj.get('schema_version')) is not int or obj['schema_version']!=1 or obj.get('kind')!=kind:
        fail('acceptance_schema_invalid')


def validate_spec(s):
    keys(s,'schema_version kind job_id manifest_sha256 mapping_sha256 source_version_sha256 file origin upstream share_expires_at')
    schema(s,'receipt_expectation');safe_name(s['job_id'])
    if len(s['job_id'])>64:fail('acceptance_label_invalid')
    for k in ('manifest_sha256','mapping_sha256','source_version_sha256'):sha(s[k])
    if s['origin'] not in ('simulation','unverified_operator_record'):fail('acceptance_untrusted_real_claim')
    f=s['file'];keys(f,'name bytes md5 sha256');safe_name(f['name']);number(f['bytes'])
    if not 0<f['bytes']<=1024**4:fail('acceptance_file_size_invalid')
    sha(f['sha256'])
    if not isinstance(f['md5'],str) or not re.fullmatch('[0-9a-f]{32}',f['md5']):fail('acceptance_hash_invalid')
    keys(s['upstream'],'source upload_readback share')
    for item in s['upstream'].values():
        keys(item,'kind record_sha256 completed_at outcome')
        if item['kind'] not in ('simulation','operator_claim','missing') or item['outcome'] not in ('completed','unknown','missing'):fail('acceptance_schema_invalid')
        sha(item['record_sha256'],True);number(item['completed_at'],True)
    number(s['share_expires_at'],True)


def prepare(job):
    view=job.view()
    if view['phase'] not in ('simulated_cloud_verified','share_draft'):fail('acceptance_workflow_not_ready')
    m=view['mapping']
    if 'sha256' not in m or 'md5' not in m:fail('acceptance_dual_hash_required')
    s={'schema_version':1,'kind':'receipt_expectation','job_id':view['job_id'],
       'manifest_sha256':view['manifest_sha256'],'mapping_sha256':view['mapping_sha256'],
       'source_version_sha256':m['source']['version_sha256'],
       'file':{'name':m['name'],'bytes':m['size'],'md5':m['md5'].lower(),'sha256':m['sha256'].lower()},
       'origin':'simulation','upstream':{},'share_expires_at':view.get('share',{}).get('expires_at')}
    for stage in ('source','upload_readback','share'):
        evidence=view.get('share') if stage=='share' else (m if 'simulated_target' in m else None)
        s['upstream'][stage]={'kind':'simulation' if evidence else 'missing',
                            'record_sha256':digest(evidence) if evidence else None,
                            'completed_at':None,'outcome':'completed' if evidence else 'missing'}
    validate_spec(s);return s


def validate_observation(o,s):
    keys(o,'schema_version kind job_id attempt_id spec_sha256 mapping_sha256 device_ref_sha256 location_claim location_evidence_sha256 acquisition observations')
    schema(o,'receipt_observation');label(o['attempt_id']);sha(o['device_ref_sha256'])
    sha(o['location_evidence_sha256'],True)
    if o['job_id']!=s['job_id'] or o['spec_sha256']!=digest(s) or o['mapping_sha256']!=s['mapping_sha256']:fail('acceptance_wrong_mapping')
    if o['location_claim'] not in ('mainland_cn','other','unknown'):fail('acceptance_schema_invalid')
    a=o['acquisition'];keys(a,'kind method started_at finished_at outcome')
    if a['kind'] not in ('simulation','operator_claim'):fail('acceptance_untrusted_real_claim')
    if a['method'] not in ('manual_browser','manual_client','local_copy') or a['outcome'] not in ('completed','unknown','failed'):fail('acceptance_schema_invalid')
    number(a['started_at'],True);number(a['finished_at'],True)
    keys(o['observations'],'elapsed_ms network_received_bytes minimum_free_bytes manual_steps')
    for v in o['observations'].values():number(v,True)


def review(s,o,checked_at):
    reasons=['real_upstream_evidence_not_verified','receiver_location_not_verified','authorization_not_verified']
    times=[]
    for stage in ('source','upload_readback','share'):
        item=s['upstream'][stage]
        if item['kind']=='missing' or item['record_sha256'] is None:reasons.append(stage+'_evidence_missing')
        if item['outcome']!='completed':reasons.append(stage+'_outcome_not_completed')
        if item['completed_at'] is None:reasons.append(stage+'_time_missing')
        else:times.append(item['completed_at'])
    a=o['acquisition']
    if s['origin']=='simulation' or any(x['kind']=='simulation' for x in s['upstream'].values()) or a['kind']=='simulation' or a['method']=='local_copy':reasons.append('simulation_is_not_real_receipt')
    if a['outcome']!='completed':reasons.append('receipt_outcome_not_completed')
    for key in ('started_at','finished_at'):
        if a[key] is None:reasons.append('receipt_time_missing')
        else:times.append(a[key])
    times.append(checked_at)
    if times!=sorted(times):reasons.append('time_order_invalid')
    if s['share_expires_at'] is None:reasons.append('share_expiry_missing')
    elif a['started_at'] is not None and a['started_at']>=s['share_expires_at']:reasons.append('share_expired_before_receipt')
    if o['location_claim']!='mainland_cn':reasons.append('mainland_receipt_not_declared')
    if any(v is None for v in o['observations'].values()):reasons.append('observations_incomplete')
    free=o['observations']['minimum_free_bytes']
    if free is not None and free<RESERVE:reasons.append('reported_space_below_reserve')
    return sorted(set(reasons))


def check_file(s,o,path):
    validate_spec(s);validate_observation(o,s)
    path=Path(path)
    if path.name!=s['file']['name']:fail('acceptance_wrong_filename')
    started=int(time.time());tick=time.monotonic_ns()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        before=os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1:fail('acceptance_file_invalid')
        if before.st_size!=s['file']['bytes']:fail('acceptance_length_mismatch')
        md,sh,total=hashlib.md5(),hashlib.sha256(),0
        while total<s['file']['bytes']:
            data=f.read(min(1024**2,s['file']['bytes']-total))
            if not data:break
            total+=len(data);md.update(data);sh.update(data)
        after=os.fstat(f.fileno())
        stamp=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if stamp(before)!=stamp(after) or stamp(os.lstat(path))!=stamp(after):fail('acceptance_file_changed')
    if total!=s['file']['bytes']:fail('acceptance_length_mismatch')
    matched=md.hexdigest()==s['file']['md5'] and sh.hexdigest()==s['file']['sha256']
    r={'schema_version':1,'kind':'local_receipt','mode':'local_only_unverified',
       'job_id':s['job_id'],'attempt_id':o['attempt_id'],'spec_sha256':digest(s),
       'mapping_sha256':s['mapping_sha256'],'observation':o,
       'file_check':{'bytes':total,'md5':md.hexdigest(),'sha256':sh.hexdigest(),'matches_expected':matched},
       'hash_started_at':started,'hash_finished_at':int(time.time()),
       'hash_elapsed_ms':(time.monotonic_ns()-tick)//1_000_000,
       'review_reasons':review(s,o,started),'status':'local_hashes_match' if matched else 'manual_review',
       **dict.fromkeys(FLAGS,False)}
    if not matched:r['review_reasons'].append('acceptance_dual_hash_mismatch')
    return r


def audit(s,receipts):
    validate_spec(s)
    if not isinstance(receipts,list) or not 1<=len(receipts)<=32:fail('acceptance_receipt_count_invalid')
    seen=set();reasons=set()
    for r in receipts:
        keys(r,'schema_version kind mode job_id attempt_id spec_sha256 mapping_sha256 observation file_check hash_started_at hash_finished_at hash_elapsed_ms review_reasons status '+' '.join(FLAGS))
        schema(r,'local_receipt')
        if r['mode']!='local_only_unverified' or any(r[k] is not False for k in FLAGS):fail('acceptance_untrusted_real_claim')
        if r['job_id']!=s['job_id'] or r['mapping_sha256']!=s['mapping_sha256'] or r['spec_sha256']!=digest(s):fail('acceptance_wrong_mapping')
        validate_observation(r['observation'],s)
        if r['attempt_id']!=r['observation']['attempt_id']:fail('acceptance_wrong_mapping')
        if r['attempt_id'] in seen:fail('acceptance_duplicate_attempt')
        seen.add(r['attempt_id'])
        for k in ('hash_started_at','hash_finished_at','hash_elapsed_ms'):number(r[k])
        if r['hash_finished_at']<r['hash_started_at']:reasons.add('time_order_invalid')
        f=r['file_check'];keys(f,'bytes md5 sha256 matches_expected')
        number(f['bytes']);sha(f['sha256'])
        if not isinstance(f['md5'],str) or not re.fullmatch('[0-9a-f]{32}',f['md5']):fail('acceptance_hash_invalid')
        matched=all(f[k]==s['file'][k] for k in ('bytes','md5','sha256'))
        if type(f['matches_expected']) is not bool or f['matches_expected']!=matched:fail('acceptance_file_claim_inconsistent')
        if r['status']!=('local_hashes_match' if matched else 'manual_review'):fail('acceptance_file_claim_inconsistent')
        if not matched:reasons.add('acceptance_dual_hash_mismatch')
        reasons.update(review(s,r['observation'],r['hash_started_at']))
        # Do not trust or echo submitted review_reasons/status, nor raw observations as proof.
    return {'schema_version':1,'kind':'receipt_audit','status':'unverified_records_reviewed',
            'unique_attempts':len(seen),'review_reasons':sorted(reasons),**dict.fromkeys(FLAGS,False)}


def write_new(path,obj):
    path=Path(path);v=DiskProbe().directory(path.absolute().parent,writable=True)
    if v.free<RESERVE+MARGIN+MAX_STATE:fail('acceptance_space_reserve')
    raw=json.dumps(obj,sort_keys=True).encode()
    if len(raw)>MAX_STATE:fail('acceptance_record_limit')
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())


def main():
    p=argparse.ArgumentParser(description='Offline M6 preparation; never marks real delivery.')
    sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('prepare');c.add_argument('--jobs-dir',type=Path,required=True);c.add_argument('--job-id',required=True)
    c=sub.add_parser('check');c.add_argument('spec',type=Path);c.add_argument('observation',type=Path);c.add_argument('file',type=Path)
    c=sub.add_parser('audit');c.add_argument('spec',type=Path);c.add_argument('receipts',type=Path)
    for c in sub.choices.values():c.add_argument('--output',type=Path)
    a=p.parse_args()
    try:
        if a.command=='prepare':out=prepare(Job(a.jobs_dir,a.job_id))
        elif a.command=='check':out=check_file(bounded_json(a.spec),bounded_json(a.observation),a.file)
        else:out=audit(bounded_json(a.spec),bounded_json(a.receipts))
        if a.output:write_new(a.output,out)
        print(json.dumps(out));return 2 if out.get('status')=='manual_review' else 0
    except Exception as exc:
        from .intake import InputProblem
        code=exc.code if isinstance(exc,InputProblem) else 'acceptance_local_input_or_io_failure'
        print(json.dumps({'status':'manual_review','reason':code,**dict.fromkeys(FLAGS,False)}));return 2


if __name__=='__main__':sys.exit(main())

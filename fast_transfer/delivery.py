"""Offline domestic handoff validation and immutable human delivery receipts.

Never invokes a native client or creates a share. Human observations remain
explicit attestations, not independent browser or cloud verification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

from .intake import InputProblem, MAX_FILES, safe_name
from .task import MAX_JSON, encoded, fail, private_directory, private_file, read_json


def matches(value, pattern):
    return type(value) is str and re.fullmatch(pattern,value) is not None


def load_private(path):
    path=Path(path).absolute();private_directory(path.parent);private_file(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        raw=stream.read(MAX_JSON+1)
    if len(raw)>MAX_JSON:fail('delivery_input_too_large')
    try:value=read_json(raw.decode('utf-8'))
    except UnicodeError:fail('delivery_input_invalid')
    return value,raw


def load_handoff(path, expected_sha256, expected_account_sha256):
    if not matches(expected_sha256,'[0-9a-f]{64}') or not matches(expected_account_sha256,'[0-9a-f]{64}'):
        fail('delivery_scope_invalid')
    doc,raw=load_private(path)
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:fail('delivery_handoff_changed')
    fields={'schema','job_id','task_spec_sha256','account_sha256','files','verification','sharing','delivered'}
    if (type(doc) is not dict or set(doc)!=fields or doc['schema']!='fast-transfer-handoff-v1'
            or not matches(doc['job_id'],'job-[0-9a-f]{32}')
            or not matches(doc['task_spec_sha256'],'[0-9a-f]{64}')
            or doc['account_sha256']!=expected_account_sha256
            or doc['verification']!='official-api-full-md5-sha256-readback'
            or doc['sharing']!='manual-native-client' or doc['delivered'] is not False
            or type(doc['files']) is not list or not 1<=len(doc['files'])<=MAX_FILES):
        fail('delivery_handoff_invalid')
    ids=set();paths=set()
    for index,item in enumerate(doc['files']):
        if (type(item) is not dict or set(item)!={'index','name','path','fs_id','bytes','md5','sha256'}
                or type(item['index']) is not int or item['index']!=index
                or type(item['bytes']) is not int or item['bytes']<=0
                or type(item['fs_id']) is not int or not 0<item['fs_id']<2**63
                or not matches(item['name'],r'[A-Za-z0-9][A-Za-z0-9._-]{0,179}')
                or not matches(item['path'],r'/apps/[A-Za-z][A-Za-z0-9_-]{0,63}/mvp-validation/'+doc['job_id']+'/'+re.escape(item['name']))
                or not matches(item['md5'],'[0-9a-f]{32}') or not matches(item['sha256'],'[0-9a-f]{64}')
                or item['fs_id'] in ids or item['path'] in paths):
            fail('delivery_handoff_invalid')
        safe_name(item['name'])
        ids.add(item['fs_id']);paths.add(item['path'])
    return doc


def record_delivery(handoff, expected_sha256, account_sha256, observation, output):
    doc=load_handoff(handoff,expected_sha256,account_sha256)
    observed,_=load_private(observation)
    if (type(observed) is not dict
            or set(observed)!={'schema','job_id','task_spec_sha256','metadata','share','recipient'}
            or observed['schema']!='fast-transfer-human-observation-v1'
            or observed['job_id']!=doc['job_id'] or observed['task_spec_sha256']!=doc['task_spec_sha256']):
        fail('delivery_observation_invalid')
    expected=[{k:item[k] for k in ('index','path','fs_id','bytes','md5')} for item in doc['files']]
    if encoded(observed['metadata'])!=encoded(expected):fail('delivery_native_metadata_mismatch')
    share=observed['share'];recipient=observed['recipient']
    if (type(share) is not dict or set(share)!={'url','code','created_at','expires_at'}
            or not matches(share['url'],r'https://pan\.baidu\.com/s/[A-Za-z0-9_-]{5,128}')
            or not matches(share['code'],'[A-Za-z0-9]{4}')
            or type(share['created_at']) is not int or type(share['expires_at']) is not int
            or not 0<share['created_at']<share['expires_at']
            or share['created_at']>time.time()+300):
        fail('delivery_share_invalid')
    if (type(recipient) is not dict or set(recipient)!={'status','logged_out','downloaded','confirmed_at'}
            or recipient['status'] not in ('pending','failed','confirmed')
            or type(recipient['logged_out']) is not bool or type(recipient['downloaded']) is not bool
            or (recipient['status']=='confirmed' and (not recipient['logged_out'] or not recipient['downloaded']))):
        fail('delivery_recipient_invalid')
    confirmed=recipient['status']=='confirmed'
    when=recipient['confirmed_at']
    if confirmed:
        if (type(when) is not int or not share['created_at']<=when<share['expires_at']
                or when>time.time()+300):fail('delivery_recipient_invalid')
    elif when is not None:fail('delivery_recipient_invalid')
    record={'schema':'fast-transfer-delivery-v1','handoff_sha256':expected_sha256,
            'handoff':doc,'human_observation':observed,
            'evidence':'operator-attestation-not-independent-verification',
            'recorded_at':int(time.time()),'delivered':confirmed}
    output=Path(output).absolute();private_directory(output.parent)
    raw=(encoded(record)+'\n').encode()
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    directory=os.open(output.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
    return {'status':'recipient_confirmed' if confirmed else 'recipient_'+recipient['status'],
            'receipt_sha256':hashlib.sha256(raw).hexdigest(),'delivered':confirmed,
            'evidence':'operator-attestation','network_actions':False}


def main(argv=None):
    p=argparse.ArgumentParser(description='Offline private handoff check and human recipient receipt.')
    p.add_argument('--handoff',required=True);p.add_argument('--handoff-sha256',required=True)
    p.add_argument('--account-sha256',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('check')
    rec=sub.add_parser('record');rec.add_argument('--observation',required=True);rec.add_argument('--output',required=True)
    a=p.parse_args(argv)
    try:
        if a.action=='check':
            doc=load_handoff(a.handoff,a.handoff_sha256,a.account_sha256)
            result={'status':'handoff_valid','files':len(doc['files']),'delivered':False,'network_actions':False}
        else:result=record_delivery(a.handoff,a.handoff_sha256,a.account_sha256,a.observation,a.output)
    except InputProblem as exc:
        print(json.dumps({'status':'manual_review','reason':exc.code,'delivered':False}));return 2
    except Exception:
        print(json.dumps({'status':'manual_review','reason':'delivery_local_failure','delivered':False}));return 2
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':sys.exit(main())

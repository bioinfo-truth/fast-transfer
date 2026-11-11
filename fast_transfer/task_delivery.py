"""Associate an explicitly approved private human receipt with its source task."""
import argparse
import hashlib
import json
import sys
import time

from .delivery import load_private, matches, validate_handoff, validate_observation
from .intake import InputProblem
from .task import Task, encoded, fail
from .task_handoff import verified_receipt
from .workflow import digest


def attach_receipt(task, receipt_path, expected_sha256):
    if not matches(expected_sha256,'[0-9a-f]{64}'):fail('delivery_receipt_digest_required')
    record,raw=load_private(receipt_path)
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:fail('delivery_receipt_changed')
    fields={'schema','handoff_sha256','handoff','human_observation','evidence','recorded_at','delivered'}
    if (type(record) is not dict or set(record)!=fields
            or record['schema']!='fast-transfer-delivery-v1'
            or record['evidence']!='operator-attestation-not-independent-verification'
            or type(record['recorded_at']) is not int or not 0<record['recorded_at']<=time.time()+300
            or type(record['delivered']) is not bool):fail('delivery_receipt_invalid')
    with task.locked() as db:
        manifest,settings,rows=task.context(db)
        if db.execute("SELECT 1 FROM operations WHERE outcome='unknown'").fetchone():fail('delivery_unknown_operation')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'upload_context','verifications'}<=tables:fail('delivery_real_verification_required')
        binding=db.execute('SELECT * FROM upload_context WHERE id=1').fetchone()
        if binding is None or binding['kind']!='official-api':fail('delivery_real_verification_required')
        doc=validate_handoff(record['handoff'],binding['account_sha256'])
        if (doc['job_id']!=task.job_id or doc['task_spec_sha256']!=task.spec_digest(manifest,settings)
                or doc['manifest_sha256']!=digest(manifest) or encoded(doc['manifest'])!=encoded(manifest)
                or hashlib.sha256((encoded(doc)+'\n').encode()).hexdigest()!=record['handoff_sha256']):
            fail('delivery_task_mismatch')
        if len(rows)!=len(doc['files']):fail('delivery_task_mismatch')
        for row,item in zip(rows,doc['files']):
            if row['phase'] not in ('cloud_verified','cleaned'):fail('delivery_real_verification_required')
            receipt=verified_receipt(task,db,manifest,settings,row)
            expected={'index':row['idx'],'name':manifest['files'][row['idx']]['name'],**receipt}
            if encoded(expected)!=encoded(item):fail('delivery_task_mismatch')
        confirmed=validate_observation(doc,record['human_observation'])
        if confirmed!=record['delivered']:fail('delivery_receipt_invalid')
        status=record['human_observation']['recipient']['status']
        db.execute('CREATE TABLE IF NOT EXISTS deliveries(receipt_sha256 TEXT PRIMARY KEY, status TEXT NOT NULL, receipt TEXT NOT NULL, attached INTEGER NOT NULL)')
        db.commit()
        existing=db.execute('SELECT receipt FROM deliveries WHERE receipt_sha256=?',(expected_sha256,)).fetchone()
        if existing is not None:
            if existing['receipt']!=encoded(record):fail('delivery_receipt_invalid')
            return {'status':'receipt_already_attached',
                    'delivered':db.execute("SELECT 1 FROM deliveries WHERE status='confirmed'").fetchone() is not None,
                    'receipt_delivered':confirmed,'network_actions':False}
        if not confirmed and db.execute("SELECT 1 FROM deliveries WHERE status='confirmed'").fetchone():
            fail('delivery_confirmed_cannot_regress')
        with db:db.execute('INSERT INTO deliveries VALUES(?,?,?,?)',(expected_sha256,status,encoded(record),int(time.time())))
        return {'status':'receipt_attached','recipient':status,'delivered':confirmed,
                'evidence':'operator-attestation','network_actions':False}


def main(argv=None):
    p=argparse.ArgumentParser(description='Associate a private human receipt with its verified source task, offline.')
    p.add_argument('--tasks-dir',required=True);p.add_argument('job_id')
    p.add_argument('--receipt',required=True);p.add_argument('--receipt-sha256',required=True)
    a=p.parse_args(argv)
    try:result=attach_receipt(Task(a.tasks_dir,a.job_id),a.receipt,a.receipt_sha256)
    except InputProblem as exc:
        print(json.dumps({'status':'manual_review','reason':exc.code}));return 2
    except Exception:
        print(json.dumps({'status':'manual_review','reason':'delivery_attach_local_failure'}));return 2
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':sys.exit(main())

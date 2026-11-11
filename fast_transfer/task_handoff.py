"""Explicit private metadata export after real upload and full readback.

No network, credentials, share creation, or delivery assertion.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from .intake import InputProblem
from .task import Task, encoded, fail, private_directory, read_json


def export_handoff(task, destination):
    """Export only fully verified real objects, never sessions or raw records."""
    destination = Path(destination).absolute()
    private_directory(destination.parent)
    with task.locked() as db:
        manifest, settings, rows = task.context(db)
        if db.execute("SELECT 1 FROM operations WHERE outcome='unknown'").fetchone():
            fail('handoff_unknown_operation')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'upload_context','verifications'} <= tables:
            fail('handoff_real_verification_required')
        binding = db.execute('SELECT * FROM upload_context WHERE id=1').fetchone()
        if (binding is None or binding['kind'] != 'official-api'
                or not re.fullmatch('[0-9a-f]{64}', binding['account_sha256'])):
            fail('handoff_real_verification_required')
        files=[]
        for row in rows:
            if row['phase'] not in ('cloud_verified','cleaned'):
                fail('handoff_all_files_required')
            verified = db.execute('SELECT * FROM verifications WHERE idx=?',(row['idx'],)).fetchone()
            if verified is None or verified['kind'] != 'official-api':
                fail('handoff_real_verification_required')
            receipt=read_json(verified['receipt'])
            source=read_json(row['source_receipt'])
            entry=manifest['files'][row['idx']]
            target='/apps/'+settings['app_name']+'/mvp-validation/'+task.job_id+'/'+entry['name']
            if (set(receipt) != {'path','fs_id','bytes','md5','sha256'}
                    or receipt['path'] != target
                    or type(receipt['fs_id']) is not int or not 0 < receipt['fs_id'] < 2**63
                    or type(receipt['bytes']) is not int or receipt['bytes'] != entry['size']
                    or any(receipt.get(k) != source.get(k) for k in ('bytes','md5','sha256'))
                    or not re.fullmatch('[0-9a-f]{32}',receipt['md5'])
                    or not re.fullmatch('[0-9a-f]{64}',receipt['sha256'])):
                fail('handoff_verification_mismatch')
            # Deliberate whitelist: never dump the manifest, DB, or upload session.
            files.append({'index':row['idx'],'name':entry['name'],**receipt})
        document={'schema':'fast-transfer-handoff-v1','job_id':task.job_id,
                  'task_spec_sha256':task.spec_digest(manifest,settings),
                  'account_sha256':binding['account_sha256'],'files':files,
                  'verification':'official-api-full-md5-sha256-readback',
                  'sharing':'manual-native-client','delivered':False}
        raw=(encoded(document)+'\n').encode()
        # The private immutable snapshot must never overwrite another handoff.
        fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            directory=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        except BaseException:
            # Keep a possibly incomplete snapshot for inspection, never claim it valid.
            raise
    return {'status':'handoff_exported','files':len(files),
            'handoff_sha256':hashlib.sha256(raw).hexdigest(),'delivered':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description='Export verified task metadata to a new private file; no network.')
    parser.add_argument('--tasks-dir',type=Path,required=True)
    parser.add_argument('job_id');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=export_handoff(Task(args.tasks_dir,args.job_id),args.output)
    except InputProblem as exc:
        print(json.dumps({'status':'manual_review','reason':exc.code,'delivered':False}));return 2
    except Exception:
        print(json.dumps({'status':'manual_review','reason':'handoff_local_failure','delivered':False}));return 2
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':sys.exit(main())

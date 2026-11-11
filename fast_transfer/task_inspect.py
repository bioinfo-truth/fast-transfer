"""Resolve one unknown commit only by exact-object read-only full verification.

The operator supplies a private object locator, never a success assertion.
Absent/mismatched objects remain unknown and are never retried here.
"""
import hashlib
import time

from .delivery import load_private
from .task import encoded, fail, read_json, MAX_RECEIPT
from .task_upload import TaskProtocol, UploadContext, _operation, METADATA_CAP
from .space import BackendNeeds, SpaceGuard
from .upload_stage import TransferControl, TransferLimits, open_regular, source_identity, file_stamp
from .workflow import digest


def inspect_commit(task, factory, account_sha256, proof_path, *, approved_task_spec_sha256, timeout=600):
    if type(timeout) not in (int,float) or not 0<timeout<=900:fail('task_upload_scope_invalid')
    proof,_=load_private(proof_path)
    if (type(proof) is not dict or set(proof)!={'job_id','task_spec_sha256','path','fs_id','bytes'}
            or proof['job_id']!=task.job_id or proof['task_spec_sha256']!=approved_task_spec_sha256
            or type(proof['fs_id']) is not int or not 0<proof['fs_id']<2**63):
        fail('task_inspection_locator_invalid')
    control=TransferControl(deadline=time.monotonic()+timeout)
    with task.locked() as db:
        manifest,settings,rows=task.context(db)
        spec=task.spec_digest(manifest,settings)
        if spec!=approved_task_spec_sha256:fail('task_upload_scope_invalid')
        unknowns=db.execute("SELECT * FROM operations WHERE outcome='unknown'").fetchall()
        if len(unknowns)!=1 or unknowns[0]['operation']!='commit':
            fail('task_inspection_commit_only')
        unknown=unknowns[0];index=unknown['idx'];row=rows[index];entry=manifest['files'][index]
        target='/apps/'+settings['app_name']+'/mvp-validation/'+task.job_id+'/'+entry['name']
        if (row['phase']!='uploading' or proof['path']!=target or type(proof['bytes']) is not int
                or proof['bytes']!=entry['size']):fail('task_inspection_locator_invalid')
        binding=db.execute('SELECT * FROM upload_context WHERE id=1').fetchone()
        if binding is None or binding['account_sha256']!=account_sha256:fail('task_backend_identity_changed')
        extras=[task.root/name for name in ('task.sqlite3','task.sqlite3-journal','task.sqlite3-wal','task.sqlite3-shm')]
        guard=SpaceGuard({entry['name']:entry['size']},task.file_root(index),
                         BackendNeeds('direct-api',65536,METADATA_CAP,METADATA_CAP,'stream'),task.root,backend_extra_files=extras)
        context=UploadContext(guard,control);context.stage='readback';context.checkpoint()
        protocol=None;verified=None;stopped=False
        with open_regular(task.source_path(index,entry)) as source:
            identity,_,stamp=source_identity(source,context.checkpoint,settings['part_bytes'],entry['size'])
            saved=read_json(row['source_receipt'])
            if (any(saved.get(k)!=identity[k] for k in ('bytes','md5','sha256'))
                    or any(entry.get(k) and entry[k].lower()!=identity[k] for k in ('md5','sha256'))):
                fail('source_changed')
            intent={'task_spec_sha256':spec,'account_sha256':account_sha256,'source_sha256':identity['sha256'],
                    'target':target,'operation':'commit','part':-1,'part_md5':None}
            if unknown['part']!=-1 or unknown['intent_sha256']!=digest(intent):fail('task_upload_state_invalid')
            limits=TransferLimits(settings['part_bytes'],settings['max_file_bytes'],1024)
            try:
                protocol=factory(target,identity,limits,settings['app_name'])
                if (type(protocol) is not TaskProtocol or protocol.account!=account_sha256 or protocol.target!=target
                        or protocol.kind!=binding['kind']):fail('task_backend_identity_changed')
                protocol.attach(context)
                if protocol.kind=='official-api':
                    grant=protocol.client.grant;grant.check(target)
                    if grant.account_sha256!=account_sha256 or grant.source_sha256!=identity['sha256']:
                        fail('task_upload_scope_invalid')
                    protocol.client.read_only=True
                # No before_mutation hook and no write arm are ever installed.
                protocol.probe()
                directory=_operation(db,0,'directory')
                if directory is None or directory['outcome']!='confirmed':fail('task_upload_state_invalid')
                directory_receipt=read_json(directory['receipt'])
                if directory_receipt['path']!=protocol.directory:fail('task_upload_state_invalid')
                protocol.directory_id=directory_receipt['fs_id'];protocol.verify_directory()
                protocol.objects[target]=(proof['fs_id'],entry['size'])
                md5,sha,total=hashlib.md5(),hashlib.sha256(),0
                for data in protocol.readback(target,limits.readback_bytes):
                    context.checkpoint();total+=len(data);md5.update(data);sha.update(data)
                if {'bytes':total,'md5':md5.hexdigest(),'sha256':sha.hexdigest()}!=identity:
                    fail('readback_hash_or_length_mismatch')
                if file_stamp(source)!=stamp:fail('source_changed')
                verified={'path':target,'fs_id':proof['fs_id'],**identity}
            finally:
                if protocol is not None:stopped=protocol.stop() is True
        if not stopped or verified is None:fail('adapter_stop_unconfirmed')
        context.metadata_write()
        receipt={'path':target,'fs_id':proof['fs_id'],'size':entry['size']}
        # A crash after saving commit confirmation can only cause another readback;
        # run_next already skips confirmed commits and never resends them.
        task.finish_operation(index,'commit',unknown['intent_sha256'],receipt,_db=db)
        with db:
            db.execute('INSERT OR REPLACE INTO verifications VALUES(?,?,?,?)',(index,protocol.kind,encoded(verified,MAX_RECEIPT),int(time.time())))
            db.execute('UPDATE files SET phase=?,reason=NULL WHERE idx=?',('cloud_verified' if protocol.kind=='official-api' else 'test_cloud_verified',index))
        return {'status':'unknown_commit_verified','cloud_verified':protocol.kind=='official-api',
                'backend':protocol.kind,'index':index,'remote_mutations':False,'delivered':False}

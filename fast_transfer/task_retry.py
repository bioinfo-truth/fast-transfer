"""Explicit one-shot replay of one unknown nonfinal part, with retained history.

This is an operator policy exception, not inspection or proof the first call
failed. No directory/precreate/commit/share replay, no new upload session.
"""
import re
import time

from .task import encoded, read_json, MAX_RECEIPT
from .task_upload import TaskProtocol, UploadContext, METADATA_CAP, _operation, request_fingerprint
from .space import BackendNeeds, SpaceGuard
from .upload_stage import TransferControl, TransferLimits, open_regular, source_identity, file_stamp
from .baidu_http import fail
from .workflow import digest


def retry_unknown_part(task, factory, account_sha256, part, *, approved_task_spec_sha256, timeout=600):
    if (type(part) is not int or not 0 <= part < 1024
            or type(account_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',account_sha256)
            or type(timeout) not in (int,float) or not 0 < timeout <= 900):
        fail('task_retry_scope_invalid')
    with task.locked() as db:
        manifest,settings,rows=task.context(db);spec=task.spec_digest(manifest,settings)
        if spec!=approved_task_spec_sha256:fail('task_retry_scope_invalid')
        unknowns=db.execute("SELECT * FROM operations WHERE outcome='unknown'").fetchall()
        if len(unknowns)!=1 or unknowns[0]['operation']!='part' or unknowns[0]['part']!=part:
            fail('task_retry_requires_one_unknown_part')
        original=unknowns[0];index=original['idx'];entry=manifest['files'][index]
        if rows[index]['phase']!='uploading' or part >= (entry['size']-1)//settings['part_bytes']:
            fail('task_retry_nonfinal_part_required')
        if _operation(db,index,'commit') is not None:fail('task_retry_scope_invalid')
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='part_retry_attempts'").fetchone():
            if db.execute('SELECT 1 FROM part_retry_attempts WHERE idx=? AND part=?',(index,part)).fetchone():
                fail('task_retry_already_attempted')
        binding=db.execute('SELECT * FROM upload_context WHERE id=1').fetchone()
        if binding is None or binding['account_sha256']!=account_sha256:fail('task_backend_identity_changed')
        extras=[task.root/n for n in ('task.sqlite3','task.sqlite3-journal','task.sqlite3-wal','task.sqlite3-shm')]
        guard=SpaceGuard({entry['name']:entry['size']},task.file_root(index),
                         BackendNeeds('direct-api',65536,METADATA_CAP,METADATA_CAP,'stream'),task.root,backend_extra_files=extras)
        context=UploadContext(guard,TransferControl(deadline=time.monotonic()+timeout))
        protocol=None;stopped=False;receipt=None
        with open_regular(task.source_path(index,entry)) as source:
            identity,blocks,stamp=source_identity(source,context.checkpoint,settings['part_bytes'],entry['size'])
            stored=read_json(rows[index]['source_receipt'])
            if (any(stored.get(k)!=identity[k] for k in ('bytes','md5','sha256'))
                    or any(entry.get(k) and entry[k].lower()!=identity[k] for k in ('md5','sha256'))):fail('source_changed')
            target='/apps/'+settings['app_name']+'/mvp-validation/'+task.job_id+'/'+entry['name']
            intent={'task_spec_sha256':spec,'account_sha256':account_sha256,'source_sha256':identity['sha256'],
                    'target':target,'operation':'part','part':part,'part_md5':blocks[part]}
            if original['intent_sha256']!=digest(intent):fail('task_upload_state_invalid')
            pre=_operation(db,index,'precreate');directory=_operation(db,0,'directory')
            if pre is None or directory is None or pre['outcome']!='confirmed' or directory['outcome']!='confirmed':fail('task_upload_state_invalid')
            session_receipt=read_json(pre['receipt']);directory_receipt=read_json(directory['receipt'])
            if (session_receipt['path']!=target or session_receipt['size']!=entry['size']
                    or session_receipt['hashes']!=blocks or part not in session_receipt['required']
                    or session_receipt['directory_id']!=directory_receipt['fs_id']):fail('task_upload_state_invalid')
            limits=TransferLimits(settings['part_bytes'],settings['max_file_bytes'],1024);limits.validate(entry['size'])
            try:
                protocol=factory(target,identity,limits,settings['app_name'])
                if (type(protocol) is not TaskProtocol or protocol.account!=account_sha256 or protocol.target!=target
                        or protocol.kind!=binding['kind']):fail('task_backend_identity_changed')
                protocol.attach(context)
                if protocol.kind=='official-api':
                    grant=protocol.client.grant;grant.check(target)
                    if grant.account_sha256!=account_sha256 or grant.source_sha256!=identity['sha256']:fail('task_retry_scope_invalid')
                facts=protocol.probe()
                if min(entry['size'],limits.part_bytes)>facts['documented_part_bytes']:fail('protocol_account_limits_unknown')
                if protocol.request_encoder.available_memory()<protocol.request_encoder.memory_admission_bytes(limits.part_bytes)+128*1024**2:fail('sdk_codec_memory_budget')
                protocol.directory_id=directory_receipt['fs_id']
                if directory_receipt['path']!=protocol.directory:fail('task_upload_state_invalid')
                protocol.verify_directory();protocol.reserved=True
                session=protocol.restore_session(session_receipt)
                size=min(limits.part_bytes,entry['size']-part*limits.part_bytes)
                source.seek(part*limits.part_bytes);data=source.read(size)
                if file_stamp(source)!=stamp:fail('source_changed')
                sent=False
                def before(req):
                    nonlocal sent
                    if (sent or req.method!='POST' or req.purpose!='upload' or req.binding!=target
                            or req.params.get('method')!='upload' or str(req.params.get('partseq'))!=str(part)
                            or req.params.get('uploadid')!=session.uploadid or req.params.get('path')!=target):fail('task_retry_scope_invalid')
                    if file_stamp(source)!=stamp:fail('source_changed')
                    context.metadata_write()
                    db.execute('''CREATE TABLE IF NOT EXISTS part_retry_attempts
                      (idx INTEGER NOT NULL, part INTEGER NOT NULL, original_unknown TEXT NOT NULL,
                       intent TEXT NOT NULL, request_sha256 TEXT NOT NULL, outcome TEXT NOT NULL,
                       receipt TEXT, started INTEGER NOT NULL, PRIMARY KEY(idx,part))''')
                    with db:
                        db.execute('INSERT INTO part_retry_attempts VALUES(?,?,?,?,?,?,?,?)',
                            (index,part,encoded(dict(original),MAX_RECEIPT),encoded(intent,MAX_RECEIPT),
                             request_fingerprint(req),'unknown',None,int(time.time())))
                    sent=True
                protocol.before_mutation=before
                md5=protocol.put_part(session,part,data)
                if not sent or file_stamp(source)!=stamp:fail('source_changed')
                receipt={'part':part,'md5':md5,'bytes':size}
                context.metadata_write()
                # Retain the original unknown snapshot forever. The operations
                # row is the current projection, confirmed by this NEW attempt.
                with db:db.execute("UPDATE part_retry_attempts SET outcome='confirmed',receipt=? WHERE idx=? AND part=?",
                                   (encoded(receipt),index,part))
                task.finish_operation(index,'part',original['intent_sha256'],receipt,part=part,_db=db)
            finally:
                if protocol is not None:stopped=protocol.stop() is True
        if not stopped or receipt is None:fail('adapter_stop_unconfirmed')
        return {'status':'part_retry_confirmed','index':index,'part':part,'bytes':receipt['bytes'],
                'attempts':1,'original_outcome':'unknown','original_record_retained':True,
                'cloud_verified':False,'delivered':False,'stop_confirmed':True}

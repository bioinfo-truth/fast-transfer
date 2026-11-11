"""One-file-at-a-time journaled SDK/API upload for generic private Tasks.

No credential discovery, refresh, implicit grant or remote cleanup. The public
CLI requires an explicit task/manifest approval and authorization-file location.
Synthetic backend observations stay visibly separate from live verification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import sqlite3
import time
import urllib.parse

from .approved_sample import access_token_first_field
from .baidu_http import PinnedBaiduHTTPClient, RuntimeGrant, HTTPRequest, fail
from .baidu_protocol import BaiduProtocol, UploadSession, FILE, METAS
from .isolated_candidate import IsolatedBaiduCandidate
from .intake import InputProblem
from .sdk_codec import SDKRequestEncoder
from .space import BackendNeeds, SpaceGuard
from .task import Task, encoded, read_json, private_file, MAX_RECEIPT
from .upload_stage import TransferLimits, TransferControl, open_regular, source_identity, file_stamp, StageFailure, safe_reason
from .workflow import digest
from .resources import ResourceSamples

METADATA_CAP = 64*1024**2
METADATA_GROWTH = 2*MAX_RECEIPT+65536


def request_fingerprint(req):
    return digest({'method':req.method,'url':req.url,'binding':req.binding,
                   'purpose':req.purpose,'params':req.params,'content_type':req.content_type,
                   'body_sha256':hashlib.sha256(req.body).hexdigest()})


class TaskHTTP(PinnedBaiduHTTPClient):
    mode = 'task-api-http'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._armed = None
        self.read_only = False

    def exchange(self, req):
        if self.read_only and req.method != 'GET':fail('task_inspection_read_only')
        return super().exchange(req)

    def arm(self, req):
        self.grant.check(req.binding)
        if self._armed is not None:fail('task_write_not_journaled')
        self._armed = request_fingerprint(req)

    def authorize_write(self, req):
        armed, self._armed = self._armed, None
        if armed is None or request_fingerprint(req) != armed:
            fail('task_write_not_journaled')


class TaskProtocol(BaiduProtocol):
    """Existing protocol with isolated-directory policy and a durable-write hook."""
    verify_directory = IsolatedBaiduCandidate.verify_directory

    def __init__(self, client, app_name, target, account_sha256, limits, encoder, *, test_mode=False):
        if (test_mode and client.mode != 'fake-http'
                or not test_mode and type(client) is not TaskHTTP
                or type(encoder) is not SDKRequestEncoder):
            fail('task_backend_invalid')
        super().__init__(client,app_name,target,account_sha256,limits,request_encoder=encoder)
        self.kind = 'test-fixture' if test_mode else 'official-api'
        self.directory = target.rsplit('/',1)[0]
        self.directory_id = None
        self.before_mutation = None
        self.precreate_sink = None
        self.last_commit = None
        self.diagnostics = []
        # The official SDK PrecreateResponse has no required path field. Binding
        # comes from the exact generated request + fresh directory verification;
        # a supplied conflicting response path still fails, and is never filled in.
        self.precreate_path_optional = True

    def write_gate(self):
        self.checkpoint()
        if self.facts is None:self.probe()
        if self.kind == 'official-api':self.client.grant.check(self.target)

    def exchange_json(self, req):
        if req.method == 'POST':
            if self.before_mutation is None:fail('task_write_not_journaled')
            self.before_mutation(req)
            if self.kind == 'official-api':self.client.arm(req)
        obj = super().exchange_json(req)
        if req.method == 'POST' and req.params.get('method') == 'create':
            form = dict(urllib.parse.parse_qsl(req.body.decode('ascii'),strict_parsing=True))
            if form.get('isdir') == '1':
                if type(obj.get('fs_id')) is not int or obj['fs_id'] <= 0:fail('protocol_shape_invalid')
                self.directory_id = obj['fs_id']
            else:self.last_commit = obj
        return obj

    def record_response_shape(self, summary):
        item = {'operation': summary.get('operation')}
        for name in ('errno','error_code'):
            value = summary.get(name)
            if type(value) is int and -1000000 <= value <= 1000000:item[name] = value
        if len(self.diagnostics) < 16:self.diagnostics.append(item)

    def precreated_checkpoint(self, record):
        if self.precreate_sink is None:fail('task_write_not_journaled')
        self.precreate_sink(record)

    def restore_session(self, receipt):
        host = self.locate_upload_host(self.target,receipt['uploadid'])
        session = UploadSession(self.target,receipt['size'],tuple(receipt['hashes']),
                                receipt['uploadid'],host,tuple(receipt['required']))
        self.sessions.append(session)
        self.confirmations[id(session)] = {}
        self.session_bindings[id(session)] = (session.path,session.size,session.hashes,
                                             session.uploadid,session.host,session.required)
        return session


class UploadContext:
    def __init__(self, guard, control):
        self.guard, self.control, self.stage = guard, control, 'upload'
    def checkpoint(self):
        self.control.checkpoint()
        return self.guard.check(self.stage)
    def metadata_write(self):
        self.control.checkpoint()
        return self.guard.check(self.stage,growth={'backend_extra':METADATA_GROWTH})


def _tables(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS upload_context
          (id INTEGER PRIMARY KEY CHECK(id=1), kind TEXT NOT NULL, account_sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS verifications
          (idx INTEGER PRIMARY KEY, kind TEXT NOT NULL, receipt TEXT NOT NULL, completed INTEGER NOT NULL);
    ''')


def _operation(db, index, operation, part=-1):
    row = db.execute('SELECT * FROM operations WHERE idx=? AND operation=? AND part=?',
                     (index,operation,part)).fetchone()
    if row is not None and row['outcome'] not in ('unknown','confirmed'):
        fail('task_upload_state_invalid')
    return row


def run_next(task, factory, account_sha256, *, timeout=600, checkpoint_hook=None, approved_task_spec_sha256=None):
    """Upload and stream-verify one source; factory is trusted code, never JSON.

    The task lock spans the worker invocation. The factory gets the independently
    rehashed source identity and must return TaskProtocol; mode/account binding is
    durable and forbids promoting synthetic receipts into a real task.
    """
    if (type(account_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',account_sha256)
            or type(timeout) not in (int,float) or not 0 < timeout <= 900):
        fail('task_upload_scope_invalid')
    control = TransferControl(deadline=time.monotonic()+timeout)
    with task.locked() as db:
        manifest, settings, rows = task.context(db)
        spec = task.spec_digest(manifest,settings)
        if approved_task_spec_sha256 is not None and approved_task_spec_sha256 != spec:
            fail('task_upload_scope_invalid')
        # Never read credentials/reach the factory when a prior effect is unknown.
        if db.execute("SELECT 1 FROM operations WHERE outcome='unknown'").fetchone():
            fail('task_unknown_operation_requires_inspection')
        row = next((r for r in rows if r['phase'] not in ('cloud_verified','test_cloud_verified','cleaned')),None)
        if row is None:return {'status':'no_pending_upload','cloud_verified':False}
        index = row['idx'];entry = manifest['files'][index]
        if row['phase'] not in ('source_verified','uploading'):
            fail('task_source_not_verified')
        folder = task.file_root(index)
        needs = BackendNeeds('direct-api',65536,METADATA_CAP,METADATA_CAP,'stream')
        extras = [task.root/name for name in ('task.sqlite3','task.sqlite3-journal','task.sqlite3-wal','task.sqlite3-shm')]
        guard = SpaceGuard({entry['name']:entry['size']},folder,needs,task.root,backend_extra_files=extras)
        context = UploadContext(guard,control);context.checkpoint()
        source = protocol = None
        stop_confirmed = False
        active = None
        verified = None
        try:
            source = open_regular(task.source_path(index,entry))
            identity, blocks, stamp = source_identity(source,context.checkpoint,settings['part_bytes'],entry['size'])
            stored = read_json(row['source_receipt'])
            if (any(stored.get(k) != identity[k] for k in ('bytes','md5','sha256'))
                    or any(entry.get(k) and entry[k].lower()!=identity[k] for k in ('md5','sha256'))):
                fail('source_changed')
            if read_json(row['source_stamp']) != list(stamp):
                # A restored identical source is safe only after independent full
                # hashes; the fresh stamp protects all subsequent reads in this run.
                context.metadata_write()
                with db:db.execute('UPDATE files SET source_stamp=? WHERE idx=?',(encoded(list(stamp)),index))
            target = '/apps/'+settings['app_name']+'/mvp-validation/'+task.job_id+'/'+entry['name']
            limits = TransferLimits(settings['part_bytes'],settings['max_file_bytes'],1024)
            limits.validate(entry['size'])
            protocol = factory(target,identity,limits,settings['app_name'])
            if type(protocol) is not TaskProtocol or protocol.account != account_sha256 or protocol.target != target:
                fail('task_backend_invalid')
            protocol.attach(context)
            if protocol.kind == 'official-api':
                grant = protocol.client.grant
                grant.check(target)
                if grant.account_sha256 != account_sha256 or grant.source_sha256 != identity['sha256']:
                    fail('task_upload_scope_invalid')
            context.metadata_write();_tables(db)
            bound = db.execute('SELECT * FROM upload_context WHERE id=1').fetchone()
            if bound is not None and (bound['kind'] != protocol.kind or bound['account_sha256'] != account_sha256):
                fail('task_backend_identity_changed')
            if bound is None:
                # Existing effects cannot be adopted without their original binding.
                if db.execute('SELECT 1 FROM operations').fetchone():fail('task_upload_unbound_history')
                with db:db.execute('INSERT INTO upload_context VALUES(1,?,?)',(protocol.kind,account_sha256))
            context.checkpoint()
            facts=protocol.probe()
            if entry['size']>facts['quota_available'] or entry['size']>facts['documented_file_bytes']:
                fail('protocol_quota_insufficient')
            if min(entry['size'],limits.part_bytes)>facts['documented_part_bytes']:
                fail('protocol_account_limits_unknown')
            if protocol.request_encoder.available_memory() < protocol.request_encoder.memory_admission_bytes(min(entry['size'],limits.part_bytes))+128*1024**2:
                fail('sdk_codec_memory_budget')
            def before_mutation(req):
                nonlocal active
                context.checkpoint()
                if active is None or active['sent'] or req.binding != target:
                    fail('task_write_not_journaled')
                op = active['operation'];part = active['part']
                expected = 'upload' if op=='part' else 'precreate' if op=='precreate' else 'create'
                if req.params.get('method') != expected:fail('task_write_not_journaled')
                if op=='part' and str(req.params.get('partseq')) != str(part):fail('task_write_not_journaled')
                if op!='part':
                    form=dict(urllib.parse.parse_qsl(req.body.decode('ascii'),strict_parsing=True))
                    if (form.get('path') != (protocol.directory if op=='directory' else target)
                            or form.get('isdir') != ('1' if op=='directory' else '0')
                            or form.get('rtype') != ('0' if op=='directory' else '1')):
                        fail('task_write_not_journaled')
                record = _operation(db,active['index'],op,part)
                if record is None or record['outcome']!='unknown' or record['intent_sha256']!=active['fingerprint']:
                    fail('task_write_not_journaled')
                if file_stamp(source)!=stamp:fail('source_changed')
                active['sent'] = True
            protocol.before_mutation = before_mutation
            def intent(operation, part=-1):
                return {'task_spec_sha256':spec,'account_sha256':account_sha256,
                        'source_sha256':identity['sha256'] if operation!='directory' else None,'target':target if operation!='directory' else protocol.directory,
                        'operation':operation,'part':part,'part_md5':blocks[part] if part>=0 else None}
            def begin(operation, part=-1, owner=None):
                nonlocal active
                owner = index if owner is None else owner
                context.metadata_write()
                fingerprint = task.begin_operation(owner,operation,intent(operation,part),part=part,_db=db)
                active={'operation':operation,'part':part,'index':owner,'fingerprint':fingerprint,'sent':False}
                return fingerprint
            def finish(operation, fingerprint, receipt, part=-1, owner=None):
                context.metadata_write()
                task.finish_operation(index if owner is None else owner,operation,fingerprint,receipt,part=part,_db=db)
                context.checkpoint()
                if checkpoint_hook is not None:checkpoint_hook(operation,part)
            def existing_operation(operation, part=-1, owner=None):
                record=_operation(db,index if owner is None else owner,operation,part)
                if record is not None and record['intent_sha256']!=digest(intent(operation,part)):
                    fail('task_upload_state_invalid')
                return record
            directory = existing_operation('directory',owner=0)
            if directory is None:
                if index!=0:fail('task_upload_state_invalid')
                fingerprint=begin('directory',owner=0)
                protocol.reserve_new(protocol.directory);protocol.verify_directory()
                finish('directory',fingerprint,{'fs_id':protocol.directory_id,'path':protocol.directory},owner=0)
            else:
                receipt=read_json(directory['receipt'])
                if receipt.get('path')!=protocol.directory:fail('task_upload_state_invalid')
                protocol.directory_id=receipt['fs_id'];protocol.verify_directory();protocol.reserved=True
            committed = existing_operation('commit')
            if committed is None:
                precreated = existing_operation('precreate')
                if precreated is None:
                    fingerprint=begin('precreate')
                    def save_precreate(record):
                        receipt={'path':target,'size':identity['bytes'],'hashes':blocks,
                                 'uploadid':record['uploadid'],'required':record['required_parts'],
                                 'host':'d.pcs.baidu.com','directory_id':protocol.directory_id}
                        finish('precreate',fingerprint,receipt)
                    protocol.precreate_sink=save_precreate
                    protocol.verify_directory()
                    session=protocol.begin_new(target,entry['size'],blocks)
                else:
                    receipt=read_json(precreated['receipt'])
                    if (receipt.get('path')!=target or receipt.get('hashes')!=blocks
                            or receipt.get('size')!=identity['bytes'] or receipt.get('directory_id')!=protocol.directory_id):
                        fail('task_upload_state_invalid')
                    session=protocol.restore_session(receipt)
                for part in session.required:
                    context.checkpoint()
                    existing=existing_operation('part',part)
                    size=min(limits.part_bytes,entry['size']-part*limits.part_bytes)
                    if existing is not None:
                        receipt=read_json(existing['receipt'])
                        if receipt!={'part':part,'md5':blocks[part],'bytes':size}:fail('task_upload_state_invalid')
                        protocol.confirmations[id(session)][part]=blocks[part]
                        continue
                    source.seek(part*limits.part_bytes);data=source.read(size)
                    if len(data)!=size or file_stamp(source)!=stamp:fail('source_changed')
                    fingerprint=begin('part',part)
                    md5=protocol.put_part(session,part,data)
                    finish('part',fingerprint,{'part':part,'md5':md5,'bytes':size},part)
                    data=None
                if file_stamp(source)!=stamp:fail('source_changed')
                protocol.verify_directory();fingerprint=begin('commit')
                protocol.commit_new(session)
                fs_id,size=protocol.objects[target]
                finish('commit',fingerprint,{'fs_id':fs_id,'path':target,'size':size})
            else:
                receipt=read_json(committed['receipt'])
                if receipt.get('path')!=target or receipt.get('size')!=entry['size'] or type(receipt.get('fs_id')) is not int or not 0<receipt['fs_id']<2**63:
                    fail('task_upload_state_invalid')
                protocol.objects[target]=(receipt['fs_id'],receipt['size'])
            context.stage='readback';context.checkpoint()
            md5,sha,total=hashlib.md5(),hashlib.sha256(),0
            for data in protocol.readback(target,limits.readback_bytes):
                context.checkpoint();total+=len(data);md5.update(data);sha.update(data)
            if {'bytes':total,'md5':md5.hexdigest(),'sha256':sha.hexdigest()}!=identity:
                fail('readback_hash_or_length_mismatch')
            if file_stamp(source)!=stamp:fail('source_changed')
            fs_id,_=protocol.objects[target]
            verified={'path':target,'fs_id':fs_id,**identity}
        except (StageFailure,InputProblem) as exc:
            try:
                context.metadata_write()
                with db:db.execute('UPDATE files SET reason=? WHERE idx=?',(safe_reason(exc.code),index))
            except (StageFailure,InputProblem,OSError,sqlite3.Error):
                pass  # Preserve the original failure and already durable write intent.
            raise
        finally:
            if source is not None:source.close()
            if protocol is not None:stop_confirmed=protocol.stop() is True
        if not stop_confirmed or verified is None:fail('adapter_stop_unconfirmed')
        context.metadata_write()
        with db:
            db.execute('INSERT OR REPLACE INTO verifications VALUES(?,?,?,?)',
                       (index,protocol.kind,encoded(verified,MAX_RECEIPT),int(time.time())))
            db.execute('UPDATE files SET phase=?,reason=NULL WHERE idx=?',
                       ('cloud_verified' if protocol.kind=='official-api' else 'test_cloud_verified',index))
        return {'status':'cloud_verified' if protocol.kind=='official-api' else 'test_cloud_verified',
                'index':index,'bytes':verified['bytes'],'backend':protocol.kind,
                'cloud_verified':protocol.kind=='official-api','stop_confirmed':True,
                'delivered':False}


def main(argv=None):
    p=argparse.ArgumentParser(description='One scoped generic Task upload/readback, no share/refresh/delete.')
    p.add_argument('--tasks-dir',type=Path,required=True);p.add_argument('job_id')
    p.add_argument('--approve-job',required=True);p.add_argument('--approved-task-sha256',required=True)
    p.add_argument('--authorization',type=Path,required=True);p.add_argument('--expected-account-sha256',required=True)
    p.add_argument('--sdk-helper',type=Path,required=True);p.add_argument('--sdk-helper-sha256',required=True)
    p.add_argument('--sdk-guard',type=Path,required=True);p.add_argument('--sdk-guard-sha256',required=True)
    p.add_argument('--timeout',type=float,default=600)
    p.add_argument('--inspect-commit-proof',type=Path)
    a=p.parse_args(argv)
    last_protocol=[None]
    samples=None
    try:
        task=Task(a.tasks_dir,a.job_id)
        if a.approve_job!=a.job_id or a.approved_task_sha256!=task.view()['task_spec_sha256']:
            fail('task_upload_scope_invalid')
        codec=SDKRequestEncoder(a.sdk_helper,a.sdk_helper_sha256,a.sdk_guard,a.sdk_guard_sha256)
        def factory(target,identity,limits,app_name):
            # Lazy read only after scope/source/state checks; no credential search.
            def token():
                private_file(a.authorization)
                return access_token_first_field(a.authorization)
            grant=RuntimeGrant(True,target,a.expected_account_sha256,identity['sha256'],
                               'operator-task-'+a.job_id,time.monotonic()+a.timeout)
            client=TaskHTTP(grant=grant,credential_provider=token)
            backend=TaskProtocol(client,app_name,target,a.expected_account_sha256,limits,codec)
            last_protocol[0]=backend
            return backend
        with ResourceSamples(task.root) as samples:
            if a.inspect_commit_proof is not None:
                from .task_inspect import inspect_commit
                result=inspect_commit(task,factory,a.expected_account_sha256,a.inspect_commit_proof,
                                      timeout=a.timeout,approved_task_spec_sha256=a.approved_task_sha256)
            else:
                result=run_next(task,factory,a.expected_account_sha256,timeout=a.timeout,approved_task_spec_sha256=a.approved_task_sha256)
        result['resource_samples']=samples.summary()
        print(json.dumps(result,sort_keys=True));return 0
    except (StageFailure,InputProblem) as exc:
        print(json.dumps({'status':'manual_review','reason':safe_reason(exc.code),
                          'cloud_verified':False,'automatic_retry':False,
                          'api_diagnostics':last_protocol[0].diagnostics if last_protocol[0] is not None else [],
                          'resource_samples':samples.summary() if samples is not None else None}));return 2
    except KeyboardInterrupt:
        print(json.dumps({'status':'interrupted','automatic_retry':False,'cloud_verified':False,
                          'resource_samples':samples.summary() if samples is not None else None}));return 130
    except Exception:
        print(json.dumps({'status':'manual_review','reason':'task_upload_local_failure',
                          'cloud_verified':False,'automatic_retry':False,
                          'resource_samples':samples.summary() if samples is not None else None}));return 2


# No raw exception text escapes the CLI boundary.
if __name__=='__main__':
    from .task_upload import main as canonical_main
    sys.exit(canonical_main())

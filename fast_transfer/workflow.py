"""Offline M1–M4 orchestration. JSON never grants network or real delivery rights."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import sys
import stat
import time
from pathlib import Path

from .intake import InputProblem, load_manifest, require_accepted, safe_name, public_url
from .simulated_cloud import MemoryCloud
from .space import BackendNeeds, DiskProbe, MARGIN, RESERVE
from .upload_stage import TransferLimits, run_simulated_upload, safe_reason

MAX_STATE = 65536
PHASES = {'source_pending', 'simulation_running', 'simulated_cloud_verified',
          'share_draft', 'manual_review', 'cancelled'}


def fail(code):
    raise InputProblem(code, 'manual_review')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bounded_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        info=os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1: fail('workflow_file_invalid')
        raw = f.read(MAX_STATE+1)
    if len(raw) > MAX_STATE: fail('workflow_record_limit')
    def unique(pairs):
        obj = {}
        for k,v in pairs:
            if k in obj: fail('workflow_duplicate_json_key')
            obj[k] = v
        return obj
    return json.loads(raw, object_pairs_hook=unique)


def input_mapping(e):
    src=e['source']
    mapping={k:e[k] for k in ('name','url','size','md5','sha256') if k in e}
    mapping['source']={'record_url':src['record_url'],'checksum_url':src['checksum_url'],
                       'rights_basis_url':src['redistribution']['basis_url'],
                       'version_sha256':digest(src['version'])}
    return mapping


def validate_state(s):
    allowed={'schema_version','job_id','mode','phase','manifest_sha256','index','mapping',
             'cloud_verified','share_verified','delivery_eligible','delivered','account_share_permission',
             'events','manual_action','retention_policy','reason','mutation_outcome_unknown','stop_confirmed','share'}
    if set(s)-allowed or s.get('retention_policy')!='retain_all_no_automatic_delete':fail('workflow_state_invalid')
    def hexhash(v,n=64):return isinstance(v,str) and re.fullmatch('[0-9a-f]{%d}'%n,v)
    if not hexhash(s.get('manifest_sha256')) or type(s.get('index')) is not int or not 0<=s['index']<100:fail('workflow_state_invalid')
    m=s.get('mapping')
    if not isinstance(m,dict) or set(m)-{'name','url','size','md5','sha256','source','simulated_target'}:fail('workflow_state_invalid')
    safe_name(m.get('name'));public_url(m.get('url'))
    if type(m.get('size')) is not int or m['size']<=0:fail('workflow_state_invalid')
    for k,n in [('md5',32),('sha256',64)]:
        if k in m and not hexhash(m[k].lower() if isinstance(m[k],str) else m[k],n):fail('workflow_state_invalid')
    src=m.get('source')
    if not isinstance(src,dict) or set(src)!={'record_url','checksum_url','rights_basis_url','version_sha256'}:fail('workflow_state_invalid')
    for k in ('record_url','checksum_url','rights_basis_url'):public_url(src[k])
    if not hexhash(src['version_sha256']):fail('workflow_state_invalid')
    if 'simulated_target' in m and m['simulated_target']!='/apps/Xtransfer/mvp-validation/'+s['job_id']+'/'+m['name']:fail('workflow_state_invalid')
    events={'created','simulation_started','simulated_cloud_verified','manual_review','share_draft_recorded',
            'manual_inspect_commit_outcome','manual_verify_source','manual_verify_share','manual_cancel'}
    if not isinstance(s.get('events'),list) or len(s['events'])>32 or any(type(x) is not str or x not in events for x in s['events']):fail('workflow_state_invalid')
    if s.get('manual_action') not in (None,'inspect_commit_outcome','verify_source','verify_share','cancel'):fail('workflow_state_invalid')
    if s.get('reason') is not None:s['reason']=safe_reason(s['reason']) if isinstance(s['reason'],str) else 'workflow_state_invalid'
    if 'share' in s:
        share=s['share']
        keys={'link_sha256','expires_at','mapping_sha256','authorization_ref_sha256','scope','verification','password_storage','link_storage'}
        if (not isinstance(share,dict) or set(share)!=keys or not hexhash(share.get('link_sha256'))
                or share.get('mapping_sha256')!=digest(m) or type(share.get('expires_at')) is not int
                or share.get('scope')!='simulation-only' or share.get('verification')!='manual_claim_unverified'
                or share.get('password_storage')!='not_supported' or share.get('link_storage')!='fingerprint_only'
                or not hexhash(share.get('authorization_ref_sha256'))):fail('workflow_state_invalid')
    for k in ('mutation_outcome_unknown','stop_confirmed'):
        if k in s and type(s[k]) is not bool:fail('workflow_state_invalid')


class Job:
    def __init__(self, parent, job_id):
        safe_name(job_id)
        if len(job_id)>64: fail('workflow_job_id_invalid')
        self.root = Path(parent).absolute()/job_id
        self.job_id = job_id

    def space(self):
        volume = DiskProbe().directory(self.root, writable=True)
        if volume.free < RESERVE+MARGIN+2*MAX_STATE: fail('workflow_space_reserve')

    @contextlib.contextmanager
    def locked(self):
        DiskProbe().directory(self.root, writable=True)
        info=self.root.stat()
        if info.st_uid!=os.geteuid() or info.st_mode & 0o077:fail('workflow_private_directory_required')
        fd = os.open(self.root/'lock', os.O_RDWR | os.O_NOFOLLOW)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:fail('workflow_file_invalid')
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: fail('workflow_busy')
            yield
        finally: os.close(fd)

    def save(self, state):
        self.space()
        raw = json.dumps(state, sort_keys=True).encode()
        if len(raw)>MAX_STATE: fail('workflow_record_limit')
        fd = os.open(self.root/'state.new', os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd,'wb') as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(self.root/'state.new', self.root/'state.json')
        fd = os.open(self.root, os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def read(self):
        state = bounded_json(self.root/'state.json')
        if (not isinstance(state,dict) or type(state.get('schema_version')) is not int or state['schema_version']!=1
                or state.get('job_id')!=self.job_id or state.get('mode')!='simulation'
                or state.get('phase') not in PHASES): fail('workflow_state_invalid')
        validate_state(state)
        # Loaded claims remain untrusted. These fields can never enable live mode.
        state.update(cloud_verified=False, share_verified=False, delivery_eligible=False,
                     delivered=False, account_share_permission='unknown')
        return state

    def create(self, manifest, index=0):
        entries = require_accepted(manifest)
        if type(index) is not int or not 0<=index<len(entries):fail('invalid_file_index')
        DiskProbe().directory(self.root.parent, writable=True)
        try:self.root.mkdir(mode=0o700)
        except FileExistsError:fail('workflow_job_exists')
        fd=os.open(self.root/'lock',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
        mapping=input_mapping(entries[index])
        state={'schema_version':1,'job_id':self.job_id,'mode':'simulation','phase':'source_pending',
               'manifest_sha256':digest(manifest),'index':index,'mapping':mapping,
               'cloud_verified':False,'share_verified':False,'delivery_eligible':False,'delivered':False,
               'account_share_permission':'unknown','events':['created'], 'manual_action':None,'retention_policy':'retain_all_no_automatic_delete'}
        with self.locked():self.save(state)
        return state

    def simulate(self, manifest, source_dir, backend_dir):
        with self.locked():
            s=self.read()
            if s['phase']!='source_pending':fail('workflow_no_automatic_retry')
            entries=require_accepted(manifest)
            if digest(manifest)!=s['manifest_sha256']:fail('workflow_manifest_mismatch')
            entry=entries[s['index']]
            if s['mapping']!=input_mapping(entry):fail('workflow_manifest_mismatch')
            # Persist intent BEFORE invocation; interrupted/unknown jobs cannot rerun.
            s['phase']='simulation_running';s['events'].append('simulation_started');self.save(s)
            try:
                src=Path(source_dir)
                r=run_simulated_upload(entry,src/entry['name'],src/'.receipts'/(str(s['index'])+'.json'),
                    Path(backend_dir),self.job_id,'Xtransfer',MemoryCloud('Xtransfer'),
                    BackendNeeds('direct-api',65536,262144,262144,'stream'),
                    TransferLimits(4*1024**2,16*1024**2,1024))
                ok=(r.get('status')=='verified_simulation' and r.get('simulated_delivery_eligible') is True
                    and r.get('state_persisted') is True and r.get('mutation_outcome_unknown') is not True)
                s['phase']='simulated_cloud_verified' if ok else 'manual_review'
                s['reason']=safe_reason(r['reason']) if r.get('reason') else None
                s['mutation_outcome_unknown']=r.get('mutation_outcome_unknown') is True
                s['stop_confirmed']=r.get('stop_confirmed') is True
                if ok:
                    identity=r['readback']
                    s['mapping'].update(md5=identity['md5'],sha256=identity['sha256'])
                    s['mapping']['simulated_target']=r['target']
            except Exception:
                s.update(phase='manual_review',reason='workflow_simulation_failed',mutation_outcome_unknown=True)
            s['events'].append(s['phase']);self.save(s)
            return s

    def share_draft(self, form, now=None):
        now=int(time.time()) if now is None else now
        with self.locked():
            s=self.read()
            if s['phase']!='simulated_cloud_verified':fail('workflow_share_not_ready')
            expected={'job_id','mapping_sha256','link','expires_at','authorization_ref','scope'}
            if not isinstance(form,dict) or set(form)!=expected:fail('share_form_invalid')
            if form['job_id']!=self.job_id or form['mapping_sha256']!=digest(s['mapping']):fail('share_wrong_file')
            if form['scope']!='simulation-only':fail('share_scope_not_authorized')
            if not isinstance(form['authorization_ref'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',form['authorization_ref']):fail('share_scope_not_authorized')
            expiry=form['expires_at']
            # Local exercise policy, not a platform/account entitlement claim.
            if type(expiry) is not int or not now<expiry<=now+30*86400:fail('share_expired_or_out_of_policy')
            link=form['link']
            if not isinstance(link,str) or not re.fullmatch(r'https://(?:pan\.baidu\.com|share\.invalid)/s/[A-Za-z0-9_-]{1,100}',link):fail('share_link_syntax_invalid')
            s['share']={'link_sha256':hashlib.sha256(link.encode()).hexdigest(),'expires_at':expiry,
                        'mapping_sha256':form['mapping_sha256'],'authorization_ref_sha256':digest(form['authorization_ref']),
                        'scope':'simulation-only','verification':'manual_claim_unverified',
                        'password_storage':'not_supported','link_storage':'fingerprint_only'}
            s['phase']='share_draft';s['events'].append('share_draft_recorded');self.save(s)
            return s

    def manual(self, action):
        if action not in ('inspect_commit_outcome','verify_source','verify_share','cancel'):fail('workflow_manual_action_invalid')
        with self.locked():
            s=self.read()
            if s['phase']=='cancelled':fail('workflow_already_cancelled')
            s['phase']='cancelled' if action=='cancel' else 'manual_review'
            s['manual_action']=action
            s['events']=(s['events']+['manual_'+action])[-32:]
            # Manual continuation is a local checklist; never resets to runnable.
            self.save(s);return s

    def diagnose(self):
        """Read-only, bounded recovery status; never repairs or invokes a backend."""
        out = {'mode': 'simulation', 'status': 'manual_review',
               'delivery_eligible': False, 'automatic_retry_allowed': False,
               'reason': 'workflow_local_input_or_io_failure',
               'next_action': 'inspect_local_records_without_retry_or_deletion'}
        try:
            with self.locked():
                try:
                    (self.root/'state.new').lstat()
                except FileNotFoundError:
                    pass
                else:
                    out['reason'] = 'workflow_pending_state_file'
                    return out
                try:
                    s = self.read()
                except FileNotFoundError:
                    out['reason'] = 'workflow_state_missing'
                    return out
                except (InputProblem, ValueError, TypeError, KeyError, OSError):
                    out['reason'] = 'workflow_state_unreadable_or_invalid'
                    return out
                out['phase'] = s['phase']
                if s['phase'] == 'simulation_running' or s.get('mutation_outcome_unknown'):
                    out['reason'] = 'workflow_incomplete_or_unknown_outcome'
                else:
                    out['status'] = 'local_record_only'
                    out['reason'] = 'workflow_record_readable'
        except InputProblem as exc:
            if exc.code == 'workflow_busy':
                out['reason'] = 'workflow_busy'
        except OSError:
            pass
        return out

    def view(self, now=None):
        with self.locked():s=self.read()
        now=int(time.time()) if now is None else now
        share=s.get('share')
        if share is not None:
            s['share_current_status']='expired' if share['expires_at']<=now else 'unverified'
        s['document_kind']='delivery_checklist_draft'
        s['mapping_sha256']=digest(s['mapping'])
        s['next_steps']=['Resolve unknown outcomes manually; do not retry writes.',
                         'Real M3 evidence and explicit share scope remain required.',
                         'Manually select exact file, set expiry/password, verify contents.',
                         'Recipient must compare length and hashes; no delivery yet.']
        return s


def main():
    p=argparse.ArgumentParser(description='Offline single-task simulation and manual share drafts only.')
    p.add_argument('--jobs-dir',type=Path,required=True);p.add_argument('--job-id',required=True)
    sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('create');c.add_argument('manifest',type=Path);c.add_argument('--index',type=int,default=0)
    c=sub.add_parser('simulate');c.add_argument('manifest',type=Path);c.add_argument('--source-dir',type=Path,required=True);c.add_argument('--backend-dir',type=Path,required=True)
    sub.add_parser('show')
    sub.add_parser('diagnose')
    c=sub.add_parser('record-share');c.add_argument('form',type=Path)
    c=sub.add_parser('manual');c.add_argument('action',choices=['inspect_commit_outcome','verify_source','verify_share','cancel'])
    a=p.parse_args()
    try:
        job=Job(a.jobs_dir,a.job_id)
        if a.command=='create':out=job.create(load_manifest(a.manifest),a.index)
        elif a.command=='simulate':out=job.simulate(load_manifest(a.manifest),a.source_dir,a.backend_dir)
        elif a.command=='record-share':out=job.share_draft(bounded_json(a.form))
        elif a.command=='manual':out=job.manual(a.action)
        elif a.command=='diagnose':out=job.diagnose()
        else:out=job.view()
        print(json.dumps(out));return 0
    except InputProblem as exc:reason=exc.code
    except Exception:reason='workflow_local_input_or_io_failure'
    print(json.dumps({'mode':'simulation','status':'manual_review','reason':reason,'delivery_eligible':False}));return 2


if __name__=='__main__':sys.exit(main())

"""One historic sample: private receipt binding and native read-only checks.

No search, credential discovery, OAuth, writes, share, or secret/identifier output.
The caller explicitly provides the original task directory and token provider.
"""
import hashlib
import hmac
import json
import os
import re
import stat
import time

from .approved_sample import NAME, SIZE, MD5, SHA256, APPROVAL_REF
from .baidu_http import PinnedBaiduHTTPClient, RuntimeGrant
from .baidu_protocol import BaiduProtocol, NAS, METAS
from .baidu_md5 import normalize_md5
from .mcp_binding import ExpectedObject
from .upload_stage import TransferLimits
from .workflow import digest


class BindingFailure(Exception):
    pass


def stop():
    raise BindingFailure('original_sample_binding_rejected') from None


def _read(directory, parts):
    """Traverse fixed relative components using no-follow directory descriptors."""
    fd=os.dup(directory)
    try:
        for part in parts[:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            os.close(fd);fd=nxt
        source=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
        with os.fdopen(source,'rb') as f:
            st=os.fstat(f.fileno())
            if (not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_nlink!=1
                    or st.st_mode&0o077 or st.st_size>262144):stop()
            raw=f.read(262145)
            after=os.fstat(f.fileno())
            if len(raw)>262144 or (st.st_size,st.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):stop()
        def unique(pairs):
            obj={}
            for k,v in pairs:
                if k in obj:stop()
                obj[k]=v
            return obj
        obj=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:stop())
        if type(obj) is not dict:stop()
        return obj
    finally:
        os.close(fd)


def load_original(root):
    """Derive a private expectation only from five explicit original records.

    Local consistency is not a signature or a current cloud-existence proof.
    uploadid may enter memory during JSON parsing but is never returned/used.
    """
    fd=None
    try:
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        st=os.fstat(fd)
        if st.st_uid!=os.geteuid() or st.st_mode&0o077:stop()
        old=_read(fd,('result.json',));proof=_read(fd,('precommit-inspection.json',))
        rec=_read(fd,('recovery-result.json',));session=_read(fd,('recovered-session.private.json',))
        receipt=_read(fd,('source','.receipts','0.json'))
        job=old.get('job_id');target=old.get('target');account=session.get('account_sha256')
        identity={'bytes':SIZE,'md5':MD5,'sha256':SHA256}
        if (type(job) is not str or not re.fullmatch('job-[0-9a-f]{32}',job)
                or type(account) is not str or not re.fullmatch('[0-9a-f]{64}',account)
                or target!='/apps/Xtransfer/mvp-validation/'+job+'/'+NAME
                or proof.get('job_id')!=job or rec.get('job_id')!=job
                or proof.get('target')!=target or rec.get('target')!=target or session.get('path')!=target
                or type(rec.get('verified_object_id')) is not int or rec['verified_object_id']<=0
                or type(session.get('directory_id')) is not int or session['directory_id']<=0
                or type(proof.get('directory_id')) is not int
                or proof.get('directory_id')!=session['directory_id']
                or proof.get('prior_commit_attempted') is not False
                or type(proof.get('prior_payload_sent')) is not int or proof['prior_payload_sent']!=0
                or session.get('source_sha256')!=SHA256 or session.get('size')!=SIZE
                or session.get('block_md5')!=[MD5] or session.get('approval_ref')!=APPROVAL_REF
                or receipt.get('status')!='source_verified' or receipt.get('file')!=NAME
                or any(receipt.get(k)!=v for k,v in identity.items())
                or rec.get('readback')!=identity or rec.get('cloud_verified') is not True
                or rec.get('verification_complete') is not True or rec.get('same_cloud_directory') is not True
                or old.get('commit_attempted') is not False or type(old.get('requested_payload_bytes')) is not int
                or old['requested_payload_bytes']!=0):stop()
        fields=dict(task=job,account='sha256:'+account,application='Xtransfer',
                    fsid=str(rec['verified_object_id']),path=target,size=SIZE,md5=MD5,sha256=SHA256)
        # Constructed now from the original joined fields; not a historic MCP receipt.
        return ExpectedObject(**fields,mapping_sha256=digest(fields))
    except Exception:
        stop()
    finally:
        if fd is not None:os.close(fd)


class _Probe(BaiduProtocol):
    def record_response_shape(self,summary):
        self.diagnostics.append({k:v for k,v in summary.items() if k in ('has_errno','has_error_code','errno','error_code')})


def metadata_flags(meta,expected):
    rows=meta.get('list') if type(meta) is dict else None
    if type(rows) is not list or len(rows)!=1 or type(rows[0]) is not dict:stop()
    row=rows[0]
    return {
        'file_id_matches':type(row.get('fs_id')) is int and str(row['fs_id'])==expected.fsid,
        'path_matches':row.get('path')==expected.path,
        'size_matches':type(row.get('size')) is int and row['size']==expected.size,
        'md5_present':type(row.get('md5')) is str,
        'md5_has_hex_format':type(row.get('md5')) is str and bool(re.fullmatch('[0-9a-fA-F]{32}',row['md5'])),
        'md5_matches':row.get('md5')==expected.md5,
        'md5_normalized_matches':normalize_md5(row.get('md5'))==expected.md5,
        'regular_file':type(row.get('isdir')) is int and row['isdir']==0,
        'row_errno_zero':type(row.get('errno',0)) is int and row.get('errno',0)==0}


def native_readonly(expected,credential_provider):
    """Exactly uinfo then one filemetas if the old account hash matches.

    No quota, directory listing, dlink, download, retry, refresh or mutation.
    """
    out={'identity_request_attempted':False,'metadata_request_attempted':False,
         'native_identity_matched':False,'native_object_matches':False,
         'share_attempted':False,'authorization_changed':False,'status':'stopped'}
    client=None;probe=None
    try:
        if type(expected) is not ExpectedObject or not expected.account.startswith('sha256:'):stop()
        grant=RuntimeGrant(True,expected.path,expected.account[7:],expected.sha256,
                           'existing-original-sample-readonly',time.monotonic()+25)
        client=PinnedBaiduHTTPClient(grant=grant,credential_provider=credential_provider)
        probe=_Probe(client,'Xtransfer',expected.path,expected.account[7:],TransferLimits(4*1024**2,16*1024**2,1024))
        probe.diagnostics=[]
        out['identity_request_attempted']=True
        identity=probe.request('GET',NAS,{'method':'uinfo','vip_version':'v2'})
        uk=identity.get('uk')
        if type(uk) is not int or uk<=0 or not hmac.compare_digest(hashlib.sha256(str(uk).encode()).hexdigest(),expected.account[7:]):
            out['status']='account_mismatch';return out
        out['native_identity_matched']=True
        out['metadata_request_attempted']=True
        meta=probe.request('GET',METAS,{'method':'filemetas','fsids':json.dumps([int(expected.fsid)]),'dlink':0})
        out['metadata_comparison']=metadata_flags(meta,expected)
        if not all(out['metadata_comparison'][k] for k in ('file_id_matches','path_matches','size_matches',
                                                          'md5_normalized_matches','regular_file','row_errno_zero')):
            out['status']='object_mismatch';return out
        out.update(native_object_matches=True,status='native_exact_object_verified')
    except Exception:
        out['status']='native_readonly_failed_validity_unknown'
    finally:
        if probe is not None:out['response_codes']=probe.diagnostics
        try:
            out['closed']=client.stop() if client is not None else True
        except Exception:
            out['closed']=False
        if not out['closed']:out['status']='manual_review_close_unconfirmed'
    return out

"""One explicitly approved NCBI sample; not a general live mode or share bypass.

Caller must consume an exclusive durable run directory before supplying a grant.
No credential discovery, refresh, config writing, Cookie or generic live CLI.
"""
import hashlib
import json
import os
import re
import stat
import time
import urllib.parse

from .baidu_http import PinnedBaiduHTTPClient, fail
from .baidu_protocol import BaiduProtocol
from .isolated_candidate import IsolatedBaiduCandidate
from .upload_stage import _run_upload

NAME = 'GCF_000005845.2_ASM584v2_genomic.fna.gz'
SIZE = 1379902
MD5 = 'c13d459b5caa702ff7e1f26fe44b8ad7'
SHA256 = 'a96d3cfa58c88d477013c768f90a11d2386d42a70d566abfb6d9013dcbd24255'
APPROVAL_REF = 'user-20261108-one-ncbi-sample'


class SampleHTTP(PinnedBaiduHTTPClient):
    mode = 'approved-sample-http'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.attempts = set()
        self.uploadid = None
        self.timings = []

    def exchange(self, req):
        if req.params.get('method')=='list' and req.params.get('dir') not in (self.grant.target.rsplit('/',1)[0],'/apps/Xtransfer/mvp-validation'):
            fail('approved_sample_scope_invalid')
        started=time.monotonic()
        event={'purpose':req.purpose,'operation':req.params.get('method','quota' if req.url.endswith('/api/quota') else 'readback'),
               'started_utc':time.time(),'request_body_bytes':len(req.body)}
        try:
            reply=super().exchange(req)
            event['http_status']=reply.status
            close=reply._close
            def finish():
                try:return close()
                finally:
                    event['elapsed_seconds']=round(time.monotonic()-started,6)
                    if len(self.timings)<32:self.timings.append(event)
            reply._close=finish
            return reply
        except Exception:
            event.update(outcome='request_failed',elapsed_seconds=round(time.monotonic()-started,6))
            if len(self.timings)<32:self.timings.append(event)
            raise

    def scope(self):
        self.grant.check(self.grant.target)
        if (self.grant.approval_ref != APPROVAL_REF or self.grant.source_sha256 != SHA256
                or not re.fullmatch('/apps/Xtransfer/mvp-validation/job-[0-9a-f]{32}/'+re.escape(NAME),self.grant.target)):
            fail('approved_sample_scope_invalid')

    def authorize_write(self, req):
        self.scope()
        if req.binding != self.grant.target:fail('approved_sample_scope_invalid')
        if req.purpose=='upload':
            p=req.params
            if (set(p)!={'method','type','path','uploadid','partseq'} or p['path']!=self.grant.target
                    or p['partseq']!=0 or not self.uploadid or p['uploadid']!=self.uploadid):fail('approved_sample_scope_invalid')
            pieces=req.body.split(b'\r\n\r\n',1)
            if len(pieces)!=2:fail('approved_sample_scope_invalid')
            data=pieces[1].rsplit(b'\r\n--',1)[0]
            if len(data)!=SIZE or hashlib.sha256(data).hexdigest()!=SHA256:fail('approved_sample_scope_invalid')
            operation='part'
        else:
            pairs=urllib.parse.parse_qsl(req.body.decode('ascii'),strict_parsing=True)
            f=dict(pairs)
            if len(f)!=len(pairs) or req.url!='https://pan.baidu.com/rest/2.0/xpan/file' or set(req.params)!={'method'}:fail('approved_sample_scope_invalid')
            operation=req.params['method']
            if f.get('isdir')=='1':
                operation='directory'
                if req.params['method']!='create' or f!={'path':self.grant.target.rsplit('/',1)[0],'isdir':'1','rtype':'0'}:fail('approved_sample_scope_invalid')
            else:
                required={'path':self.grant.target,'size':str(SIZE),'isdir':'0','rtype':'1','block_list':json.dumps([MD5],separators=(',',':'))}
                if operation=='precreate':required['autoinit']='1'
                elif operation=='create':required.update(is_revision='0',uploadid=self.uploadid)
                else:fail('approved_sample_scope_invalid')
                if f!=required:fail('approved_sample_scope_invalid')
        order=['directory','precreate','part','create']
        if len(self.attempts)>=len(order) or operation in self.attempts or operation!=order[len(self.attempts)]:fail('approved_sample_replay')
        # Consume intent before any connection/credential operation; unknown never retries.
        self.attempts.add(operation)


class ApprovedSample(IsolatedBaiduCandidate):
    mode = 'approved-live-sample'

    def __init__(self, client, account_sha256, limits, *, session_store=None):
        if type(client) is not SampleHTTP:fail('approved_sample_scope_invalid')
        client.scope()
        BaiduProtocol.__init__(self,client,'Xtransfer',client.grant.target,account_sha256,limits)
        self.mode='approved-live-sample'
        self.initialize_policy(self.target)
        self.session_store=session_store
        self.protocol_diagnostics=[]
        self.recovered_directory=False

    def write_gate(self):
        self.checkpoint();self.client.scope()
        if self.facts is None:self.probe()

    def record_response_shape(self, summary):
        if len(self.protocol_diagnostics)<32:self.protocol_diagnostics.append(summary)

    def precreated_checkpoint(self, record):
        if self.session_store is not None:
            # Private, local session identifier only; no access/refresh token.
            self.session_store({**record,'directory_id':self.directory_id,
                                'account_sha256':self.account,'source_sha256':SHA256,
                                'approval_ref':APPROVAL_REF,'created_utc':time.time()})

    def begin_new(self,path,size,hashes):
        session=super().begin_new(path,size,hashes)
        self.client.uploadid=session.uploadid
        return session

    def inspect_empty_precommit_directory(self, proof):
        self.client.scope()
        if (self.phase!='new' or self.client.attempts or proof.get('target')!=self.target
                or proof.get('prior_commit_attempted') is not False
                or type(proof.get('prior_payload_sent')) is not int or proof['prior_payload_sent']!=0
                or type(proof.get('directory_id')) is not int or proof['directory_id']<=0):
            fail('approved_sample_scope_invalid')
        self.probe()
        self.directory_id=proof['directory_id']
        self.verify_directory()
        listing=self.request('GET','https://pan.baidu.com/rest/2.0/xpan/file',
                             {'method':'list','dir':self.directory,'start':0,'limit':1000})
        if listing.get('list')!=[]:fail('protocol_conflict')
        # Fresh server checks, not a JSON true field, establish an empty known directory.
        self.recovered_directory=True
        self.client.attempts.add('directory')

    def reserve_policy(self,path):
        if not self.recovered_directory:return super().reserve_policy(path)
        if path!=self.directory or self.reserved:fail('protocol_path_changed')
        self.verify_directory();self.reserved=True

    def validate_scope(self, entry, job_id, app_name):
        self.client.scope()
        if (app_name!='Xtransfer' or self.account!=self.client.grant.account_sha256
                or self.target!='/apps/Xtransfer/mvp-validation/'+job_id+'/'+NAME
                or entry.get('name')!=NAME or entry.get('size')!=SIZE
                or entry.get('md5')!=MD5 or entry.get('sha256',SHA256)!=SHA256):fail('approved_sample_scope_invalid')


def run_approved_sample(entry,source,receipt,backend,job_id,transport,needs,limits,*,probe=None):
    if type(transport) is not ApprovedSample:fail('approved_sample_scope_invalid')
    return _run_upload(entry,source,receipt,backend,job_id,'Xtransfer',transport,needs,limits,
                       probe=probe,_approved_sample=transport)


def access_token_first_field(path):
    """Read only a first access_token JSON string; never read later auth fields."""
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb',buffering=0) as f:
        info=os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_mode&0o077:fail('approved_sample_token_layout')
        prefix=b''
        for _ in range(80):
            c=f.read(1)
            if not c:fail('approved_sample_token_layout')
            prefix+=c
            if c==b':':break
        if not re.fullmatch(rb'\s*\{\s*"access_token"\s*:',prefix):fail('approved_sample_token_layout')
        value=b''
        for _ in range(8192):
            c=f.read(1)
            if not c:fail('approved_sample_token_layout')
            value+=c
            try:token=json.loads(value)
            except (ValueError,UnicodeError):continue
            if not isinstance(token,str) or not token or len(token)>4096:fail('approved_sample_token_layout')
            return token
        fail('approved_sample_token_layout')

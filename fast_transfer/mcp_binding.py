"""Explicit object binding and candidate MCP business decoder.

README documents fields, not the business text envelope or app/share provenance.
No boolean or caller-supplied receipt can authorize a real mutation here.
"""
from dataclasses import dataclass
import json
import re

from . import mcp_share as c
from . import mcp_sse as wire
from .workflow import Job, digest


def reject(code):
    c.reject(code)


def identifier(value):
    if type(value) is int and value > 0:
        return str(value)
    if type(value) is str and re.fullmatch('[1-9][0-9]{0,19}', value):
        return value
    reject('mcp_binding_identifier_invalid')


@dataclass(frozen=True, repr=False)
class ExpectedObject:
    """Caller expectations from private records, NOT authority/provenance proof."""
    task: str
    account: str
    application: str
    fsid: str
    path: str
    size: int
    md5: str
    sha256: str
    mapping_sha256: str

    def __repr__(self):return '<private_expected_mcp_object>'

    def __post_init__(self):
        for value in (self.task,self.application):
            if type(value) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',value):
                reject('mcp_binding_expectation_invalid')
        for value in (self.account,self.fsid):
            if type(value) is not str or identifier(value)!=value:reject('mcp_binding_expectation_invalid')
        if (type(self.path) is not str or not self.path.startswith('/apps/'+self.application+'/')
                or len(self.path)>1024 or '\\' in self.path
                or any(part in ('','.','..') for part in self.path.split('/')[1:])
                or any(ord(ch)<32 for ch in self.path)
                or type(self.size) is not int or self.size<=0):
            reject('mcp_binding_expectation_invalid')
        for value,length in ((self.md5,32),(self.sha256,64),(self.mapping_sha256,64)):
            if type(value) is not str or not re.fullmatch('[0-9a-f]{%d}'%length,value):
                reject('mcp_binding_expectation_invalid')

    def arguments(self,period,pwd):
        if type(period) is not int or period!=7 or type(pwd) is not str or not re.fullmatch('[a-z0-9]{4}',pwd):
            reject('mcp_candidate_arguments_invalid')
        return {'fsid_list':json.dumps([self.fsid],separators=(',',':')),'period':period,'pwd':pwd}


def decode_result(result):
    """Standard MCP envelope plus explicit *candidate* single-JSON-text profile.

    No extraction from prose/fences, status guessing or REST errno unwrapping.
    This does not establish that the official service uses this business profile.
    """
    if (type(result) is not dict or set(result)-{'content','isError'}
            or type(result.get('isError',False)) is not bool):reject('mcp_binding_envelope_unknown')
    if result.get('isError',False):reject('mcp_sse_tool_error')
    content=result.get('content')
    if (type(content) is not list or len(content)!=1 or type(content[0]) is not dict
            or set(content[0])!={'type','text'} or content[0]['type']!='text'
            or type(content[0]['text']) is not str):reject('mcp_binding_envelope_unknown')
    return c.payload(content[0]['text'].encode())


def check_identity(fields,expected):
    if (type(fields) is not dict or set(fields)-{'uk','avatar_url','vip_type'} or 'uk' not in fields
            or identifier(fields['uk'])!=expected.account):reject('mcp_binding_account_mismatch')
    # README has no app/client_id/scope/session assertion. Never derive it from uk.


def check_metadata(fields,expected):
    if type(fields) is not dict or set(fields)!={'list'} or type(fields['list']) is not list or len(fields['list'])!=1:
        reject('mcp_binding_object_mismatch')
    item=fields['list'][0]
    allowed={'fsid','path','md5','size','category','filename','content','thumbnail','abstract'}
    if (type(item) is not dict or set(item)-allowed or not {'fsid','path','md5','size'}<=set(item)
            or identifier(item['fsid'])!=expected.fsid or item['path']!=expected.path
            or type(item['size']) is not int or item['size']!=expected.size
            or type(item['md5']) is not str or item['md5']!=expected.md5):
        reject('mcp_binding_object_mismatch')
    # SHA256 remains a local readback receipt expectation; README doesn't return it.


class BoundSession(wire.SSEClient):
    """Non-fixture IDs without pretending the business profile is authenticated.

    Scripted construction is for candidate tests. Official construction is
    read-only; both this session and the official HTTP driver deny sharing.
    """
    def __init__(self,driver,expected,*,budget=5):
        if type(expected) is not ExpectedObject:reject('mcp_binding_expectation_invalid')
        super().__init__(driver,budget=budget)
        self.expected=expected
        self.scope='scripted-candidate'

    @classmethod
    def official_readonly(cls,driver,expected,*,budget=30):
        from .mcp_official_http import OfficialHTTPSDriver
        if type(driver) is not OfficialHTTPSDriver or type(expected) is not ExpectedObject:
            reject('mcp_sse_driver_unavailable')
        if type(budget) not in (int,float) or not 0<budget<=30:reject('mcp_sse_protocol_rejected')
        obj=cls.__new__(cls);obj._setup(driver,budget)
        obj.expected=expected;obj.scope='official-readonly'
        obj.origin=driver.origin;obj.endpoint=driver.endpoint
        return obj

    def review_descriptors(self,descriptors):
        # Deliberately conservative candidate input profile. Discovery mismatch
        # stops before account/object calls; it is not a server compatibility claim.
        names=('user_info','file_meta') if self.scope=='official-readonly' else tuple(wire.schemas())
        if any(descriptors.get(name)!=wire.schemas()[name] for name in names):
            reject('mcp_sse_schema_unproven')

    def tool(self,name,arguments):
        if type(arguments) is not dict:reject('mcp_sse_protocol_rejected')
        if name=='user_info':
            if arguments!={}:reject('mcp_sse_protocol_rejected')
        elif name=='file_meta':
            if arguments!={'fsids':[int(self.expected.fsid)]} or type(arguments['fsids'][0]) is not int:
                reject('mcp_binding_object_mismatch')
        elif name=='file_sharelink_set':
            if self.scope!='scripted-candidate':reject('mcp_official_operation_locked')
            if (set(arguments)!={'fsid_list','period','pwd'} or arguments!=self.expected.arguments(arguments['period'],arguments['pwd'])):
                reject('mcp_candidate_arguments_invalid')
        else:reject('mcp_official_operation_locked')
        self.connect();self.check()
        if name in self.called:reject('mcp_binding_call_consumed')
        self.called.add(name)
        return decode_result(self.rpc('tools/call',{'name':name,'arguments':arguments}))

    def inspect(self):
        check_identity(self.tool('user_info',{}),self.expected)
        check_metadata(self.tool('file_meta',{'fsids':[int(self.expected.fsid)]}),self.expected)
        return {'candidate_fields_match':True,'live_authenticated':False,'share_eligible':False,
                'application_proven':False,'business_envelope_verified':False,
                'missing_evidence':['business_envelope','credential_application_scope','share_object_mapping']}


def stage_candidate_share(job,session,*,pwd,period=7):
    """Existing Job lock/save; only scripted candidate can consume share intent.

    The real read-only path is rejected before observation, state change or I/O.
    Persistent JSON is never authority to dispatch real mutations.
    """
    out={'status':'rejected','reason':'mcp_binding_candidate_rejected','create_attempted':False,
         'outcome_unknown':False,'live_authenticated':False,'mapping_verified':False,
         'delivery_eligible':False,'automatic_retry_allowed':False}
    try:
        if (type(job) is not Job or type(session) is not BoundSession
                or session.scope!='scripted-candidate' or type(session.driver) is not wire.ScriptedHTTP):
            reject('mcp_official_operation_locked')
        expected=session.expected
        args=expected.arguments(period,pwd)
        with job.locked():
            state=job.read();out['outcome_unknown']=state.get('mutation_outcome_unknown') is True
            if state['phase']!='simulated_cloud_verified' or out['outcome_unknown']:
                reject('mcp_binding_intent_consumed')
            mapping=state['mapping']
            if (job.job_id!=expected.task or digest(mapping)!=expected.mapping_sha256
                    or mapping.get('size')!=expected.size or mapping.get('md5')!=expected.md5
                    or mapping.get('sha256')!=expected.sha256 or mapping.get('simulated_target')!=expected.path):
                reject('mcp_binding_job_mismatch')
            session.inspect()
            state.update(phase='manual_review',manual_action='verify_share',mutation_outcome_unknown=True)
            state['events']=(state['events']+['manual_verify_share'])[-32:]
            job.save(state)  # Must fsync successfully before the single dispatch.
            out.update(status='unverified',create_attempted=True,outcome_unknown=True)
            fields=session.tool('file_sharelink_set',args)
            c._check_share(fields,c.ShareArguments(expected.fsid,period,pwd))
            out.update(status='candidate_unverified',reason='mcp_share_mapping_unproven')
    except c.Rejected as exc:
        code=exc.args[0] if exc.args else None
        safe={'mcp_official_operation_locked','mcp_binding_intent_consumed','mcp_binding_job_mismatch',
              'mcp_binding_account_mismatch','mcp_binding_object_mismatch','mcp_binding_envelope_unknown',
              'mcp_binding_call_consumed','mcp_share_mapping_unproven'} | c.SAFE_CODES
        out['reason']=code if type(code) is str and code in safe else 'mcp_binding_candidate_rejected'
    except Exception:
        out['reason']='mcp_binding_candidate_rejected'
    finally:
        if type(session) is BoundSession:
            out['protocol_closed']=session.close()
            if not out['protocol_closed']:out.update(status='manual_review',reason='mcp_sse_stop_unconfirmed')
    return out

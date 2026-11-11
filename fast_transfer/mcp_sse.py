"""Deterministic SSE/JSON-RPC profile; separate scripted and local-TLS factories.

Sequence adapted from baidu-netdisk/mcp (MIT, Copyright 2025 baidu-netdisk).
See third_party/NOTICE.md and licenses. No LLM, credential discovery or retry.
An explicit official read-only factory is separate from fixture sharing. Local TLS I/O does not
prove that an external account/server supports this strict profile.
"""
from collections import deque
import json
import re
import time
import urllib.parse

from . import mcp_share as contract

ORIGIN = 'https://mcp-pan.baidu.com'
ENDPOINT = ORIGIN + '/sse'
VERSION = '2024-11-05'
AUTH_SLOT = object()  # Symbolic only; no string credential is accepted here.
MAX_EVENT = 16384


def fail(code='mcp_sse_protocol_rejected'):
    contract.reject(code)


def message_endpoint(value, *, origin=ORIGIN, profile="legacy"):
    if profile not in ("legacy","official"):fail("mcp_sse_endpoint_rejected")
    paths=("/message",) if profile=="official" else ("/messages","/messages/")
    query=r"sessionId=[A-Za-z0-9_-]{1,128}" if profile=="official" else r"session_id=[A-Za-z0-9_-]{1,128}"
    if (type(value) is not str or len(value) > 512 or '%' in value or '\\' in value
            or any(ord(c) < 33 or ord(c) > 126 for c in value)):
        fail('mcp_sse_endpoint_rejected')
    u = urllib.parse.urlsplit(urllib.parse.urljoin(origin+'/sse', value))
    if (u.scheme != 'https' or u.netloc != urllib.parse.urlsplit(origin).netloc
            or u.path not in paths or u.fragment
            or not re.fullmatch(query, u.query)):
        fail('mcp_sse_endpoint_rejected')
    return urllib.parse.urlunsplit(u)


def encode(value):
    return json.dumps(value, separators=(',', ':')).encode()


def frame(value):
    return b'event: message\ndata: '+encode(value)+b'\n\n'


class ScriptedHTTP:
    """Raw in-memory HTTP/SSE test driver. No network, callbacks or credentials.

    Steps contain expected RPC method/tool and a raw response event (or timeout).
    Public trace records names/IDs/key names only; raw synthetic bodies are private.
    """
    def __init__(self, steps, *, opening=b'event: endpoint\ndata: /messages/?session_id=fixture\n\n',
                 status=200, content_type='text/event-stream', post_status=202,
                 chunk_bytes=7, close_ok=True):
        self.steps=deque(steps);self.pending=bytearray(opening)
        self.status=status;self.content_type=content_type;self.post_status=post_status
        self.chunk_bytes=chunk_bytes;self.close_ok=close_ok
        self.trace=[];self.closed=False;self.opened=False

    def __repr__(self): return '<private_scripted_sse>'

    def open(self, url, auth_slot):
        if self.opened or self.closed or url != ENDPOINT or auth_slot is not AUTH_SLOT:
            fail()
        self.opened=True;self.trace.append({'method':'GET','operation':'sse_open'})
        return self.status,self.content_type

    def read(self, limit):
        if self.closed: fail('mcp_sse_closed')
        if not self.pending: return b''
        n=min(limit,self.chunk_bytes,len(self.pending))
        if n <= 0: fail()
        out=bytes(self.pending[:n]);del self.pending[:n];return out

    def post(self, url, raw):
        if self.closed or not self.opened: fail('mcp_sse_closed')
        message_endpoint(url)
        msg=contract.payload(raw)
        self.trace.append({'method':'POST','operation':msg.get('method'), 'id':msg.get('id'),
                           'tool':msg.get('params',{}).get('name'),
                           'argument_keys':sorted(msg.get('params',{}).get('arguments',{}))})
        if not self.steps: fail()
        method,tool,response=self.steps.popleft()
        if msg.get('method') != method or msg.get('params',{}).get('name') != tool: fail()
        if response == 'timeout': raise TimeoutError()
        status=self.post_status
        if type(response) is tuple and len(response)==2:
            status,response=response
        if type(response) is not bytes or type(status) is not int: fail()
        self.pending.extend(response)
        return status

    def close(self):
        self.closed=True;self.pending.clear();self.steps.clear()
        return self.close_ok is True


class SSEClient:
    """Strict sequential, bounded MCP 2024-11-05 session. No automatic reconnect."""
    def __init__(self, driver, *, budget=5):
        if type(driver) is not ScriptedHTTP: fail('mcp_sse_driver_unavailable')
        if type(budget) not in (int,float) or not 0 < budget <= 30: fail()
        self._setup(driver,budget)

    def _setup(self,driver,budget):
        self.origin=ORIGIN;self.endpoint=ENDPOINT;self.message_profile="legacy"
        self.driver=driver;self.deadline=time.monotonic()+budget
        self.buffer=bytearray();self.total=0;self.lines=0;self.identifier=0
        self.url=None;self.connected=False;self.closed=False;self.called=set();self.last_rpc_error=None
        self.stage='not_started';self.failure_rule=None;self.event_bytes=0;self.event_count=0
        self.pending_line_bytes=0;self.line_buffer_high_water_bytes=0;self.last_event_kind='none';self.rpc_id_matches=None
        self.pagination_present=False

    @classmethod
    def for_local_fixture(cls,driver,*,budget=5):
        from .mcp_http import LocalHTTPSDriver
        if type(driver) is not LocalHTTPSDriver:fail('mcp_sse_driver_unavailable')
        if type(budget) not in (int,float) or not 0<budget<=30:fail()
        client=cls.__new__(cls);client._setup(driver,budget)
        client.origin=driver.origin;client.endpoint=driver.endpoint
        return client

    @classmethod
    def for_official_readonly(cls, driver, *, expected, budget=30):
        # A non-fixture object is mandatory; the former factory retained the
        # fixture-only tool() restriction and could not inspect an actual object.
        from .mcp_binding import BoundSession
        return BoundSession.official_readonly(driver,expected,budget=budget)

    def __repr__(self): return '<private_sse_session>'

    def check(self):
        if self.closed: fail('mcp_sse_closed')
        if time.monotonic() >= self.deadline: fail('mcp_sse_deadline')

    def reject_rule(self,rule):
        self.failure_rule=rule
        fail()  # Keep the existing public rejection code; add only a safe discriminator.

    def protocol_diagnostics(self):
        # Fixed labels, own sequence numbers, lengths and numeric HTTP statuses.
        # No endpoint/session, actual response ID, schema/text/key/exception values.
        statuses=getattr(self.driver,'http_statuses',[])
        from .mcp_http import LocalHTTPSDriver
        transport=self.driver.io_diagnostics() if isinstance(self.driver,LocalHTTPSDriver) else None
        return {'stage':self.stage,'failure_rule':self.failure_rule,
                'sse_bytes_read':self.total,'sse_lines_read':self.lines,
                'event_bytes':self.event_bytes,'pending_line_bytes':self.pending_line_bytes,
                'buffered_bytes':len(self.buffer),'line_buffer_high_water_bytes':self.line_buffer_high_water_bytes,
                'transport':transport,'event_count':self.event_count,'last_event_kind':self.last_event_kind,
                'rpc_sequence':self.identifier,'rpc_id_matches':self.rpc_id_matches,
                'pagination_present':self.pagination_present,
                'http_statuses':[v for v in statuses[-6:] if type(v) is int and 100<=v<=599]}

    def event(self):
        kind=None;data=[];event_bytes=0;self.event_bytes=0
        self.pending_line_bytes=len(self.buffer) if b'\n' not in self.buffer else 0
        self.line_buffer_high_water_bytes=len(self.buffer)
        while True:
            self.check()
            while b'\n' not in self.buffer:
                chunk=self.driver.read(1024);self.check()
                if type(chunk) is not bytes or len(chunk)>1024:self.reject_rule('stream_chunk_shape')
                if not chunk:self.reject_rule('stream_eof')
                self.total+=len(chunk);size=len(self.buffer)+len(chunk)
                self.line_buffer_high_water_bytes=max(self.line_buffer_high_water_bytes,size)
                if self.total>262144:self.reject_rule('stream_byte_limit')
                if size>MAX_EVENT:self.reject_rule('pending_line_limit')
                self.buffer.extend(chunk)
                self.pending_line_bytes=len(self.buffer) if b'\n' not in self.buffer else 0
            raw,_,rest=self.buffer.partition(b'\n');self.buffer=bytearray(rest)
            self.pending_line_bytes=len(self.buffer) if b'\n' not in self.buffer else 0
            self.lines+=1;event_bytes+=len(raw)+1;self.event_bytes=event_bytes
            if self.lines>512:self.reject_rule('stream_line_limit')
            if event_bytes>MAX_EVENT:self.reject_rule('event_byte_limit')
            try: line=raw.removesuffix(b'\r').decode('utf-8')
            except UnicodeError:self.reject_rule('invalid_utf8')
            if not line:
                if kind is None and not data: continue
                if kind not in ('endpoint','message') or not data:self.reject_rule('event_profile_unknown')
                self.event_count+=1
                self.last_event_kind=kind
                return kind,'\n'.join(data)
            if line.startswith(':'): continue
            key,separator,value=line.partition(':')
            if not separator:self.reject_rule('sse_field_shape')
            if value.startswith(' '):value=value[1:]
            if key=='event' and kind is None:
                kind=value;self.last_event_kind=value if value in ('endpoint','message') else 'other'
            elif key=='data':data.append(value)
            else:self.reject_rule('sse_field_unreviewed')  # No id/retry/reconnect.

    def rpc(self, method, params=None, *, notification=False):
        label={'initialize':'initialize','notifications/initialized':'initialized','tools/list':'tools_list','tools/call':'tool_call'}.get(method,'rpc')
        self.stage=label+'_post';self.rpc_id_matches=None
        self.check();msg={'jsonrpc':'2.0','method':method}
        if params is not None:msg['params']=params
        if not notification:self.identifier+=1;msg['id']=self.identifier
        # One dispatch, even when status/response is unknown. Never retry.
        status=self.driver.post(self.url,encode(msg));self.check()
        if type(status) is not int or status not in (200,202):self.reject_rule('post_status_unreviewed')
        if notification:
            self.stage=label+'_accepted';return None
        self.stage=label+'_reply'
        event,text=self.event()
        if event!='message':self.reject_rule('rpc_event_kind')
        try:response=contract.payload(text.encode())
        except contract.Rejected:
            self.failure_rule='json_profile_rejected';raise
        self.rpc_id_matches=type(response.get('id')) is int and response['id']==self.identifier
        if set(response)-{'jsonrpc','id','result','error'}:self.reject_rule('rpc_envelope_extra_fields')
        if response.get('jsonrpc')!='2.0':self.reject_rule('rpc_version')
        if not self.rpc_id_matches:self.reject_rule('rpc_id_mismatch')
        if ('result' in response)==('error' in response):self.reject_rule('rpc_result_error_exclusivity')
        if 'error' in response:
            error=response['error'];self.last_rpc_error={'category':'unclassified'}
            if type(error) is dict:
                if type(error.get('code')) is int:self.last_rpc_error['code']=error['code']
                message=error.get('message')
                if type(message) is str and any(word in message.lower() for word in
                        ('token','auth','credential','鉴权','认证','授权')):
                    self.last_rpc_error['category']='authentication_related'
            self.failure_rule='rpc_error_response'
            fail('mcp_sse_rpc_error')
        if type(response['result']) is not dict:self.reject_rule('rpc_result_type')
        return response['result']

    def connect(self):
        if self.connected: return
        self.stage='sse_open'
        self.check();status,mime=self.driver.open(self.endpoint,AUTH_SLOT)
        if type(status) is not int or status!=200 or mime!='text/event-stream':self.reject_rule('sse_open_profile')
        self.stage='endpoint_event'
        event,value=self.event()
        if event!='endpoint':self.reject_rule('endpoint_event_kind')
        self.url=message_endpoint(value,origin=self.origin,profile=self.message_profile)
        result=self.rpc('initialize',{'protocolVersion':VERSION,'capabilities':{},
                                     'clientInfo':{'name':'fast-transfer-offline','version':'0.1'}})
        if (result.get('protocolVersion')!=VERSION or type(result.get('capabilities')) is not dict
                or type(result.get('serverInfo')) is not dict):self.reject_rule('initialize_result_profile')
        self.rpc('notifications/initialized',notification=True)
        tools=self.rpc('tools/list')
        self.stage='tools_list_shape'
        self.pagination_present=tools.get('nextCursor') is not None
        if set(tools)-{'tools','nextCursor','_meta'}:self.reject_rule('tools_list_extra_fields')
        if tools.get('_meta') is not None and type(tools['_meta']) is not dict:self.reject_rule('tools_meta_type')
        if self.pagination_present:self.reject_rule('tools_pagination_unreviewed')
        if type(tools.get('tools')) is not list:self.reject_rule('tools_list_type')
        descriptors={}
        for item in tools['tools']:
            if type(item) is not dict or type(item.get('name')) is not str or item['name'] in descriptors:self.reject_rule('tool_descriptor_shape_or_duplicate')
            descriptors[item['name']]=item.get('inputSchema')
        self.stage='schema_review'
        try:self.review_descriptors(descriptors)
        except contract.Rejected:
            self.failure_rule='input_schema_unproven';raise
        self.connected=True;self.stage='connected'

    def review_descriptors(self,descriptors):
        if any(descriptors.get(k)!=v for k,v in schemas().items()):fail('mcp_sse_schema_unproven')

    def tool(self, name, arguments):
        if type(arguments) is not dict: fail()
        if name=='user_info':
            if arguments!={}: fail()
        elif name=='file_meta':
            if (arguments!={'fsids':[int(contract.FIXTURE_FSID)]}
                    or type(arguments['fsids'][0]) is not int): fail()
        elif name=='file_sharelink_set':
            if (set(arguments)!={'fsid_list','period','pwd'}
                    or arguments['fsid_list']!=json.dumps([contract.FIXTURE_FSID],separators=(',',':'))
                    or type(arguments['period']) is not int or arguments['period']!=7
                    or type(arguments['pwd']) is not str or not re.fullmatch('[a-z0-9]{4}',arguments['pwd'])): fail()
        else: fail()
        self.connect();self.check()
        if name not in schemas() or name in self.called:fail()
        self.called.add(name)
        result=self.rpc('tools/call',{'name':name,'arguments':arguments})
        if set(result)-{'content','isError'} or type(result.get('isError',False)) is not bool:fail()
        if result.get('isError',False):fail('mcp_sse_tool_error')
        content=result.get('content')
        if (type(content) is not list or len(content)!=1 or type(content[0]) is not dict
                or set(content[0])!={'type','text'} or content[0]['type']!='text'
                or type(content[0]['text']) is not str):fail()
        # MCP TextContent is standard; JSON inside text is a fixture business profile,
        # not a claim about the real service's business envelope or authentication.
        return contract.Observation(encode(contract.payload(content[0]['text'].encode())))

    def close(self):
        self.closed=True;self.connected=False;self.buffer.clear();self.url=None
        try:return self.driver.close() is True
        except Exception:return False


def schemas():
    """Conservative fixture/discovery profile, NOT a published Baidu schema."""
    def obj(fields):return {'type':'object','properties':fields,'required':list(fields)}
    return {'user_info':obj({}),
            'file_meta':obj({'fsids':{'type':'array','items':{'type':'integer'}}}),
            'file_sharelink_set':obj({'fsid_list':{'type':'string'},'period':{'type':'integer'},'pwd':{'type':'string'}})}


def exercise(job,driver,*,pwd):
    return _exercise(job,driver,pwd=pwd,local=False)

def exercise_local_fixture(job,driver,*,pwd):
    return _exercise(job,driver,pwd=pwd,local=True)

def _exercise(job,driver,*,pwd,local):
    client=None
    try:
        client=SSEClient.for_local_fixture(driver) if local else SSEClient(driver)
        transport=contract.FixtureTransport(None,None,None,protocol=client)
        result=contract.exercise_share(job,transport,pwd=pwd)
    except Exception:
        result={'mode':'mcp-fixture-only','status':'rejected','reason':'mcp_sse_driver_unavailable',
                'create_attempted':False,'outcome_unknown':False,'delivery_eligible':False,
                'mapping_verified':False,'live_authenticated':False,'share_eligible':False,
                'automatic_retry_allowed':False}
    closed=client.close() if client is not None else None
    result.update(protocol_closed=closed,live_connected=False,external_service_connected=False,
                  transport_scope='local-loopback-tls' if local else 'scripted-memory',
                  local_tls_connected=bool(local and client is not None and client.driver.tls_version))
    if closed is False:result.update(status='manual_review',reason='mcp_sse_stop_unconfirmed')
    return result

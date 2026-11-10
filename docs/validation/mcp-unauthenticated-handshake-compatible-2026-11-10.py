"""Bounded unauthenticated SSE/initialize probe. No business calls or retries."""
import datetime
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import threading
import time
import urllib.parse

HOST='mcp-pan.baidu.com';ORIGIN='https://'+HOST;VERSION='2024-11-05'
start=time.monotonic();deadline=start+15
r={'observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
   'target':ORIGIN+'/sse','execution_scope':'current project execution host; not overseas VPS',
   'authentication_sent':False,'business_calls':0,'share_calls':0,'get_requests':0,
   'initialize_requests':0,'initialized_notifications':0,'redirects_followed':0,
   'sse_endpoint_event_verified':False,'mcp_initialize_verified':False,
   'identity_verified':False,'business_verified':False,'protocol_version_requested':VERSION}
owned=[];connections=[];responses=[];total=0;lines=0;buffer=bytearray()
class Stop(Exception):pass

def remaining():
    left=deadline-time.monotonic()
    if left<=0:raise Stop('deadline')
    return min(4,left)

def interrupt():
    for item in tuple(owned):
        try:item.shutdown(socket.SHUT_RDWR)
        except OSError:pass
watch=threading.Timer(15,interrupt);watch.daemon=True;watch.start()

def parse(raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise Stop('duplicate_json_key')
            value[key]=item
        return value
    try:
        value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(Stop('invalid_json_constant')))
    except (ValueError,UnicodeError,RecursionError):raise Stop('invalid_json') from None
    if type(value) is not dict:raise Stop('json_object_required')
    return value

def event(reply):
    global total,lines,buffer
    kind=None;data=[];size=0
    while True:
        remaining()
        while b'\n' not in buffer:
            for item in owned:
                if item.fileno()>=0:item.settimeout(remaining())
            chunk=reply.read1(1024)
            if not chunk:raise Stop('sse_eof')
            total+=len(chunk)
            if total>16384 or len(buffer)+len(chunk)>8192:raise Stop('sse_byte_limit')
            buffer.extend(chunk)
        raw,_,tail=buffer.partition(b'\n');buffer=bytearray(tail)
        lines+=1;size+=len(raw)+1
        if lines>256 or size>8192:raise Stop('sse_frame_limit')
        try:line=raw.removesuffix(b'\r').decode('utf-8')
        except UnicodeError:raise Stop('invalid_utf8') from None
        if not line:
            if kind is None and not data:continue
            if kind not in ('endpoint','message') or not data:raise Stop('sse_event_profile_unknown')
            return kind,'\n'.join(data)
        if line.startswith(':'):continue
        key,sep,value=line.partition(':')
        if not sep:raise Stop('sse_field_invalid')
        if value.startswith(' '):value=value[1:]
        if key=='event' and kind is None:kind=value
        elif key=='data':data.append(value)
        else:raise Stop('sse_field_profile_unknown')

def endpoint(text):
    if (len(text)>512 or '%' in text or '\\' in text or any(ord(ch)<33 or ord(ch)>126 for ch in text)):
        raise Stop('message_endpoint_rejected')
    u=urllib.parse.urlsplit(urllib.parse.urljoin(ORIGIN+'/sse',text))
    if (u.scheme!='https' or u.netloc!=HOST or u.path not in ('/messages','/messages/','/message','/message/','/mcp/message','/mcp/message/','/mcp/messages','/mcp/messages/','/sse/message','/sse/message/','/sse/messages','/sse/messages/')
            or u.fragment or not re.fullmatch(r'sessionId=[A-Za-z0-9_-]{1,128}',u.query)):
        raise Stop('message_endpoint_rejected')
    r['message_route_profile']=u.path  # Value can only be one of the static routes above.
    r['session_query_key']='sessionId'
    return urllib.parse.urlunsplit(('', '', u.path,u.query,''))

phase='dns'
try:
    addresses=socket.getaddrinfo(HOST,443,type=socket.SOCK_STREAM)
    if not addresses:raise Stop('dns_empty')
    for family,kind,proto,canon,address in addresses:
        ip=ipaddress.ip_address(address[0])
        if family not in (socket.AF_INET,socket.AF_INET6) or not ip.is_global or ip.is_multicast:
            raise Stop('dns_nonpublic')
    family,_,_,_,address=addresses[0];r['dns_verified']=True
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.load_default_certs()
    def connect():
        raw=socket.socket(family,socket.SOCK_STREAM);owned.append(raw)
        raw.settimeout(remaining());raw.connect(address)
        wrapped=ctx.wrap_socket(raw,server_hostname=HOST,do_handshake_on_connect=False);owned.append(wrapped)
        wrapped.settimeout(remaining());wrapped.do_handshake()
        r['tls_version']=wrapped.version();r['certificate_chain_and_hostname_verified']=True
        connection=http.client.HTTPSConnection(HOST,timeout=remaining(),context=ctx)
        connection.sock=wrapped;connection.set_debuglevel(0);connections.append(connection)
        return connection
    def response(connection):
        reply=connection.getresponse();responses.append(reply)
        headers=reply.getheaders()
        if len(headers)>32 or sum(len(k)+len(v) for k,v in headers)>16384:raise Stop('header_limit')
        for key in ('content-type','content-length','transfer-encoding'):
            if sum(k.lower()==key for k,v in headers)>1:raise Stop('duplicate_header')
        if reply.getheader('Content-Length') and reply.getheader('Transfer-Encoding'):raise Stop('header_conflict')
        if reply.getheader('Content-Encoding') not in (None,'identity'):raise Stop('content_encoding_rejected')
        return reply
    phase='sse_get';connection=connect();r['get_requests']+=1
    connection.request('GET','/sse',headers={'Accept':'text/event-stream','Accept-Encoding':'identity'})
    reply=response(connection);r['get_http_status']=reply.status
    if reply.status!=200:raise Stop('sse_get_http_status')
    if reply.getheader('Content-Type','').split(';',1)[0].strip().lower()!='text/event-stream':raise Stop('sse_mime_rejected')
    phase='sse_endpoint_event';kind,text=event(reply)
    if kind!='endpoint':
        # Do not interpret arbitrary event text as a successful auth envelope.
        raise Stop('initial_event_not_endpoint')
    path=endpoint(text);text=None;r['sse_endpoint_event_verified']=True
    def post(message,counter):
        c=connect();r[counter]+=1
        c.request('POST',path,body=json.dumps(message,separators=(',',':')).encode(),
                  headers={'Content-Type':'application/json','Accept-Encoding':'identity'})
        response_value=response(c);status=response_value.status
        response_value.close();c.close()
        return status
    phase='initialize_post'
    status=post({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':VERSION,
        'capabilities':{},'clientInfo':{'name':'fast-transfer-reachability-probe','version':'0.1'}}},'initialize_requests')
    r['initialize_post_status']=status
    if status not in (200,202):raise Stop('initialize_http_status')
    phase='initialize_result';kind,text=event(reply)
    if kind!='message':raise Stop('initialize_event_not_message')
    value=parse(text);text=None
    if (set(value)-{'jsonrpc','id','result','error'} or value.get('jsonrpc')!='2.0'
            or type(value.get('id')) is not int or value['id']!=1
            or ('result' in value)==('error' in value)):raise Stop('initialize_rpc_envelope_invalid')
    if 'error' in value:
        error=value['error']
        if type(error) is dict and type(error.get('code')) is int:r['rpc_error_code']=error['code']
        raise Stop('initialize_rpc_error')
    result=value['result']
    if type(result) is not dict:raise Stop('initialize_result_invalid')
    accepted=result.get('protocolVersion')
    if type(accepted) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',accepted):r['protocol_version_returned']=accepted
    if (accepted!=VERSION or type(result.get('capabilities')) is not dict
            or type(result.get('serverInfo')) is not dict):raise Stop('initialize_profile_not_verified')
    r['mcp_initialize_verified']=True
    phase='initialized_notification'
    status=post({'jsonrpc':'2.0','method':'notifications/initialized'},'initialized_notifications')
    r['initialized_post_status']=status
    if status not in (200,202):raise Stop('initialized_http_status')
    r['result']='unauthenticated_minimal_handshake_completed'
except Stop as exc:
    r.update(result='stopped',stop_reason=exc.args[0],failure_phase=phase)
except Exception as exc:
    r.update(result='stopped',failure_phase=phase,error_type=type(exc).__name__)
    if isinstance(exc,OSError) and type(exc.errno) is int:r['os_errno']=exc.errno
    if isinstance(exc,ssl.SSLCertVerificationError):r['certificate_verify_code']=exc.verify_code
finally:
    path=None;buffer.clear();watch.cancel();interrupt();closed=True
    for resource in responses+connections+owned:
        try:resource.close()
        except Exception:closed=False
    watch.join(timeout=.2)
    r.update(protocol_bytes_read=total,sse_lines_read=lines,elapsed_seconds=round(time.monotonic()-start,4),
             close_confirmed=closed and not watch.is_alive() and all(sock.fileno()<0 for sock in owned))
print(json.dumps(r,ensure_ascii=False,indent=2))

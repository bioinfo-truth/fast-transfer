"""One unauthenticated official SSE GET; no proxies, redirects or retries."""
import datetime
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import threading
import time

HOST='mcp-pan.baidu.com'
start=time.monotonic()
r={'observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
   'target':'https://mcp-pan.baidu.com/sse','request_method':'GET','authentication_sent':False,
   'proxy_used':False,'redirect_followed':False,'attempts':1,'dns':False,'tcp':False,'tls':False,
   'http':False,'sse_protocol_verified':False,'identity_verified':False,'business_verified':False,
   'business_calls':0,'share_calls':0}
owned=[]
def expire():
    for sock in tuple(owned):
        try:sock.shutdown(socket.SHUT_RDWR)
        except OSError:pass
watch=threading.Timer(15,expire);watch.daemon=True;watch.start()
phase='dns'
try:
    before=time.monotonic()
    answers=socket.getaddrinfo(HOST,443,type=socket.SOCK_STREAM)
    r['dns_seconds']=round(time.monotonic()-before,4)
    candidates=[]
    for family,kind,proto,canon,address in answers:
        ip=ipaddress.ip_address(address[0])
        if family not in (socket.AF_INET,socket.AF_INET6) or not ip.is_global or ip.is_multicast:
            raise ValueError('nonpublic_dns_answer')
        pair=(family,address)
        if pair not in candidates:candidates.append(pair)
    if not candidates:raise ValueError('empty_dns_answer')
    r.update(dns=True,dns_public_addresses=[a[0] for _,a in candidates])
    family,address=candidates[0]
    phase='tcp';before=time.monotonic()
    raw=socket.socket(family,socket.SOCK_STREAM);owned.append(raw)
    raw.settimeout(5);raw.connect(address)
    r.update(tcp=True,connected_address=address[0],tcp_seconds=round(time.monotonic()-before,4))
    phase='tls';before=time.monotonic()
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.load_default_certs()
    secured=ctx.wrap_socket(raw,server_hostname=HOST,do_handshake_on_connect=False);owned.append(secured)
    secured.settimeout(5);secured.do_handshake()
    r.update(tls=True,tls_seconds=round(time.monotonic()-before,4),tls_version=secured.version(),
             certificate_chain_verified=True,hostname_verified=True,
             leaf_certificate_sha256=hashlib.sha256(secured.getpeercert(binary_form=True)).hexdigest())
    phase='http';before=time.monotonic()
    connection=http.client.HTTPSConnection(HOST,timeout=5,context=ctx);connection.sock=secured
    connection.set_debuglevel(0)
    connection.request('GET','/sse',headers={'Accept':'text/event-stream','Accept-Encoding':'identity','Connection':'close'})
    response=connection.getresponse()
    mime=response.getheader('Content-Type','').split(';',1)[0].strip().lower()
    r.update(http=True,http_status=response.status,http_header_seconds=round(time.monotonic()-before,4),
             content_type=mime if mime in ('application/json','text/event-stream','text/plain','text/html') else 'other',
             redirect_present=response.getheader('Location') is not None)
    phase='body_classification'
    if mime=='text/event-stream':
        r['response_category']='event_stream_headers_only_not_protocol_validation'
    else:
        data=response.read1(2048)
        r['body_sample_bytes']=len(data)
        r['response_category']='non_sse_response'
        try:
            value=json.loads(data)
            if isinstance(value,dict):
                r['response_category']='json_object'
                for key in ('errno','error_code','code'):
                    if type(value.get(key)) is int:r['service_'+key]=value[key]
                combined=' '.join(str(value.get(k,'')) for k in ('error','error_msg','message','msg')).lower()
                if any(word in combined for word in ('token','auth','credential','鉴权','授权','认证')):
                    r['response_category']='json_authentication_related'
        except (ValueError,UnicodeError):pass
    response.close();connection.close()
except Exception as exc:
    r.update(failure_phase=phase,error_type=type(exc).__name__)
    if isinstance(exc,OSError) and type(exc.errno) is int:r['os_errno']=exc.errno
    if isinstance(exc,ssl.SSLCertVerificationError):r['certificate_verify_code']=exc.verify_code
finally:
    watch.cancel()
    for sock in owned:
        try:sock.close()
        except OSError:pass
    r['elapsed_seconds']=round(time.monotonic()-start,4)
print(json.dumps(r,ensure_ascii=False,indent=2))

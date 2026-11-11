"""Fixed Baidu device OAuth GET transport; explicit in-memory arguments only.

No OAuth call occurs on import/construction. Query credentials never enter logs.
Official generated SDK confirms GET/query, not an assumed POST/body variant.
"""
import http.client
import ipaddress
import queue
import socket
import ssl
import threading
import urllib.parse

from .mcp_http import LocalHTTPSDriver
from . import mcp_share as c

HOST='openapi.baidu.com'


def _resolve(out):
    try:out.put(socket.getaddrinfo(HOST,443,type=socket.SOCK_STREAM))
    except Exception:out.put(None)


class _Connection(http.client.HTTPSConnection):
    def __init__(self,driver):
        super().__init__(HOST,port=443,timeout=driver.timeout(),context=driver.context)
        self.driver=driver;self.set_debuglevel(0)
    def connect(self):
        d=self.driver;d.check_tls();family,address=d.address
        raw=socket.socket(family,socket.SOCK_STREAM);d.own_socket(raw)
        try:
            raw.settimeout(d.timeout());raw.connect(address)
            wrapped=d.context.wrap_socket(raw,server_hostname=HOST,do_handshake_on_connect=False)
            d.own_socket(wrapped);self.sock=wrapped
            wrapped.settimeout(d.timeout());wrapped.do_handshake();d.check()
        except BaseException:
            raw.close()
            if self.sock is not None:self.sock.close()
            raise


class _Request(LocalHTTPSDriver):
    def __init__(self):
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version=ssl.TLSVersion.TLSv1_2;context.load_default_certs()
        super().__init__(4430,context,io_timeout=3,budget=15)
        self.address=None
    def open(self,*args,**kwargs):c.reject('device_sse_unavailable')
    def post(self,*args,**kwargs):c.reject('device_sse_unavailable')
    def request_json(self,path,params):
        if path not in ('/oauth/2.0/device/code','/oauth/2.0/token'):c.reject('device_target_rejected')
        expected=({'response_type','openapi','client_id','scope'} if path.endswith('/device/code') else
                  {'grant_type','openapi','client_id','client_secret','code'})
        if (type(params) is not dict or set(params)!=expected or params.get('openapi')!='xpansdk'
                or (path.endswith('/device/code') and (params['response_type']!='device_code' or params['scope']!='basic,netdisk'))
                or (path.endswith('/token') and params['grant_type']!='device_token')):
            c.reject('device_request_scope_rejected')
        with self.operation():
            out=queue.Queue(maxsize=1)
            threading.Thread(target=_resolve,args=(out,),daemon=True).start()
            try:answers=out.get(timeout=self.timeout())
            except queue.Empty:c.reject('device_dns_timeout')
            self.check()
            if not answers:c.reject('device_dns_failed')
            for family,kind,proto,name,address in answers:
                ip=ipaddress.ip_address(address[0])
                if family not in (socket.AF_INET,socket.AF_INET6) or not ip.is_global or ip.is_multicast or address[1]!=443:
                    c.reject('device_dns_rejected')
            family,_,_,_,address=answers[0];self.address=(family,address)
            connection=_Connection(self);self._connections.append(connection)
            # HTTP debug is fixed off. No proxy env, redirect or automatic retry.
            connection.request('GET',path+'?'+urllib.parse.urlencode(params),headers={
                'Accept':'application/json','Accept-Encoding':'identity'})
            reply=connection.getresponse();self._responses.append(reply)
            headers=reply.getheaders()
            if len(headers)>32 or sum(len(k)+len(v) for k,v in headers)>16384:c.reject('device_headers_rejected')
            if any(sum(k.lower()==key for k,v in headers)>1 for key in ('content-type','content-length','transfer-encoding')):
                c.reject('device_headers_rejected')
            if reply.getheader('Content-Length') and reply.getheader('Transfer-Encoding'):c.reject('device_headers_rejected')
            if reply.getheader('Content-Encoding') not in (None,'identity'):c.reject('device_headers_rejected')
            if reply.status not in (200,400):c.reject('device_http_status_rejected')
            if reply.getheader('Content-Type','').split(';',1)[0].strip().lower()!='application/json':
                c.reject('device_mime_rejected')
            raw=bytearray()
            while True:
                self.check()
                for sock in self._sockets:
                    if sock.fileno()>=0:sock.settimeout(self.timeout())
                chunk=reply.read1(1024)
                if not chunk:break
                raw.extend(chunk)
                if len(raw)>16384:c.reject('device_response_limit')
            value=c.payload(bytes(raw));raw.clear()
            if reply.status==400 and 'error' not in value:c.reject('device_http_status_rejected')
            return value


class DeviceOAuthHTTP:
    """Only same application device/create and device-token exchange, no refresh."""
    def __repr__(self):return '<private_device_oauth_transport>'
    def _get(self,path,params):
        request=None
        try:
            request=_Request()
            return request.request_json(path,params)
        finally:
            params.clear()
            if request is not None and not request.close():c.reject('device_close_unconfirmed')
    def device(self,app_key,scope):
        if scope!='basic,netdisk':c.reject('device_scope_rejected')
        return self._get('/oauth/2.0/device/code',{'response_type':'device_code',
            'openapi':'xpansdk','client_id':app_key,'scope':scope})
    def poll(self,app_key,secret_key,device_code):
        return self._get('/oauth/2.0/token',{'grant_type':'device_token','openapi':'xpansdk',
            'client_id':app_key,'client_secret':secret_key,'code':device_code})

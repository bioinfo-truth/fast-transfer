"""Candidate real HTTPS/SSE I/O, exposed ONLY for explicit loopback fixtures.

No credentials, DNS, environment proxies, redirects, reconnects or retries.
External service factory always rejects. Socket watchdog owns only this driver.
"""
import contextlib
import http.client
import math
import socket
import ssl
import threading
import time

from . import mcp_share as contract


def fail(code): contract.reject(code)


def external_driver(*args, **kwargs):
    fail('mcp_external_driver_locked')


class _Connection(http.client.HTTPSConnection):
    def __init__(self, driver):
        super().__init__('127.0.0.1',port=driver.port,timeout=driver.timeout(),context=driver.context)
        self.driver=driver
        self.set_debuglevel(0)

    def connect(self):
        self.driver.check_tls()
        raw=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.driver.own_socket(raw)
        try:
            raw.settimeout(self.driver.timeout());raw.connect(('127.0.0.1',self.driver.port))
            wrapped=self.driver.context.wrap_socket(raw,server_hostname='127.0.0.1',do_handshake_on_connect=False)
            self.driver.own_socket(wrapped);self.sock=wrapped
            wrapped.settimeout(self.driver.timeout());wrapped.do_handshake()
            self.driver.tls_version=wrapped.version()
            self.driver.check()
        except BaseException:
            raw.close()
            if self.sock is not None:self.sock.close()
            raise


class LocalHTTPSDriver:
    """Physical destination is hard-pinned numeric loopback, no host argument.

    Accepts a fixture CA context with certificate/hostname checks and TLS>=1.2.
    The public production/SSE constructor still rejects this type: use the
    separate SSEClient.for_local_fixture / exercise_local_fixture entry only.
    """
    def __init__(self, port, context, *, io_timeout=.5, budget=3):
        if type(port) is not int or not 1024<=port<=65535:fail('mcp_local_scope_rejected')
        for value in (io_timeout,budget):
            if type(value) not in (int,float) or not math.isfinite(value) or not .05<=value<=30:
                fail('mcp_local_scope_rejected')
        self.port=port;self.context=context;self.io_timeout=io_timeout;self.message_profile='legacy'
        self.origin=f'https://127.0.0.1:{port}';self.endpoint=self.origin+'/sse'
        self.deadline=time.monotonic()+budget;self.tls_version=None
        self._lock=threading.Lock();self._read_lock=threading.Lock();self._post_lock=threading.Lock()
        self._sockets=[];self._connections=[];self._responses=[];self._active=0;self._closers=0
        self._closed=False;self._expired=False;self._cleanup_failed=False;self._opened=False
        self._reply=None;self._total=0;self._posts=0;self.trace=[];self.http_statuses=[]
        self.check_tls()
        self._timer=threading.Timer(budget,self._expire);self._timer.daemon=True;self._timer.start()

    def __repr__(self):return '<private_local_https_driver>'

    def check_tls(self):
        if (not isinstance(self.context,ssl.SSLContext) or self.context.verify_mode!=ssl.CERT_REQUIRED
                or not self.context.check_hostname or self.context.minimum_version<ssl.TLSVersion.TLSv1_2
                or self.context.keylog_filename is not None):
            fail('mcp_local_tls_policy_rejected')

    def check(self):
        if self._closed:fail('mcp_local_closed')
        if self._expired or time.monotonic()>=self.deadline:fail('mcp_local_deadline')

    def timeout(self):
        self.check();return min(self.io_timeout,max(.001,self.deadline-time.monotonic()))

    def own_socket(self,sock):
        with self._lock:
            if self._closed or self._expired:
                sock.close();self.check();fail('mcp_local_closed')
            self._sockets.append(sock)

    def _interrupt(self):
        with self._lock:sockets=tuple(self._sockets)
        for sock in sockets:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass  # Detached, already closed, or not connected yet.

    def _expire(self):
        self._expired=True;self._interrupt()

    @contextlib.contextmanager
    def operation(self):
        self.check()
        with self._lock:self._active+=1
        try:
            yield
            self.check()
        except contract.Rejected:raise
        except (TimeoutError,socket.timeout):
            fail('mcp_local_deadline' if self._expired else 'mcp_local_timeout')
        except ssl.SSLError:
            fail('mcp_local_deadline' if self._expired else 'mcp_local_tls_error')
        except Exception:
            fail('mcp_local_closed' if self._closed else 'mcp_local_deadline' if self._expired else 'mcp_local_io_failure')
        finally:
            with self._lock:self._active-=1

    def _connection(self):
        self.check_tls();c=_Connection(self)
        with self._lock:self._connections.append(c)
        return c

    def _response(self,c):
        response=c.getresponse()
        self.http_statuses.append(response.status)
        with self._lock:self._responses.append(response)
        headers=response.getheaders()
        if (len(headers)>32 or sum(len(k)+len(v) for k,v in headers)>16384
                or any(len([v for k,v in headers if k.lower()==name])>1
                       for name in ('content-type','content-length','transfer-encoding'))):
            fail('mcp_local_headers_rejected')
        if response.getheader('Content-Length') and response.getheader('Transfer-Encoding'):
            fail('mcp_local_headers_rejected')
        if response.getheader('Content-Encoding') not in (None,'identity'):fail('mcp_local_headers_rejected')
        if response.status not in (200,202):fail('mcp_local_status_rejected')
        return response

    def _opening_path(self):return '/sse'

    def open(self,url,auth_slot):
        from .mcp_sse import AUTH_SLOT
        if url!=self.endpoint or auth_slot is not AUTH_SLOT or self._opened:fail('mcp_local_scope_rejected')
        self._opened=True
        with self.operation():
            self.trace.append({'method':'GET','operation':'sse_open'})
            c=self._connection();c.request('GET',self._opening_path(),headers={'Accept':'text/event-stream','Accept-Encoding':'identity'})
            self._reply=self._response(c)
            if self._reply.status!=200:fail('mcp_local_status_rejected')
            mime=self._reply.getheader('Content-Type','').split(';',1)[0].strip().lower()
            if mime!='text/event-stream':fail('mcp_local_headers_rejected')
            return 200,mime

    def read(self,limit):
        if type(limit) is not int or not 1<=limit<=1024 or self._reply is None:fail('mcp_local_scope_rejected')
        with self._read_lock,self.operation():
            for sock in self._sockets:
                if sock.fileno()>=0:sock.settimeout(self.timeout())
            data=self._reply.read1(limit)
            self._total+=len(data)
            if self._total>262144:fail('mcp_local_limit')
            return data

    def post(self,url,raw):
        from .mcp_sse import message_endpoint
        message_endpoint(url,origin=self.origin,profile=self.message_profile)
        if type(raw) is not bytes or len(raw)>16384:fail('mcp_local_limit')
        # No arbitrary trace values, headers, credentials or response bodies.
        msg=contract.payload(raw)
        path=url[len(self.origin):]
        with self._post_lock,self.operation():
            self._posts+=1
            if self._posts>6:fail('mcp_local_limit')
            self.trace.append({'method':'POST','operation':msg.get('method'),'id':msg.get('id'),
                               'tool':msg.get('params',{}).get('name')})
            c=self._connection()
            try:
                c.request('POST',path,body=raw,headers={'Content-Type':'application/json','Accept-Encoding':'identity'})
                response=self._response(c)
                status=response.status
                response.close();return status
            finally:c.close()

    def close(self):
        with self._lock:self._closers+=1
        try:
            self._closed=True;self._timer.cancel();self._interrupt()
            for resource in self._responses+self._connections+self._sockets:
                try:resource.close()
                except Exception:self._cleanup_failed=True
            if self._timer is not threading.current_thread():self._timer.join(timeout=.2)
        finally:
            with self._lock:self._closers-=1
        with self._lock:
            return (not self._cleanup_failed and not self._active and not self._closers
                    and not self._timer.is_alive())

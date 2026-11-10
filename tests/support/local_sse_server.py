"""Owned loopback TLS fixture. No production credentials or external requests."""
import http.server
import json
from pathlib import Path
import queue
import socket
import socketserver
import ssl
import threading
import time


class Case:
    def __init__(self,mode='normal',context=None):
        self.mode=mode;self.context=context;self.release=threading.Event();self.feed=queue.Queue()
        self.gets=0;self.posts=0;self.shares=0;self.trace=[]


class Server(http.server.ThreadingHTTPServer):
    daemon_threads=True;block_on_close=False
    def __init__(self,context):
        super().__init__(('127.0.0.1',0),Handler)
        self.context=context;self.case=Case();self.owned=[];self.guard=threading.Lock()
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name='local-fixture';self.server_port=self.server_address[1]
    def get_request(self):
        raw,address=self.socket.accept();raw.settimeout(1)
        case=self.case
        if case.mode=='stall_tls':
            case.release.wait(2);raw.close();raise OSError('fixture TLS stall ended')
        try:
            wrapped=(case.context or self.context).wrap_socket(raw,server_side=True)
            with self.guard:self.owned.append(wrapped)
            return wrapped,address
        except Exception:raw.close();raise
    def handle_error(self,*args):pass
    def reset(self,case):
        self.case.release.set()
        with self.guard:sockets=tuple(self.owned);self.owned=[]
        for sock in sockets:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            sock.close()
        self.case=case
    def finish_fixture(self):
        self.reset(Case());self.shutdown();self.server_close()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def _chunk(self,data):
        self.wfile.write(f'{len(data):x}\r\n'.encode()+data+b'\r\n');self.wfile.flush()
    def do_GET(self):
        c=self.server.case;c.gets+=1
        if self.path!='/sse':self.send_error(404);return
        if c.mode=='stall_headers':c.release.wait(2);return
        if c.mode=='trickle_headers':
            try:
                for b in b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n\r\n':
                    if c.release.is_set():return
                    self.wfile.write(bytes([b]));self.wfile.flush();time.sleep(.03)
            except OSError:pass
            return
        if c.mode=='redirect_get':
            self.send_response(302);self.send_header('Location','https://not-a-real-target.invalid/?access_token=SYNTHETIC_PRIVATE')
            self.send_header('Content-Length','0');self.end_headers();return
        self.send_response(200);self.send_header('Content-Type','text/html' if c.mode=='wrong_mime' else 'text/event-stream; charset=utf-8')
        if c.mode=='duplicate_type':self.send_header('Content-Type','text/event-stream')
        self.send_header('Transfer-Encoding','chunked');self.end_headers();self.wfile.flush()
        if c.mode=='stall_read':
            c.release.wait(2);return
        try:
            if c.mode=='drop_frame':self._chunk(b'event: endpoint\ndata: /messages/');self.wfile.write(b'0\r\n\r\n');self.wfile.flush();return
            endpoint=b'https://not-a-real-target.invalid/messages/?session_id=fixture' if c.mode=='cross_origin' else b'/messages/?session_id=fixture'
            self._chunk(b'event: endpoint\ndata: '+endpoint+b'\n\n')
            while not c.release.is_set():
                try:data=c.feed.get(timeout=.05)
                except queue.Empty:continue
                self._chunk(data)
        except (OSError,ValueError):pass
    def do_POST(self):
        from fast_transfer.mcp_sse import frame,schemas,VERSION
        from test_mcp_share import fixture
        c=self.server.case;c.posts+=1
        if self.path!='/messages/?session_id=fixture':self.send_error(404);return
        length=self.headers.get('Content-Length','0')
        if not length.isdigit() or int(length)>16384:self.send_error(413);return
        try:msg=json.loads(self.rfile.read(int(length)))
        except (ValueError,OSError):return
        name=msg.get('params',{}).get('name');method=msg.get('method')
        c.trace.append({'method':method,'tool':name,'id':msg.get('id')})
        if name=='file_sharelink_set':
            c.shares+=1
            if c.mode=='share_timeout':c.release.wait(2);return
            if c.mode=='redirect_share':
                self.send_response(307);self.send_header('Location','https://not-a-real-target.invalid/?pwd=SYNTHETIC_PRIVATE')
                self.send_header('Content-Length','0');self.end_headers();return
        result=None
        if method=='initialize':result={'protocolVersion':VERSION,'capabilities':{},'serverInfo':{'name':'local-TLS-fixture','version':'1'}}
        elif method=='tools/list':result={'tools':[{'name':k,'inputSchema':v} for k,v in schemas().items()]}
        elif method=='notifications/initialized':pass
        elif method=='tools/call':
            f=fixture()
            obj=json.loads((f._share if name=='file_sharelink_set' else f._observations[name]).raw)
            if c.mode=='wrong_identity' and name=='user_info':obj={'uk':'9999'}
            result={'content':[{'type':'text','text':json.dumps(obj)}]}
        else:self.send_error(400);return
        self.send_response(202);self.send_header('Content-Length','0');self.end_headers();self.wfile.flush()
        if result is not None:
            if c.mode=='corrupt_share' and name=='file_sharelink_set':c.feed.put(b'event: message\ndata: INVALID\n\n')
            else:c.feed.put(frame({'jsonrpc':'2.0','id':msg['id'],'result':result}))

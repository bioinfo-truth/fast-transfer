"""Explicit official MCP transport; no discovery, OAuth, LLM or automatic retry.

This stage exposes read-only protocol requests. Real sharing remains gated by
application/object contract review and the existing durable intent workflow.
"""
import http.client
import ipaddress
import queue
import socket
import ssl
import threading
import urllib.parse

from . import mcp_http as base
from . import mcp_share as contract

HOST = 'mcp-pan.baidu.com'
ORIGIN = 'https://' + HOST


def _resolve(result):
    # No driver/token reference enters the resolver thread. OS DNS itself cannot
    # be cancelled; caller waiting is bounded and an overdue result is discarded.
    try:
        addresses = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
        result.put(addresses)
    except Exception:
        result.put(None)


class _OfficialConnection(http.client.HTTPSConnection):
    def __init__(self, driver):
        super().__init__(HOST, port=443, timeout=driver.timeout(), context=driver.context)
        self.driver = driver
        self.set_debuglevel(0)

    def connect(self):
        d = self.driver
        d.check_tls()
        family, address = d.address
        raw = socket.socket(family, socket.SOCK_STREAM)
        d.own_socket(raw)
        try:
            with d.io_phase('tcp_connect'):
                raw.settimeout(d.timeout())
                raw.connect(address)
            with d.io_phase('tls_handshake'):
                wrapped = d.context.wrap_socket(raw, server_hostname=HOST, do_handshake_on_connect=False)
                d.own_socket(wrapped)
                self.sock = wrapped
                wrapped.settimeout(d.timeout())
                wrapped.do_handshake()
            d.tls_version = wrapped.version()
            d.check()
        except BaseException:
            raw.close()
            if self.sock is not None:
                self.sock.close()
            raise


class OfficialHTTPSDriver(base.LocalHTTPSDriver):
    """Fixed official destination; no-token discovery or explicit temporary token.

    Construction performs no network I/O. DNS is resolved once before the first
    request, restricted to public addresses and pinned for this session. No
    custom CA, proxy, redirect, token callback or environment token is accepted.
    """
    def __init__(self, *, access_token=None, io_timeout=5, budget=30):
        if access_token is not None and (type(access_token) is not str or not 1 <= len(access_token) <= 8192
                or any(ord(c) < 33 or ord(c) > 126 for c in access_token)):
            contract.reject('mcp_official_credential_rejected')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # Explicit system trust loading avoids SSLKEYLOGFILE handling in
        # create_default_context. No caller-provided TLS context is accepted.
        context.load_default_certs()
        super().__init__(4430, context, io_timeout=io_timeout, budget=budget)
        self.port = 443
        self.origin = ORIGIN
        self.endpoint = ORIGIN + '/sse'
        self.message_profile = 'official'
        self._token = access_token
        self.address = None

    def __repr__(self):
        return '<private_official_https_driver>'

    def _connection(self):
        self.check_tls()
        if self.address is None:
            with self.io_phase('dns'):
                self._dns_lookup_count+=1
                result = queue.Queue(maxsize=1)
                threading.Thread(target=_resolve, args=(result,), daemon=True).start()
                try:
                    addresses = result.get(timeout=self.timeout())
                except queue.Empty:
                    contract.reject('mcp_official_dns_timeout')
                self.check()
                if not addresses:
                    contract.reject('mcp_official_dns_failed')
                candidates = []
                for family, kind, proto, name, address in addresses:
                    try:
                        ip = ipaddress.ip_address(address[0])
                    except ValueError:
                        contract.reject('mcp_official_dns_rejected')
                    if (family not in (socket.AF_INET, socket.AF_INET6) or not ip.is_global
                            or ip.is_multicast or address[1] != 443):
                        contract.reject('mcp_official_dns_rejected')
                    candidates.append((family, address))
                if not candidates:
                    contract.reject('mcp_official_dns_rejected')
                self.address = candidates[0]  # No automatic alternate-address retry.
        c = _OfficialConnection(self)
        with self._lock:
            self._connections.append(c)
        return c

    def _opening_path(self):
        if self._token is None:return '/sse'
        return '/sse?' + urllib.parse.urlencode({'access_token': self._token})

    def post(self, url, raw):
        message = contract.payload(raw)
        method = message.get('method')
        if method not in ('initialize', 'notifications/initialized', 'tools/list', 'tools/call'):
            contract.reject('mcp_official_operation_locked')
        if method == 'tools/call':
            if self._token is None:contract.reject('mcp_official_authentication_required')
            params = message.get('params', {})
            if params.get('name') not in ('user_info', 'file_meta'):
                contract.reject('mcp_official_operation_locked')
        return super().post(url, raw)

    def close(self):
        self._token = None
        return super().close()

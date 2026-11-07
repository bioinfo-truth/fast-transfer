"""Credential-free public HTTPS GET, with per-hop DNS checks and pinned sockets."""
import http.client
import ipaddress
import socket
import ssl
import time
import urllib.parse

from .intake import InputProblem, public_url


def public_addresses(host):
    try:
        results = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(row[4][0] for row in results))
        if not addresses or any(not ipaddress.ip_address(x).is_global
                                or ipaddress.ip_address(x).is_multicast for x in addresses):
            raise InputProblem('nonpublic_dns_result')
        return addresses
    except (socket.gaierror, ValueError) as exc:
        if isinstance(exc, InputProblem):
            raise
        raise InputProblem('dns_lookup_failed', 'manual_review') from None


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Never resolve the hostname a second time; retain its SNI/certificate checks.
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def open_public(url, deadline, max_redirects=3):
    """Caller must close both returned response and connection. No env proxy/auth."""
    seen = set()
    for hop in range(max_redirects + 1):
        u = public_url(url)
        if url in seen:
            raise InputProblem('redirect_loop')
        seen.add(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise InputProblem('download_deadline', 'manual_review')
        addresses = public_addresses(u.hostname)
        connection = PinnedHTTPSConnection(u.hostname, addresses[0], min(30, remaining))
        try:
            target = urllib.parse.urlunsplit(('', '', u.path or '/', '', ''))
            connection.request('GET', target, headers={'User-Agent': 'fast-transfer-mvp/0.1', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise InputProblem('redirect_location_missing')
                if len(location) > 2048 or any(ord(c) <= 32 or ord(c) >= 127 for c in location) or '\\' in location:
                    raise InputProblem('invalid_redirect_location')
                if hop == max_redirects:
                    raise InputProblem('too_many_redirects')
                # Validate before attempting the next request, including cross-host hops.
                url = urllib.parse.urljoin(url, location)
                public_url(url)
                response.close()
                connection.close()
                continue
            if response.status in (401, 403):
                raise InputProblem('source_access_denied', 'manual_review')
            if response.status != 200:
                raise InputProblem('source_http_status', 'manual_review')
            return response, connection, hop
        except BaseException:
            connection.close()
            raise
    raise InputProblem('too_many_redirects')

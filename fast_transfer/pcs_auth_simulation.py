"""Offline design model, NOT a PCS client, protocol binding or authentication proof.

Only the literal public fixture and exact in-memory transport are accepted. No
network, persistence, credential discovery, force-login or production adapter.
"""
import re
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit

FIXTURE_COOKIE = 'BDUSS=FAKE_ONLY_BDUSS; STOKEN=FAKE_ONLY_STOKEN;'
IDENTITY_URL = 'https://pan.baidu.com/offline-design/identity'
PROFILE_URL = 'https://pan.baidu.com/offline-design/profile'
# These paths are invented model labels, NOT supported Baidu API endpoints.


class Rejected(Exception):
    """Only fixed safe codes may escape; never wrap a transport exception."""


def strict_tls_context():
    return ssl.create_default_context()


def require_destination(url, context):
    try:
        u = urlsplit(url)
        valid = (url in (IDENTITY_URL, PROFILE_URL) and u.scheme == 'https'
                 and u.hostname == 'pan.baidu.com' and not u.username
                 and not u.password and not u.query and not u.fragment
                 and u.port in (None, 443))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise Rejected('destination_rejected') from None
    if (not isinstance(context, ssl.SSLContext)
            or context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname):
        raise Rejected('tls_policy_rejected') from None


def fixture_cookie(text):
    # Format checks precede the fixture-only allowlist. Real values are rejected.
    if (type(text) is not str or len(text) > 256 or '\r' in text or '\n' in text):
        raise Rejected('credential_format_rejected')
    fields = [part.strip() for part in text.split(';') if part.strip()]
    pairs = [part.split('=', 1) for part in fields]
    if (len(pairs) != 2 or any(len(p) != 2 for p in pairs)
            or [p[0] for p in pairs] != ['BDUSS', 'STOKEN']
            or any(not re.fullmatch(r'[A-Za-z0-9_]+', p[1]) for p in pairs)):
        raise Rejected('credential_format_rejected')
    if text != FIXTURE_COOKIE:
        raise Rejected('fixture_only')
    return text


class FakeTransport:
    """Finite in-memory script. Stores only operation names, never request data."""
    def __init__(self, identity, profile=None):
        self.script = {'identity': identity, 'profile': profile}
        self.calls = []
        self.closed = False

    def exchange(self, operation, credential, context):
        if self.closed or operation in self.calls:
            raise Rejected('transport_closed_or_replayed')
        require_destination({'identity': IDENTITY_URL, 'profile': PROFILE_URL}[operation], context)
        if credential != FIXTURE_COOKIE:
            raise Rejected('fixture_only')
        self.calls.append(operation)
        reply = self.script[operation]
        if isinstance(reply, Exception):
            raise reply
        return reply

    def close(self):
        self.closed = True
        self.script.clear()


@dataclass(frozen=True)
class SimulationResult:
    status: str
    profile_status: str
    events: tuple
    simulated_identity_verified: bool
    transport_closed: bool
    credential_reference_released: bool
    live_authenticated: bool = False
    share_eligible: bool = False


def simulate_login(transport, cookie=FIXTURE_COOKIE, expected_uid='1001', *,
                   tls_context=None, force_login=False):
    """Accept identity only from the fake identity step, never from profile.

    Real integration must select a supported authenticated identity endpoint and
    verify its account binding. No such endpoint is implemented by this model.
    """
    if type(transport) is not FakeTransport:
        raise Rejected('fake_transport_required')
    events = []
    credential = None
    verified = False
    status, profile_status = 'rejected', 'not_attempted'
    try:
        if force_login is not False:
            raise Rejected('force_login_rejected')
        if type(expected_uid) is not str or not re.fullmatch(r'[1-9][0-9]{0,19}', expected_uid):
            raise Rejected('expected_identity_rejected')
        credential = fixture_cookie(cookie)
        context = tls_context if tls_context is not None else strict_tls_context()
        require_destination(IDENTITY_URL, context)
        try:
            identity = transport.exchange('identity', credential, context)
        except ssl.SSLCertVerificationError:
            raise Rejected('identity_tls_failed') from None
        except TimeoutError:
            status = 'identity_unknown'
            raise Rejected(status) from None
        except Exception:
            status = 'identity_transport_failed'
            raise Rejected(status) from None
        if type(identity) is not dict or identity.get('status') not in ('valid', 'invalid'):
            raise Rejected('identity_unknown')
        if identity['status'] == 'invalid':
            raise Rejected('credential_invalid')
        uid = identity.get('uid')
        if type(uid) is not str or not re.fullmatch(r'[1-9][0-9]{0,19}', uid):
            raise Rejected('identity_unknown')
        if uid != expected_uid:
            raise Rejected('account_mismatch')
        verified = True
        events.append('simulated_identity_verified')
        # Profile is optional enrichment, not a source of authentication.
        try:
            profile = transport.exchange('profile', credential, context)
        except TimeoutError:
            profile_status = 'profile_timeout'
        except Exception:
            profile_status = 'profile_unavailable'
        else:
            if type(profile) is not dict:
                profile_status = 'profile_invalid'
            elif profile.get('uid') != uid:
                raise Rejected('profile_identity_conflict')
            else:
                profile_status = 'profile_available'  # Do not retain arbitrary text.
        status = 'simulated_authenticated'
        events.append(profile_status)
    except Rejected as error:
        status = str(error)
        verified = False
        events.append(status)
    finally:
        credential = None
        transport.close()
    return SimulationResult(status, profile_status, tuple(events), verified,
                            transport.closed, credential is None)

"""Offline policy tests. Socket and file opens forbidden during every test."""
import builtins
import socket
import ssl
import unittest
from unittest.mock import patch

from fast_transfer.pcs_auth_simulation import (
    FakeTransport, FIXTURE_COOKIE, IDENTITY_URL, Rejected, fixture_cookie,
    require_destination, simulate_login, strict_tls_context,
)


class AuthSimulationTests(unittest.TestCase):
    def setUp(self):
        self.context = strict_tls_context()
        self.guards = [patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')),
                       patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')),
                       patch.object(builtins, 'open', side_effect=AssertionError('persistence forbidden'))]
        for guard in self.guards:
            guard.start()
            self.addCleanup(guard.stop)

    def run_model(self, identity=None, profile=None, **kwargs):
        t = FakeTransport(identity if identity is not None else {'status': 'valid', 'uid': '1001'},
                          profile if profile is not None else {'uid': '1001', 'name': 'not-retained'})
        result = simulate_login(t, tls_context=self.context, **kwargs)
        self.assertTrue(result.transport_closed)
        self.assertTrue(result.credential_reference_released)
        self.assertFalse(result.live_authenticated)
        self.assertFalse(result.share_eligible)
        self.assertEqual(t.script, {})
        return result, t

    def test_strict_certificate_and_hostname_policy(self):
        self.assertEqual(self.context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(self.context.check_hostname)
        unsafe = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        unsafe.check_hostname = False
        unsafe.verify_mode = ssl.CERT_NONE
        t = FakeTransport({'status': 'valid', 'uid': '1001'})
        r = simulate_login(t, tls_context=unsafe)
        self.assertEqual(r.status, 'tls_policy_rejected')
        self.assertEqual(t.calls, [])

    def test_http_and_credential_url_rejected_before_exchange(self):
        for url in ('http://pan.baidu.com/offline-design/identity',
                    IDENTITY_URL + '?BDUSS=FAKE_ONLY_BDUSS',
                    'https://pan.baidu.com.evil.invalid/offline-design/identity',
                    'https://FAKE_ONLY_BDUSS@pan.baidu.com/offline-design/identity'):
            with self.subTest(url=url), self.assertRaises(Rejected):
                require_destination(url, self.context)

    def test_profile_timeout_after_identity_is_optional(self):
        r, t = self.run_model(profile=TimeoutError('secret error text'))
        self.assertEqual(r.status, 'simulated_authenticated')
        self.assertEqual(r.profile_status, 'profile_timeout')
        self.assertTrue(r.simulated_identity_verified)
        self.assertEqual(t.calls, ['identity', 'profile'])

    def test_identity_timeout_stops_without_profile_or_retry(self):
        r, t = self.run_model(identity=TimeoutError('secret'))
        self.assertEqual(r.status, 'identity_unknown')
        self.assertFalse(r.simulated_identity_verified)
        self.assertEqual(t.calls, ['identity'])

    def test_invalid_unknown_and_mismatched_identity_rejected(self):
        for identity, code in [({'status': 'invalid'}, 'credential_invalid'),
                               ({'status': 'valid'}, 'identity_unknown'),
                               ({'status': 'valid', 'uid': 1001}, 'identity_unknown'),
                               ({'status': 'valid', 'uid': '1002'}, 'account_mismatch'),
                               ({'status': True, 'uid': '1001'}, 'identity_unknown')]:
            with self.subTest(code=code):
                r, t = self.run_model(identity=identity)
                self.assertEqual(r.status, code)
                self.assertEqual(t.calls, ['identity'])

    def test_profile_cannot_replace_conflicting_identity(self):
        r, _ = self.run_model(profile={'uid': '1002'})
        self.assertEqual(r.status, 'profile_identity_conflict')
        self.assertFalse(r.simulated_identity_verified)

    def test_certificate_failure_is_not_invalid_credential(self):
        r, t = self.run_model(identity=ssl.SSLCertVerificationError('sensitive context'))
        self.assertEqual(r.status, 'identity_tls_failed')
        self.assertEqual(t.calls, ['identity'])

    def test_credential_format_and_fixture_only_reject_before_exchange(self):
        for value in ('BDUSS=FAKE_ONLY_BDUSS;', FIXTURE_COOKIE + '\n',
                      'BDUSS=x; BDUSS=y;', 'BDUSS=x; STOKEN=y;', None):
            with self.subTest(value=value):
                r, t = self.run_model(cookie=value)
                self.assertIn(r.status, ('credential_format_rejected', 'fixture_only'))
                self.assertEqual(t.calls, [])
        self.assertEqual(fixture_cookie(FIXTURE_COOKIE), FIXTURE_COOKIE)

    def test_force_login_and_unknown_expected_identity_rejected(self):
        for kwargs in ({'force_login': True}, {'force_login': 'name'}, {'expected_uid': ''}):
            r, t = self.run_model(**kwargs)
            self.assertNotEqual(r.status, 'simulated_authenticated')
            self.assertEqual(t.calls, [])

    def test_arbitrary_transport_not_accepted(self):
        with self.assertRaisesRegex(Rejected, 'fake_transport_required'):
            simulate_login(object())

    def test_exceptions_and_profile_text_never_in_result_or_logs(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            r, _ = self.run_model(profile=RuntimeError('sensitive ' + FIXTURE_COOKIE))
        self.assertEqual(out.getvalue(), '')
        self.assertNotIn('FAKE_ONLY', repr(r))
        self.assertNotIn('sensitive', repr(r))
        self.assertEqual(r.profile_status, 'profile_unavailable')
        r, _ = self.run_model(profile=Rejected('sensitive ' + FIXTURE_COOKIE))
        self.assertNotIn('sensitive', repr(r))
        self.assertEqual(r.profile_status, 'profile_unavailable')
        r, _ = self.run_model(profile={'uid': '1001', 'name': 'sensitive'})
        self.assertNotIn('sensitive', repr(r))

    def test_completed_transport_is_terminal(self):
        r, t = self.run_model()
        self.assertEqual(r.status, 'simulated_authenticated')
        again = simulate_login(t, tls_context=self.context)
        self.assertEqual(again.status, 'identity_transport_failed')
        self.assertEqual(t.calls, ['identity', 'profile'])

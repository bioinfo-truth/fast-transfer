"""Credential-free MCP candidate contract. No MCP client or wire decoder exists.

README field names are not authentication. Observations below are internal,
explicit fixture normalization, NOT an official MCP response envelope.
Uses the existing simulation Job for single-intent persistence and locking.
"""
import hashlib
import json
import re
from dataclasses import dataclass


SOURCE_COMMIT = 'b3983d330fea79c7b72e6b7014803e1830148d2c'
README_BLOB = 'aebcff89265d8948be9e6dc7147cc2998b4e5d61'
FIXTURE_TASK = 'job-mcp-fixture'
FIXTURE_APP = 'fixture-only-Xtransfer-app'
FIXTURE_SESSION = 'fixture-only-session'
FIXTURE_UK = '1001'
FIXTURE_FSID = '2001'
FIXTURE_DATA = b'ACGT' * 4
FIXTURE_PATH = '/apps/Xtransfer/mvp-validation/' + FIXTURE_TASK + '/fixture.fna'
PRIVATE = '<private_mcp_fixture>'
SAFE_CODES = frozenset('''
    mcp_live_connection_unavailable mcp_candidate_shape_invalid mcp_fixture_scope_mismatch
    mcp_fixture_permission_denied mcp_response_contract_unknown mcp_candidate_arguments_invalid
    mcp_fixture_intent_consumed mcp_fixture_transport_required mcp_fixture_not_ready_or_consumed
    mcp_fixture_object_mismatch mcp_fixture_identity_mismatch mcp_candidate_url_invalid
    mcp_candidate_share_mismatch
'''.split())


class Rejected(Exception):
    pass


def reject(code):
    raise Rejected(code) from None


def live_connect(*args, **kwargs):
    reject('mcp_live_connection_unavailable')


def payload(raw):
    """Small internal payload only; never interprets a live MCP envelope."""
    if type(raw) is not bytes or not 0 < len(raw) <= 16384:
        reject('mcp_candidate_shape_invalid')
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out: reject('mcp_candidate_shape_invalid')
            out[k] = v
        return out
    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda _: reject('mcp_candidate_shape_invalid'))
    except (ValueError, UnicodeError, RecursionError):
        reject('mcp_candidate_shape_invalid')
    def bounded(v, depth=0):
        if depth > 8: reject('mcp_candidate_shape_invalid')
        if isinstance(v, dict):
            if len(v) > 32: reject('mcp_candidate_shape_invalid')
            for k, item in v.items():
                if len(k) > 128: reject('mcp_candidate_shape_invalid')
                bounded(item, depth+1)
        elif isinstance(v, list):
            if len(v) > 16: reject('mcp_candidate_shape_invalid')
            for item in v: bounded(item, depth+1)
        elif isinstance(v, str) and len(v) > 2048:
            reject('mcp_candidate_shape_invalid')
    bounded(value)
    if type(value) is not dict: reject('mcp_candidate_shape_invalid')
    return value


@dataclass(frozen=True, repr=False)
class Observation:
    """Internal synthetic provenance; never a trusted server/account assertion."""
    raw: bytes
    status: str = 'candidate_fields'
    app: str = FIXTURE_APP
    session: str = FIXTURE_SESSION
    task: str = FIXTURE_TASK
    account: str = FIXTURE_UK

    def __repr__(self): return PRIVATE

    def fields(self):
        if (self.app, self.session, self.task, self.account) != (
                FIXTURE_APP, FIXTURE_SESSION, FIXTURE_TASK, FIXTURE_UK):
            reject('mcp_fixture_scope_mismatch')
        if self.status == 'permission_denied': reject('mcp_fixture_permission_denied')
        if self.status != 'candidate_fields': reject('mcp_response_contract_unknown')
        return payload(self.raw)


@dataclass(frozen=True, repr=False)
class ShareArguments:
    """Private local request candidate; only explicit export exposes arguments."""
    fsid: str
    period: int
    pwd: str

    def __repr__(self): return PRIVATE

    def fixture_arguments(self):
        # Seven days is our conservative fixture policy, not all supported periods.
        if (self.fsid != FIXTURE_FSID or type(self.period) is not int or self.period != 7
                or type(self.pwd) is not str or not re.fullmatch('[a-z0-9]{4}', self.pwd)):
            reject('mcp_candidate_arguments_invalid')
        return {'fsid_list': json.dumps([self.fsid], separators=(',', ':')),
                'period': self.period, 'pwd': self.pwd}


class FixtureTransport:
    """In-memory observations and ONE scripted share result. No callbacks/network."""
    def __init__(self, identity, metadata, share):
        self._observations = {'user_info': identity, 'file_meta': metadata}
        self._share = share
        self.calls = []
        self._consumed = False

    def __repr__(self): return PRIVATE

    def observe(self, name):
        self.calls.append(name)
        observation = self._observations[name]
        if type(observation) is not Observation: reject('mcp_response_contract_unknown')
        return observation.fields()

    def share(self, arguments):
        if self._consumed: reject('mcp_fixture_intent_consumed')
        self._consumed = True
        arguments.fixture_arguments()
        self.calls.append('file_sharelink_set')
        if self._share == 'timeout': raise TimeoutError()
        if type(self._share) is not Observation: reject('mcp_response_contract_unknown')
        return self._share.fields()


def _check_binding(job, state, transport):
    if type(transport) is not FixtureTransport: reject('mcp_fixture_transport_required')
    if job.job_id != FIXTURE_TASK or state['phase'] != 'simulated_cloud_verified':
        reject('mcp_fixture_not_ready_or_consumed')
    mapping = state['mapping']
    if (mapping.get('name') != 'fixture.fna' or mapping.get('size') != len(FIXTURE_DATA)
            or mapping.get('md5') != hashlib.md5(FIXTURE_DATA).hexdigest()
            or mapping.get('sha256') != hashlib.sha256(FIXTURE_DATA).hexdigest()
            or mapping.get('simulated_target') != FIXTURE_PATH):
        reject('mcp_fixture_object_mismatch')
    identity = transport.observe('user_info')
    # Exact shapes are local normalized requirements, not an official wire schema.
    if set(identity) != {'uk'} or type(identity['uk']) is not str or identity['uk'] != FIXTURE_UK:
        reject('mcp_fixture_identity_mismatch')
    meta = transport.observe('file_meta')
    expected = {'fsid': FIXTURE_FSID, 'path': FIXTURE_PATH,
                'md5': mapping['md5'], 'size': mapping['size']}
    if (set(meta) != {'list'} or type(meta['list']) is not list or len(meta['list']) != 1
            or type(meta['list'][0]) is not dict or meta['list'][0] != expected
            or type(meta['list'][0].get('size')) is not int):
        reject('mcp_fixture_object_mismatch')


def _check_share(fields, arguments):
    if set(fields) != {'link', 'short_url', 'period', 'pwd'}:
        reject('mcp_candidate_shape_invalid')
    # Conservative local allowlist, not a claim that every real link has this shape.
    for key in ('link', 'short_url'):
        if type(fields[key]) is not str or not re.fullmatch(
                r'https://pan\.baidu\.com/s/[A-Za-z0-9_-]{6,128}', fields[key]):
            reject('mcp_candidate_url_invalid')
    if (type(fields['period']) is not int or fields['period'] != arguments.period
            or type(fields['pwd']) is not str or fields['pwd'] != arguments.pwd):
        reject('mcp_candidate_share_mismatch')
    # No owner/shareid/object mapping is promised by README. Never fabricate it.


def exercise_share(job, transport, *, period=7, pwd):
    """Only the literal synthetic job. Reuses Job lock/save, never starts live.

    Persists manual-review intent before the fixture create. No new ledger,
    automatic retry/reset or response secret persistence. A second invocation
    on the same Job cannot dispatch, even with a new fixture transport/process.
    """
    result = {'mode': 'mcp-fixture-only', 'status': 'rejected',
              'reason': 'mcp_fixture_input_or_state_invalid', 'create_attempted': False,
              'outcome_unknown': False, 'mapping_verified': False,
              'live_authenticated': False, 'share_eligible': False,
              'delivery_eligible': False, 'automatic_retry_allowed': False}
    try:
        with job.locked():
            state = job.read()
            result['outcome_unknown'] = state.get('mutation_outcome_unknown') is True
            _check_binding(job, state, transport)
            arguments = ShareArguments(FIXTURE_FSID, period, pwd)
            arguments.fixture_arguments()
            # Existing simulation/manual-review state; do not add an MCP service ledger.
            state.update(phase='manual_review', manual_action='verify_share',
                         mutation_outcome_unknown=True)
            state['events'] = (state['events'] + ['manual_verify_share'])[-32:]
            job.save(state)  # Failure here means no dispatch; retain existing M5 residue.
            result.update(create_attempted=True, outcome_unknown=True, status='unverified')
            fields = transport.share(arguments)
            _check_share(fields, arguments)
            result.update(reason='mcp_share_mapping_unproven', status='candidate_unverified')
            # Persist no link/pwd or fake owner; earlier intent remains manual_review.
    except Rejected as exc:
        reason = exc.args[0] if exc.args else None
        result['reason'] = reason if type(reason) is str and reason in SAFE_CODES else 'mcp_fixture_input_or_state_invalid'
    except TimeoutError:
        result['reason'] = ('mcp_fixture_create_outcome_unknown' if result['create_attempted']
                            else 'mcp_fixture_input_or_state_invalid')
    except Exception:
        # Never expose raw tool/transport/state exceptions, URLs or tokens.
        result['reason'] = 'mcp_fixture_input_or_state_invalid'
    return result

"""Bounded Xtransfer device flow. No request/approval occurs automatically.

Same explicit application key for both steps. Device/user/token values are
private; generic protocol compatibility does not establish Xtransfer rights.
"""
import re
import time
from . import mcp_share as c

SCOPE='basic,netdisk'
MAX_SECONDS=300
MAX_POLLS=30
KNOWN_ERRORS=frozenset(('authorization_pending','slow_down','authorization_declined',
    'access_denied','expired_token','invalid_grant','invalid_client','unauthorized_client',
    'unsupported_grant_type','invalid_scope','invalid_request'))


def fail(code):c.reject(code)


def secret(value):
    if type(value) is not str or not 1<=len(value)<=2048 or any(not 33<=ord(ch)<=126 for ch in value):
        fail('device_private_field_invalid')
    return value


class TokenLease:
    def __init__(self,token,scope,deadline,clock):
        self._token=token;self.scope=scope;self.deadline=deadline;self.clock=clock
    def __repr__(self):return '<private_device_token_lease>'
    def take(self):
        if self._token is None or self.clock()>=self.deadline: self.close();fail('device_token_expired_or_consumed')
        value=self._token;self._token=None;return value
    def close(self):self._token=None


class DeviceFlow:
    def __init__(self,app_key,*,clock=time.monotonic):
        self._key=secret(app_key);self.clock=clock;self.phase='new';self._code=None;self._user=None
        self.verification_url=None;self.deadline=0;self.interval=6;self.next_poll=0;self.polls=0
    def __repr__(self):return '<private_Xtransfer_device_flow>'
    def start(self,transport):
        if self.phase!='new':fail('device_intent_consumed')
        self.phase='create_unknown';began=self.clock()
        response=transport.device(self._key,SCOPE)  # Exactly one create; unknown never reissued.
        if type(response) is not dict:fail('device_response_unknown')
        if 'error' in response:
            if set(response)-{'error','error_description'} or type(response['error']) is not str or response['error'] not in KNOWN_ERRORS:
                fail('device_response_unknown')
            self.phase='stopped';fail('device_create_rejected')
        if set(response)-{'device_code','user_code','verification_url','qrcode_url','expires_in','interval'}:
            fail('device_response_unknown')
        expiry=response.get('expires_in');interval=response.get('interval')
        if type(expiry) is not int or expiry<=0 or type(interval) is not int or not 1<=interval<=300:
            fail('device_response_unknown')
        url=response.get('verification_url')
        if url not in ('https://openapi.baidu.com/device','https://openapi.baidu.com/oauth/2.0/device'):
            fail('device_verification_target_rejected')
        self._code=secret(response.get('device_code'));self._user=secret(response.get('user_code'))
        if not re.fullmatch('[A-Za-z0-9_-]{4,64}',self._user):fail('device_response_unknown')
        self.verification_url=url;self.deadline=began+min(expiry,MAX_SECONDS)
        self.interval=max(6,interval);self.next_poll=self.clock()+self.interval
        self.phase='awaiting_user'
    def private_instructions(self):
        if self.phase!='awaiting_user':fail('device_phase_invalid')
        self.ready()
        # Explicit private-terminal display only. Never include device_code.
        return self.verification_url,self._user
    def ready(self):
        if self.phase not in ('awaiting_user','polling'):fail('device_intent_consumed')
        if self.clock()>=self.deadline or self.polls>=MAX_POLLS:
            self.phase='stopped';fail('device_expired_or_poll_limit')
        return max(0,self.next_poll-self.clock())
    def poll_once(self,transport,secret_key):
        secret(secret_key)
        if self.ready()>0:fail('device_poll_too_early')
        self.phase='exchange_unknown';self.polls+=1;began=self.clock()
        response=transport.poll(self._key,secret_key,self._code)
        if type(response) is not dict:fail('device_response_unknown')
        if 'error' in response:
            if set(response)-{'error','error_description'}:fail('device_response_unknown')
            error=response['error']
            if type(error) is not str or error not in KNOWN_ERRORS:fail('device_error_unknown')
            if error not in ('authorization_pending','slow_down'):
                self.phase='stopped';fail('device_'+error)
            if self.clock()>=self.deadline:self.phase='stopped';fail('device_expired_or_poll_limit')
            if error=='slow_down':self.interval+=5  # Conservative local backoff policy.
            self.next_poll=self.clock()+self.interval;self.phase='polling';return None
        if set(response)-{'access_token','expires_in','scope','refresh_token','session_key','session_secret'}:
            fail('device_response_unknown')
        expiry=response.get('expires_in');scope=response.get('scope')
        if (type(expiry) is not int or expiry<=0 or type(scope) is not str
                or set(scope.split())!={'basic','netdisk'} or len(scope.split())!=2):
            fail('device_granted_scope_unproven')
        if self.clock()>=self.deadline or began+expiry<=self.clock():fail('device_expired_or_poll_limit')
        lease=TokenLease(secret(response.get('access_token')),'basic netdisk',began+expiry,self.clock)
        # Ignore/drop refresh/session credentials: response bytes still entered
        # this process. No promise that the server did not issue them.
        response.clear();self.phase='consumed';self._code=None;self._user=None
        return lease
    def close(self):
        self._key=None;self._code=None;self._user=None;self.phase='closed'

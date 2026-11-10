"""User-operated Xtransfer device flow. Never auto-started or invoked by tests.

Explicit new-grant/query-risk flags and hidden scope confirmation are required.
No existing secrets, browser automation, refresh, token output or persistence.
"""
import json
import os
import re
import signal
import sys
import time

from . import mcp_share as c
from .device_oauth import DeviceFlow,SCOPE,KNOWN_ERRORS
from .device_oauth_http import DeviceOAuthHTTP
from .mcp_terminal import read_secret,TerminalFailure,_Parser,run_discovery


def show_private_device(url,user_code):
    if url not in ('https://openapi.baidu.com/device','https://openapi.baidu.com/oauth/2.0/device') or type(user_code) is not str or not re.fullmatch('[A-Za-z0-9_-]{4,64}',user_code):
        raise TerminalFailure('device_private_display_rejected')
    if not all(os.isatty(fd) for fd in (0,1,2)):raise TerminalFailure('terminal_interactive_required')
    fd=os.open('/dev/tty',os.O_WRONLY|os.O_NOCTTY|os.O_CLOEXEC)
    try:
        if not os.isatty(fd) or os.tcgetpgrp(fd)!=os.getpgrp():raise TerminalFailure('terminal_interactive_required')
        os.write(fd,('Open yourself: '+url+'\nPrivate user code: '+user_code+
            '\nConfirm the page names your existing Xtransfer application and intended account/scope.\n').encode('ascii'))
    finally:os.close(fd)


SAFE_CODES=frozenset(('device_cancelled','device_intent_consumed','device_phase_invalid',
    'device_create_rejected','device_response_unknown','device_verification_target_rejected',
    'device_expired_or_poll_limit','device_error_unknown','device_granted_scope_unproven',
    'device_close_unconfirmed','device_dns_timeout','device_dns_failed','device_dns_rejected',
    'device_http_status_rejected','device_headers_rejected','device_mime_rejected','device_response_limit',
    'device_poll_too_early','device_private_field_invalid','device_user_declined',
    'device_request_scope_rejected')) | frozenset('device_'+name for name in KNOWN_ERRORS) | c.SAFE_CODES


def main(argv=None):
    key=secret_key=token=None;flow=lease=None;handlers={}
    report={'expected_application':'Xtransfer','application_binding_verified':False,'status':'stopped','reason':'device_operation_failed',
            'token_stored':False,'token_displayed':False,'refresh_performed':False,
            'mcp_attempted':False,'account_verified':False,'object_verified':False,'share_attempted':False}
    def cancelled(signum,frame):c.reject('device_cancelled')
    try:
        parser=_Parser(description='User-operated Xtransfer device authorization; new grant, no token storage.')
        parser.add_argument('--scope',required=True,choices=[SCOPE])
        parser.add_argument('--ack-new-user-grant',required=True,action='store_true')
        parser.add_argument('--ack-query-credential-risk',required=True,action='store_true')
        parser.parse_args(argv)
        for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):handlers[sig]=signal.signal(sig,cancelled)
        sys.stdout.write('Existing Xtransfer application only. Proposed scope: basic,netdisk.\n'
            'This creates a NEW user grant; service may issue refresh/session credentials.\n'
            'No credential is stored/refreshed here; grant can outlive this process.\n'
            'AppKey and SecretKey are sent as HTTPS query parameters to openapi.baidu.com.\n'
            'Official server/proxy logging is outside client control. No automatic browser or sharing.\n')
        if read_secret('Type XTRANSFER-DEVICE-basic,netdisk to confirm (hidden): ',limit=64)!='XTRANSFER-DEVICE-basic,netdisk':
            c.reject('device_user_declined')
        key=read_secret('Existing Xtransfer AppKey (hidden): ',limit=256)
        flow=DeviceFlow(key);key=None;transport=DeviceOAuthHTTP()
        flow.start(transport)
        url,user_code=flow.private_instructions()
        show_private_device(url,user_code);url=user_code=None
        if read_secret('After approving Xtransfer yourself, type XTRANSFER-APPROVED (hidden): ',limit=32)!='XTRANSFER-APPROVED':
            c.reject('device_user_declined')
        flow.ready()  # Check expiry before requesting/using SecretKey.
        secret_key=read_secret('SecretKey of the SAME Xtransfer application (hidden): ',limit=256)
        while lease is None:
            delay=flow.ready()
            if delay>0:time.sleep(min(.2,delay));continue
            lease=flow.poll_once(transport,secret_key)
        secret_key=None
        report.update(reason='device_authorized_in_memory',scope=lease.scope,
                      token_remaining_seconds=max(0,int(lease.deadline-lease.clock())))
        flow.close()
        # Separate action before handing the token to a different official host.
        if read_secret('Type MCP-DISCOVER to submit token to official MCP (hidden), or cancel: ',limit=32)=='MCP-DISCOVER':
            token=lease.take();report['mcp_attempted']=True
            report['mcp']=run_discovery(token);token=None
        report['status']='finished'
    except TerminalFailure:
        report['reason']='device_terminal_input_stopped'
    except c.Rejected as exc:
        code=exc.args[0] if exc.args else None
        report['reason']=code if type(code) is str and code in SAFE_CODES else 'device_operation_failed'
    except (Exception,KeyboardInterrupt):pass
    finally:
        key=secret_key=token=None
        if lease is not None:lease.close()
        if flow is not None:
            report['poll_requests']=flow.polls
            report['authorization_outcome_unknown']=flow.phase in ('create_unknown','exchange_unknown')
            flow.close()
        for sig,handler in handlers.items():signal.signal(sig,handler)
    sys.stdout.write(json.dumps(report,ensure_ascii=False)+'\n')
    return 0 if report['status']=='finished' else 1


if __name__=='__main__':raise SystemExit(main())

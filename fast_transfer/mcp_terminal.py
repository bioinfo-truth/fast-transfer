"""Explicit private-terminal token input and bounded, exact-object read-only run.

No token discovery, echo fallback, OAuth, subprocess, persistent secret or share.
Running this entry is a user action; developing it grants no real access rights.
"""
import argparse
import json
import math
import os
import select
import signal
import stat
import sys
import termios
import time

from . import mcp_share as contract
from .mcp_binding import BoundSession, ExpectedObject
from . import mcp_sse as wire
from .mcp_official_http import OfficialHTTPSDriver


class TerminalFailure(Exception):pass


def stop(code):raise TerminalFailure(code) from None


def read_secret(prompt='Short-lived access_token (hidden): ', *, timeout=60, limit=8192):
    """Only controlling TTY with echo disabled; never getpass's stdin fallback.

    Flush unconsumed input before restoring echo, including cancel/timeout paths.
    Process exit/SIGKILL, OS/terminal recording and memory copies are not erased.
    """
    if (type(timeout) not in (int,float) or not math.isfinite(timeout) or not .05<=timeout<=120
            or type(limit) is not int or not 1<=limit<=8192):stop('terminal_input_policy_invalid')
    if not all(os.isatty(fd) for fd in (0,1,2)):stop('terminal_interactive_required')
    fd=None;old=None;handlers={};data=bytearray()
    def interrupted(signum,frame):stop('terminal_input_cancelled')
    try:
        fd=os.open('/dev/tty',os.O_RDWR|os.O_NOCTTY|os.O_CLOEXEC)
        if not os.isatty(fd) or os.tcgetpgrp(fd)!=os.getpgrp():stop('terminal_interactive_required')
        old=termios.tcgetattr(fd)
        settings=termios.tcgetattr(fd)
        settings[0] &= ~(termios.IXON|termios.IXOFF)
        settings[3] &= ~(termios.ECHO|termios.ECHONL|termios.ICANON|termios.ISIG)
        settings[6][termios.VMIN]=1;settings[6][termios.VTIME]=0
        for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):
            handlers[sig]=signal.signal(sig,interrupted)
        termios.tcsetattr(fd,termios.TCSAFLUSH,settings)
        # Verify the actual terminal did not silently retain echo/canonical mode.
        actual=termios.tcgetattr(fd)
        if actual[3] & (termios.ECHO|termios.ECHONL|termios.ICANON):stop('terminal_echo_disable_failed')
        os.write(fd,prompt.encode('ascii'))
        deadline=time.monotonic()+timeout
        while True:
            left=deadline-time.monotonic()
            if left<=0 or not select.select([fd],[],[],max(0,left))[0]:stop('terminal_input_timeout')
            char=os.read(fd,1)
            if not char or char==b'\x04':stop('terminal_input_eof')
            if char in (b'\x03',b'\x1a'):stop('terminal_input_cancelled')
            if char in (b'\n',b'\r'):
                if not data:stop('terminal_input_empty')
                return bytes(data).decode('ascii')
            if char in (b'\x08',b'\x7f'):
                if data:data.pop()
                continue
            if char==b'\x15':data.clear();continue
            if not 33<=char[0]<=126 or len(data)>=limit:stop('terminal_input_invalid')
            data.extend(char)
    except TerminalFailure:raise
    except (Exception,KeyboardInterrupt):stop('terminal_input_unavailable')
    finally:
        for i in range(len(data)):data[i]=0
        if fd is not None:
            restored=True
            try:
                termios.tcflush(fd,termios.TCIFLUSH)
                if old is not None:termios.tcsetattr(fd,termios.TCSANOW,old)
                os.write(fd,b'\n')
            except Exception:restored=False
            finally:os.close(fd)
            for sig,handler in handlers.items():signal.signal(sig,handler)
            if not restored:stop('terminal_restore_unconfirmed')


def load_expected(path):
    """Only the explicitly named private expectation record, never credentials."""
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as source:
        info=os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.geteuid()
                or stat.S_IMODE(info.st_mode)&0o077):stop('terminal_private_expectation_required')
        raw=source.read(16385)
    fields=contract.payload(raw)
    if set(fields)!=set(ExpectedObject.__dataclass_fields__):stop('terminal_expectation_invalid')
    return ExpectedObject(**fields)


def _schema_flags(descriptors):
    # Only fixed names/counts/booleans may leave the process, never arbitrary
    # schema text, property names, descriptions, defaults or server echoes.
    return {'tool_count':len(descriptors),'known_tools':{
        name:{'present':name in descriptors,'candidate_schema_match':descriptors.get(name)==profile}
        for name,profile in wire.schemas().items()}}


class _TerminalReadSession(BoundSession):
    def review_descriptors(self,descriptors):
        self.schema_report=_schema_flags(descriptors)
        super().review_descriptors(descriptors)


class _TerminalDiscoverySession(wire.SSEClient):
    """Explicit credential-input discovery, separate from no-token discovery.

    No account/object expectations are needed because business RPC is denied.
    """
    def __init__(self,driver):
        from .mcp_official_http import OfficialHTTPSDriver as DriverType
        if type(driver) is not DriverType or driver._token is None:
            stop('terminal_explicit_token_required')
        self._setup(driver,15)
        self.origin=driver.origin;self.endpoint=driver.endpoint;self.message_profile='official'
        self.schema_report=_schema_flags({})

    def review_descriptors(self,descriptors):self.schema_report=_schema_flags(descriptors)

    def rpc(self,method,params=None,*,notification=False):
        if method not in ('initialize','notifications/initialized','tools/list'):
            contract.reject('mcp_discovery_business_locked')
        return super().rpc(method,params,notification=notification)

    def tool(self,*args,**kwargs):contract.reject('mcp_discovery_business_locked')


SAFE_REASONS=frozenset(('mcp_sse_schema_unproven','mcp_sse_rpc_error','mcp_sse_tool_error',
    'mcp_sse_protocol_rejected','mcp_binding_account_mismatch','mcp_binding_object_mismatch',
    'mcp_binding_envelope_unknown','mcp_official_authentication_required',
    'mcp_official_dns_timeout','mcp_official_dns_failed','mcp_official_dns_rejected',
    'mcp_share_prerequisites_unproven')) | contract.SAFE_CODES


def run_readonly(expected,token):
    """At most one discovery/user_info/exact file_meta; no share or Job writes.

    Schema/identity/metadata matches stay candidate-only: application provenance
    and share-result mapping are not invented by interactive credential entry.
    """
    result={'mode':'terminal-readonly','status':'stopped','reason':'terminal_operation_failed',
            'candidate_fields_match':False,'live_authenticated':False,'share_eligible':False,
            'delivery_eligible':False,'share_attempted':False,'automatic_retry_allowed':False}
    driver=None;client=None
    try:
        if type(expected) is not ExpectedObject:stop('terminal_expectation_invalid')
        driver=OfficialHTTPSDriver(access_token=token,io_timeout=3,budget=15)
        token=None
        client=_TerminalReadSession.official_readonly(driver,expected,budget=15)
        result.update(client.inspect(),reason='mcp_share_prerequisites_unproven')
    except contract.Rejected as exc:
        reason=exc.args[0] if exc.args else None
        result['reason']=reason if type(reason) is str and reason in SAFE_REASONS else 'terminal_operation_failed'
    except (Exception,KeyboardInterrupt):pass  # Never show input/URL/raw exception.
    finally:
        token=None
        if driver is not None:driver._token=None
        if client is not None:
            if hasattr(client,'schema_report'):result['discovery']=client.schema_report
            result['close_confirmed']=client.close()
        elif driver is not None:result['close_confirmed']=driver.close()
        if driver is not None:
            result['request_counts']={name:sum(item.get('operation')==name for item in driver.trace)
                for name in ('sse_open','initialize','notifications/initialized','tools/list')}
            result['readonly_tool_calls']=sum(item.get('operation')=='tools/call' for item in driver.trace)
        if result.get('close_confirmed') is False:
            result.update(status='manual_review',reason='mcp_sse_stop_unconfirmed')
    return result


def run_discovery(token):
    result={'mode':'terminal-discovery-only','status':'stopped','reason':'terminal_operation_failed',
            'live_authenticated':False,'account_verified':False,'object_verified':False,
            'share_eligible':False,'share_attempted':False,'automatic_retry_allowed':False}
    driver=None;client=None
    try:
        driver=OfficialHTTPSDriver(access_token=token,io_timeout=3,budget=15)
        token=None
        client=_TerminalDiscoverySession(driver)
        client.connect()
        result.update(status='discovery_complete',discovery=client.schema_report,reason='terminal_discovery_complete')
    except contract.Rejected as exc:
        reason=exc.args[0] if exc.args else None
        result['reason']=reason if type(reason) is str and reason in SAFE_REASONS else 'terminal_operation_failed'
    except (Exception,KeyboardInterrupt):pass
    finally:
        token=None
        if driver is not None:driver._token=None
        if client is not None:result['close_confirmed']=client.close()
        elif driver is not None:result['close_confirmed']=driver.close()
        if driver is not None:
            result['request_counts']={name:sum(item.get('operation')==name for item in driver.trace)
                for name in ('sse_open','initialize','notifications/initialized','tools/list')}
        if result.get('close_confirmed') is False:
            result.update(status='manual_review',reason='mcp_sse_stop_unconfirmed')
    return result


class _Parser(argparse.ArgumentParser):
    def error(self,message):stop('terminal_arguments_invalid')


def main(argv=None):
    secret=None;handlers={}
    def interrupted(signum,frame):stop('terminal_operation_cancelled')
    try:
        for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):
            handlers[sig]=signal.signal(sig,interrupted)
        parser=_Parser(description='Explicit private-terminal official MCP read-only check. No sharing.')
        parser.add_argument('--expectations',metavar='PRIVATE_JSON')
        modes=parser.add_mutually_exclusive_group(required=True)
        modes.add_argument('--read-only',action='store_true')
        modes.add_argument('--discover-only',action='store_true')
        args=parser.parse_args(argv)
        if args.read_only and not args.expectations:stop('terminal_expectation_required')
        if args.discover_only and args.expectations:stop('terminal_arguments_invalid')
        expected=load_expected(args.expectations) if args.read_only else None
        sys.stdout.write('Official destination: https://mcp-pan.baidu.com/sse\n'
            'Token is sent in its HTTPS query; official server logging is outside client control.\n'
            'No sharing, OAuth or refresh.\n')
        scope='DISCOVER-ONLY' if args.discover_only else 'READ-ONLY'
        sys.stdout.write('Only tool schema discovery; no account/file calls.\n' if args.discover_only else
                         'Only discovery, expected account and one exact file.\n')
        confirmation=read_secret('Type '+scope+' to confirm this scope (hidden): ',limit=16)
        if confirmation!=scope:stop('terminal_confirmation_declined')
        secret=read_secret()
        report=run_discovery(secret) if args.discover_only else run_readonly(expected,secret)
        secret=None
        sys.stdout.write(json.dumps(report,ensure_ascii=False)+'\n')
        return 0 if report['reason'] in ('mcp_share_prerequisites_unproven','terminal_discovery_complete') else 1
    except TerminalFailure as exc:
        sys.stdout.write(json.dumps({'status':'stopped','reason':exc.args[0]})+'\n')
        return 1
    except contract.Rejected:
        sys.stdout.write('{"status":"stopped","reason":"terminal_expectation_invalid"}\n');return 1
    except (Exception,KeyboardInterrupt):
        sys.stdout.write('{"status":"stopped","reason":"terminal_operation_failed"}\n');return 1
    finally:
        secret=None
        for sig,handler in handlers.items():signal.signal(sig,handler)


if __name__=='__main__':raise SystemExit(main())

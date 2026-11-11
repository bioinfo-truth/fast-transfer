"""One no-credential production-client discovery session; no business calls."""
import datetime
import json
from pathlib import Path
import re
import sys
import time
sys.path.insert(0,str(Path.cwd()))
from fast_transfer.mcp_official_http import OfficialHTTPSDriver
from fast_transfer.mcp_discovery import OfficialDiscoverySession
from fast_transfer.mcp_share import Rejected

start=time.monotonic()
result={'observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'execution_scope':'current project execution host; not overseas VPS',
        'target':'https://mcp-pan.baidu.com/sse','production_client_used':True,
        'authentication_sent':False,'real_credentials_read':False,'business_calls':0,'share_calls':0,
        'redirects_followed':0,'automatic_retries':0}
driver=None;client=None
try:
    driver=OfficialHTTPSDriver(io_timeout=3,budget=15)
    client=OfficialDiscoverySession(driver,budget=15)
    client.connect()
    result.update(client.summary(),status='discovery_completed')
except Rejected as exc:
    reason=exc.args[0] if exc.args else None
    result.update(status='stopped',reason=reason if type(reason) is str and re.fullmatch('mcp_[a-z_]{1,80}',reason) else 'rejected')
    if client is not None and client.last_rpc_error is not None:result['rpc_error']=client.last_rpc_error
except Exception as exc:
    result.update(status='stopped',error_type=type(exc).__name__)
finally:
    if driver is not None:
        result.update(tls_version=driver.tls_version,tls_certificate_and_hostname_verified=driver.tls_version is not None,
                      http_statuses=driver.http_statuses,
                      get_requests=sum(x['method']=='GET' for x in driver.trace),
                      initialize_requests=sum(x.get('operation')=='initialize' for x in driver.trace),
                      initialized_notifications=sum(x.get('operation')=='notifications/initialized' for x in driver.trace),
                      tools_list_requests=sum(x.get('operation')=='tools/list' for x in driver.trace),
                      rpc_ids=[x['id'] for x in driver.trace if x.get('id') is not None])
    if client is not None:
        result.update(sse_bytes_read=client.total,close_confirmed=client.close())
    elif driver is not None:result['close_confirmed']=driver.close()
    result['elapsed_seconds']=round(time.monotonic()-start,4)
print(json.dumps(result,ensure_ascii=False,indent=2))

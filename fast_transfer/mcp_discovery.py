"""Official protocol discovery only: no account/object/business dispatch."""
import re

from . import mcp_sse as wire
from . import mcp_share as contract
from .mcp_official_http import OfficialHTTPSDriver


class OfficialDiscoverySession(wire.SSEClient):
    def __init__(self,driver,*,budget=15):
        if type(driver) is not OfficialHTTPSDriver or driver._token is not None:
            contract.reject('mcp_discovery_requires_no_credentials')
        if type(budget) not in (int,float) or not 0<budget<=30:
            contract.reject('mcp_sse_protocol_rejected')
        self._setup(driver,budget)
        self.origin=driver.origin;self.endpoint=driver.endpoint;self.message_profile='official'
        self.descriptors={}

    def rpc(self,method,params=None,*,notification=False):
        if method not in ('initialize','notifications/initialized','tools/list'):
            contract.reject('mcp_discovery_business_locked')
        return super().rpc(method,params,notification=notification)

    def tool(self,*args,**kwargs):
        contract.reject('mcp_discovery_business_locked')

    def review_descriptors(self,descriptors):
        # Discovery observes schemas; it does NOT approve them for business use.
        self.descriptors=descriptors

    def summary(self):
        known={}
        for name in ('user_info','file_meta','file_sharelink_set'):
            value=self.descriptors.get(name)
            if type(value) is not dict:
                known[name]={'present':name in self.descriptors,'object_schema':False}
                continue
            properties=value.get('properties',{})
            required=value.get('required',[])
            valid=(type(properties) is dict and type(required) is list
                   and all(type(k) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,63}',k) for k in properties)
                   and all(type(k) is str and k in properties for k in required))
            if not valid:
                known[name]={'present':True,'schema_summary_supported':False}
                continue
            fields={}
            for key,item in properties.items():
                fields[key]={'type':item.get('type') if type(item) is dict and item.get('type') in
                             ('object','array','string','integer','number','boolean','null') else 'unspecified'}
                if type(item) is dict and type(item.get('items')) is dict:
                    item_type=item['items'].get('type')
                    fields[key]['item_type']=item_type if item_type in ('string','integer','number','object') else 'unspecified'
            known[name]={'present':True,'schema_summary_supported':True,
                         'object_schema':value.get('type')=='object','properties':fields,'required':required}
        return {'tool_count':len(self.descriptors),'selected_tool_schemas':known,
                'schema_discovery_completed':self.connected,'live_authenticated':False,
                'account_verified':False,'object_verified':False,'share_eligible':False}

    def close(self):
        self.descriptors.clear()
        return super().close()

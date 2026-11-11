"""Read one explicit private OAuth JSON in-place; return fixed safe metadata only.

Parsing the mixed JSON necessarily puts credential bytes in this process.
No credentials, opaque identifiers, arbitrary keys/values, file copy or network.
"""
import datetime as dt
import json
import os
import re
import stat

UTC=dt.timezone.utc
SCOPES=frozenset(('basic','netdisk','offline_access','email','mobile','public','friends','super_msg'))
SENSITIVE=('access_token','refresh_token','session_key','session_secret','client_secret',
           'secret_key','SecretKey','AppKey','app_key','api_key','client_id','password','cookie','bduss')
CONTAINERS=('metadata','oauth_metadata','token_metadata')


class UnsafeMetadata(Exception):pass


def _unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise UnsafeMetadata()
        value[key]=item
    return value


def _safe_time(value):
    basis=None
    if type(value) is str and re.fullmatch(r'[0-9]{9,13}(?:\.[0-9]{1,6})?',value):value=float(value)
    if type(value) in (int,float):
        if 946684800<=value<=4102444800:basis='unix_seconds'
        elif 946684800000<=value<=4102444800000:value/=1000;basis='unix_milliseconds'
        else:return None
        try:return dt.datetime.fromtimestamp(value,UTC),basis
        except (ValueError,OverflowError,OSError):return None
    if type(value) is str and len(value)<=35:
        try:parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:return None
        if parsed.tzinfo is None or not 2000<=parsed.year<=2100:return None
        return parsed.astimezone(UTC),'timezone_explicit_iso8601'
    return None


def extract_metadata(root,now):
    if type(root) is not dict or len(root)>128:raise UnsafeMetadata()
    views=[('',root)]
    for name in CONTAINERS:
        if name in root:
            item=root[name]
            if type(item) is not dict or len(item)>64:raise UnsafeMetadata()
            views.append((name+'.',item))
    taints=[]
    for _,view in views:
        for name in SENSITIVE:
            value=view.get(name)
            if type(value) in (str,int,float) and value:taints.append(str(value))
    def allowed(value):
        rendered=json.dumps(value,ensure_ascii=False)
        return not any(value==item or (len(item)>=4 and item in rendered) for item in taints)
    def fields(names):
        return [(prefix+name,item[name]) for prefix,item in views for name in names if name in item]
    result={'status':'metadata_extracted','checked_at_utc':now.astimezone(UTC).isoformat(),
            'historical_expected_application':'Xtransfer','application_binding_verified':False,
            'official_live_validity_verified':False,'share_permission_verified':False,
            'mixed_credential_json_parsed_in_vps_memory':True,'secret_values_returned':False,
            'credentials_submitted':False,'authorization_changed':False}
    names=fields(('app_name','application_name','application','appname'))
    result['application_name']={'status':'missing'}
    if names:
        matches=all(type(value) is str and value=='Xtransfer' and allowed(value) for _,value in names)
        result['application_name']={'status':'recorded_expected_name' if matches else 'unverified_or_redacted'}
        if matches:result['application_name']['value']='Xtransfer'
    ids=fields(('app_id','appid','application_id','AppID'))
    # No private application identifier/hash is returned to the agent or logs.
    result['application_id']={'status':'missing' if not ids else 'present_value_not_exported',
        'all_numeric_format':bool(ids) and all(type(value) in (str,int) and re.fullmatch('[1-9][0-9]{0,19}',str(value)) is not None for _,value in ids)}
    scopes=fields(('scope','scopes'));normal=[];scope_sources=[]
    for name,value in scopes:
        if type(value) is str and len(value)<=256:parts=re.split('[, ]+',value.strip())
        elif type(value) is list and len(value)<=16 and all(type(item) is str for item in value):parts=value
        else:parts=[]
        if not parts or any(item not in SCOPES for item in parts) or not allowed(' '.join(sorted(set(parts)))):
            normal.append(None)
        else:normal.append(tuple(sorted(set(parts))));scope_sources.append(name)
    if not scopes:result['scope']={'status':'missing'}
    elif None in normal:result['scope']={'status':'unsupported_or_redacted'}
    elif len(set(normal))!=1:result['scope']={'status':'conflicting_records'}
    else:result['scope']={'status':'recorded','value':' '.join(normal[0]),'source_fields':scope_sources}
    def times(names):
        records=fields(names);out=[]
        for name,value in records:
            parsed=_safe_time(value)
            if parsed is None or not allowed(value) or not allowed(parsed[0].isoformat()):return {'status':'unusable_or_redacted'},None
            out.append((name,*parsed))
        if not out:return {'status':'missing'},None
        if len({item[1] for item in out})!=1:return {'status':'conflicting_records'},None
        return {'status':'recorded','utc':out[0][1].isoformat(),
                'source_fields':[item[0] for item in out],'conversion':[item[2] for item in out]},out[0][1]
    result['issuance'],issued=times(('issued_at','token_issued_at','obtained_at','token_obtained_at','authorized_at'))
    result['expiry'],expires=times(('expires_at','expire_at','token_expires_at'))
    result['other_recorded_times'],_=times(('created_at','created_utc','authorization_time'))
    durations=fields(('expires_in',));values=[]
    for name,value in durations:
        if type(value) is str and re.fullmatch('[0-9]{1,10}',value):value=int(value)
        if type(value) is not int or not 0<value<=366*86400 or not allowed(value):values.append(None)
        else:values.append(value)
    duration=None
    if not values:result['expires_in']={'status':'missing'}
    elif None in values or len(set(values))!=1:result['expires_in']={'status':'unusable_or_conflicting'}
    else:duration=values[0];result['expires_in']={'status':'recorded','seconds':duration}
    result['expiry_calculation_basis']='none_no_sufficient_metadata'
    if expires is not None:result['expiry_calculation_basis']='recorded_absolute_expiry_not_service_verified'
    elif issued is not None and duration is not None:
        expires=issued+dt.timedelta(seconds=duration)
        result['expiry']={'status':'calculated_from_metadata','utc':expires.isoformat()}
        result['expiry_calculation_basis']='explicit_issuance_metadata_plus_expires_in'
    if expires is None:result['local_expiry_assessment']='unknown'
    else:
        result['local_expiry_assessment']='past_recorded_expiry' if now>=expires else 'not_past_recorded_expiry'
        result['recorded_remaining_seconds']=int((expires-now).total_seconds())
    # created_at, file mtime, successful uploads and other grants are NOT expiry anchors.
    return result


def read_authorization_metadata(path,now=None):
    root=None;raw=None
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        with os.fdopen(fd,'rb') as source:
            before=os.fstat(source.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_uid!=os.geteuid()
                    or stat.S_IMODE(before.st_mode)&0o077):raise UnsafeMetadata()
            raw=source.read(65537);after=os.fstat(source.fileno())
            if len(raw)>65536 or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise UnsafeMetadata()
        root=json.loads(raw,object_pairs_hook=_unique,parse_constant=lambda _:(_ for _ in ()).throw(UnsafeMetadata()))
        return extract_metadata(root,now or dt.datetime.now(UTC))
    except Exception:
        # No raw JSON, parser snippets, sensitive keys, paths or exception details.
        return {'status':'metadata_unavailable_or_rejected','secret_values_returned':False,
                'credentials_submitted':False,'authorization_changed':False}
    finally:
        raw=None
        if type(root) is dict:root.clear()

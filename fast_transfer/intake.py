"""MVP intake: deterministic assessment, without network or credentials."""
import argparse
import ipaddress
import json
import re
import sys
import urllib.parse
from pathlib import Path

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_FILES = 100


class InputProblem(ValueError):
    def __init__(self, code, status='rejected'):
        self.code, self.status = code, status
        super().__init__(code)  # Never include the submitted URL or network exception.


def safe_name(name):
    if (not isinstance(name, str) or len(name) > 180
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name)
            or name.endswith('.')
            or name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
        raise InputProblem('invalid_filename')
    return name


def public_url(url):
    """Syntax/literal checks only. DNS must be checked and pinned at connection time."""
    if (not isinstance(url, str) or not url or len(url) > 2048
            or any(ord(c) <= 32 or ord(c) >= 127 for c in url) or '\\' in url):
        raise InputProblem('invalid_url')
    try:
        u = urllib.parse.urlsplit(url)
        if u.scheme != 'https':
            raise InputProblem('https_required')
        if u.username is not None or u.password is not None or u.query or u.fragment:
            raise InputProblem('credential_or_query_url_not_supported')
        host = u.hostname
        if not host or u.port not in (None, 443) or '%' in host:
            raise InputProblem('invalid_host_or_port')
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if (len(host) > 253 or '.' not in host or host.endswith('.')
                    or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                           for label in host.split('.'))
                    or host.endswith(('.localhost', '.local', '.internal'))):
                raise InputProblem('nonpublic_or_invalid_host')
        else:
            if not address.is_global or address.is_multicast:
                raise InputProblem('nonpublic_host')
    except ValueError as exc:
        if isinstance(exc, InputProblem):
            raise
        raise InputProblem('invalid_url') from None
    return u


def _text(value):
    return isinstance(value, str) and 0 < len(value) <= 1000 and all(ord(c) >= 32 for c in value)


def assess(manifest):
    """Return safe reason codes; accepted means intake-ready, never delivered."""
    if (not isinstance(manifest, dict) or set(manifest) - {'schema_version', 'files'}
            or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1
            or not isinstance(manifest.get('files'), list)
            or not 1 <= len(manifest['files']) <= MAX_FILES):
        return {'status': 'rejected', 'reasons': ['invalid_manifest'], 'files': []}
    rows, names = [], set()
    for index, entry in enumerate(manifest['files']):
        reasons = []
        def add(code, status='rejected'):
            reasons.append({'code': code, 'status': status})
        name = None
        if not isinstance(entry, dict):
            add('invalid_file_entry')
        else:
            if set(entry) - {'name', 'url', 'size', 'md5', 'sha256', 'source'}:
                add('unknown_file_fields')
            try:
                name = safe_name(entry.get('name'))
                if name.casefold() in names:
                    add('duplicate_filename')
                names.add(name.casefold())
            except InputProblem as exc:
                add(exc.code)
            try:
                public_url(entry.get('url'))
            except InputProblem as exc:
                add(exc.code)
            size = entry.get('size')
            if size is None:
                add('size_required', 'manual_review')
            elif type(size) is not int or size <= 0:
                add('invalid_size')
            if not any(entry.get(k) for k in ('md5', 'sha256')):
                add('source_checksum_required', 'manual_review')
            for field, width in [('md5', 32), ('sha256', 64)]:
                if field in entry and (not isinstance(entry[field], str)
                        or not re.fullmatch(r'[0-9a-fA-F]{%d}' % width, entry[field])):
                    add('invalid_' + field)
            source = entry.get('source')
            if not isinstance(source, dict):
                add('source_provenance_required', 'manual_review')
            else:
                if set(source) - {'access', 'record_url', 'version', 'checksum_url', 'redistribution'}:
                    add('unknown_source_fields')
                if source.get('access') == 'controlled':
                    add('controlled_access_not_supported')
                elif source.get('access') != 'public':
                    add('public_access_review_required', 'manual_review')
                if not _text(source.get('version')):
                    add('source_version_required', 'manual_review')
                for field in ('record_url', 'checksum_url'):
                    if field not in source:
                        add(field + '_required', 'manual_review')
                    else:
                        try:
                            public_url(source[field])
                        except InputProblem:
                            add('invalid_' + field)
                rights = source.get('redistribution')
                if not isinstance(rights, dict):
                    add('redistribution_review_required', 'manual_review')
                else:
                    if set(rights) - {'status', 'basis_url', 'note'}:
                        add('unknown_redistribution_fields')
                    if rights.get('status') == 'prohibited':
                        add('redistribution_prohibited')
                    elif rights.get('status') != 'reviewed' or not _text(rights.get('note')):
                        add('redistribution_review_required', 'manual_review')
                    try:
                        public_url(rights.get('basis_url'))
                    except InputProblem:
                        add('redistribution_basis_required', 'manual_review')
        status = ('rejected' if any(x['status'] == 'rejected' for x in reasons)
                  else 'manual_review' if reasons else 'accepted')
        rows.append({'index': index, 'name': name, 'status': status, 'reasons': reasons})
    status = ('rejected' if any(x['status'] == 'rejected' for x in rows)
              else 'manual_review' if any(x['status'] == 'manual_review' for x in rows) else 'accepted')
    return {'status': status, 'files': rows}


def require_accepted(manifest):
    report = assess(manifest)
    if report['status'] != 'accepted':
        raise InputProblem('intake_' + report['status'], report['status'])
    return manifest['files']


def load_manifest(path):
    try:
        with Path(path).open('rb') as f:
            data = f.read(MAX_MANIFEST_BYTES + 1)
        if len(data) > MAX_MANIFEST_BYTES:
            raise InputProblem('manifest_too_large')
        def unique(pairs):
            result = {}
            for k, v in pairs:
                if k in result:
                    raise InputProblem('duplicate_json_key')
                result[k] = v
            return result
        return json.loads(data, object_pairs_hook=unique)
    except InputProblem:
        raise
    except (OSError, UnicodeError, ValueError):
        raise InputProblem('manifest_unreadable_or_invalid_json') from None


def main():
    p = argparse.ArgumentParser(description='Assess MVP public-file input without fetching it.')
    p.add_argument('manifest', nargs='?', type=Path)
    p.add_argument('--url', help='A single public HTTPS URL; incomplete metadata needs manual review.')
    p.add_argument('--name')
    a = p.parse_args()
    if bool(a.manifest) == bool(a.url):
        p.error('provide a manifest OR --url with --name')
    try:
        obj = load_manifest(a.manifest) if a.manifest else {'schema_version': 1, 'files': [{'url': a.url, 'name': a.name}]}
        result = assess(obj)
    except InputProblem as exc:
        result = {'status': exc.status, 'reasons': [exc.code], 'files': []}
    print(json.dumps(result, ensure_ascii=False))
    return {'accepted': 0, 'manual_review': 2, 'rejected': 1}[result['status']]


if __name__ == '__main__':
    sys.exit(main())

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CHUNK = 4 * 1024 * 1024
API = 'https://pan.baidu.com/rest/2.0/xpan/file'


def request(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def json_request(url, data=None, headers=None):
    result = json.loads(request(url, data, headers))
    error = result.get('errno', result.get('error_code', 0))
    if error != 0:
        raise RuntimeError(f"Baidu API error {error} (request_id={result.get('request_id', 'unknown')})")
    return result


def api_url(method, token):
    return API + '?' + urllib.parse.urlencode({'method': method, 'access_token': token})


def post_form(url, values):
    return json_request(url, urllib.parse.urlencode(values).encode())


def hashes(path):
    whole = hashlib.md5()  # Public database checksum and Baidu protocol, not authentication.
    blocks = []
    size = 0
    with path.open('rb') as stream:
        while block := stream.read(CHUNK):
            size += len(block)
            whole.update(block)
            blocks.append(hashlib.md5(block).hexdigest())
    if not blocks:
        blocks = [hashlib.md5(b'').hexdigest()]
    return size, whole.hexdigest(), blocks


def safe_name(name):
    if not isinstance(name, str) or not name or name in ('.', '..') or '/' in name or '\\' in name or '\x00' in name:
        raise ValueError('filename must be a simple, non-empty filename')
    return name


def download(entry, path, max_bytes, reserve):
    url = entry['url']
    if urllib.parse.urlparse(url).scheme != 'https':
        raise ValueError('source must use HTTPS')
    expected = entry.get('size')
    if expected is not None and (not isinstance(expected, int) or isinstance(expected, bool) or expected < 0):
        raise ValueError('size must be a nonnegative integer')
    if expected is not None and expected > max_bytes:
        raise ValueError('file exceeds configured limit')
    if expected is not None and shutil.disk_usage(path.parent).free - expected < reserve:
        raise ValueError('insufficient free disk space')
    total = 0
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'fast-transfer-poc/0.1'}), timeout=120) as source, path.open('xb') as output:
        length = source.headers.get('Content-Length')
        if length and int(length) > max_bytes:
            raise ValueError('Content-Length exceeds configured limit')
        while True:
            data = source.read(min(1024 * 1024, max_bytes - total + 1))
            if not data:
                break
            if total + len(data) > max_bytes or shutil.disk_usage(path.parent).free - len(data) < reserve:
                raise ValueError('download stopped: disk budget or free-space reserve reached')
            output.write(data)
            total += len(data)
    if expected is not None and total != expected:
        raise ValueError(f'size mismatch: expected {expected}, got {total}')
    return total


def upload(path, remote, token):
    size, md5, blocks = hashes(path)
    block_list = json.dumps(blocks, separators=(',', ':'))
    common = {'path': remote, 'size': size, 'isdir': 0, 'rtype': 0, 'block_list': block_list}
    pre = post_form(api_url('precreate', token), {**common, 'autoinit': 1})
    upload_id = pre['uploadid']
    host_result = json_request('https://d.pcs.baidu.com/rest/2.0/pcs/file?' + urllib.parse.urlencode({'method': 'locateupload', 'appid': 250528, 'access_token': token, 'path': remote, 'uploadid': upload_id, 'upload_version': '2.0'}))
    hosts = host_result.get('servers') or []
    if not hosts:
        raise RuntimeError('Baidu did not return an upload host')
    host = next((item.get('server', '') for item in hosts if item.get('server', '').startswith('https://')), '')
    if not host.startswith('https://'):
        raise RuntimeError('Baidu upload host is not HTTPS; refusing to send credentials')
    indexes = pre.get('block_list') or ([0] if len(blocks) == 1 else [])
    with path.open('rb') as source:
        for index in indexes:
            if not isinstance(index, int) or index < 0 or index >= len(blocks):
                raise RuntimeError('invalid upload block index')
            source.seek(index * CHUNK)
            block = source.read(CHUNK)
            boundary = '----fasttransfer' + os.urandom(12).hex()
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="chunk"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + block + f'\r\n--{boundary}--\r\n'.encode())
            query = urllib.parse.urlencode({'method': 'upload', 'access_token': token, 'type': 'tmpfile', 'path': remote, 'uploadid': upload_id, 'partseq': index})
            result = json_request(host.rstrip('/') + '/rest/2.0/pcs/superfile2?' + query, body, {'Content-Type': 'multipart/form-data; boundary=' + boundary})
            if result.get('md5', '').lower() != blocks[index]:
                raise RuntimeError(f'uploaded block {index} checksum mismatch')
    result = post_form(api_url('create', token), {**common, 'uploadid': upload_id})
    if result.get('size') != size:
        raise RuntimeError('remote size mismatch or missing from response')
    return {'size': size, 'md5': md5, 'remote_path': result.get('path', remote), 'fs_id': result.get('fs_id')}


def main():
    parser = argparse.ArgumentParser(description='Transfer public files sequentially to an authorized Baidu app folder.')
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--remote-dir', required=True, help='Baidu application folder, e.g. /apps/myapp/test')
    parser.add_argument('--max-file-gib', type=float, default=10)
    parser.add_argument('--reserve-gib', type=float, default=5)
    parser.add_argument('--download-only', action='store_true', help='validate download and checksum without uploading')
    args = parser.parse_args()
    if not args.remote_dir.startswith('/apps/') or '..' in args.remote_dir.split('/'):
        parser.error('remote-dir must be inside /apps/<appname>')
    if args.max_file_gib <= 0 or args.reserve_gib < 0:
        parser.error('invalid disk budget')
    token = os.environ.get('BAIDU_ACCESS_TOKEN')
    if not args.download_only and not token:
        parser.error('set BAIDU_ACCESS_TOKEN in the environment')
    manifest = json.loads(args.manifest.read_text())
    entries = manifest['files']
    if not isinstance(entries, list) or not entries:
        raise ValueError('manifest files must be a non-empty list')
    names = [safe_name(x['name']) for x in entries]
    if len(names) != len(set(names)):
        raise ValueError('duplicate filenames')
    args.work_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        name = safe_name(entry['name'])
        print(json.dumps({'event': 'starting', 'file': name}, ensure_ascii=False), flush=True)
        # A private per-file directory prevents collisions and scopes cleanup to this invocation.
        with tempfile.TemporaryDirectory(prefix='fast-transfer-', dir=args.work_dir) as tmp:
            path = Path(tmp) / name
            start = time.monotonic()
            download(entry, path, int(args.max_file_gib * 1024**3), int(args.reserve_gib * 1024**3))
            size, md5, _ = hashes(path)
            if entry.get('md5') and md5.lower() != entry['md5'].lower():
                raise ValueError(f'checksum mismatch for {name}')
            result = {'file': name, 'size': size, 'md5': md5, 'source_checksum_verified': bool(entry.get('md5'))}
            if not args.download_only:
                result.update(upload(path, args.remote_dir.rstrip('/') + '/' + name, token))
            result.update({'event': 'complete', 'seconds': round(time.monotonic() - start, 2)})
            print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, urllib.error.URLError) as exc:
        # Network exceptions may include access tokens in URLs; never print their contents.
        if isinstance(exc, (urllib.error.URLError, OSError)):
            print(f'Transfer failed: {type(exc).__name__}; check connectivity and permissions.', file=sys.stderr)
        else:
            print(f'Transfer failed: {exc}', file=sys.stderr)
        sys.exit(1)

"""M2: bounded source download and verification; no cloud operations."""
import argparse
import hashlib
import http.client
import json
import os
import socket
import ssl
import sys
import time
from pathlib import Path

from .intake import InputProblem, load_manifest, require_accepted
from .safe_http import open_public
from .space import (BackendNeeds, SpaceGuard, SpaceProblem, RESERVE,
                    SOURCE_OVERHEAD, preflight_workspace)


def download_verified(entry, path, max_bytes, reserve=RESERVE, timeout=300, space_guard=None):
    require_accepted({'schema_version': 1, 'files': [entry]})
    if type(max_bytes) is not int or max_bytes <= 0 or reserve < RESERVE or timeout <= 0:
        raise InputProblem('invalid_download_budget')
    expected = entry['size']
    if expected > max_bytes:
        raise InputProblem('file_budget_exceeded', 'manual_review')
    guard = space_guard or SpaceGuard({path.name: expected}, path.parent,
                                     BackendNeeds.source_only(), reserve=reserve)
    guard.require_source(path, expected)
    guard.check('download')
    deadline = time.monotonic() + timeout
    response = connection = None
    created = False
    try:
        response, connection, hops = open_public(entry['url'], deadline)
        lengths = response.headers.get_all('Content-Length', [])
        if lengths and (len(lengths) != 1 or len(lengths[0]) > 20
                        or not lengths[0].isascii() or not lengths[0].isdigit()):
            raise InputProblem('invalid_content_length')
        if lengths and int(lengths[0]) != expected:
            raise InputProblem('content_length_mismatch')
        if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise InputProblem('unexpected_content_encoding')
        if response.getheader('Transfer-Encoding') and lengths:
            raise InputProblem('ambiguous_response_framing')
        guard.check('download')
        total, md5, sha = 0, hashlib.md5(), hashlib.sha256()
        # Exclusive creation; no existing path/symlink is overwritten or removed.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, 'wb') as output:
            while True:
                guard.check('download')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise InputProblem('download_deadline', 'manual_review')
                if connection.sock:
                    connection.sock.settimeout(min(30, remaining))
                data = response.read1(min(1024**2, expected - total + 1))
                if not data:
                    break
                if total + len(data) > expected:
                    raise InputProblem('source_size_exceeded')
                guard.check('download', growth={'source': len(data)})
                output.write(data)
                # Checkpoints must see allocated file blocks, not buffered progress counters.
                output.flush()
                total += len(data)
                md5.update(data)
                sha.update(data)
            output.flush()
            os.fsync(output.fileno())
        if total != expected:
            raise InputProblem('source_size_mismatch')
        result = {'bytes': total, 'md5': md5.hexdigest(), 'sha256': sha.hexdigest()}
        if any(entry.get(key) and entry[key].lower() != result[key] for key in ('md5', 'sha256')):
            raise InputProblem('source_checksum_mismatch')
        guard.check('download')
        return {'status': 'source_verified', **result, 'redirect_hops': hops,
                'source_checksum_algorithms': [k for k in ('md5', 'sha256') if k in entry]}
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise
    finally:
        if response is not None:
            response.close()
        if connection is not None:
            connection.close()


def main():
    p = argparse.ArgumentParser(description='Download accepted public inputs; never upload or share.')
    p.add_argument('manifest', type=Path)
    p.add_argument('--output-dir', type=Path, required=True, help='Fresh per-run directory, must not exist.')
    p.add_argument('--max-file-bytes', type=int, default=16 * 1024**2)
    p.add_argument('--backend', choices=('source-only', 'openlist', 'direct-api'), default='source-only',
                   help='Disk plan only: this command never uploads.')
    p.add_argument('--backend-dir', type=Path, help='Existing task-private backend workspace; never inferred from a parent.')
    p.add_argument('--source-overhead-bytes', type=int)
    p.add_argument('--upload-temp-bytes', type=int)
    p.add_argument('--readback-temp-bytes', type=int)
    p.add_argument('--readback-mode', choices=('stream', 'file'))
    p.add_argument('--expected-layout', choices=('auto', 'same', 'separate'), default='auto')
    a = p.parse_args()
    try:
        entries = require_accepted(load_manifest(a.manifest))
        if a.max_file_bytes <= 0 or any(e['size'] > a.max_file_bytes for e in entries):
            raise InputProblem('file_budget_exceeded', 'manual_review')
        overhead = a.source_overhead_bytes
        if overhead is None and a.backend == 'source-only':
            overhead = SOURCE_OVERHEAD
        needs = BackendNeeds(a.backend, overhead, a.upload_temp_bytes,
                             a.readback_temp_bytes, a.readback_mode)
        needs.validate()
        preflight_workspace(a.output_dir.parent, a.backend_dir)
        a.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        receipts = a.output_dir / '.receipts'
        receipts.mkdir(mode=0o700)
        guard = SpaceGuard({e['name']: e['size'] for e in entries}, a.output_dir, needs,
                           a.backend_dir, source_extra_files=[receipts / (str(i)+'.json') for i in range(len(entries))],
                           expected_layout=a.expected_layout)
        admission = guard.check('download')
        print(json.dumps({'event': 'space_admission', **admission}))
        for index, e in enumerate(entries):
            result = download_verified(e, a.output_dir / e['name'], a.max_file_bytes, space_guard=guard)
            record = json.dumps({'file': e['name'], **result}, indent=2).encode()
            guard.check('download', growth={'source_extra': len(record)})
            fd = os.open(receipts / (str(index) + '.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(record)
                f.flush()
                os.fsync(f.fileno())
            guard.check('download')
            print(json.dumps({'file': e['name'], **result}))
        return 0
    except InputProblem as exc:
        result = {'status': exc.status, 'reason': exc.code}
        if isinstance(exc, SpaceProblem) and exc.report is not None:
            result['space_budget'] = exc.report
        print(json.dumps(result))
        return 2 if exc.status == 'manual_review' else 1
    except (OSError, http.client.HTTPException, socket.timeout, ssl.SSLError):
        print(json.dumps({'status': 'manual_review', 'reason': 'source_io_or_network_failure'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())

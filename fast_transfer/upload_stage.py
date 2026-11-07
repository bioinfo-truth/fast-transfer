"""M3 direct-API flow with an injected simulation transport; no HTTP/auth implementation."""
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .intake import InputProblem, require_accepted
from .space import SpaceGuard, preflight_workspace

MAX_RECORD = 16 * 1024
MAX_SIMULATION_BYTES = 16 * 1024**2
SAFE_REASONS = frozenset('''
    unknown_or_invalid_transfer_limits local_buffer_or_part_limit file_exceeds_transfer_limits
    unsafe_source_or_receipt source_size_mismatch source_changed job_record_limit job_record_conflict
    reserved_adapter_filename simulation_file_limit unsupported_adapter_storage_contract
    invalid_task_or_app_name transport_mode_or_app_mismatch source_or_receipt_path_mismatch duplicate_job
    source_receipt_limit invalid_source_receipt source_receipt_mismatch source_checksum_mismatch
    part_receipt_mismatch remote_size_mismatch invalid_readback_chunk readback_size_exceeded
    readback_hash_or_length_mismatch remote_target_exists remote_target_exists_or_simulation_limit
    simulated_part_conflict simulated_payload_limit simulated_commit_conflict simulated_commit_size
    intake_manual_review intake_rejected invalid_filename invalid_space_requirement
    unknown_backend_requirements unknown_source_overhead inapplicable_backend_requirements
    unknown_backend_overhead unknown_readback_storage_mode unsafe_space_path unusable_space_directory
    space_path_unavailable space_file_unavailable unsafe_or_unknown_space_file space_workspace_reserve
    invalid_space_sources backend_directory_required inapplicable_backend_directory invalid_space_layout
    inapplicable_space_layout space_layout_mismatch invalid_space_resource space_file_outside_task_root
    duplicate_or_invalid_space_file space_file_parent_device_mismatch space_file_parent_changed
    space_source_plan_mismatch invalid_space_stage space_stage_regression space_directory_changed
    space_file_device_or_alias_changed source_exceeds_space_plan source_not_complete_for_stage
    payload_exceeds_space_plan temporary_overhead_exceeds_plan disk_budget_exceeded
    http_runtime_locked http_stopped http_scope_invalid http_url_rejected http_redirect_rejected
    http_header_rejected http_status_rejected http_limit_exceeded http_deadline http_io_failure
    http_auth_missing http_concurrent_request protocol_json_invalid protocol_api_error
    protocol_conflict protocol_identity_mismatch protocol_account_limits_unknown protocol_quota_insufficient
    protocol_strict_conflict_unproven protocol_shape_invalid protocol_path_changed protocol_part_mismatch
    protocol_session_invalid protocol_not_ready protocol_readback_mismatch
'''.split())


def safe_reason(code):
    return code if type(code) is str and code in SAFE_REASONS else 'adapter_or_local_io_failure'


class StageFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TransferLimits:
    part_bytes: int
    max_file_bytes: int
    max_parts: int
    readback_bytes: int = 1024**2

    def validate(self, size):
        for n in (self.part_bytes, self.max_file_bytes, self.max_parts, self.readback_bytes):
            if type(n) is not int or n <= 0:
                raise StageFailure('unknown_or_invalid_transfer_limits')
        if self.part_bytes > 32*1024**2 or self.readback_bytes > 1024**2 or self.max_parts > 1024:
            raise StageFailure('local_buffer_or_part_limit')
        if size > self.max_file_bytes or (size+self.part_bytes-1)//self.part_bytes > self.max_parts:
            raise StageFailure('file_exceeds_transfer_limits')


def open_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    s = os.fstat(fd)
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
        os.close(fd)
        raise StageFailure('unsafe_source_or_receipt')
    return os.fdopen(fd, 'rb')


def file_stamp(stream):
    s = os.fstat(stream.fileno())
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def source_identity(stream, checkpoint, part_bytes, size):
    before = file_stamp(stream)
    if before[2] != size:
        raise StageFailure('source_size_mismatch')
    md, sha, blocks, total = hashlib.md5(), hashlib.sha256(), [], 0
    while True:
        checkpoint()
        data = stream.read(part_bytes)
        if not data:
            break
        total += len(data)
        if total > size:
            raise StageFailure('source_changed')
        md.update(data); sha.update(data)
        blocks.append(hashlib.md5(data).hexdigest())
    if file_stamp(stream) != before or total != size:
        raise StageFailure('source_changed')
    return {'bytes': total, 'md5': md.hexdigest(), 'sha256': sha.hexdigest()}, blocks, before


class JobRecord:
    """Only metadata in a newly claimed private directory. Never stores raw transport state."""
    def __init__(self, root, guard):
        self.root, self.guard, self.owned_state = root, guard, False
        for name in ('state.json', 'state.new'):
            guard.register('backend_extra', root/name)

    def save(self, obj, stage):
        data = json.dumps(obj, sort_keys=True).encode()
        if len(data) > MAX_RECORD:
            raise StageFailure('job_record_limit')
        self.guard.check(stage, growth={'backend_extra': len(data)})
        target, temp = self.root/'state.json', self.root/'state.new'
        if not self.owned_state and target.exists():
            raise StageFailure('job_record_conflict')
        created = False
        try:
            fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            created = True
            with os.fdopen(fd, 'wb') as f:
                f.write(data); f.flush(); os.fsync(f.fileno())
            os.replace(temp, target)
            self.owned_state = True
        finally:
            if created:
                temp.unlink(missing_ok=True)


class AdapterContext:
    def __init__(self, root, guard):
        self.root, self.guard, self.stage = root, guard, 'upload'

    def register_temporary(self, name):
        from .intake import safe_name
        safe_name(name)
        if name.casefold() in ('state.json', 'state.new'):
            raise StageFailure('reserved_adapter_filename')
        path = self.root/name
        self.guard.register('backend_extra', path)
        return path

    def checkpoint(self):
        return self.guard.check(self.stage)

    def before_temporary_write(self, bytes_upper_bound):
        return self.guard.check(self.stage, growth={'backend_extra': bytes_upper_bound})


def run_simulated_upload(entry, source_path, receipt_path, backend_root, job_id,
                         app_name, transport, needs, limits, *, probe=None,
                         expected_layout='auto'):
    """Transport contract: reserve_new/begin_new/put_part/commit_new/metadata/readback/stop.

    All calls are synchronous and cooperative. Real transports are deliberately
    rejected in this round. stop() is local-only, returns True when stopped, and
    must never delete remote objects. A new instance is owned by this single job.
    """
    result = {'mode': 'simulation', 'status': 'manual_review', 'reason': None,
              'verification_complete': False, 'simulated_delivery_eligible': False,
              'delivery_eligible': False, 'cloud_verified': False,
              'phase': 'input', 'confirmed_parts': [], 'requested_payload_bytes': 0,
              'stop_confirmed': None, 'state_persisted': False}
    source = record = guard = None
    started = False
    try:
        require_accepted({'schema_version': 1, 'files': [entry]})
        if entry['size'] > MAX_SIMULATION_BYTES:
            raise StageFailure('simulation_file_limit')
        limits.validate(entry['size'])
        needs.validate()
        if needs.name != 'direct-api' or needs.readback_mode != 'stream':
            raise StageFailure('unsupported_adapter_storage_contract')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', job_id) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', app_name):
            raise StageFailure('invalid_task_or_app_name')
        if transport.mode != 'simulation' or transport.app_name != app_name:
            raise StageFailure('transport_mode_or_app_mismatch')
        source_path, receipt_path = Path(source_path).absolute(), Path(receipt_path).absolute()
        backend_root = Path(backend_root).absolute()
        # Check exact existing parents before claiming a new task. No existing job is read/reused.
        from .space import DiskProbe
        disk = probe or DiskProbe()
        disk.directory(receipt_path.parent, writable=True)
        preflight_workspace(source_path.parent, backend_root, probe=disk)
        if source_path.name != entry['name'] or not receipt_path.is_relative_to(source_path.parent):
            raise StageFailure('source_or_receipt_path_mismatch')
        root = backend_root/job_id
        try:
            root.mkdir(mode=0o700)
        except FileExistsError:
            raise StageFailure('duplicate_job') from None
        target_dir = '/apps/'+app_name+'/mvp-validation/'+job_id
        target = target_dir+'/'+entry['name']
        result.update(job_id=job_id, target=target, phase='source_validation')
        guard = SpaceGuard({entry['name']: entry['size']}, source_path.parent, needs,
                           root, source_extra_files=[receipt_path], probe=probe,
                           expected_layout=expected_layout)
        guard.check('download')
        with open_regular(receipt_path) as f:
            raw = f.read(MAX_RECORD+1)
        if len(raw) > MAX_RECORD:
            raise StageFailure('source_receipt_limit')
        try:
            receipt = json.loads(raw)
        except (ValueError, UnicodeError):
            raise StageFailure('invalid_source_receipt') from None
        source = open_regular(source_path)
        identity, blocks, stamp = source_identity(source, lambda: guard.check('download'),
                                                  limits.part_bytes, entry['size'])
        if (not isinstance(receipt, dict) or receipt.get('status') != 'source_verified'
                or type(receipt.get('bytes')) is not int
                or receipt.get('file') != entry['name'] or any(receipt.get(k) != v for k, v in identity.items())):
            raise StageFailure('source_receipt_mismatch')
        if any(entry.get(k) and entry[k].lower() != identity[k] for k in ('md5', 'sha256')):
            raise StageFailure('source_checksum_mismatch')
        result['source'] = identity
        guard.check('upload')
        record = JobRecord(root, guard)
        record.save(result, 'upload')
        context = AdapterContext(root, guard)
        result['phase'] = 'remote_reservation'
        started = True
        transport.attach(context)
        guard.check('upload')
        transport.reserve_new(target_dir)
        guard.check('upload')
        session = transport.begin_new(target, identity['bytes'], tuple(blocks))
        required = tuple(transport.required_parts(session)) if hasattr(transport, 'required_parts') else tuple(range(len(blocks)))
        if (any(type(i) is not int or not 0 <= i < len(blocks) for i in required)
                or len(set(required)) != len(required)):
            raise StageFailure('protocol_shape_invalid')
        result['required_parts'] = list(required)
        result['phase'] = 'upload'
        for index in required:
            md5 = blocks[index]
            guard.check('upload')
            if file_stamp(source) != stamp:
                raise StageFailure('source_changed')
            source.seek(index*limits.part_bytes)
            data = source.read(limits.part_bytes)
            if hashlib.md5(data).hexdigest() != md5:
                raise StageFailure('source_changed')
            result['requested_payload_bytes'] += len(data)
            receipt_md5 = transport.put_part(session, index, data)
            if receipt_md5 != md5:
                raise StageFailure('part_receipt_mismatch')
            guard.check('upload')
            result['confirmed_parts'].append(index)
            record.save(result, 'upload')
        if file_stamp(source) != stamp:
            raise StageFailure('source_changed')
        guard.check('upload')
        transport.commit_new(session)
        guard.check('upload')
        metadata = transport.metadata(target)
        if not isinstance(metadata, dict) or type(metadata.get('size')) is not int or metadata['size'] != identity['bytes']:
            raise StageFailure('remote_size_mismatch')
        result['phase'] = 'readback'
        guard.check('readback')
        context.stage = 'readback'
        md, sha, total = hashlib.md5(), hashlib.sha256(), 0
        iterator = iter(transport.readback(target, limits.readback_bytes))
        try:
            while True:
                guard.check('readback')
                try:
                    data = next(iterator)
                except StopIteration:
                    break
                guard.check('readback')
                if type(data) is not bytes or not 0 < len(data) <= limits.readback_bytes:
                    raise StageFailure('invalid_readback_chunk')
                total += len(data)
                if total > identity['bytes']:
                    raise StageFailure('readback_size_exceeded')
                md.update(data); sha.update(data)
        finally:
            if hasattr(iterator, 'close'):
                iterator.close()
        back = {'bytes': total, 'md5': md.hexdigest(), 'sha256': sha.hexdigest()}
        if back != identity:
            raise StageFailure('readback_hash_or_length_mismatch')
        if file_stamp(source) != stamp:
            raise StageFailure('source_changed')
        result.update(readback=back, verification_complete=True, phase='verified', status='verified_simulation')
    except StageFailure as exc:
        result['reason'] = safe_reason(exc.code)
    except InputProblem as exc:
        result['reason'] = safe_reason(exc.code)
    except Exception:
        # Arbitrary injected exceptions may contain tokens or signed URLs. Never stringify.
        result['reason'] = 'adapter_or_local_io_failure'
    finally:
        if source is not None:
            try:
                source.close()
            except Exception:
                result['reason'] = result['reason'] or 'source_close_failure'
        if started:
            try:
                result['stop_confirmed'] = transport.stop() is True
            except Exception:
                result['stop_confirmed'] = False
            if not result['stop_confirmed']:
                result.update(reason=result['reason'] or 'adapter_stop_unconfirmed', status='manual_review')
        if result['reason'] is None and result['verification_complete'] and result['stop_confirmed']:
            result['simulated_delivery_eligible'] = True
        else:
            result['status'] = 'manual_review'
            result['simulated_delivery_eligible'] = False
        if record is not None:
            try:
                result['state_persisted'] = True
                record.save(result, 'readback' if guard.stage == 2 else 'upload')
            except Exception:
                result.update(state_persisted=False, status='manual_review',
                              reason=result['reason'] or 'job_state_not_persisted',
                              state_error='job_state_not_persisted', simulated_delivery_eligible=False)
    return result

"""Single-task disk admission/checkpoints. No file deletion, network, or credentials."""
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from .intake import InputProblem, safe_name

RESERVE = 5 * 1024**3
MARGIN = 256 * 1024**2
SOURCE_OVERHEAD = 1024**2  # Bounded local receipt allowance, not a backend estimate.
STAGES = ('download', 'upload', 'readback')
RESOURCES = ('source', 'source_extra', 'cache', 'backend_extra', 'readback')


class SpaceProblem(InputProblem):
    def __init__(self, code, report=None):
        super().__init__(code, 'manual_review')
        self.report = report


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise SpaceProblem('invalid_space_requirement')
    return value


def rounded(value, quantum):
    return ((value + quantum - 1) // quantum) * quantum


@dataclass(frozen=True)
class BackendNeeds:
    name: str
    source_overhead_bytes: int | None = None
    upload_temp_bytes: int | None = None
    readback_temp_bytes: int | None = None
    readback_mode: str | None = None

    @classmethod
    def source_only(cls, source_overhead_bytes=SOURCE_OVERHEAD):
        return cls('source-only', source_overhead_bytes)

    def validate(self):
        if self.name not in ('source-only', 'openlist', 'direct-api'):
            raise SpaceProblem('unknown_backend_requirements')
        if self.source_overhead_bytes is None:
            raise SpaceProblem('unknown_source_overhead')
        integer(self.source_overhead_bytes)
        if self.name == 'source-only':
            if any(x is not None for x in (self.upload_temp_bytes, self.readback_temp_bytes, self.readback_mode)):
                raise SpaceProblem('inapplicable_backend_requirements')
            return
        if self.upload_temp_bytes is None or self.readback_temp_bytes is None:
            raise SpaceProblem('unknown_backend_overhead')
        integer(self.upload_temp_bytes)
        integer(self.readback_temp_bytes)
        if self.readback_mode not in ('stream', 'file'):
            raise SpaceProblem('unknown_readback_storage_mode')


@dataclass(frozen=True)
class Volume:
    device: int
    inode: int
    free: int
    quantum: int


@dataclass(frozen=True)
class Allocation:
    device: int
    inode: int
    size: int
    allocated: int


class DiskProbe:
    def directory(self, path, writable=False):
        try:
            # Require the exact existing directory. Never infer a missing mount from its parent.
            if '..' in path.parts or path.absolute() != path.resolve(strict=True):
                raise SpaceProblem('unsafe_space_path')
            s = path.stat()
            if not stat.S_ISDIR(s.st_mode) or (writable and not os.access(path, os.W_OK | os.X_OK)):
                raise SpaceProblem('unusable_space_directory')
            fs = os.statvfs(path)
            if writable and fs.f_flag & os.ST_RDONLY:
                raise SpaceProblem('unusable_space_directory')
            return Volume(s.st_dev, s.st_ino, shutil.disk_usage(path).free, max(fs.f_frsize, 1))
        except (OSError, RuntimeError):
            raise SpaceProblem('space_path_unavailable') from None

    def file(self, path):
        self.directory(path.parent)
        try:
            s = path.lstat()
        except FileNotFoundError:
            return None
        except OSError:
            raise SpaceProblem('space_file_unavailable') from None
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or not hasattr(s, 'st_blocks'):
            raise SpaceProblem('unsafe_or_unknown_space_file')
        return Allocation(s.st_dev, s.st_ino, s.st_size, s.st_blocks * 512)


def preflight_workspace(parent, backend_dir=None):
    """Before creating a fresh child workspace, protect each existing filesystem.

    This preliminary floor check does not replace admission using the actual new
    directory. The caller intentionally creates one child, not a missing mount tree.
    """
    probe = DiskProbe()
    for path in [Path(parent).absolute(), Path('/')] + ([Path(backend_dir).absolute()] if backend_dir is not None else []):
        volume = probe.directory(path, writable=path != Path('/'))
        if volume.free < RESERVE + MARGIN + SOURCE_OVERHEAD:
            raise SpaceProblem('space_workspace_reserve')


class SpaceGuard:
    """Retained source batch plus one sequential backend file, with future-stage admission.

    All extra-file lists are task-owned, explicitly registered paths. Their physical
    allocation counts against a phase cap, including retained files from earlier phases.
    Checks are cooperative, not a filesystem quota or a background process monitor.
    """
    def __init__(self, sources, source_dir, needs, backend_dir=None, *,
                 source_extra_files=(), cache_files=(), backend_extra_files=(),
                 readback_files=(), reserve=RESERVE, margin=MARGIN, probe=None,
                 expected_layout='auto'):
        needs.validate()
        integer(reserve, RESERVE)
        integer(margin, MARGIN)
        if not isinstance(sources, dict) or not sources:
            raise SpaceProblem('invalid_space_sources')
        self.sources = {safe_name(k): integer(v, 1) for k, v in sources.items()}
        self.needs, self.reserve, self.margin = needs, reserve, margin
        self.probe = probe or DiskProbe()
        self.roots = {'source': Path(source_dir).absolute(), 'system': Path('/')}
        if needs.name != 'source-only':
            if backend_dir is None:
                raise SpaceProblem('backend_directory_required')
            self.roots['backend'] = Path(backend_dir).absolute()
        elif backend_dir is not None or cache_files or backend_extra_files or readback_files:
            raise SpaceProblem('inapplicable_backend_directory')
        self.anchors = {role: self.probe.directory(p, writable=role != 'system')
                        for role, p in self.roots.items()}
        if expected_layout not in ('auto', 'same', 'separate'):
            raise SpaceProblem('invalid_space_layout')
        if expected_layout != 'auto':
            if 'backend' not in self.anchors:
                raise SpaceProblem('inapplicable_space_layout')
            same = self.anchors['source'].device == self.anchors['backend'].device
            if same != (expected_layout == 'same'):
                raise SpaceProblem('space_layout_mismatch')
        self.files = {r: [] for r in RESOURCES}
        self.parents = {}
        self.stage = 0
        for name in self.sources:
            self.register('source', self.roots['source'] / name)
        for resource, files in [('source_extra', source_extra_files), ('cache', cache_files),
                                ('backend_extra', backend_extra_files), ('readback', readback_files)]:
            for path in files:
                self.register(resource, path)

    def role(self, resource):
        return 'source' if resource in ('source', 'source_extra') else 'backend'

    def register(self, resource, path):
        if resource not in RESOURCES or self.role(resource) not in self.roots:
            raise SpaceProblem('invalid_space_resource')
        path = Path(path).absolute()
        try:
            relative = path.relative_to(self.roots[self.role(resource)])
        except ValueError:
            raise SpaceProblem('space_file_outside_task_root') from None
        if not relative.parts or '..' in relative.parts or any(path in xs for xs in self.files.values()):
            raise SpaceProblem('duplicate_or_invalid_space_file')
        parent = self.probe.directory(path.parent, writable=True)
        if parent.device != self.anchors[self.role(resource)].device:
            raise SpaceProblem('space_file_parent_device_mismatch')
        old = self.parents.get(path.parent)
        if old is not None and (parent.device, parent.inode, parent.quantum) != (old.device, old.inode, old.quantum):
            raise SpaceProblem('space_file_parent_changed')
        self.parents[path.parent] = parent
        self.files[resource].append(path)

    def require_source(self, path, size):
        p = Path(path).absolute()
        if p.parent != self.roots['source'] or self.sources.get(p.name) != size:
            raise SpaceProblem('space_source_plan_mismatch')

    def goals(self, stage, volumes):
        sq = volumes['source'].quantum
        goals = dict.fromkeys(RESOURCES, 0)
        goals['source'] = sum(rounded(n, sq) for n in self.sources.values())
        goals['source_extra'] = rounded(self.needs.source_overhead_bytes, sq)
        if self.needs.name != 'source-only' and stage != 'download':
            bq = volumes['backend'].quantum
            # Retain cache capacity through readback; do not assume automatic cache cleanup.
            goals['cache'] = rounded(max(self.sources.values()), bq) if self.needs.name == 'openlist' else 0
            cap = self.needs.upload_temp_bytes if stage == 'upload' else self.needs.readback_temp_bytes
            goals['backend_extra'] = rounded(cap, bq)
            if stage == 'readback' and self.needs.readback_mode == 'file':
                goals['readback'] = rounded(max(self.sources.values()), bq)
        return goals

    def check(self, stage='download', *, growth=None):
        """Check now and all planned future stages; growth is a pre-write upper bound.

        For source/cache/readback payloads growth means appended logical bytes (0
        for overwriting already preallocated extents). For extras it means potential
        additional physical allocation; include block rounding. Never a progress %.
        """
        if stage not in STAGES or (self.needs.name == 'source-only' and stage != 'download'):
            raise SpaceProblem('invalid_space_stage')
        index = STAGES.index(stage)
        if index < self.stage:
            raise SpaceProblem('space_stage_regression')
        growth = growth or {}
        if set(growth) - set(RESOURCES):
            raise SpaceProblem('invalid_space_resource')
        for n in growth.values():
            integer(n)
        volumes = {role: self.probe.directory(p, writable=role != 'system')
                   for role, p in self.roots.items()}
        for role, v in volumes.items():
            old = self.anchors[role]
            if (v.device, v.inode, v.quantum) != (old.device, old.inode, old.quantum):
                raise SpaceProblem('space_directory_changed')
        for path, old in self.parents.items():
            v = self.probe.directory(path, writable=True)
            if (v.device, v.inode, v.quantum) != (old.device, old.inode, old.quantum):
                raise SpaceProblem('space_file_parent_changed')
        used = dict.fromkeys(RESOURCES, 0)
        logical = dict.fromkeys(RESOURCES, 0)
        identities = set()
        for resource, paths in self.files.items():
            volume = volumes.get(self.role(resource))
            for path in paths:
                a = self.probe.file(path)
                if a is None:
                    continue
                if a.device != volume.device or (a.device, a.inode) in identities:
                    raise SpaceProblem('space_file_device_or_alias_changed')
                identities.add((a.device, a.inode))
                if resource == 'source' and a.size > self.sources[path.name]:
                    raise SpaceProblem('source_exceeds_space_plan')
                logical[resource] += a.size
                if resource == 'source':
                    # One file's preallocation must never pay for another missing file.
                    used[resource] += min(a.allocated, rounded(self.sources[path.name], volume.quantum))
                elif resource in ('cache', 'readback'):
                    used[resource] += min(a.allocated, rounded(a.size, volume.quantum))
                else:
                    used[resource] += a.allocated
        if stage != 'download' and logical['source'] != sum(self.sources.values()):
            raise SpaceProblem('source_not_complete_for_stage')
        current = self.goals(stage, volumes)
        for resource in RESOURCES:
            q = volumes[self.role(resource)].quantum if self.role(resource) in volumes else 1
            if resource in ('source', 'cache', 'readback'):
                limit = sum(self.sources.values()) if resource == 'source' else (
                    max(self.sources.values()) if current[resource] else 0)
                if logical[resource] + growth.get(resource, 0) > limit:
                    raise SpaceProblem('payload_exceeds_space_plan')
            elif used[resource] + rounded(growth.get(resource, 0), q) > current[resource]:
                raise SpaceProblem('temporary_overhead_exceeds_plan')
        devices = {}
        for role, v in volumes.items():
            row = devices.setdefault(v.device, {'roles': [], 'free_bytes': v.free, 'remaining_bytes': 0})
            row['roles'].append(role)
            row['free_bytes'] = min(row['free_bytes'], v.free)
        stages = STAGES[index:] if self.needs.name != 'source-only' else ('download',)
        for future in stages:
            per_device = dict.fromkeys(devices, 0)
            goals = self.goals(future, volumes)
            for resource, goal in goals.items():
                if goal:
                    device = volumes[self.role(resource)].device
                    per_device[device] += max(goal - used[resource], 0)
            # Merge simultaneous resources on a device FIRST, then take the phase maximum.
            for device, n in per_device.items():
                devices[device]['remaining_bytes'] = max(devices[device]['remaining_bytes'], n)
        rows = list(devices.values())
        for row in rows:
            row['required_free_bytes'] = row['remaining_bytes'] + self.reserve + self.margin
        report = {'backend': self.needs.name, 'stage': stage, 'planned_stages': list(stages),
                  'reserve_bytes': self.reserve, 'margin_bytes': self.margin, 'volumes': rows,
                  'requirements': {'source_overhead_bytes': self.needs.source_overhead_bytes,
                                   'upload_temp_bytes': self.needs.upload_temp_bytes,
                                   'readback_temp_bytes': self.needs.readback_temp_bytes,
                                   'readback_mode': self.needs.readback_mode},
                  'assurance': 'cooperative_checkpoints_only'}
        if any(row['free_bytes'] < row['required_free_bytes'] for row in rows):
            raise SpaceProblem('disk_budget_exceeded', report)
        self.stage = index
        return report

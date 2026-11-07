"""Deterministic in-memory fake. Not a Baidu client and never opens a socket."""
import hashlib
from dataclasses import dataclass, field

from .upload_stage import StageFailure, MAX_SIMULATION_BYTES


@dataclass
class Session:
    path: str
    size: int
    hashes: tuple
    parts: dict = field(default_factory=dict)


class MemoryCloud:
    mode = 'simulation'

    def __init__(self, app_name='Xtransfer'):
        self.app_name = app_name
        self.directories, self.objects = set(), {}
        self.operations = []
        self.context, self.stopped = None, False

    def attach(self, context):
        self.context = context

    def reserve_new(self, path):
        self.operations.append('reserve')
        self.context.checkpoint()
        if path in self.directories:
            raise StageFailure('remote_target_exists')
        self.directories.add(path)

    def begin_new(self, path, size, hashes):
        self.operations.append('begin')
        self.context.checkpoint()
        if path in self.objects or size > MAX_SIMULATION_BYTES:
            raise StageFailure('remote_target_exists_or_simulation_limit')
        return Session(path, size, hashes)

    def put_part(self, session, index, data):
        self.context.checkpoint()
        self.operations.append('part:'+str(index))
        if index in session.parts or hashlib.md5(data).hexdigest() != session.hashes[index]:
            raise StageFailure('simulated_part_conflict')
        if sum(map(len, session.parts.values())) + len(data) > session.size:
            raise StageFailure('simulated_payload_limit')
        session.parts[index] = data
        return hashlib.md5(data).hexdigest()

    def commit_new(self, session):
        self.context.checkpoint()
        self.operations.append('commit')
        if session.path in self.objects or set(session.parts) != set(range(len(session.hashes))):
            raise StageFailure('simulated_commit_conflict')
        data = b''.join(session.parts[i] for i in range(len(session.hashes)))
        if len(data) != session.size:
            raise StageFailure('simulated_commit_size')
        self.objects[session.path] = data
        session.parts.clear()

    def metadata(self, path):
        self.context.checkpoint()
        self.operations.append('metadata')
        return {'size': len(self.objects[path])}

    def readback(self, path, chunk_bytes):
        self.operations.append('readback')
        data = self.objects[path]
        for index in range(0, len(data), chunk_bytes):
            self.context.checkpoint()
            yield data[index:index+chunk_bytes]

    def stop(self):
        self.stopped = True
        self.operations.append('stop')
        return True

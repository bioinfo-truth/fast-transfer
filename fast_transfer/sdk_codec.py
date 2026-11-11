"""Credential-free official Go SDK request encoder; existing Python HTTP owns I/O.

The helper and guard are explicit owner-controlled hash-checked artifacts. All
helper processes are network-denied and receive only metadata plus a sealed
memfd containing one public-data part. This is not an upload authorization.
"""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import time
import urllib.parse

from .baidu_http import HTTPRequest, PART_LIMIT, fail

MAX_OUTPUT = ((PART_LIMIT+4096+2)//3)*4+65536
MAX_INPUT = 65536


def artifact(path, expected):
    path = Path(path).absolute()
    if not re.fullmatch('[0-9a-f]{64}', expected or ''):
        fail('sdk_codec_artifact_rejected')
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o022 or info.st_nlink != 1):
        fail('sdk_codec_artifact_rejected')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
            fail('sdk_codec_artifact_rejected')
    return path


class SDKRequestEncoder:
    def __init__(self, helper, helper_sha256, guard, guard_sha256, *, timeout=25):
        if type(timeout) not in (int,float) or not 0 < timeout <= 30:
            fail('sdk_codec_input_rejected')
        self.helper = artifact(helper, helper_sha256)
        self.guard = artifact(guard, guard_sha256)
        self.hashes = helper_sha256, guard_sha256
        self.timeout = timeout

    def _run(self, payload, fd=None):
        # Recheck before exec, without inspecting unrelated executables/configs.
        artifact(self.helper, self.hashes[0]);artifact(self.guard, self.hashes[1])
        raw = json.dumps(payload, separators=(',', ':')).encode()
        if len(raw) > MAX_INPUT:
            fail('sdk_codec_input_rejected')
        output = bytearray()
        process = subprocess.Popen(['/usr/bin/python3','-I','-S','-B',str(self.guard),str(self.helper)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, close_fds=True,
                                   pass_fds=() if fd is None else (fd,), env={},
                                   start_new_session=True)
        deadline = time.monotonic()+self.timeout
        try:
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
            offset = 0
            with selectors.DefaultSelector() as poll:
                poll.register(process.stdin, selectors.EVENT_WRITE)
                poll.register(process.stdout, selectors.EVENT_READ)
                while poll.get_map():
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        fail('sdk_codec_deadline')
                    for key, _ in poll.select(min(.2,remaining)):
                        if key.fileobj is process.stdin:
                            try:n = os.write(process.stdin.fileno(),raw[offset:offset+8192])
                            except BrokenPipeError:fail('sdk_codec_failed')
                            offset += n
                            if offset == len(raw):
                                poll.unregister(process.stdin);process.stdin.close()
                        else:
                            chunk = os.read(process.stdout.fileno(),min(65536,MAX_OUTPUT-len(output)+1))
                            if not chunk:
                                poll.unregister(process.stdout);process.stdout.close()
                            else:
                                output.extend(chunk)
                                if len(output) > MAX_OUTPUT:
                                    fail('sdk_codec_output_rejected')
            if process.wait(timeout=max(.001,deadline-time.monotonic())) != 0:
                fail('sdk_codec_failed')
            def unique(pairs):
                out = {}
                for key, value in pairs:
                    if key in out:fail('sdk_codec_output_rejected')
                    out[key] = value
                return out
            obj = json.loads(output, object_pairs_hook=unique)
            if type(obj) is not dict or set(obj) != {'method','url','params','body','content_type'}:
                fail('sdk_codec_output_rejected')
            if type(obj['body']) is not str:
                fail('sdk_codec_output_rejected')
            obj['body'] = base64.b64decode(obj['body'], validate=True)
            return obj
        except (ValueError,TypeError,subprocess.TimeoutExpired):
            fail('sdk_codec_output_rejected')
        finally:
            if process.poll() is None:
                process.kill();process.wait()
            for pipe in (process.stdin,process.stdout):
                if not pipe.closed:pipe.close()

    @staticmethod
    def _request(obj, target, url, params, purpose):
        if (obj['method'] != 'POST' or obj['url'] != url
                or obj['params'] != {k:str(v) for k,v in params.items()}):
            fail('sdk_codec_binding_mismatch')
        req = HTTPRequest('POST',url,target,purpose,obj['params'],obj['body'],obj['content_type'])
        req.validate()
        return req

    def control(self, url, target, params, form):
        if type(form) is not dict or type(params) is not dict or set(params) != {'method'}:
            fail('sdk_codec_input_rejected')
        operation = params['method']
        values = {'operation':operation,'target':target}
        if operation == 'create' and form.get('isdir') == 1:
            if form != {'path':target.rsplit('/',1)[0],'isdir':1,'rtype':0}:
                fail('sdk_codec_input_rejected')
            values['operation'] = 'directory'
        elif operation in ('precreate','create'):
            expected = {'path','size','isdir','rtype','block_list'}
            if operation == 'precreate':expected.add('autoinit')
            else:expected.update(('uploadid','is_revision'))
            if (set(form) != expected or form['path'] != target or form['isdir'] != 0
                    or form['rtype'] != 1 or operation == 'precreate' and form['autoinit'] != 1
                    or operation == 'create' and form['is_revision'] != 0):
                fail('sdk_codec_input_rejected')
            try:
                hashes = json.loads(form['block_list'])
            except (ValueError,TypeError):
                fail('sdk_codec_input_rejected')
            values.update(operation='precreate' if operation=='precreate' else 'commit',
                          size=form['size'],hashes=hashes)
            if operation == 'create':values['uploadid']=form['uploadid']
        else:
            fail('sdk_codec_input_rejected')
        obj = self._run(values)
        req = self._request(obj,target,url,params,'control')
        if req.content_type != 'application/x-www-form-urlencoded':
            fail('sdk_codec_binding_mismatch')
        try:
            pairs = urllib.parse.parse_qsl(req.body.decode('ascii'),strict_parsing=True)
        except (ValueError,UnicodeError):
            fail('sdk_codec_binding_mismatch')
        if len(pairs) != len(dict(pairs)) or dict(pairs) != {k:str(v) for k,v in form.items()}:
            fail('sdk_codec_binding_mismatch')
        return req

    @staticmethod
    def memory_admission_bytes(part_bytes):
        """Conservative admission estimate, not a measured or hard RSS limit."""
        if type(part_bytes) is not int or not 0 < part_bytes <= PART_LIMIT:
            fail('sdk_codec_input_rejected')
        # SDK buffer, Go capture/JSON, Python JSON/base64/body and sealed memfd.
        return 16*part_bytes+128*1024**2

    @staticmethod
    def available_memory():
        try:
            lines = Path('/proc/meminfo').read_text().splitlines()
            value = next(line.split()[1] for line in lines if line.startswith('MemAvailable:'))
            available = int(value)*1024
            limit_file = Path('/sys/fs/cgroup/memory.max')
            if limit_file.is_file():
                limit = limit_file.read_text().strip()
                if limit != 'max':
                    current = int(Path('/sys/fs/cgroup/memory.current').read_text().strip())
                    available = min(available,max(0,int(limit)-current))
            if available < 0:fail('sdk_codec_memory_unknown')
            return available
        except (OSError,ValueError,StopIteration):
            fail('sdk_codec_memory_unknown')

    def part(self, target, host, uploadid, index, data):
        if type(data) is not bytes or not 0 < len(data) <= PART_LIMIT:
            fail('sdk_codec_input_rejected')
        if self.available_memory() < self.memory_admission_bytes(len(data))+128*1024**2:
            fail('sdk_codec_memory_budget')
        u = urllib.parse.urlsplit(host)
        if u.scheme != 'https' or u.path or u.query or u.fragment or u.username or u.port:
            fail('sdk_codec_input_rejected')
        fd = os.memfd_create('fast-transfer-part',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
        try:
            with os.fdopen(os.dup(fd),'wb') as stream:stream.write(data);stream.flush()
            os.lseek(fd,0,os.SEEK_SET)
            fcntl.fcntl(fd,fcntl.F_ADD_SEALS,fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL)
            obj = self._run({'operation':'part','target':target,'host':u.hostname,
                             'uploadid':uploadid,'part':index,'source_fd':fd,
                             'part_bytes':len(data),'part_md5':hashlib.md5(data).hexdigest()},fd)
        finally:
            os.close(fd)
        params = {'method':'upload','type':'tmpfile','path':target,'uploadid':uploadid,'partseq':index}
        req = self._request(obj,target,host+'/rest/2.0/pcs/superfile2',params,'upload')
        match = re.fullmatch('multipart/form-data; boundary=([0-9a-f]{60})',req.content_type)
        if not match:fail('sdk_codec_binding_mismatch')
        boundary = match[1]
        prefix = ('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="file"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
        suffix = ('\r\n--'+boundary+'--\r\n').encode()
        if (len(req.body) != len(prefix)+len(data)+len(suffix)
                or not req.body.startswith(prefix) or not req.body.endswith(suffix)
                or memoryview(req.body)[len(prefix):-len(suffix)] != data):
            fail('sdk_codec_binding_mismatch')
        return req

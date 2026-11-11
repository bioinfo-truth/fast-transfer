"""Synthetic subprocess fault boundaries; no live backend or credential support."""
import errno
import json
import os
from pathlib import Path
import socket
import stat
import sys
import time

# Invoked with -I -S and explicit clean env. The test runner's seccomp is inherited.
try:
    socket.socket()
except OSError as exc:
    assert exc.errno == errno.EPERM
else:
    raise AssertionError('kernel_network_guard_missing')
assert not list(Path(os.environ['HOME']).iterdir())
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fast_transfer import workflow as w
from unittest.mock import patch
root=Path(sys.argv[1]);mode=sys.argv[2]
j=w.Job(root/'jobs','job-process')
manifest=json.loads((root/'manifest.json').read_text())

def barrier():
    print('READY',flush=True)
    while True: time.sleep(1)

def backend(*args, **kwargs):
    with (root/'backend-calls').open('ab') as f:
        f.write(b'call\n');f.flush();os.fsync(f.fileno())
    if mode=='during_backend':barrier()
    return {'status':'unknown','mutation_outcome_unknown':True,'reason':'http_io_failure'}

if mode=='diagnose':
    sys.argv=['workflow','--jobs-dir',str(root/'jobs'),'--job-id','job-process','diagnose']
    raise SystemExit(w.main())
if mode=='create':j.create(manifest)
elif mode=='hold_lock':
    with j.locked():barrier()
else:
    save=j.save
    def fault_save(state):
        intent=state['phase']=='simulation_running'
        if intent and mode=='before_intent':barrier()
        if not intent and mode=='after_backend':barrier()
        result=save(state)
        if intent and mode=='after_intent':barrier()
        return result
    original_fsync=w.os.fsync
    original_replace=w.os.replace
    def fsync(fd):
        if mode=='directory_fsync_failure' and stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EIO,'synthetic')
        if mode=='terminal_fsync_failure' and (root/'backend-calls').exists():
            raise OSError(errno.ENOSPC,'synthetic')
        if mode=='write_failure':raise OSError(errno.ENOSPC,'synthetic')
        if mode=='during_new':barrier()
        return original_fsync(fd)
    def replace(*args):
        if mode=='replace_failure':raise OSError(errno.EIO,'synthetic')
        result=original_replace(*args)
        if mode=='after_replace':barrier()
        return result
    with patch.object(j,'save',fault_save),patch.object(w,'run_simulated_upload',backend),patch.object(w.os,'fsync',fsync),patch.object(w.os,'replace',replace):
        try:j.simulate(manifest,root/'source',root/'backend')
        except w.InputProblem as exc:print(json.dumps({'reason':exc.code}),flush=True)
        except OSError:print(json.dumps({'reason':'injected_io_failure'}),flush=True)
        except (ValueError,TypeError,KeyError):print(json.dumps({'reason':'invalid_local_record'}),flush=True)

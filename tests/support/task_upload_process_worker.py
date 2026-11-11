"""Fresh-process SDK uploader against persisted synthetic cloud state, never live."""
import base64
import json
import os
from pathlib import Path
import signal
import sys

repo=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(repo),str(repo/'tests')]
from test_task_upload import Cloud, MemoryAPI, ACCOUNT
from test_sdk_codec import HELPER, sha
from fast_transfer.sdk_codec import SDKRequestEncoder
from fast_transfer.task import Task
from fast_transfer.task_upload import TaskProtocol, run_next, PauseSignal
from fast_transfer.task_inspect import inspect_commit


def pack(value):
    if isinstance(value,bytes):return {'__fixture_bytes__':base64.b64encode(value).decode('ascii')}
    if isinstance(value,dict):return {str(k):pack(v) for k,v in value.items()}
    if isinstance(value,list):return [pack(v) for v in value]
    return value


def unpack(value):
    if isinstance(value,dict):
        if set(value)=={'__fixture_bytes__'}:return base64.b64decode(value['__fixture_bytes__'],validate=True)
        return {k:unpack(v) for k,v in value.items()}
    if isinstance(value,list):return [unpack(v) for v in value]
    return value


def load_cloud(path):
    state=unpack(json.loads(Path(path).read_text()))
    cloud=Cloud({});cloud.__dict__.update(state)
    cloud.rows={int(k):v for k,v in cloud.rows.items()}
    for session in cloud.sessions.values():session['parts']={int(k):v for k,v in session['parts'].items()}
    return cloud


def save_cloud(cloud,path):
    path=Path(path);temporary=path.with_suffix('.next')
    with temporary.open('w') as stream:
        json.dump(pack(cloud.__dict__),stream,separators=(',',':'));stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def main():
    parent,job,guard_path,snapshot,checkpoint,result_path,proof_path=sys.argv[1:]
    cloud=load_cloud(snapshot);task=Task(parent,job)
    codec=SDKRequestEncoder(HELPER,sha(HELPER),Path(guard_path),sha(Path(guard_path)))
    requested=PauseSignal()
    def pause():
        print('READY',flush=True)
        while True:signal.pause()
    class PersistentAPI(MemoryAPI):
        def exchange(self,req):
            reply=super().exchange(req);save_cloud(cloud,snapshot)
            if checkpoint=='graceful-part' and req.purpose=='upload':
                print('READY',flush=True)
                while not requested.requested:signal.pause()
            if checkpoint=='unknown-commit' and req.method=='POST' and req.params.get('method')=='create':
                form=dict(__import__('urllib.parse',fromlist=['parse_qsl']).parse_qsl(req.body.decode()))
                if form.get('isdir')=='0':pause()
            return reply
    def factory(target,identity,limits,app):
        return TaskProtocol(PersistentAPI(cloud),app,target,ACCOUNT,limits,codec,test_mode=True)
    def hook(operation,part):
        if checkpoint==operation+':'+str(part):pause()
    if checkpoint=='inspect':
        result=inspect_commit(task,factory,ACCOUNT,proof_path,approved_task_spec_sha256=task.view()['task_spec_sha256'])
    else:
        with requested:
            result=run_next(task,factory,ACCOUNT,checkpoint_hook=hook,pause_requested=lambda:requested.requested)
    save_cloud(cloud,snapshot);Path(result_path).write_text(json.dumps(result))


if __name__=='__main__':main()

"""Build a local immutable MVP runtime archive from a clean tracked revision.

No credential reads, dependencies fetched, or network calls. The SDK encoder
must already have been built from the pinned integration and reviewed.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

repo=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--helper',type=Path,required=True)
p.add_argument('--sdk-license',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=repo):
    raise SystemExit('tracked_worktree_must_be_clean')
revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
tracked=subprocess.check_output(['git','ls-files','fast_transfer','examples/ncbi-ecoli-protein','scripts/baidu-sdk-codec-guard.py'],cwd=repo,text=True).splitlines()
files={name:((repo/name).read_bytes(),0o600) for name in tracked if name.endswith(('.py','.json','.md','.txt'))}
files['bin/ft-sdk-codec']=(a.helper.read_bytes(),0o500)
files['licenses/baidu-drive-sdk-go-LICENSE']=(a.sdk_license.read_bytes(),0o600)
files['third_party/baidupcs-go/LICENSE']=((repo/'third_party/baidupcs-go/LICENSE').read_bytes(),0o600)
files['licenses/SDK-SOURCE.txt']=(b'github.com/baidu-netdisk/baidu-drive-sdk-go\ncommit 472e4a1b111eac1d6307e38802f8fe7adf7e8c21\nSDK request encoder; Apache-2.0.\n',0o600)
launcher='''"""Use /usr/bin/python3 -I -S -B launcher.py COMMAND [arguments]."""
import os,resource,runpy,sys
from pathlib import Path
os.umask(0o077);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
allowed={'task','task_upload','task_handoff','task_cleanup','delivery','task_delivery','intake'}
if len(sys.argv)<2 or sys.argv[1] not in allowed:raise SystemExit('unsupported_command')
command=sys.argv.pop(1);sys.path.insert(0,str(Path(__file__).resolve().parent))
runpy.run_module('fast_transfer.'+command,run_name='__main__')
'''
files['launcher.py']=(launcher.encode(),0o600)
manifest={'schema':'fast-transfer-release-v1','revision':revision,'architecture':'linux-amd64',
          'sdk_commit':'472e4a1b111eac1d6307e38802f8fe7adf7e8c21',
          'files':{name:{'sha256':hashlib.sha256(data).hexdigest(),'mode':mode} for name,(data,mode) in sorted(files.items())}}
files['release.json']=((json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode(),0o600)
a.output.parent.mkdir(parents=True,exist_ok=True)
fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'wb') as stream:
    with tarfile.open(fileobj=stream,mode='w:gz') as archive:
        for name,(data,mode) in sorted(files.items()):
            info=tarfile.TarInfo(name);info.mode=mode;info.size=len(data);info.mtime=0
            archive.addfile(info,io.BytesIO(data))
    stream.flush();os.fsync(stream.fileno())
print(json.dumps({'revision':revision,'archive_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'files':len(files)}))

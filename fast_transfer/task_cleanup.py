"""Delete only a verified task's local payload, with a durable local intent."""
import argparse
import json
import os
import stat
import sys
import time

from .intake import InputProblem
from .task import Task, encoded, fail, private_directory, read_json
from .task_handoff import verified_receipt
from .upload_stage import StageFailure, file_stamp, source_identity


def cleanup_file(task, index, *, checkpoint_hook=None):
    if type(index) is not int or index < 0:fail('cleanup_index_invalid')
    with task.locked() as db:
        manifest,settings,rows=task.context(db)
        row=next((r for r in rows if r['idx']==index),None)
        if row is None or row['phase'] not in ('cloud_verified','cleaned'):
            fail('cleanup_real_verification_required')
        if db.execute("SELECT 1 FROM operations WHERE outcome='unknown'").fetchone():
            fail('cleanup_unknown_operation')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'upload_context','verifications'}<=tables:fail('cleanup_real_verification_required')
        binding=db.execute('SELECT kind FROM upload_context WHERE id=1').fetchone()
        if binding is None or binding['kind']!='official-api':fail('cleanup_real_verification_required')
        receipt=verified_receipt(task,db,manifest,settings,row)
        private_directory(task.root/'files');folder=private_directory(task.file_root(index))
        name=manifest['files'][index]['name']
        directory=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            db.execute('CREATE TABLE IF NOT EXISTS local_cleanups(idx INTEGER PRIMARY KEY, stamp TEXT NOT NULL, completed INTEGER)')
            db.commit()
            record=db.execute('SELECT * FROM local_cleanups WHERE idx=?',(index,)).fetchone()
            try:current=os.stat(name,dir_fd=directory,follow_symlinks=False)
            except FileNotFoundError:current=None
            if current is None:
                if record is None:fail('cleanup_missing_without_intent')
                # A saved intent proves which payload was selected before unlink.
                saved=read_json(record['stamp'])
                if not isinstance(saved,list) or len(saved)!=5 or saved[2]!=receipt['bytes']:
                    fail('cleanup_intent_invalid')
                os.fsync(directory)
            else:
                if row['phase']=='cleaned' or (record is not None and record['completed'] is not None):
                    fail('cleanup_payload_reappeared')
                if (not stat.S_ISREG(current.st_mode) or current.st_nlink!=1
                        or current.st_uid!=os.geteuid()):fail('cleanup_unsafe_payload')
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
                with os.fdopen(fd,'rb') as source:
                    identity,_,stamp=source_identity(source,lambda:None,settings['part_bytes'],receipt['bytes'])
                    if any(identity[k]!=receipt[k] for k in ('bytes','md5','sha256')):
                        fail('cleanup_source_changed')
                    if record is not None and read_json(record['stamp'])!=list(stamp):
                        fail('cleanup_source_changed')
                    if record is None:
                        with db:db.execute('INSERT INTO local_cleanups VALUES(?,?,NULL)',(index,encoded(list(stamp))))
                    if checkpoint_hook:checkpoint_hook('intent_saved')
                    current=os.stat(name,dir_fd=directory,follow_symlinks=False)
                    actual=(current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns)
                    if actual!=stamp or file_stamp(source)!=stamp or current.st_nlink!=1:
                        fail('cleanup_source_changed')
                    os.unlink(name,dir_fd=directory)
                    os.fsync(directory)
                    if checkpoint_hook:checkpoint_hook('payload_removed')
            with db:
                db.execute('UPDATE local_cleanups SET completed=? WHERE idx=?',(int(time.time()),index))
                db.execute("UPDATE files SET phase='cleaned',reason=NULL WHERE idx=?",(index,))
            return {'status':'cleaned','index':index,'bytes':receipt['bytes'],'cloud_deleted':False,'delivered':False}
        finally:os.close(directory)


def main(argv=None):
    p=argparse.ArgumentParser(description='Remove one verified local task payload; retain all receipts and cloud objects.')
    p.add_argument('--tasks-dir',required=True);p.add_argument('job_id');p.add_argument('--index',type=int,required=True)
    a=p.parse_args(argv)
    try:result=cleanup_file(Task(a.tasks_dir,a.job_id),a.index)
    except (InputProblem,StageFailure) as exc:
        print(json.dumps({'status':'manual_review','reason':exc.code}));return 2
    except Exception:
        print(json.dumps({'status':'manual_review','reason':'cleanup_local_failure'}));return 2
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':sys.exit(main())

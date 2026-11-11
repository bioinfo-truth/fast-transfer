"""Bounded observational Linux RSS/disk sampling; never credentials or argv.

Sampling is evidence, not a resource limit or an exact peak measurement.
"""
import os
from pathlib import Path
import shutil
import threading
import time


class ResourceSamples:
    def __init__(self, root, *, interval=.05):
        if type(interval) not in (int,float) or not .02<=interval<=1:
            raise ValueError('invalid_sampling_interval')
        self.root=Path(root);self.interval=interval;self.pid=os.getpid()
        self.count=0;self.errors=0;self.minimum_free=None;self.peak_self=0;self.peak_tree=0
        self.truncated=False;self.began=None;self.ended=None
        self.event=threading.Event();self.thread=threading.Thread(target=self.loop,daemon=True)

    def rss_tree(self):
        queue=[(self.pid,None)];seen=set();total=own=0
        while queue:
            pid,parent=queue.pop()
            if pid in seen:continue
            if len(seen)>=64:self.truncated=True;break
            seen.add(pid)
            try:
                fields={}
                for line in Path('/proc',str(pid),'status').read_text().splitlines():
                    if line.startswith(('PPid:','VmRSS:')):fields[line.split(':',1)[0]]=int(line.split()[1])
                if parent is not None and fields.get('PPid')!=parent:continue
                rss=fields.get('VmRSS',0);total+=rss
                if pid==self.pid:own=rss
                children=Path('/proc',str(pid),'task',str(pid),'children').read_text().split()
                queue.extend((int(child),pid) for child in children)
            except FileNotFoundError:continue  # A short-lived helper can exit between reads.
        return own,total

    def sample(self):
        free=shutil.disk_usage(self.root).free
        own,total=self.rss_tree()
        self.minimum_free=free if self.minimum_free is None else min(self.minimum_free,free)
        self.peak_self=max(self.peak_self,own);self.peak_tree=max(self.peak_tree,total);self.count+=1

    def try_sample(self):
        try:self.sample()
        except (OSError,ValueError):self.errors+=1

    def loop(self):
        while not self.event.wait(self.interval):self.try_sample()

    def __enter__(self):
        self.began=time.monotonic();self.try_sample();self.thread.start();return self

    def __exit__(self,*ignored):
        self.event.set();self.thread.join(1)
        if not self.thread.is_alive():self.try_sample()
        self.ended=time.monotonic()

    def summary(self):
        stopped=self.ended is not None and not self.thread.is_alive()
        return {'schema':'fast-transfer-resource-samples-v1','samples':self.count,'sample_errors':self.errors,
                'interval_seconds':self.interval,'elapsed_seconds':round((self.ended or time.monotonic())-self.began,6),
                'minimum_sampled_free_bytes':self.minimum_free,'peak_sampled_self_rss_kib':self.peak_self,
                'peak_sampled_process_tree_rss_kib':self.peak_tree,'process_tree_truncated':self.truncated,
                'sampler_stopped':stopped,'complete':stopped and self.count>0 and self.errors==0 and not self.truncated,
                'measurement':'periodic-rss-sum-may-double-count-shared-pages-and-miss-peaks'}

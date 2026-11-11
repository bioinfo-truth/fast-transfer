"""Actual bounded sampling of temporary storage and one synthetic child."""
import json
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fast_transfer.resources import ResourceSamples


class ResourceTests(unittest.TestCase):
    def test_live_child_allocation_is_in_process_tree_and_sampler_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            child=subprocess.Popen([sys.executable,'-I','-S','-B','-c',
                                    'import sys;data=bytearray(24*1024**2);print("READY",flush=True);sys.stdin.readline()'],
                                   stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={})
            try:
                ready,_,_=select.select([child.stdout],[],[],10);self.assertTrue(ready)
                self.assertEqual(child.stdout.readline(),b'READY\n')
                with ResourceSamples(folder) as samples:samples.sample()
                result=samples.summary()
                self.assertTrue(result['sampler_stopped']);self.assertTrue(result['complete'])
                self.assertGreaterEqual(result['peak_sampled_process_tree_rss_kib'],result['peak_sampled_self_rss_kib']+16*1024)
                self.assertGreater(result['minimum_sampled_free_bytes'],0)
                self.assertNotIn(folder,json.dumps(result));self.assertNotIn('READY',json.dumps(result))
                child.communicate(b'finish\n',timeout=10)
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=10)
                child.stdin.close();child.stdout.close();child.stderr.close()

    def test_exception_does_not_leave_sampler_running(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(KeyboardInterrupt):
                with ResourceSamples(folder) as samples:raise KeyboardInterrupt()
            self.assertTrue(samples.summary()['sampler_stopped'])

    def test_sampling_failure_is_explicit_and_not_a_resource_success_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('fast_transfer.resources.shutil.disk_usage',side_effect=OSError()):
                with ResourceSamples(folder) as samples:pass
            result=samples.summary();self.assertFalse(result['complete']);self.assertGreater(result['sample_errors'],0)
            self.assertIsNone(result['minimum_sampled_free_bytes'])

    def test_bounded_interval_validation(self):
        for interval in (0,True,2,None):
            with self.assertRaises(ValueError):ResourceSamples('/tmp',interval=interval)

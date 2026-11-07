"""Pure allocation models and tiny local fixtures; never create GB payloads."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fast_transfer.space import (Allocation, BackendNeeds, DiskProbe, SpaceGuard,
                                 SpaceProblem, Volume, RESERVE, MARGIN)

FLOOR = RESERVE + MARGIN


class Probe:
    def __init__(self, split=False):
        self.devices = {'/': 0, '/source': 1 if split else 0, '/backend': 2 if split else 0}
        self.free = {d: 100*1024**3 for d in self.devices.values()}
        self.inodes = {p: i+10 for i, p in enumerate(self.devices)}
        self.files = {}
        self.quantum = 1

    def directory(self, path, writable=False):
        key = str(path)
        if key not in self.devices:
            raise SpaceProblem('space_path_unavailable')
        d = self.devices[key]
        return Volume(d, self.inodes[key], self.free[d], self.quantum)

    def file(self, path):
        return self.files.get(str(path))

    def put(self, path, size, allocated=None, inode=None):
        path = Path(path)
        d = self.devices[str(path.parent)]
        before = self.files.get(str(path))
        allocated = size if allocated is None else allocated
        inode = inode if inode is not None else (before.inode if before else len(self.files)+100)
        self.free[d] -= allocated - (before.allocated if before else 0)
        self.files[str(path)] = Allocation(d, inode, size, allocated)


def needs(backend='openlist', mode='stream'):
    return BackendNeeds(backend, 12, 7, 11, mode)


def guard(probe, size=1000, backend='openlist', mode='stream', **kwargs):
    return SpaceGuard({'data.gz': size}, Path('/source'), needs(backend, mode),
                      Path('/backend'), probe=probe, **kwargs)


class SpaceModelTests(unittest.TestCase):
    def test_same_device_adds_resources_before_phase_max_and_reserves_once(self):
        p = Probe(); g = guard(p)
        report = g.check()
        self.assertEqual(len(report['volumes']), 1)
        row = report['volumes'][0]
        self.assertEqual(set(row['roles']), {'source', 'backend', 'system'})
        self.assertEqual(row['remaining_bytes'], 2000+12+11)
        self.assertEqual(row['required_free_bytes'], FLOOR+2023)
        p.free[0] = FLOOR+2023
        g.check()  # Exact threshold is allowed.
        p.free[0] -= 1
        with self.assertRaises(SpaceProblem) as caught:
            g.check()
        self.assertEqual(caught.exception.code, 'disk_budget_exceeded')
        self.assertEqual(caught.exception.status, 'manual_review')
        self.assertIsNotNone(caught.exception.report)

    def test_split_devices_each_get_independent_floor_and_remaining(self):
        p = Probe(split=True); g = guard(p)
        rows = {tuple(row['roles']): row for row in g.check()['volumes']}
        self.assertEqual(rows[('source',)]['required_free_bytes'], FLOOR+1012)
        self.assertEqual(rows[('backend',)]['required_free_bytes'], FLOOR+1011)
        self.assertEqual(rows[('system',)]['required_free_bytes'], FLOOR)
        for device in (0, 1, 2):
            with self.subTest(device=device):
                old = p.free[device]; p.free[device] = FLOOR-1
                with self.assertRaisesRegex(SpaceProblem, 'disk_budget'):
                    g.check()
                p.free[device] = old

    def test_expected_separate_mount_does_not_silently_fall_back_to_system_volume(self):
        with self.assertRaisesRegex(SpaceProblem, 'layout_mismatch'):
            guard(Probe(), expected_layout='separate')
        guard(Probe(split=True), expected_layout='separate').check()
        with self.assertRaisesRegex(SpaceProblem, 'layout_mismatch'):
            guard(Probe(split=True), expected_layout='same')

    def test_direct_api_has_no_full_cache_but_still_has_explicit_extras(self):
        p = Probe(); g = guard(p, backend='direct-api')
        self.assertEqual(g.check()['volumes'][0]['remaining_bytes'], 1023)
        p.put('/source/data.gz', 1000)
        self.assertEqual(g.check('upload')['volumes'][0]['remaining_bytes'], 23)
        with self.assertRaisesRegex(SpaceProblem, 'payload_exceeds'):
            g.check('upload', growth={'cache': 1})

    def test_file_readback_is_a_separate_full_copy_not_streaming(self):
        p = Probe()
        self.assertEqual(guard(p, mode='file').check()['volumes'][0]['remaining_bytes'], 3023)
        self.assertEqual(guard(p, backend='direct-api', mode='file').check()['volumes'][0]['remaining_bytes'], 2023)

    def test_downloaded_source_and_growing_cache_are_not_counted_twice(self):
        p = Probe(); p.put('/source/data.gz', 1000)
        g = guard(p, cache_files=[Path('/backend/cache')])
        self.assertEqual(g.check('upload')['volumes'][0]['remaining_bytes'], 1023)
        p.put('/backend/cache', 400)
        self.assertEqual(g.check('upload')['volumes'][0]['remaining_bytes'], 623)
        p.put('/backend/cache', 1000)
        self.assertEqual(g.check('upload')['volumes'][0]['remaining_bytes'], 23)

    def test_already_allocated_extras_are_credited_and_retained_phase_cap_enforced(self):
        p = Probe(); p.put('/source/data.gz', 1000)
        g = guard(p, source_extra_files=[Path('/source/receipt')], backend_extra_files=[Path('/backend/temp')])
        p.put('/source/receipt', 12); p.put('/backend/temp', 7)
        self.assertEqual(g.check('upload')['volumes'][0]['remaining_bytes'], 1004)
        g.check('readback')
        p.put('/backend/temp', 12)
        with self.assertRaisesRegex(SpaceProblem, 'overhead_exceeds'):
            g.check('readback')

    def test_unregistered_old_file_is_not_credited_or_deleted(self):
        p = Probe(); p.put('/backend/unrelated', 500)
        before = dict(p.files)
        g = guard(p)
        self.assertEqual(g.check()['volumes'][0]['remaining_bytes'], 2023)
        self.assertEqual(p.files, before)

    def test_sparse_cache_does_not_claim_unallocated_capacity(self):
        p = Probe(); p.put('/source/data.gz', 1000); p.put('/backend/cache', 1000, allocated=100)
        g = guard(p, cache_files=[Path('/backend/cache')])
        self.assertEqual(g.check('upload')['volumes'][0]['remaining_bytes'], 923)

    def test_block_rounding_and_existing_allocation_credit(self):
        p = Probe(); p.quantum = 4096
        g = guard(p)
        self.assertEqual(g.check()['volumes'][0]['remaining_bytes'], 4*4096)
        p.put('/source/data.gz', 1000, allocated=4096)
        self.assertEqual(g.check('upload')['volumes'][0]['remaining_bytes'], 3*4096)

    def test_lower_next_phase_cap_requires_releasing_retained_temporary_files(self):
        p = Probe(); p.put('/source/data.gz', 1000)
        profile = BackendNeeds('openlist', 12, 11, 7, 'stream')
        g = SpaceGuard({'data.gz': 1000}, '/source', profile, '/backend',
                       backend_extra_files=[Path('/backend/temp')], probe=p)
        p.put('/backend/temp', 11)
        g.check('upload')
        with self.assertRaisesRegex(SpaceProblem, 'overhead_exceeds'):
            g.check('readback')

    def test_source_only_does_not_claim_backend_stage_admission(self):
        g = SpaceGuard({'data.gz': 1000}, '/source', BackendNeeds.source_only(12), probe=Probe())
        self.assertEqual(g.check()['planned_stages'], ['download'])
        with self.assertRaisesRegex(SpaceProblem, 'invalid_space_stage'):
            g.check('upload')

    def test_batch_retains_all_sources_and_reserves_largest_backend_file(self):
        p = Probe()
        g = SpaceGuard({'big': 5000, 'small': 1000}, '/source', needs(), '/backend', probe=p)
        self.assertEqual(g.check()['volumes'][0]['remaining_bytes'], 11023)
        p.put('/source/big', 5000)
        self.assertEqual(g.check()['volumes'][0]['remaining_bytes'], 6023)
        with self.assertRaisesRegex(SpaceProblem, 'source_not_complete'):
            g.check('upload')
        p.put('/source/small', 1000)
        self.assertEqual(g.check('upload')['volumes'][0]['remaining_bytes'], 5023)

    def test_one_files_preallocation_cannot_cover_another_missing_source(self):
        p = Probe(); p.put('/source/first', 1000, allocated=10000)
        g = SpaceGuard({'first': 1000, 'second': 1000}, '/source', BackendNeeds.source_only(0), probe=p)
        self.assertEqual(g.check()['volumes'][0]['remaining_bytes'], 1000)

    def test_extra_cache_preallocation_is_not_credited_to_other_cache_files(self):
        p = Probe(); p.put('/source/data.gz', 1000)
        p.put('/backend/cache', 100, allocated=10000)
        g = guard(p, cache_files=[Path('/backend/cache')])
        self.assertEqual(g.check('upload')['volumes'][0]['remaining_bytes'], 923)

    def test_unknown_backend_and_overhead_fail_closed(self):
        candidates = [BackendNeeds('other', 0, 0, 0, 'stream'), BackendNeeds('openlist'),
                      BackendNeeds('openlist', 0, None, 0, 'stream'),
                      BackendNeeds('direct-api', 0, 0, None, 'stream'),
                      BackendNeeds('direct-api', 0, 0, 0),
                      BackendNeeds('openlist', True, 0, 0, 'stream')]
        for item in candidates:
            with self.subTest(item=item), self.assertRaises(SpaceProblem):
                SpaceGuard({'data': 1}, '/source', item, '/backend', probe=Probe())
        # Explicitly known zero is allowed by the model; not proof of a real backend's needs.
        SpaceGuard({'data': 1}, '/source', BackendNeeds('direct-api', 0, 0, 0, 'stream'), '/backend', probe=Probe()).check()

    def test_one_and_five_decimal_gb_models_only(self):
        for size in (1_000_000_000, 5_000_000_000):
            p = Probe(); g = guard(p, size=size)
            self.assertEqual(g.check()['volumes'][0]['remaining_bytes'], 2*size+23)
            p.free[0] = FLOOR+2*size+22
            with self.assertRaisesRegex(SpaceProblem, 'disk_budget'):
                g.check()
            self.assertEqual(p.files, {})

    def test_bad_paths_mount_changes_aliases_and_regression(self):
        p = Probe()
        with self.assertRaisesRegex(SpaceProblem, 'path_unavailable'):
            SpaceGuard({'data': 1}, '/missing', BackendNeeds.source_only(), probe=p)
        g = guard(p)
        with self.assertRaisesRegex(SpaceProblem, 'outside_task'):
            g.register('cache', '/elsewhere/data')
        with self.assertRaisesRegex(SpaceProblem, 'invalid_space_file'):
            g.register('cache', '/backend/../source/data')
        p.devices['/backend'] = 5; p.free[5] = 100*1024**3
        with self.assertRaisesRegex(SpaceProblem, 'directory_changed'):
            g.check()
        p = Probe(); p.put('/source/data.gz', 1000); p.put('/backend/cache', 1000, inode=100)
        with self.assertRaisesRegex(SpaceProblem, 'alias_changed'):
            guard(p, cache_files=[Path('/backend/cache')]).check('upload')
        p = Probe(); p.put('/source/data.gz', 1000); g = guard(p); g.check('upload')
        with self.assertRaisesRegex(SpaceProblem, 'stage_regression'):
            g.check('download')

    def test_simulated_adapter_stops_before_write_when_free_drops(self):
        p = Probe(); p.put('/source/data.gz', 1000)
        g = guard(p, cache_files=[Path('/backend/cache')])
        written = 0
        with patch('socket.create_connection', side_effect=AssertionError('No network in simulation')) as network:
            for i in range(4):
                if i == 2:
                    p.free[0] = FLOOR+100  # Not enough for the remaining planned allocation.
                try:
                    g.check('upload', growth={'cache': 250})
                except SpaceProblem:
                    break
                written += 250
                p.put('/backend/cache', written)
                g.check('upload')
            network.assert_not_called()
        self.assertEqual(written, 500)
        self.assertEqual(p.files['/backend/cache'].size, 500)


class RealPathTests(unittest.TestCase):
    def test_missing_symlink_and_file_directories_are_not_inferred(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); existing = root/'existing'; existing.mkdir()
            link = root/'link'; link.symlink_to(existing, target_is_directory=True)
            file = root/'file'; file.write_bytes(b'preserve')
            for target in (root/'missing', link, file):
                with self.subTest(target=target), self.assertRaises(SpaceProblem):
                    DiskProbe().directory(target)
            self.assertEqual(file.read_bytes(), b'preserve')

    def test_file_symlinks_and_hardlinks_are_rejected_without_touching_original(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); original = root/'old'; original.write_bytes(b'preserve')
            link = root/'link'; link.symlink_to(original)
            with self.assertRaises(SpaceProblem):
                DiskProbe().file(link)
            import os
            os.link(original, root/'hardlink')
            with self.assertRaises(SpaceProblem):
                DiskProbe().file(original)
            self.assertEqual(original.read_bytes(), b'preserve')

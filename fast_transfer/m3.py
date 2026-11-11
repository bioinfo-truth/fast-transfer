"""Explicit offline simulation CLI. There is no live mode or credential loading."""
import argparse
import json
import sys
from pathlib import Path

from .intake import InputProblem, load_manifest, require_accepted
from .simulated_cloud import MemoryCloud
from .space import BackendNeeds
from .upload_stage import run_simulated_upload, TransferLimits


def main():
    p = argparse.ArgumentParser(description='Offline M3 simulation only; never contacts Baidu.')
    p.add_argument('--simulate', action='store_true', required=True)
    p.add_argument('manifest', type=Path)
    p.add_argument('--source-dir', type=Path, required=True)
    p.add_argument('--backend-dir', type=Path, required=True, help='Exact existing private parent for a new job.')
    p.add_argument('--job-id', required=True)
    p.add_argument('--index', type=int, default=0)
    p.add_argument('--app-name', default='Xtransfer', help='Simulated namespace, not a verified account/app.')
    a = p.parse_args()
    try:
        entries = require_accepted(load_manifest(a.manifest))
        if not 0 <= a.index < len(entries):
            raise InputProblem('invalid_file_index')
        entry = entries[a.index]
        # Bounds for THIS simulator: two <=16 KiB state files, no disk payload cache.
        needs = BackendNeeds('direct-api', 64*1024, 256*1024, 256*1024, 'stream')
        limits = TransferLimits(4*1024**2, 16*1024**2, 1024)
        result = run_simulated_upload(entry, a.source_dir/entry['name'],
                                     a.source_dir/'.receipts'/(str(a.index)+'.json'),
                                     a.backend_dir, a.job_id, a.app_name,
                                     MemoryCloud(a.app_name), needs, limits)
    except InputProblem as exc:
        result = {'mode': 'simulation', 'status': 'manual_review', 'reason': exc.code,
                  'delivery_eligible': False, 'cloud_verified': False}
    except Exception:
        result = {'mode': 'simulation', 'status': 'manual_review', 'reason': 'simulation_input_failure',
                  'delivery_eligible': False, 'cloud_verified': False}
    print(json.dumps(result))
    return 0 if result['status'] == 'verified_simulation' else 2


if __name__ == '__main__':
    sys.exit(main())

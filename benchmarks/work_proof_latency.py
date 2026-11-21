"""Reproducible microbenchmark: old hash-only validation vs new one-time proof.

Python 3.10+, standard library. NOT a production benchmark or equivalent security
workload: the new proof additionally reads/pins a request and writes SQLite.
"""
import datetime as dt
import hashlib
import json
import statistics
import tempfile
import time
from pathlib import Path

from verifier import validate
from work_proof import DOMAIN, verify_once


def run(n=120):
    now = dt.datetime(2026, 11, 19, 12, 0, tzinfo=dt.timezone.utc)
    with tempfile.TemporaryDirectory() as dirname:
        root = Path(dirname)
        (root / 'x.txt').write_bytes(b'work' * 100)
        manifest = root / 'manifest.json'
        manifest.write_text(json.dumps({'artifacts': [{
            'path': 'x.txt',
            'sha256': hashlib.sha256(b'work' * 100).hexdigest()
        }]}))
        manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
        ledger = root / 'ledger.sqlite3'
        newer = []
        for i in range(n):
            request = root / 'request.json'
            request.write_text(json.dumps({
                'schema': DOMAIN, 'task_id': f'job-{i}',
                'nonce': f'{i:032x}',
                'issued_at': '2026-11-19T11:59:00Z',
                'expires_at': '2026-11-19T12:10:00Z',
                'manifest_sha256': manifest_hash,
            }))
            pin = hashlib.sha256(request.read_bytes()).hexdigest()
            start = time.perf_counter_ns()
            outcome = verify_once(request, manifest, root, pin, ledger, now=now)
            newer.append((time.perf_counter_ns() - start) / 1e6)
            assert outcome['passed'], outcome
        older = []
        for _ in range(n):
            start = time.perf_counter_ns()
            outcome = validate(manifest, root)
            older.append((time.perf_counter_ns() - start) / 1e6)
            assert outcome['passed'], outcome
        return {
            'runs_per_variant': n,
            'artifact_bytes': 400,
            'legacy_hash_only_median_ms': round(statistics.median(older), 4),
            'one_time_proof_median_ms': round(statistics.median(newer), 4),
            'one_time_proof_p95_ms': round(sorted(newer)[int(.95 * n) - 1], 4),
            'median_overhead_ratio': round(statistics.median(newer) / statistics.median(older), 2),
            'limitations': 'Local filesystem, cached reads, synthetic work; new path includes request pinning and SQLite transaction, not an apples-to-apples security comparison.'
        }


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))

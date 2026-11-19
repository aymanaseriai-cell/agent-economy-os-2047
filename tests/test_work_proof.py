"""Adversarial, offline tests for one-time request-bound evidence integrity."""
import datetime as dt
import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from work_proof import DOMAIN, verify_once

NOW = dt.datetime(2026, 11, 19, 12, 0, tzinfo=dt.timezone.utc)


class WorkProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.request = self.root / 'request.json'
        self.manifest = self.root / 'manifest.json'
        self.ledger = self.root / 'nonces.sqlite3'
        (self.root / 'work.txt').write_bytes(b'job output')
        self.manifest_obj = {'artifacts': [{'path': 'work.txt',
            'sha256': hashlib.sha256(b'job output').hexdigest()}]}
        self.request_obj = {'schema': DOMAIN, 'task_id': 'job-123',
            'nonce': 'a1' * 16,
            'issued_at': '2026-11-19T11:59:00Z',
            'expires_at': '2026-11-19T12:10:00Z',
            'manifest_sha256': ''}
        self.refresh()

    def refresh(self):
        self.manifest.write_text(json.dumps(self.manifest_obj), encoding='utf8')
        self.request_obj['manifest_sha256'] = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.request.write_text(json.dumps(self.request_obj), encoding='utf8')
        self.pin = hashlib.sha256(self.request.read_bytes()).hexdigest()

    def verify(self, pin=None):
        return verify_once(self.request, self.manifest, self.root,
                           self.pin if pin is None else pin, self.ledger, now=NOW)

    def test_success_and_explicit_unverified_commercial_fields(self):
        out = self.verify()
        self.assertTrue(out['passed'])
        self.assertTrue(out['replay_recorded'])
        self.assertFalse(out['buyer_accepted'])
        self.assertFalse(out['execution_attested'])
        self.assertFalse(out['payment_verified'])

    def test_replay_is_rejected(self):
        self.assertTrue(self.verify()['passed'])
        self.assertEqual(self.verify()['reason'], 'replay_detected')

    def test_artifact_tampering_is_rejected_without_nonce_consumption(self):
        (self.root / 'work.txt').write_bytes(b'tampered')
        self.assertEqual(self.verify()['reason'], 'artifact_integrity_failure')
        (self.root / 'work.txt').write_bytes(b'job output')
        self.assertTrue(self.verify()['passed'])

    def test_manifest_tampering_is_rejected(self):
        self.manifest.write_text('{}')
        self.assertEqual(self.verify()['reason'], 'manifest_mismatch')

    def test_pinned_request_mismatch_is_rejected(self):
        self.request_obj['task_id'] = 'other-job'
        self.refresh()
        self.assertEqual(self.verify('0' * 64)['reason'], 'request_pin_mismatch')

    def test_expired_request_is_rejected(self):
        self.request_obj['expires_at'] = '2026-11-19T11:59:59Z'
        self.refresh()
        self.assertEqual(self.verify()['reason'], 'request_expired')

    def test_future_request_is_rejected(self):
        self.request_obj['issued_at'] = '2026-11-19T12:05:00Z'
        self.refresh()
        self.assertEqual(self.verify()['reason'], 'request_not_yet_valid')

    def test_duplicate_artifact_path_is_rejected(self):
        self.manifest_obj['artifacts'].append(dict(self.manifest_obj['artifacts'][0]))
        self.refresh()
        self.assertEqual(self.verify()['reason'], 'duplicate_artifact_path')

    def test_traversal_is_rejected(self):
        self.manifest_obj['artifacts'][0]['path'] = '../work.txt'
        self.refresh()
        self.assertEqual(self.verify()['reason'], 'unsafe_artifact_path')

    def test_invalid_nonce_is_rejected(self):
        self.request_obj['nonce'] = 'x'
        self.refresh()
        self.assertEqual(self.verify()['reason'], 'invalid_nonce')

    def test_sqlite_replay_is_atomic_for_parallel_verifiers(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.verify(), range(4)))
        self.assertEqual(sum(x['passed'] for x in results), 1)
        self.assertEqual(sum(x.get('reason') == 'replay_detected' for x in results), 3)

    def test_duplicate_json_key_is_rejected(self):
        self.request.write_text(self.request.read_text()[:-1] + ',"task_id":"evil"}')
        self.pin = hashlib.sha256(self.request.read_bytes()).hexdigest()
        self.assertEqual(self.verify()['reason'], 'duplicate_json_key')

    def test_nonpersistent_ledger_is_rejected(self):
        self.ledger = Path(':memory:')
        self.assertEqual(self.verify()['reason'], 'nonpersistent_ledger')


if __name__ == '__main__':
    unittest.main()

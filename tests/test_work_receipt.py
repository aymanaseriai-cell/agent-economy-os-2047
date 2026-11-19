import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from work_receipt import SCHEMA, verify_receipt


class WorkReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        (self.root / 'result.txt').write_bytes(b'checked result')
        self.receipt = {
            'schema': SCHEMA, 'contract_id': 'a' * 64, 'audience': 'buyer-001',
            'nonce': 'b' * 32,
            'issued_at': (self.now - timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'expires_at': (self.now + timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'artifacts': [{'path': 'result.txt', 'sha256': hashlib.sha256(b'checked result').hexdigest()}],
        }
        self.path = self.root / 'receipt.json'
        self.ledger = self.root / 'ledger.sqlite3'

    def run_receipt(self):
        return verify_receipt(self.path, self.root, 'a' * 64, 'buyer-001', self.ledger, now=self.now)

    def save(self):
        self.path.write_text(json.dumps(self.receipt), encoding='utf-8')

    def test_pass_and_repeat_rejected(self):
        self.save()
        first = self.run_receipt()
        self.assertTrue(first['passed'])
        self.assertFalse(first['buyer_acceptance_verified'])
        self.assertFalse(first['payment_verified'])
        self.assertEqual(self.run_receipt()['reason'], 'replay_detected')

    def test_altered_nonce_same_evidence_rejected(self):
        self.save()
        self.assertTrue(self.run_receipt()['passed'])
        self.receipt['nonce'] = 'c' * 32
        self.save()
        self.assertEqual(self.run_receipt()['reason'], 'replay_detected')

    def test_wrong_buyer_intent_rejected(self):
        self.save()
        response = verify_receipt(self.path, self.root, 'c' * 64, 'buyer-001', self.ledger, self.now)
        self.assertEqual(response['reason'], 'contract_not_pinned')
        self.assertFalse(self.ledger.exists())

    def test_wrong_audience_rejected(self):
        self.save()
        response = verify_receipt(self.path, self.root, 'a' * 64, 'another-buyer', self.ledger, self.now)
        self.assertEqual(response['reason'], 'audience_mismatch')

    def test_tampered_file_rejected_without_consuming_nonce(self):
        self.save()
        (self.root / 'result.txt').write_text('tampered')
        self.assertEqual(self.run_receipt()['reason'], 'artifact_integrity_failed')
        (self.root / 'result.txt').write_bytes(b'checked result')
        self.assertTrue(self.run_receipt()['passed'])

    def test_path_traversal_rejected(self):
        self.receipt['artifacts'][0]['path'] = '../private.txt'
        self.save()
        self.assertEqual(self.run_receipt()['reason'], 'unsafe_artifact_path')

    def test_duplicate_artifact_rejected(self):
        self.receipt['artifacts'].append(dict(self.receipt['artifacts'][0]))
        self.save()
        self.assertEqual(self.run_receipt()['reason'], 'duplicate_artifact_path')

    def test_expired_and_future_rejected(self):
        self.receipt['expires_at'] = (self.now - timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.save()
        self.assertEqual(self.run_receipt()['reason'], 'expired')
        self.receipt['issued_at'] = (self.now + timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.receipt['expires_at'] = (self.now + timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.save()
        self.assertEqual(self.run_receipt()['reason'], 'not_yet_valid')

    def test_duplicate_json_key_rejected(self):
        self.save()
        raw = self.path.read_text()
        self.path.write_text(raw.replace('"nonce":', '"nonce": "0", "nonce":', 1))
        self.assertEqual(self.run_receipt()['reason'], 'duplicate_json_key')

    def test_symlink_rejected(self):
        (self.root / 'link.txt').symlink_to(self.root / 'result.txt')
        self.receipt['artifacts'][0]['path'] = 'link.txt'
        self.save()
        self.assertEqual(self.run_receipt()['reason'], 'symlink_disallowed')

    def test_concurrent_replay_one_success(self):
        self.save()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.run_receipt(), (1, 2)))
        self.assertEqual(sum(x['passed'] for x in results), 1)
        self.assertEqual(sum(x['reason'] == 'replay_detected' for x in results), 1)


if __name__ == '__main__':
    unittest.main()

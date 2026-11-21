#!/usr/bin/env python3
"""No-network, no-payment Work Receipt v1 demo with an intentionally synthetic task."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import tempfile

from work_receipt import SCHEMA, verify_receipt


def main():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        artifact = root / 'sample.txt'
        artifact.write_bytes(b'example technical output only\n')
        # Synthetic demonstration: in real use, pin the contract ID out of band.
        pinned_contract = hashlib.sha256(b'synthetic buyer task v1').hexdigest()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        receipt = {
            'schema': SCHEMA,
            'contract_id': pinned_contract,
            'audience': 'synthetic-buyer',
            'nonce': secrets.token_hex(16),
            'issued_at': (now - timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'expires_at': (now + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'artifacts': [{'path': 'sample.txt', 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}],
        }
        receipt_file = root / 'receipt.json'
        receipt_file.write_text(json.dumps(receipt), encoding='utf-8')
        ledger = root / 'single-use.sqlite3'
        first = verify_receipt(receipt_file, root, pinned_contract, 'synthetic-buyer', ledger, now)
        replay = verify_receipt(receipt_file, root, pinned_contract, 'synthetic-buyer', ledger, now)
        assert first['passed'] and replay['reason'] == 'replay_detected'
        assert not first['buyer_acceptance_verified'] and not first['payment_verified']
        print(json.dumps({'first': first, 'replay': replay}, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Offline work-receipt verifier: pinned work intent + single-use local ledger.

This is NOT an authentication, signature, execution-attestation, or payment system.
All receipt fields are untrusted until independently authorized by a buyer.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3

from verifier import validate

SCHEMA = 'agent-economy.work-receipt.v1'
HEX64 = re.compile(r'^[0-9a-f]{64}$')
NONCE = re.compile(r'^[0-9a-f]{32}$')
AUDIENCE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$')
TIMESTAMP = '%Y-%m-%dT%H:%M:%SZ'
REQUIRED = {'schema', 'contract_id', 'audience', 'nonce', 'issued_at', 'expires_at', 'artifacts'}


class ReceiptError(ValueError):
    pass


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError('duplicate_json_key')
        result[key] = value
    return result


def parse_time(value):
    if not isinstance(value, str):
        raise ReceiptError('invalid_timestamp')
    try:
        parsed = datetime.strptime(value, TIMESTAMP).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ReceiptError('invalid_timestamp') from exc
    if parsed.strftime(TIMESTAMP) != value:
        raise ReceiptError('invalid_timestamp')
    return parsed


def validate_format(receipt, now):
    if not isinstance(receipt, dict) or set(receipt) != REQUIRED or receipt['schema'] != SCHEMA:
        raise ReceiptError('invalid_schema')
    if not isinstance(receipt['contract_id'], str) or not HEX64.fullmatch(receipt['contract_id']):
        raise ReceiptError('invalid_contract_id')
    if not isinstance(receipt['audience'], str) or not AUDIENCE.fullmatch(receipt['audience']):
        raise ReceiptError('invalid_audience')
    if not isinstance(receipt['nonce'], str) or not NONCE.fullmatch(receipt['nonce']):
        raise ReceiptError('invalid_nonce')
    issued, expires = parse_time(receipt['issued_at']), parse_time(receipt['expires_at'])
    if expires <= issued or expires - issued > timedelta(hours=24):
        raise ReceiptError('invalid_ttl')
    if issued > now:
        raise ReceiptError('not_yet_valid')
    if expires <= now:
        raise ReceiptError('expired')
    artifacts = receipt['artifacts']
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 32:
        raise ReceiptError('invalid_artifacts')
    paths = set()
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {'path', 'sha256'}:
            raise ReceiptError('invalid_artifact')
        path, digest = item['path'], item['sha256']
        if (not isinstance(path, str) or not path or len(path) > 240
                or path.startswith('/') or '\\' in path or '\x00' in path
                or any(part in ('', '.', '..') for part in path.split('/'))):
            raise ReceiptError('unsafe_artifact_path')
        if path in paths:
            raise ReceiptError('duplicate_artifact_path')
        paths.add(path)
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise ReceiptError('invalid_artifact_hash')


def verify_receipt(receipt_path, root, expected_contract_id, expected_audience,
                   ledger_path, now=None):
    """Return technical result; record successful receipts atomically in SQLite.

    The expected contract/audience must be supplied from an independent trusted
    source, not copied from the receipt being verified. A shared ledger is needed
    across replicas for global single-use guarantees.
    """
    result = {'passed': False, 'status': 'rejected', 'reason': None,
              'buyer_acceptance_verified': False, 'payment_verified': False,
              'signer_identity_verified': False, 'global_replay_protection': False}
    try:
        now = datetime.now(timezone.utc) if now is None else now
        if now.tzinfo is None:
            raise ReceiptError('naive_clock')
        now = now.astimezone(timezone.utc)
        if not isinstance(expected_contract_id, str) or not HEX64.fullmatch(expected_contract_id):
            raise ReceiptError('invalid_expected_contract_id')
        if not isinstance(expected_audience, str) or not AUDIENCE.fullmatch(expected_audience):
            raise ReceiptError('invalid_expected_audience')
        receipt_path, root = Path(receipt_path), Path(root).resolve()
        if receipt_path.stat().st_size > 65536:
            raise ReceiptError('receipt_too_large')
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'), object_pairs_hook=no_duplicate_keys)
        validate_format(receipt, now)
        if not hmac.compare_digest(receipt['contract_id'], expected_contract_id):
            raise ReceiptError('contract_not_pinned')
        if not hmac.compare_digest(receipt['audience'], expected_audience):
            raise ReceiptError('audience_mismatch')
        for item in receipt['artifacts']:
            location = root
            for part in item['path'].split('/'):
                location = location / part
                if location.is_symlink():
                    raise ReceiptError('symlink_disallowed')
            try:
                location.resolve().relative_to(root)
            except ValueError as exc:
                raise ReceiptError('unsafe_artifact_path') from exc
            if location.is_file() and location.stat().st_size > 16 * 1024 * 1024:
                raise ReceiptError('artifact_too_large')
        evidence = validate(receipt_path, root)
        if not evidence['passed']:
            raise ReceiptError('artifact_integrity_failed')
        normalized = json.dumps(receipt, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        receipt_id = hashlib.sha256((SCHEMA + '\x00' + normalized).encode()).hexdigest()
        evidence_digest = hashlib.sha256(json.dumps(receipt['artifacts'], sort_keys=True,
                                                separators=(',', ':')).encode()).hexdigest()
        ledger_path = Path(ledger_path)
        if not ledger_path.parent.is_dir():
            raise ReceiptError('ledger_parent_missing')
        with sqlite3.connect(ledger_path, timeout=5, isolation_level=None) as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('''CREATE TABLE IF NOT EXISTS work_receipts (
                audience TEXT NOT NULL, contract_id TEXT NOT NULL,
                nonce TEXT NOT NULL, evidence_digest TEXT NOT NULL,
                receipt_id TEXT NOT NULL, recorded_at TEXT NOT NULL,
                PRIMARY KEY (audience, contract_id, nonce),
                UNIQUE (audience, contract_id, evidence_digest)
            )''')
            try:
                conn.execute('INSERT INTO work_receipts VALUES (?, ?, ?, ?, ?, ?)',
                             (receipt['audience'], receipt['contract_id'], receipt['nonce'],
                              evidence_digest, receipt_id, now.isoformat()))
                conn.execute('COMMIT')
            except sqlite3.IntegrityError as exc:
                conn.execute('ROLLBACK')
                raise ReceiptError('replay_detected') from exc
        result.update(passed=True, status='local_technical_checks_passed',
                      receipt_id=receipt_id, checked=evidence['checked'], reason=None,
                      local_replay_recorded=True)
    except (ReceiptError, OSError, UnicodeError, json.JSONDecodeError, sqlite3.Error, ValueError) as exc:
        result['reason'] = str(exc) if isinstance(exc, ReceiptError) else type(exc).__name__
    return result


def main():
    parser = argparse.ArgumentParser(description='Verify a pinned agent work receipt with single-use local ledger')
    parser.add_argument('receipt', type=Path)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--contract-id', required=True)
    parser.add_argument('--audience', required=True)
    parser.add_argument('--ledger', required=True, type=Path)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    result = verify_receipt(args.receipt, args.root, args.contract_id, args.audience, args.ledger)
    data = json.dumps(result, indent=2, sort_keys=True) + '\n'
    print(data, end='')
    if args.json_out:
        args.json_out.write_text(data, encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

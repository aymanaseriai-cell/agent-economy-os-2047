#!/usr/bin/env python3
"""Offline, one-time, request-bound evidence integrity check (Python stdlib).

It does NOT authenticate the requester, attest agent execution, or prove settlement.
The caller must pin the request SHA-256 out of band and protect the SQLite ledger.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import re
import sqlite3
from pathlib import Path, PurePosixPath

from verifier import validate

DOMAIN = 'agent-economy.work-proof.v1'
HEX64 = re.compile(r'^[0-9a-f]{64}$')
NONCE = re.compile(r'^[0-9a-f]{32,64}$')
TASK = re.compile(r'^[A-Za-z0-9_.:-]{1,100}$')
FIELDS = frozenset({'schema', 'task_id', 'nonce', 'issued_at', 'expires_at', 'manifest_sha256'})
MAX_BYTES = 1_048_576


class InvalidProof(ValueError):
    pass


def _no_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InvalidProof('duplicate_json_key')
        out[key] = value
    return out


def _read_json(path: Path):
    with path.open('rb') as f:
        raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise InvalidProof('input_too_large')
    try:
        obj = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidProof('invalid_json') from exc
    return raw, obj


def _time(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', value):
        raise InvalidProof('invalid_timestamp')
    try:
        timestamp = dt.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise InvalidProof('invalid_timestamp') from exc
    return timestamp


def _safe_paths(manifest):
    rows = manifest.get('artifacts') if isinstance(manifest, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise InvalidProof('invalid_artifacts_count')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'path', 'sha256'}:
            raise InvalidProof('invalid_artifact_row')
        p, digest = row['path'], row['sha256']
        if not isinstance(p, str) or not 1 <= len(p) <= 240 or '\\' in p or '\x00' in p:
            raise InvalidProof('unsafe_artifact_path')
        path = PurePosixPath(p)
        if path.is_absolute() or any(part in ('', '.', '..') for part in p.split('/')) or str(path) != p:
            raise InvalidProof('unsafe_artifact_path')
        if p in seen:
            raise InvalidProof('duplicate_artifact_path')
        seen.add(p)
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise InvalidProof('invalid_artifact_sha256')


def verify_once(request_path: Path, manifest_path: Path, root: Path,
                expected_request_sha256: str, ledger_path: Path,
                now: dt.datetime | None = None) -> dict:
    """Fail closed: consume (request, nonce) only after all integrity checks succeed.

    Reusing the same database makes replay prevention atomic across processes.
    This method alone does not prevent replay across different ledger databases.
    """
    response = {'schema': DOMAIN, 'passed': False, 'status': 'rejected',
                'buyer_accepted': False, 'execution_attested': False, 'payment_verified': False}
    try:
        if not isinstance(expected_request_sha256, str) or not HEX64.fullmatch(expected_request_sha256):
            raise InvalidProof('invalid_pinned_request_sha256')
        req_raw, req = _read_json(request_path)
        digest = hashlib.sha256(req_raw).hexdigest()
        if not hmac.compare_digest(digest, expected_request_sha256):
            raise InvalidProof('request_pin_mismatch')
        if not isinstance(req, dict) or set(req) != FIELDS or req['schema'] != DOMAIN:
            raise InvalidProof('invalid_work_request_schema')
        if not isinstance(req['task_id'], str) or not TASK.fullmatch(req['task_id']):
            raise InvalidProof('invalid_task_id')
        if not isinstance(req['nonce'], str) or not NONCE.fullmatch(req['nonce']):
            raise InvalidProof('invalid_nonce')
        if not isinstance(req['manifest_sha256'], str) or not HEX64.fullmatch(req['manifest_sha256']):
            raise InvalidProof('invalid_manifest_sha256')
        issued = _time(req['issued_at'])
        expires = _time(req['expires_at'])
        current = now or dt.datetime.now(dt.timezone.utc)
        if current.tzinfo is None:
            raise InvalidProof('naive_current_time')
        current = current.astimezone(dt.timezone.utc)
        if issued > current + dt.timedelta(seconds=60):
            raise InvalidProof('request_not_yet_valid')
        if expires <= current:
            raise InvalidProof('request_expired')
        if expires <= issued or expires - issued > dt.timedelta(days=7):
            raise InvalidProof('invalid_request_lifetime')
        raw_manifest, manifest = _read_json(manifest_path)
        if not hmac.compare_digest(hashlib.sha256(raw_manifest).hexdigest(), req['manifest_sha256']):
            raise InvalidProof('manifest_mismatch')
        _safe_paths(manifest)
        result = validate(manifest_path, root)
        if not result['passed'] or result['checked'] != len(manifest['artifacts']):
            raise InvalidProof('artifact_integrity_failure')
        if str(ledger_path) == ':memory:':
            raise InvalidProof('nonpersistent_ledger')
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(ledger_path), timeout=10, isolation_level=None) as db:
            db.execute('PRAGMA busy_timeout=10000')
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('CREATE TABLE IF NOT EXISTS used_proofs ('
                           'request_sha TEXT NOT NULL, nonce TEXT NOT NULL, '
                           'consumed_at TEXT NOT NULL, PRIMARY KEY(request_sha, nonce))')
                try:
                    db.execute('INSERT INTO used_proofs(request_sha,nonce,consumed_at) VALUES (?,?,?)',
                               (digest, req['nonce'], current.isoformat()))
                except sqlite3.IntegrityError as exc:
                    raise InvalidProof('replay_detected') from exc
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise
        response.update(passed=True, status='integrity_passed_once', reason=None,
                        task_id=req['task_id'], request_sha256=digest,
                        manifest_sha256=req['manifest_sha256'], checked=result['checked'],
                        replay_recorded=True,
                        limitations='Only caller-provided bytes validated; no independent identity, execution or settlement proof.')
    except (InvalidProof, OSError, sqlite3.Error, TypeError) as exc:
        response['reason'] = str(exc) if isinstance(exc, InvalidProof) else 'io_or_storage_error'
    return response


def main():
    parser = argparse.ArgumentParser(description='Verify a pinned work request once (offline).')
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--pinned-request-sha256', required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    args = parser.parse_args()
    result = verify_once(args.request, args.manifest, args.root,
                         args.pinned_request_sha256, args.ledger)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Offline, buyer-held, one-time evidence acceptance gate (stdlib only).

This validates bytes against a buyer-pinned manifest with verifier.validate,
then atomically claims the challenge AND exact evidence fingerprint in SQLite.
It is NOT identity, execution provenance, buyer acceptance, payment or escrow.
"""
import argparse
import hashlib
import json
import os
import secrets
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

from verifier import validate

DOMAIN = "agent-economy.evidence-gate.v1"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ARTIFACTS = 100


def _hex(data):
    return hashlib.sha256(data).hexdigest()


def _manifest_bytes(path):
    path = Path(path)
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("manifest_too_large")
    data = path.read_bytes()
    try:
        obj = json.loads(data)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_manifest_json") from exc
    records = obj.get("artifacts") if isinstance(obj, dict) else None
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_ARTIFACTS:
        raise ValueError("invalid_artifact_count")
    return data, records


def _db(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    conn = sqlite3.connect(str(path), timeout=10.0, isolation_level=None)
    if new and os.name == "posix":
        os.chmod(path, 0o600)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS challenges (
            token_hash TEXT PRIMARY KEY,
            manifest_sha256 TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            redeemed_at INTEGER,
            receipt_id TEXT
        );
        CREATE TABLE IF NOT EXISTS claimed_evidence (
            fingerprint TEXT PRIMARY KEY,
            token_hash TEXT UNIQUE NOT NULL,
            claimed_at INTEGER NOT NULL
        );
    """)
    return conn


def issue_challenge(ledger, manifest, ttl_seconds=300, now=None):
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
        raise ValueError("invalid_ttl")
    manifest_bytes, _ = _manifest_bytes(manifest)
    now = int(time.time() if now is None else now)
    token = secrets.token_urlsafe(32)
    with closing(_db(ledger)) as db:
        with db:
            db.execute("INSERT INTO challenges(token_hash,manifest_sha256,expires_at) VALUES(?,?,?)",
                       (_hex(token.encode("ascii")), _hex(manifest_bytes), now + ttl_seconds))
    return {"status": "issued", "challenge": token,
            "manifest_sha256": _hex(manifest_bytes), "expires_at": now + ttl_seconds,
            "limitations": "Buyer-held local challenge only; no remote caller authentication."}


def _result(reason):
    return {"status": "rejected", "accepted": False, "reason": reason}


def redeem_challenge(ledger, manifest, root, challenge, now=None):
    if not isinstance(challenge, str) or not 32 <= len(challenge) <= 128 or not challenge.isascii():
        return _result("invalid_challenge")
    try:
        data, records = _manifest_bytes(manifest)
        resolved_root = Path(root).resolve()
        real_paths = []
        for rec in records:
            if not isinstance(rec, dict) or not isinstance(rec.get("path"), str):
                return _result("invalid_artifact_path")
            relative = Path(rec["path"])
            if relative.is_absolute():
                return _result("invalid_artifact_path")
            path = (resolved_root / relative).resolve()
            if not path.is_relative_to(resolved_root):
                return _result("path_escapes_root")
            real_paths.append(str(path))
        if len(real_paths) != len(set(real_paths)):
            return _result("duplicate_artifact_path")
        report = validate(Path(manifest), resolved_root)
        if not report["passed"] or len(report["artifacts"]) != len(records):
            return _result("artifact_validation_failed")
        evidence = sorted((x["path"], x["sha256"]) for x in report["artifacts"])
        fingerprint = _hex(json.dumps({"domain": DOMAIN, "artifacts": evidence},
              sort_keys=True, separators=(",", ":")).encode("utf-8"))
    except (ValueError, OSError, TypeError):
        return _result("invalid_evidence_input")
    now = int(time.time() if now is None else now)
    th = _hex(challenge.encode("ascii"))
    conn = _db(ledger)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT manifest_sha256,expires_at,redeemed_at FROM challenges WHERE token_hash=?", (th,)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return _result("unknown_challenge")
        if row[2] is not None:
            conn.execute("ROLLBACK")
            return _result("challenge_already_redeemed")
        if now >= row[1]:
            conn.execute("ROLLBACK")
            return _result("challenge_expired")
        if not secrets.compare_digest(row[0], _hex(data)):
            conn.execute("ROLLBACK")
            return _result("manifest_mismatch")
        try:
            conn.execute("INSERT INTO claimed_evidence(fingerprint,token_hash,claimed_at) VALUES(?,?,?)",
                         (fingerprint, th, now))
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            return _result("exact_evidence_reused")
        receipt_id = _hex((DOMAIN + ":" + th + ":" + fingerprint).encode("ascii"))
        conn.execute("UPDATE challenges SET redeemed_at=?, receipt_id=? WHERE token_hash=? AND redeemed_at IS NULL",
                     (now, receipt_id, th))
        conn.execute("COMMIT")
        return {"status": "accepted_once", "accepted": True, "receipt_id": receipt_id,
                "evidence_fingerprint": fingerprint, "manifest_sha256": row[0],
                "trust_scope": "local_hash_and_one_time_ledger_only",
                "buyer_acceptance_verified": False, "payment_verified": False,
                "execution_provenance_verified": False}
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("issue", help="Buyer locally issues a one-use challenge")
    a.add_argument("--ledger", type=Path, required=True)
    a.add_argument("--manifest", type=Path, required=True)
    a.add_argument("--ttl", type=int, default=300)
    b = sub.add_parser("redeem", help="Buyer validates artifact bytes and consumes challenge")
    b.add_argument("--ledger", type=Path, required=True)
    b.add_argument("--manifest", type=Path, required=True)
    b.add_argument("--root", type=Path, default=Path("."))
    b.add_argument("--challenge", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "issue":
            result = issue_challenge(args.ledger, args.manifest, args.ttl)
        else:
            result = redeem_challenge(args.ledger, args.manifest, args.root, args.challenge)
    except (OSError, ValueError, sqlite3.Error) as exc:
        result = _result(type(exc).__name__)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in ("issued", "accepted_once") else 1


if __name__ == "__main__":
    sys.exit(main())

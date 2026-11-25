#!/usr/bin/env python3
"""Local one-use work-evidence gate. No payment, identity or execution proof."""
import argparse
import hashlib
import json
import os
import stat
import tempfile
import re
import secrets
import sqlite3
import time
from pathlib import Path
from verifier import validate

DOMAIN = "agent-economy.evidence-challenge.v1"
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
NONCE = re.compile(r"^[0-9a-f]{48}$")
DDL = """CREATE TABLE IF NOT EXISTS evidence_challenges(
    nonce TEXT PRIMARY KEY, request_id TEXT NOT NULL, audience TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL, expires_at INTEGER NOT NULL, used_at INTEGER)"""


CLAIMS_DDL = """CREATE TABLE IF NOT EXISTS evidence_claims(
    nonce TEXT PRIMARY KEY, request_id TEXT NOT NULL, audience TEXT NOT NULL,
    fingerprint TEXT NOT NULL, claimed_at INTEGER NOT NULL,
    UNIQUE(request_id,audience,fingerprint))"""


def _db(path, *, existing=False):
    if not Path(path).parent.is_dir():
        raise ValueError("db_parent_missing")
    target = Path(path).resolve().as_uri() + "?mode=rw" if existing else str(path)
    conn = sqlite3.connect(target, uri=existing, timeout=5, isolation_level=None)
    try:
        conn.execute(DDL)
        conn.execute(CLAIMS_DDL)
        return conn
    except BaseException:
        conn.close()
        raise


def _manifest_bytes(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("manifest_not_regular")
        raw = handle.read(131073)
    if len(raw) > 131072:
        raise ValueError("manifest_too_large")
    return raw


def manifest_hash(path):
    return hashlib.sha256(_manifest_bytes(path)).hexdigest()


def issue(db, request_id, audience, expected_hash, ttl=300, *, now=None):
    if not isinstance(request_id, str) or not ID.fullmatch(request_id):
        raise ValueError("invalid_request_id")
    if not isinstance(audience, str) or not ID.fullmatch(audience):
        raise ValueError("invalid_audience")
    if not isinstance(expected_hash, str) or not HASH.fullmatch(expected_hash):
        raise ValueError("invalid_manifest_hash")
    if type(ttl) is not int or not 1 <= ttl <= 3600:
        raise ValueError("invalid_ttl")
    stamp = int(time.time()) if now is None else int(now)
    nonce = secrets.token_hex(24)
    conn = _db(db)
    try:
        conn.execute("INSERT INTO evidence_challenges VALUES (?,?,?,?,?,NULL)",
                     (nonce, request_id, audience, expected_hash, stamp + ttl))
    finally:
        conn.close()
    return {"schema": DOMAIN, "nonce": nonce, "request_id": request_id,
            "audience": audience, "manifest_sha256": expected_hash,
            "expires_at": stamp + ttl, "signed": False}


def _preflight(raw, root):
    if root.is_symlink() or not root.is_dir():
        return "unsafe_root"
    try:
        data = json.loads(raw)
    except (ValueError, OSError, UnicodeError):
        return "invalid_manifest"
    if not isinstance(data, dict) or not isinstance(data.get("artifacts"), list):
        return "invalid_manifest"
    rows = data["artifacts"]
    if not 1 <= len(rows) <= 32:
        return "invalid_artifact_count"
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            return "invalid_path"
        name = row["path"]
        if not name or len(name) > 240 or name.startswith("/") or "\\" in name or "\x00" in name:
            return "unsafe_path"
        parts = name.split("/")
        if any(part in ("", ".", "..") for part in parts):
            return "unsafe_path"
        if name in seen:
            return "duplicate_artifact"
        seen.add(name)
        part_path = root
        for part in parts:
            part_path = part_path / part
            if part_path.is_symlink():
                return "symlink_rejected"
    return None


def verify(db, nonce, request_id, audience, manifest, root, *, now=None):
    try:
        return _verify(db, nonce, request_id, audience, manifest, root, now=now)
    except (OSError, sqlite3.Error, ValueError, RecursionError):
        return {"schema": DOMAIN, "passed": False, "status": "verification_unavailable"}


def _verify(db, nonce, request_id, audience, manifest, root, *, now=None):
    stamp = int(time.time()) if now is None else int(now)
    fail = lambda state: {"schema": DOMAIN, "passed": False, "status": state}
    if not isinstance(nonce, str) or not NONCE.fullmatch(nonce):
        return fail("invalid_nonce")
    if not isinstance(request_id, str) or not ID.fullmatch(request_id):
        return fail("invalid_request_id")
    if not isinstance(audience, str) or not ID.fullmatch(audience):
        return fail("invalid_audience")
    manifest, root = Path(manifest), Path(root)
    if not Path(db).is_file():
        return fail("challenge_unknown")
    conn = _db(db, existing=True)
    try:
        record = conn.execute(
            "SELECT request_id,audience,manifest_sha256,expires_at,used_at "
            "FROM evidence_challenges WHERE nonce=?", (nonce,)).fetchone()
    finally:
        conn.close()
    if not record:
        return fail("challenge_unknown")
    req, target, expected, expires, used = record
    if used is not None:
        return fail("replay_blocked")
    if stamp >= expires:
        return fail("challenge_expired")
    if req != request_id or target != audience:
        return fail("binding_mismatch")
    try:
        raw = _manifest_bytes(manifest)
        if hashlib.sha256(raw).hexdigest() != expected:
            return fail("manifest_mismatch")
    except (OSError, ValueError):
        return fail("manifest_unreadable")
    problem = _preflight(raw, root)
    if problem:
        return fail(problem)
    # Validate exactly the bytes checked against the independently pinned digest.
    with tempfile.TemporaryDirectory(prefix="aeos-manifest-") as temp:
        snapshot = Path(temp) / "manifest.json"
        snapshot.write_bytes(raw)
        report = validate(snapshot, root)
    if not report["passed"]:
        return fail("artifact_integrity_failed")
    hashes = {x["path"]: x["sha256"] for x in report["artifacts"]}
    statement = json.dumps({
        "domain": DOMAIN, "request_id": req, "audience": target, "nonce": nonce,
        "manifest_sha256": expected, "artifacts": hashes},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    receipt = hashlib.sha256(statement).hexdigest()
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    conn = _db(db, existing=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        # An older used nonce without a claim has unknown replay history. Do not silently reset it.
        if conn.execute("SELECT 1 FROM evidence_challenges c LEFT JOIN evidence_claims p ON p.nonce=c.nonce WHERE c.used_at IS NOT NULL AND p.nonce IS NULL LIMIT 1").fetchone():
            conn.rollback()
            return fail("legacy_claim_history_unverified")
        stamp = int(time.time()) if now is None else stamp
        try:
            conn.execute("INSERT INTO evidence_claims VALUES (?,?,?,?,?)", (nonce, req, target, fingerprint, stamp))
        except sqlite3.IntegrityError:
            conn.rollback()
            return fail("evidence_reused_or_replay")
        changed = conn.execute(
            "UPDATE evidence_challenges SET used_at=? "
            "WHERE nonce=? AND used_at IS NULL AND expires_at>? AND request_id=? AND audience=? AND manifest_sha256=?",
            (stamp, nonce, stamp, req, target, expected)).rowcount
        if changed != 1:
            conn.rollback()
            return fail("replay_or_expired")
        conn.commit()
    finally:
        conn.close()
    return {"schema": DOMAIN, "passed": True, "status": "local_integrity_passed",
            "receipt_sha256": receipt, "artifacts_checked": len(hashes),
            "request_id": req, "audience": target,
            "independent_identity_verified": False, "buyer_acceptance_verified": False,
            "payment_verified": False, "cryptographic_signature_present": False}


def main():
    p = argparse.ArgumentParser(description="Offline one-time proof verification")
    subs = p.add_subparsers(dest="action", required=True)
    for action in ("issue", "verify"):
        sub = subs.add_parser(action)
        for name in ("db", "manifest", "request-id", "audience"):
            sub.add_argument("--" + name, required=True)
        if action == "issue":
            sub.add_argument("--ttl", type=int, default=300)
        else:
            sub.add_argument("--nonce", required=True)
            sub.add_argument("--root", required=True)
    a = p.parse_args()
    if a.action == "issue":
        result = issue(a.db, a.request_id, a.audience, manifest_hash(a.manifest), a.ttl)
    else:
        result = verify(a.db, a.nonce, a.request_id, a.audience, a.manifest, a.root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if a.action == "issue" or result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

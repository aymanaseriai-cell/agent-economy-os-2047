#!/usr/bin/env python3
"""Signed, replay-resistant offline gate for two harmless local agent operations.

Credentials are per-principal HMAC keys supplied only by the operator through
an environment variable. This is NOT federated agent identity, production
API authorization, or a way to execute financial / write operations.
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

from agent_action_policy import (
    NAME_RE, PolicyError, evaluate, read_strict_json, validate_request
)

ENVELOPE_SCHEMA = "agent-economy.signed-action-envelope.v1"
RESULT_SCHEMA = "agent-economy.signed-action-result.v1"
DOMAIN = b"agent-economy.os2047.authenticated-action.v1\x00"
KEYS_ENV = "AGENT_ECONOMY_HMAC_KEYS_JSON"
SAFE_EXECUTION = frozenset({"health.inspect", "evidence.inspect"})
EXECUTION_RESOURCE = "service:work-covenant"
NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{22,128}$")
B64_RE = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_TTL = timedelta(minutes=5)
MAX_CLOCK_SKEW = timedelta(seconds=30)
MAX_EVIDENCE = 8192


def decode_b64(value):
    if not isinstance(value, str) or not value or not B64_RE.fullmatch(value):
        raise PolicyError("invalid_base64url")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * ((-len(value)) % 4))
    except (ValueError, base64.binascii.Error) as exc:
        raise PolicyError("invalid_base64url") from exc
    if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
        raise PolicyError("noncanonical_base64url")
    return raw


def duplicate_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise PolicyError("duplicate_key")
        result[key] = value
    return result


def load_trusted_keys(environment=None):
    """Never load keys from the envelope, policy or repository."""
    env = environment if environment is not None else os.environ
    raw = env.get(KEYS_ENV)
    if not isinstance(raw, str) or not (2 <= len(raw) <= 16384):
        raise PolicyError("trusted_keys_unconfigured")
    try:
        values = json.loads(raw, object_pairs_hook=duplicate_pairs)
    except (TypeError, ValueError) as exc:
        raise PolicyError("invalid_trusted_keys") from exc
    if not isinstance(values, dict) or not (1 <= len(values) <= 32):
        raise PolicyError("invalid_trusted_keys")
    keys = {}
    for principal, encoded in values.items():
        if not isinstance(principal, str) or NAME_RE.fullmatch(principal) is None:
            raise PolicyError("invalid_trusted_principal")
        secret = decode_b64(encoded)
        if not (32 <= len(secret) <= 64):
            raise PolicyError("insufficient_key_strength")
        keys[principal] = secret
    return keys


def utc_timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value
    ):
        raise PolicyError("invalid_timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise PolicyError("invalid_timestamp") from exc


def unsigned_envelope(envelope):
    if not isinstance(envelope, dict) or set(envelope) != {
        "schema", "request", "payload", "issued_at", "expires_at", "nonce", "signature"
    }:
        raise PolicyError("invalid_envelope_shape")
    if envelope["schema"] != ENVELOPE_SCHEMA:
        raise PolicyError("unsupported_envelope_schema")
    validate_request(envelope["request"])
    if not isinstance(envelope["payload"], dict):
        raise PolicyError("invalid_payload")
    nonce = envelope["nonce"]
    if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
        raise PolicyError("invalid_nonce")
    return {key: value for key, value in envelope.items() if key != "signature"}


def canonical_bytes(document):
    try:
        return DOMAIN + json.dumps(
            document, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise PolicyError("noncanonical_envelope") from exc


def verify_signed_envelope(envelope, trusted_keys, now):
    unsigned = unsigned_envelope(envelope)
    issued_at = utc_timestamp(envelope["issued_at"])
    expires_at = utc_timestamp(envelope["expires_at"])
    if (expires_at <= issued_at or expires_at - issued_at > MAX_TTL
        or now >= expires_at or issued_at > now + MAX_CLOCK_SKEW):
        raise PolicyError("expired_or_invalid_window")
    principal = envelope["request"]["principal"]
    secret = trusted_keys.get(principal)
    if not isinstance(secret, bytes) or not (32 <= len(secret) <= 64):
        raise PolicyError("unknown_principal")
    provided = decode_b64(envelope["signature"])
    if len(provided) != 32:
        raise PolicyError("invalid_signature")
    expected = hmac.new(secret, canonical_bytes(unsigned), hashlib.sha256).digest()
    if not hmac.compare_digest(provided, expected):
        raise PolicyError("invalid_signature")
    return expires_at


def validate_execution(request, payload):
    if request["action"] not in SAFE_EXECUTION or request["resource"] != EXECUTION_RESOURCE:
        raise PolicyError("unsupported_local_execution")
    if request["action"] == "health.inspect":
        if payload:
            raise PolicyError("invalid_health_payload")
    elif (set(payload) != {"text"} or not isinstance(payload.get("text"), str)
          or len(payload["text"].encode("utf-8")) > MAX_EVIDENCE):
        raise PolicyError("invalid_evidence_payload")


def reserve_nonce(database_path, principal, nonce, expires_at, now):
    """Atomic single-host SQLite anti-replay admission; fails closed on IO errors."""
    if not isinstance(database_path, (str, Path)):
        raise PolicyError("invalid_replay_db")
    try:
        with sqlite3.connect(str(database_path), timeout=5, isolation_level=None) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("CREATE TABLE IF NOT EXISTS used_nonce ("
                         "principal TEXT NOT NULL, nonce TEXT NOT NULL,"
                         "expires_at INTEGER NOT NULL, PRIMARY KEY(principal, nonce))")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM used_nonce WHERE expires_at <= ?", (int(now.timestamp()),))
            conn.execute("INSERT INTO used_nonce(principal, nonce, expires_at) VALUES (?,?,?)",
                         (principal, nonce, int(expires_at.timestamp())))
            conn.execute("COMMIT")
    except sqlite3.IntegrityError as exc:
        raise PolicyError("replayed_nonce") from exc
    except (sqlite3.DatabaseError, OSError, OverflowError, ValueError) as exc:
        raise PolicyError("replay_store_unavailable") from exc


def execute_local(request, payload):
    """Closed dispatch table: no shell, network, credentials or external writes."""
    if request["action"] == "health.inspect":
        return {"ok": True, "service": "agent-economy-local-policy-gate",
                "scope": "local_self_check_not_production_health"}
    if request["action"] == "evidence.inspect":
        raw = payload["text"].encode("utf-8")
        return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                "note": "caller_supplied_bytes_only_not_independent_execution_proof"}
    raise PolicyError("unsupported_local_execution")


def authorize_and_execute(policy, envelope, trusted_keys, replay_db, *, clock=None):
    now = clock if clock is not None else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise PolicyError("invalid_clock")
    now = now.astimezone(timezone.utc)
    expires_at = verify_signed_envelope(envelope, trusted_keys, now)
    decision = evaluate(policy, envelope["request"], clock=now)
    metadata = {
        "schema": RESULT_SCHEMA,
        "principal_authenticated_by_shared_key": True,
        "real_world_identity_verified": False,
        "external_authorization_granted": False,
        "payment_authorized": False,
        "matching_rule_ids": decision["matching_rule_ids"],
        "policy_sha256": decision["policy_sha256"],
    }
    if decision["decision"] != "allow":
        return {**metadata, "decision": "deny", "reason": decision["reason"],
                "action_executed": False}
    validate_execution(envelope["request"], envelope["payload"])
    # Reserve before dispatch. A failed local task cannot be retried with the
    # same nonce; never interpret this as a financial exactly-once guarantee.
    reserve_nonce(replay_db, envelope["request"]["principal"], envelope["nonce"], expires_at, now)
    result = execute_local(envelope["request"], envelope["payload"])
    return {**metadata, "decision": "allow", "reason": "signed_policy_and_nonce_verified",
            "action_executed": True, "result": result}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True, help="Trusted operator policy path")
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--replay-db", type=Path, required=True, help="Durable trusted local SQLite file")
    args = parser.parse_args(argv)
    try:
        result = authorize_and_execute(
            read_strict_json(args.policy), read_strict_json(args.envelope),
            load_trusted_keys(), args.replay_db
        )
    except (PolicyError, OSError, sqlite3.Error, TypeError, ValueError, OverflowError):
        result = {"schema": RESULT_SCHEMA, "decision": "deny",
                  "reason": "authentication_or_policy_failure",
                  "principal_authenticated_by_shared_key": False,
                  "real_world_identity_verified": False,
                  "external_authorization_granted": False,
                  "payment_authorized": False,
                  "action_executed": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["decision"] == "allow" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Offline x402-v2 quote + atomic budget reservation; NEVER signs, pays or executes.

Trust boundary: trusted local operator owns policy and database. Calling agents' claimed
identities, quote contents and operation IDs are NOT independently authenticated.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
EVM_ADDRESS = re.compile(r"0x[a-fA-F0-9]{40}\Z", re.ASCII)
ATOMIC = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}\Z", re.ASCII)
MAX_CAPTURE_BYTES = 64 * 1024
MAX_BUDGET = 10**12  # micro-USDC; 1 million USDC upper hard cap for arithmetic


class InvalidInput(ValueError):
    pass


def _unique_json_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InvalidInput("duplicate_json_key")
        out[key] = value
    return out


def read_challenge(raw: bytes) -> dict:
    if not 0 < len(raw) <= MAX_CAPTURE_BYTES:
        raise InvalidInput("invalid_capture_size")
    if raw.lstrip().startswith(b"{"):
        data = raw
    else:
        try:
            header = raw.decode("ascii")
            if not re.fullmatch(r"[A-Za-z0-9_+/=-]+", header):
                raise InvalidInput("invalid_header_encoding")
            standard = header.replace("-", "+").replace("_", "/")
            if len(standard) % 4 == 1:
                raise InvalidInput("invalid_header_encoding")
            standard += "=" * ((4 - len(standard) % 4) % 4)
            data = base64.b64decode(standard, validate=True)
        except (UnicodeError, binascii.Error, ValueError) as exc:
            raise InvalidInput("invalid_header_encoding") from exc
    if not 0 < len(data) <= MAX_CAPTURE_BYTES:
        raise InvalidInput("invalid_capture_size")
    try:
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_json_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(InvalidInput("nonfinite_number")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InvalidInput("invalid_json") from exc
    if not isinstance(parsed, dict):
        raise InvalidInput("invalid_root")
    return parsed


def _policy(policy: dict) -> dict:
    if not isinstance(policy, dict):
        raise InvalidInput("invalid_policy")
    url = policy.get("resource_url")
    try:
        parts = urlsplit(url)
        valid_url = (parts.scheme == "https" and bool(parts.hostname) and
                     not parts.username and not parts.password and not parts.fragment and
                     not any(c.isspace() for c in url))
    except (ValueError, TypeError):
        valid_url = False
    if not valid_url:
        raise InvalidInput("invalid_resource_pin")
    payee = policy.get("payee")
    if not isinstance(payee, str) or not EVM_ADDRESS.fullmatch(payee):
        raise InvalidInput("invalid_payee_pin")
    max_quote = policy.get("max_quote_micro")
    daily = policy.get("daily_budget_micro")
    if (type(max_quote) is not int or type(daily) is not int or
            not 0 < max_quote <= daily <= MAX_BUDGET):
        raise InvalidInput("invalid_budget_policy")
    return {
        "resource_url": url, "payee": payee.lower(), "max_quote_micro": max_quote,
        "daily_budget_micro": daily, "network": "eip155:8453", "asset": BASE_USDC.lower(),
    }


def inspect_quote(challenge: dict, policy: dict) -> tuple[list[str], int | None]:
    errors = []
    if type(challenge.get("x402Version")) is not int or challenge["x402Version"] != 2:
        errors.append("wrong_x402_version")
    resource = challenge.get("resource")
    if not isinstance(resource, dict) or resource.get("url") != policy["resource_url"]:
        errors.append("resource_mismatch")
    offers = challenge.get("accepts")
    if not isinstance(offers, list) or len(offers) != 1 or not isinstance(offers[0], dict):
        return errors + ["requires_one_offer"], None
    offer = offers[0]
    if offer.get("scheme") != "exact":
        errors.append("scheme_mismatch")
    if offer.get("network") != policy["network"]:
        errors.append("network_mismatch")
    for field, pinned in (("asset", policy["asset"]), ("payTo", policy["payee"])):
        value = offer.get(field)
        if not isinstance(value, str) or value.lower() != pinned:
            errors.append(field + "_mismatch")
    raw = offer.get("amount")
    if not isinstance(raw, str) or len(raw) > 16 or not ATOMIC.fullmatch(raw):
        errors.append("invalid_amount")
        amount = None
    else:
        amount = int(raw)
        if not 0 < amount <= policy["max_quote_micro"]:
            errors.append("amount_exceeds_pin")
    timeout = offer.get("maxTimeoutSeconds")
    if type(timeout) is not int or not 10 <= timeout <= 300:
        errors.append("invalid_timeout")
    return errors, amount


def _sha(value: dict) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _result(state: str, *, new_reservation: bool = False,
            errors: list[str] | None = None, total_reserved_micro: int | None = None) -> dict:
    return {
        "schema": "agent-economy.atomic-preflight.v1",
        "state": state, "eligible_for_new_execution": False,
        "reservation_created": new_reservation,
        "errors": errors or [], "total_reserved_today_micro": total_reserved_micro,
        "payment_authorized": False, "payment_executed": False,
        "settlement_verified": False, "identity_verified": False,
    }


def reserve_quote(*, challenge: dict, raw_policy: dict, operation_id: str,
                  db_path: str | Path) -> dict:
    """Create a conservative, atomic local budget reservation. Never pays or authorizes.

    A repeated ID, even with identical terms, is REJECTED for another execution.
    Future operations must have unique IDs from a trusted orchestrator.
    Reservations do not expire automatically, so failures cannot free budget silently.
    """
    try:
        policy = _policy(raw_policy)
    except InvalidInput as exc:
        return _result("policy_rejected", errors=[str(exc)])
    if not isinstance(operation_id, str) or not IDENTIFIER.fullmatch(operation_id):
        return _result("invalid_operation_id", errors=["invalid_operation_id"])
    if not isinstance(challenge, dict):
        return _result("quote_rejected", errors=["invalid_challenge"])
    errors, amount = inspect_quote(challenge, policy)
    if errors:
        return _result("quote_rejected", errors=errors)
    quote_digest = _sha({"quote": challenge, "resource": policy["resource_url"]})
    policy_digest = _sha(policy)
    day = datetime.now(timezone.utc).date().isoformat()
    # SQLite BEGIN IMMEDIATE serializes competing reservations across processes.
    # SQLite error => deny; no fallback to permissive in-memory counters.
    connection = None
    try:
        connection = sqlite3.connect(str(db_path), timeout=4, isolation_level=None)
        connection.execute("PRAGMA busy_timeout=4000")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS policy_lock (singleton INTEGER PRIMARY KEY CHECK(singleton=1), fingerprint TEXT NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS reservations (operation_id TEXT PRIMARY KEY, quote_sha TEXT NOT NULL, amount_micro INTEGER NOT NULL CHECK(amount_micro>0), day_utc TEXT NOT NULL)")
        row = connection.execute("SELECT fingerprint FROM policy_lock WHERE singleton=1").fetchone()
        if row is None:
            connection.execute("INSERT INTO policy_lock VALUES (1, ?)", (policy_digest,))
        elif row[0] != policy_digest:
            connection.rollback()
            return _result("policy_lock_mismatch", errors=["policy_changed_db_reuse_denied"])
        original = connection.execute("SELECT quote_sha FROM reservations WHERE operation_id=?", (operation_id,)).fetchone()
        if original is not None:
            connection.rollback()
            return _result("duplicate_operation" if original[0] == quote_digest else "operation_conflict",
                           errors=["replay_blocked" if original[0] == quote_digest else "operation_id_reused_with_different_quote"])
        used = connection.execute("SELECT COALESCE(SUM(amount_micro), 0) FROM reservations WHERE day_utc=?", (day,)).fetchone()[0]
        if used + amount > policy["daily_budget_micro"]:
            connection.rollback()
            return _result("budget_exceeded", errors=["daily_budget_exceeded"], total_reserved_micro=used)
        connection.execute("INSERT INTO reservations (operation_id, quote_sha, amount_micro, day_utc) VALUES (?, ?, ?, ?)",
                           (operation_id, quote_digest, amount, day))
        connection.commit()
        return _result("reserved_preflight_only", new_reservation=True, total_reserved_micro=used + amount)
    except (sqlite3.Error, OSError, OverflowError):
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
        return _result("ledger_unavailable", errors=["fail_closed"])
    finally:
        if connection is not None:
            connection.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture", required=True, type=Path)
    p.add_argument("--db", required=True, type=Path)
    p.add_argument("--operation-id", required=True)
    p.add_argument("--expected-url", required=True)
    p.add_argument("--expected-payee", required=True)
    p.add_argument("--max-quote-micro", required=True, type=int)
    p.add_argument("--daily-budget-micro", required=True, type=int)
    args = p.parse_args(argv)
    try:
        if args.capture.stat().st_size > MAX_CAPTURE_BYTES:
            raise InvalidInput("invalid_capture_size")
        challenge = read_challenge(args.capture.read_bytes())
        result = reserve_quote(challenge=challenge, operation_id=args.operation_id,
            db_path=args.db, raw_policy={"resource_url": args.expected_url,
            "payee": args.expected_payee, "max_quote_micro": args.max_quote_micro,
            "daily_budget_micro": args.daily_budget_micro})
    except (InvalidInput, OSError) as exc:
        result = _result("capture_rejected", errors=["invalid_capture"])
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["reservation_created"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
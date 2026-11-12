#!/usr/bin/env python3
"""Offline, fail-closed x402-v2 payment-challenge inspector. This never pays or signs."""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import sys
from pathlib import Path
from typing import Any

BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
HEX_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")
ATOMIC_AMOUNT = re.compile(r"(?:0|[1-9][0-9]*)\Z")
MAX_CAPTURE_BYTES = 64 * 1024


class InvalidChallenge(ValueError):
    pass


def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise InvalidChallenge("duplicate_json_key")
        output[key] = value
    return output


def read_challenge(data: bytes) -> dict[str, Any]:
    """Accept decoded JSON or exact Base64 PAYMENT-REQUIRED header content."""
    if not data or len(data) > MAX_CAPTURE_BYTES:
        raise InvalidChallenge("capture_missing_or_oversized")
    try:
        text = data.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise InvalidChallenge("capture_must_be_ascii") from exc
    if not text.startswith("{"):
        if not re.fullmatch(r"[A-Za-z0-9+/=_-]+", text):
            raise InvalidChallenge("invalid_base64_header")
        try:
            # URL-safe encoding is accepted; padding length is validated by decoder.
            padded = text.replace("-", "+").replace("_", "/")
            decoded = base64.b64decode(padded, validate=True)
            text = decoded.decode("ascii")
        except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
            raise InvalidChallenge("invalid_base64_header") from exc
        if len(decoded) > MAX_CAPTURE_BYTES:
            raise InvalidChallenge("capture_missing_or_oversized")
    try:
        root = json.loads(text, object_pairs_hook=no_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidChallenge("invalid_json") from exc
    if not isinstance(root, dict):
        raise InvalidChallenge("challenge_must_be_object")
    return root


def inspect(
    challenge: dict[str, Any], *, expected_url: str, expected_payee: str,
    max_atomic: int, network: str = "eip155:8453",
    asset: str = BASE_USDC,
) -> dict[str, Any]:
    """Validate a single, exact-chain/asset/payee/resource x402-v2 offer.

    A passing preflight is *not* authorization, settlement, fraud prevention,
    receipt evidence, or assurance that the merchant will deliver anything.
    """
    if not expected_url.startswith("https://") or any(ch.isspace() for ch in expected_url):
        raise ValueError("expected_url_must_be_https")
    if not HEX_ADDRESS.fullmatch(expected_payee) or not HEX_ADDRESS.fullmatch(asset):
        raise ValueError("invalid_pinned_address")
    if isinstance(max_atomic, bool) or not isinstance(max_atomic, int) or max_atomic <= 0:
        raise ValueError("max_atomic_must_be_positive_integer")
    problems: list[str] = []
    version = challenge.get("x402Version")
    if type(version) is not int or version != 2:
        problems.append("unsupported_x402_version")
    resource = challenge.get("resource")
    uri = resource.get("url") if isinstance(resource, dict) else resource
    if not isinstance(uri, str) or uri != expected_url:
        problems.append("resource_url_mismatch")
    accepts = challenge.get("accepts")
    if not isinstance(accepts, list) or len(accepts) != 1 or not isinstance(accepts[0], dict):
        problems.append("requires_exactly_one_payment_offer")
        accepts = []
    amount: int | None = None
    if accepts:
        offer = accepts[0]
        if offer.get("scheme") != "exact":
            problems.append("scheme_mismatch")
        if offer.get("network") != network:
            problems.append("network_mismatch")
        offered_asset = offer.get("asset")
        if not isinstance(offered_asset, str) or offered_asset.lower() != asset.lower():
            problems.append("asset_mismatch")
        offered_payee = offer.get("payTo")
        if not isinstance(offered_payee, str) or offered_payee.lower() != expected_payee.lower():
            problems.append("payee_mismatch")
        raw = offer.get("amount")
        if not isinstance(raw, str) or not ATOMIC_AMOUNT.fullmatch(raw):
            problems.append("invalid_atomic_amount")
        else:
            amount = int(raw)
            if amount < 1 or amount > max_atomic:
                problems.append("amount_outside_pinned_limit")
        timeout = offer.get("maxTimeoutSeconds")
        if type(timeout) is not int or not 10 <= timeout <= 300:
            problems.append("timeout_outside_pinned_range")
    return {
        "schema": "agent-economy.x402-v2-quote-preflight.v1",
        "eligible": not problems,
        "errors": problems,
        "network": network,
        "resource": expected_url,
        "max_micro_usdc": str(max_atomic),
        "offered_micro_usdc": str(amount) if amount is not None else None,
        "payment_authorized": False,
        "payment_executed": False,
        "disclaimer": "Offline quote consistency only; owner authorization and on-chain settlement remain separate.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="Decoded JSON or Base64 PAYMENT-REQUIRED header in a local file")
    parser.add_argument("--expected-url", required=True, help="Exact HTTPS resource URL pinned by the buyer")
    parser.add_argument("--expected-payee", required=True, help="Expected merchant wallet; never learn from the challenge")
    parser.add_argument("--max-atomic", required=True, type=int, help="Maximum allowed micro-USDC, e.g. 10000 = 0.01 USDC")
    args = parser.parse_args(argv)
    try:
        if args.capture.stat().st_size > MAX_CAPTURE_BYTES:
            raise InvalidChallenge("capture_missing_or_oversized")
        quote = read_challenge(args.capture.read_bytes())
        verdict = inspect(quote, expected_url=args.expected_url,
                          expected_payee=args.expected_payee, max_atomic=args.max_atomic)
    except (InvalidChallenge, ValueError, OSError) as exc:
        # Never echo arbitrary capture content, passwords, URLs or filesystem paths.
        reason = str(exc) if isinstance(exc, InvalidChallenge) else "invalid_input_or_capture"
        verdict = {"schema": "agent-economy.x402-v2-quote-preflight.v1",
                   "eligible": False, "errors": [reason],
                   "payment_authorized": False, "payment_executed": False}
    print(json.dumps(verdict, sort_keys=True, separators=(",", ":")))
    return 0 if verdict["eligible"] else 2


if __name__ == "__main__":
    sys.exit(main())

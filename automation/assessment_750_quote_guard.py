#!/usr/bin/env python3
"""Check one public synthetic buyer path to an UNSIGNED x402 v2 price challenge.

Three fixed, allowlisted requests: GET public example input, POST free preflight,
POST the same fake aggregate to the paid URL WITHOUT PAYMENT-SIGNATURE.
A valid 402 is NOT a successful purchase, delivery, settlement, or a paid call.
No credentials, real users, customer data, wallet keys or signing.
"""
import argparse
import base64
import binascii
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from automation.agent_buyer_smoke import NoRedirect, parse_strict

BASE = "https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-automated-assessment"
SAMPLE = BASE + "/example-input.json"
PREFLIGHT = BASE + "/preflight"
REPORT = BASE + "/report"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PAYEE = "0x935ad91b70c6d0769871416c5904d06fbf9ef586"
MAX_BYTES = 24_000
MAX_HEADER = 16_000


def error(message):
    raise ValueError(message)


def json_200(response):
    if response.status != 200:
        error("unexpected_status")
    if not response.headers.get("Content-Type", "").lower().startswith("application/json"):
        error("not_json")
    payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        error("response_too_large")
    value = parse_strict(payload)
    if not isinstance(value, dict) or value.get("error"):
        error("bad_json_document")
    return value


def request(method, url, body=None):
    if (method, url) not in (("GET", SAMPLE), ("POST", PREFLIGHT), ("POST", REPORT)):
        error("request_not_allowlisted")
    headers = {"Accept": "application/json",
               "User-Agent": "AgentEconomy-UnsignedPriceGuard/1.0"}
    if body is not None:
        if method != "POST":
            error("unexpected_request_body")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    if any("payment" in name.lower() or "authorization" in name.lower()
           for name in req.headers):
        error("payment_or_auth_header_forbidden")
    return req


def parse_payment_header(encoded):
    if not isinstance(encoded, str) or not (0 < len(encoded) <= MAX_HEADER):
        error("missing_or_large_payment_required")
    if not re.fullmatch(r"[A-Za-z0-9+/=_-]+", encoded):
        error("invalid_payment_header_characters")
    try:
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4),
                               altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        error("invalid_payment_header_encoding")
    if len(raw) > MAX_BYTES:
        error("oversize_payment_challenge")
    return parse_strict(raw)


def check_challenge(challenge):
    if not isinstance(challenge, dict) or type(challenge.get("x402Version")) is not int or challenge["x402Version"] != 2:
        error("not_x402_v2")
    resource = challenge.get("resource")
    if not isinstance(resource, dict) or resource.get("url") != REPORT:
        error("resource_not_exactly_pinned")
    offers = challenge.get("accepts")
    if not isinstance(offers, list) or len(offers) != 1 or not isinstance(offers[0], dict):
        error("ambiguous_or_missing_offers")
    offer = offers[0]
    if (offer.get("scheme") != "exact"
            or offer.get("network") != "eip155:8453"
            or offer.get("amount") != "750000000"
            or not isinstance(offer.get("asset"), str)
            or offer["asset"].lower() != USDC.lower()
            or not isinstance(offer.get("payTo"), str)
            or offer["payTo"].lower() != PAYEE.lower()):
        error("payment_terms_mismatch")
    return {"network": "eip155:8453", "asset": "native_base_usdc",
            "amount_atomic": "750000000", "amount_usdc": "750.00",
            "payee_matches_deployed_offer": True}


def run(opener=None):
    opener = opener or build_opener(NoRedirect())
    report = {"schema": "agent-economy.unsigned-assessment-quote.v1",
              "ok": False, "source": "synthetic_public_example_only",
              "unsigned_paid_resource_requests": 0,
              "signed_payment_requests": 0,
              "payments_executed": 0,
              "delivery_verified": False,
              "customer_or_revenue_verified": False}
    try:
        with opener.open(request("GET", SAMPLE), timeout=8) as response:
            sample = json_200(response)
        if sample.get("synthetic") is not True or sample.get("paid") is not False:
            error("example_not_public_and_synthetic")
        body = sample.get("input")
        if not isinstance(body, dict) or body.get("schema") != "agent-economy.reuse-guard.offline-evaluation.v1":
            error("invalid_example_input")
        if body.get("consent") != {"data_rights": True, "no_personal_data": True,
                                   "accepted_automated_scope": True}:
            error("invalid_example_consent")
        payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(payload) > MAX_BYTES:
            error("example_input_too_large")
        with opener.open(request("POST", PREFLIGHT, payload), timeout=8) as response:
            pre = json_200(response)
        if (pre.get("ok") is not True or pre.get("preflight") is not True
                or pre.get("paid") is not False or pre.get("amount_charged") != 0
                or pre.get("report_delivered") is not False
                or pre.get("price_usdc") != "750.00"
                or not isinstance(pre.get("input_sha256"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", pre["input_sha256"])):
            error("invalid_free_preflight")
        report["free_preflight_validated"] = True
        report["unsigned_paid_resource_requests"] = 1
        try:
            with opener.open(request("POST", REPORT, payload), timeout=8) as response:
                error("missing_402_price_challenge")
        except HTTPError as response:
            if response.code != 402 or response.geturl() != REPORT:
                error("unexpected_quote_http_status_or_redirect")
            challenge = parse_payment_header(response.headers.get("PAYMENT-REQUIRED"))
        report["verified_quote"] = check_challenge(challenge)
        report["ok"] = True
    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeError, OSError) as exc:
        report["error"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    return report


def main():
    p = argparse.ArgumentParser(description="Read-only synthetic preflight and unsigned 402 quote; no payment")
    p.parse_args()
    result = run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

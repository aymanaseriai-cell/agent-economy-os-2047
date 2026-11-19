#!/usr/bin/env python3
"""No-dependency, public-test-data-only client for Agent Economy Work Covenant.

This does not verify who authored an artifact, who a buyer is, or whether any
payment occurred. By default it makes no network requests.
"""
import argparse
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

GATEWAY = "https://agent-economy-wc-failover.agent-economy-os2047.workers.dev"
PRIMARY = "https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047"
ENDPOINTS = {"gateway": GATEWAY, "primary": PRIMARY}
MAX_RESPONSE = 65_536
MAX_REQUEST = 16_384
SHA256 = re.compile(r"^[a-f0-9]{64}$")


class DemoError(Exception):
    """A predictable failure with no raw response data or credentials."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DemoError("redirect_refused")


def transport(opener=None):
    return opener if opener is not None else build_opener(NoRedirects())


def json_request(path, *, origin="gateway", payload=None, opener=None):
    if origin not in ENDPOINTS or path not in ("/demo", "/v1/evaluate"):
        raise DemoError("unsupported_api_target")
    if (path == "/demo") != (payload is None):
        raise DemoError("invalid_method_for_path")
    body = None
    if payload is not None:
        try:
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False,
                              allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise DemoError("invalid_request_payload") from exc
        if len(body) > MAX_REQUEST:
            raise DemoError("request_too_large")
    req = Request(
        ENDPOINTS[origin] + path,
        data=body,
        method="POST" if body is not None else "GET",
        headers={"Accept": "application/json", "Content-Type": "application/json",
                 "User-Agent": "Agent-Economy-Work-Covenant-Example/1.0"},
    )
    try:
        with transport(opener).open(req, timeout=12) as res:
            if res.status != 200:
                raise DemoError("unexpected_http_status")
            declared = res.headers.get("Content-Length")
            if declared is not None and (not declared.isdecimal() or int(declared) > MAX_RESPONSE):
                raise DemoError("response_too_large")
            data = res.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                raise DemoError("response_too_large")
    except HTTPError as exc:
        raise DemoError("http_error_" + str(exc.code)) from None
    except (URLError, OSError, TimeoutError) as exc:
        raise DemoError("network_unavailable") from None
    try:
        parsed = json.loads(data.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DemoError("invalid_json_response") from exc
    if not isinstance(parsed, dict):
        raise DemoError("expected_object_response")
    return parsed


def validate_demo(demo):
    if (demo.get("ok") is not True or not isinstance(demo.get("contract"), dict)
            or not isinstance(demo.get("sample_submission"), dict)
            or not isinstance(demo.get("contract_id"), str)
            or SHA256.fullmatch(demo["contract_id"]) is None):
        raise DemoError("invalid_demo_contract")
    return {"contract": demo["contract"], "contract_id": demo["contract_id"],
            "submission": demo["sample_submission"]}


def validate_evaluation(result, expected_contract_id):
    if (result.get("ok") is not True
            or result.get("status") != "local_checks_passed"
            or result.get("contract_id") != expected_contract_id
            or not isinstance(result.get("proof_id"), str)
            or SHA256.fullmatch(result["proof_id"]) is None
            or result.get("buyer_acceptance_verified") is not False
            or result.get("payment_verified") is not False
            or result.get("onchain_settlement_verified") is not False
            or result.get("evidence_covers_supplied_bytes_only") is not True
            or not isinstance(result.get("results"), list)
            or not result["results"]
            or any(not isinstance(check, dict) or check.get("pass") is not True
                   for check in result["results"])):
        raise DemoError("unexpected_or_unsafe_demo_result")
    return {"demo_only": True, "status": result["status"],
            "contract_id": expected_contract_id, "proof_id": result["proof_id"],
            "checks_passed": len(result["results"]),
            "buyer_acceptance_verified": False, "payment_verified": False,
            "technical_proof_of_caller_supplied_data_only": True}


def run_live(origin="gateway", opener=None):
    demo = json_request("/demo", origin=origin, opener=opener)
    data = validate_demo(demo)
    result = json_request("/v1/evaluate", origin=origin, payload=data, opener=opener)
    return validate_evaluation(result, data["contract_id"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Send public demo data only, to official API")
    parser.add_argument("--origin", choices=tuple(ENDPOINTS), default="gateway")
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({"network_requests_made": False, "usage": "Run --live for a public-data-only demo",
                          "endpoint": ENDPOINTS[args.origin], "payment_required": False}, sort_keys=True))
        return 0
    try:
        print(json.dumps(run_live(args.origin), sort_keys=True))
        return 0
    except DemoError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "payment_verified": False}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Check the live PUBLIC Work Covenant with synthetic data only.

Four allowlisted requests: GET /demo, POST /v1/compile, POST /v1/evaluate
passing fixture, POST /v1/evaluate tampered fixture. Never redirects, pays,
sends secrets, claims independent buyer acceptance, or tests real customers.
"""
import copy
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from automation.agent_buyer_smoke import NoRedirect, parse_strict

BASE = "https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047"
DEMO = BASE + "/demo"
COMPILE = BASE + "/v1/compile"
EVALUATE = BASE + "/v1/evaluate"
MAX_BYTES = 32768
MAX_BODY = 16384


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def build_request(method, url, payload=None):
    require((method, url) in (("GET", DEMO), ("POST", COMPILE), ("POST", EVALUATE)),
            "non_allowlisted_endpoint")
    require(method == "POST" or payload is None, "body_on_get")
    data = None
    headers = {"Accept": "application/json",
               "User-Agent": "AgentEconomy-PublicWorkCovenantSyntheticSmoke/1.0"}
    if method == "POST":
        require(isinstance(payload, dict), "post_requires_json_object")
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        require(0 < len(data) < MAX_BODY, "request_too_large")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    require(not any("payment" in k.lower() or "authorization" in k.lower()
                    for k in req.headers), "forbidden_sensitive_header")
    return req


def get_json(opener, request):
    with opener.open(request, timeout=8) as response:
        require(response.status == 200, "non_200_response")
        require(response.headers.get("Content-Type", "").lower().startswith("application/json"),
                "non_json_response")
        raw = response.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "oversize_response")
    payload = parse_strict(raw)
    require(isinstance(payload, dict) and payload.get("ok") is True
            and "error" not in payload, "invalid_service_response")
    return payload


def no_commercial_claims(payload):
    for field in ("buyer_acceptance_verified", "payment_verified", "onchain_settlement_verified"):
        require(payload.get(field) is False, "unexpected_commercial_claim_" + field)
    require(payload.get("evidence_covers_supplied_bytes_only") is True,
            "missing_scope_disclaimer")


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def run(opener=None):
    opener = opener or build_opener(NoRedirect())
    output = {"schema": "agent-economy.work-covenant-live-buyer-smoke.v1",
              "ok": False, "completed_requests": 0, "payment_requests": 0,
              "customer_or_revenue_verified": False, "buyer_authorization_verified": False,
              "scope": "Public synthetic local checks; not external acceptance or paid delivery"}
    try:
        demo = get_json(opener, build_request("GET", DEMO))
        output["completed_requests"] += 1
        require(isinstance(demo.get("contract"), dict)
                and isinstance(demo.get("sample_submission"), dict)
                and valid_id(demo.get("contract_id")), "invalid_demo")
        contract = demo["contract"]
        require(isinstance(contract.get("task"), dict)
                and isinstance(contract.get("criteria"), list)
                and len(contract["criteria"]) == 3, "unexpected_demo_contract")
        compiled = get_json(opener, build_request("POST", COMPILE, {
            "task": contract["task"], "criteria": contract["criteria"]
        }))
        output["completed_requests"] += 1
        require(compiled.get("status") == "compiled"
                and compiled.get("contract") == contract
                and compiled.get("contract_id") == demo["contract_id"],
                "compile_contract_mismatch")
        output["compiled_id_verified"] = True
        request_body = {"contract": contract, "contract_id": demo["contract_id"],
                        "submission": demo["sample_submission"]}
        positive = get_json(opener, build_request("POST", EVALUATE, request_body))
        output["completed_requests"] += 1
        no_commercial_claims(positive)
        require(positive.get("status") == "local_checks_passed"
                and positive.get("contract_id") == demo["contract_id"]
                and positive.get("passed") == positive.get("total") == 3
                and valid_id(positive.get("proof_id"))
                and isinstance(positive.get("results"), list)
                and len(positive["results"]) == 3
                and all(x.get("pass") is True for x in positive["results"]),
                "positive_fixture_not_passed")
        output["untampered_fixture_accepted"] = True
        negative_body = copy.deepcopy(request_body)
        artifacts = negative_body["submission"].get("artifacts")
        require(isinstance(artifacts, list) and len(artifacts) == 1
                and artifacts[0].get("name") == "report.json", "unexpected_artifact_fixture")
        original = artifacts[0].get("content")
        require(isinstance(original, str) and parse_strict(original.encode("utf-8")) == {"ok": True},
                "unexpected_artifact_content")
        artifacts[0]["content"] = '{"ok":false}'
        negative = get_json(opener, build_request("POST", EVALUATE, negative_body))
        output["completed_requests"] += 1
        no_commercial_claims(negative)
        require(negative.get("status") == "local_checks_failed"
                and negative.get("contract_id") == demo["contract_id"]
                and negative.get("passed") == 2
                and negative.get("total") == 3
                and valid_id(negative.get("proof_id"))
                and negative.get("proof_id") != positive["proof_id"]
                and isinstance(negative.get("results"), list)
                and len(negative["results"]) == 3
                and any(x.get("id") == "status_ok" and x.get("pass") is False
                        for x in negative["results"]), "tamper_not_detected")
        output["tampered_fixture_rejected"] = True
        output["ok"] = True
    except (HTTPError, URLError, ValueError, TimeoutError, OSError, UnicodeError) as exc:
        output["error"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    return output


def main():
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

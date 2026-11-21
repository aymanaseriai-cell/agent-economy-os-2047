#!/usr/bin/env python3
"""Reproducible public Work Covenant smoke test (no keys, payments or customer data)."""
import copy
import json
import sys
from urllib.request import Request, urlopen

BASE = "https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047"

def live_json(path, payload=None):
    if path not in ("/demo", "/v1/evaluate"):
        raise ValueError("Unsupported path")
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    req = Request(BASE + path, data=data, method="GET" if data is None else "POST",
                  headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urlopen(req, timeout=12) as response:
        if response.status != 200:
            raise RuntimeError("Unexpected response status")
        raw = response.read(32769)
    if len(raw) > 32768:
        raise RuntimeError("Response too large")
    return json.loads(raw)

def require(value, error):
    if not value:
        raise RuntimeError(error)

def check(client=live_json):
    demo = client("/demo")
    require(isinstance(demo, dict) and demo.get("ok") is True, "Invalid demo")
    contract, contract_id = demo["contract"], demo["contract_id"]
    sample = demo["sample_submission"]
    require(isinstance(contract_id, str) and isinstance(sample, dict), "Bad demo contract")
    positive = client("/v1/evaluate", {"contract": contract, "contract_id": contract_id,
                                      "submission": sample})
    require(positive.get("status") == "local_checks_passed", "Positive control failed")
    altered = copy.deepcopy(sample)
    artifacts = altered.get("artifacts")
    require(isinstance(artifacts, list), "No artifacts")
    reports = [a for a in artifacts if isinstance(a, dict) and a.get("name") == "report.json"]
    require(len(reports) == 1, "Expected exactly one report.json")
    reports[0]["content"] = '{"ok":false}'
    negative = client("/v1/evaluate", {"contract": contract, "contract_id": contract_id,
                                      "submission": altered})
    require(negative.get("status") == "local_checks_failed", "Tampered output passed")
    checks = negative.get("results")
    require(isinstance(checks, list) and any(
        isinstance(x, dict) and x.get("id") == "status_ok" and x.get("pass") is False
        for x in checks), "Missing negative-case failing criterion")
    for label, response in (("positive", positive), ("negative", negative)):
        require(response.get("contract_id") == contract_id, label + ": contract drift")
        for key in ("buyer_acceptance_verified", "payment_verified", "onchain_settlement_verified"):
            require(response.get(key) is False, label + ": unsupported " + key)
    return {
        "schema": "agent-economy.live-api-smoke/1",
        "public_endpoint": BASE, "positive": "local_checks_passed",
        "tampered_negative": "local_checks_failed",
        "customer_adoption_verified": False, "payment_verified": False,
        "trust_boundary": "Synthetic caller-supplied bytes only; no buyer acceptance or sale",
    }

if __name__ == "__main__":
    try:
        print(json.dumps(check(), indent=2, sort_keys=True))
    except (ValueError, TypeError, KeyError, RuntimeError, OSError, TimeoutError,
            json.JSONDecodeError) as exc:
        print("LIVE_SMOKE_FAIL_CLOSED: " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        sys.exit(1)

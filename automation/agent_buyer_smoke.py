#!/usr/bin/env python3
"""No-payment, fail-closed smoke check for public Agent Economy discovery URLs.

Only fixed free GET endpoints. Does not visit x402 paid resources, send payment
headers, sign anything, or validate customers/revenue. Never follows redirects.
"""
import argparse
import json
import math
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "agent-services.json"
HOST = "https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1"

# Each key is present in the on-disk catalog. Never derive a URL from caller input.
CHECKS = (
    ("work_covenant_free", "demo", HOST + "/agent-work-covenant-2047/demo"),
    ("base_usdc_receipt_lite", "demo", HOST + "/agent-usdc-receipt-lite/api/v1/demo"),
    ("base_usdc_receipt", "demo", HOST + "/agent-usdc-receipt/api/v1/demo"),
    ("automated_assessment_750", "sample_report", HOST + "/agent-automated-assessment/sample-report"),
    ("automated_assessment_750", "offer_card", HOST + "/agent-assessment-750-a2a/.well-known/agent-card.json"),
)
MAX_RESPONSE_BYTES = 32768


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def reject_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate_json_key")
        obj[key] = value
    return obj


def reject_constant(token):
    raise ValueError("non_standard_json_constant")


def finite_float(token):
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("non_finite_json_float")
    return value


def parse_strict(raw):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates,
                      parse_constant=reject_constant, parse_float=finite_float)


def inspect_target(service, key, expected_url, opener):
    actual = service.get(key)
    item = {"service": service.get("id"), "check": key,
            "status": "UNVERIFIED", "payment_attempted": False}
    # Equality includes scheme, authority, full path, absent query, and fragment.
    if actual != expected_url:
        item["reason"] = "catalog_url_not_exactly_allowlisted"
        return item
    req = Request(actual, method="GET", headers={
        "Accept": "application/json",
        "User-Agent": "AgentEconomy-ReadOnlyDiscoveryProbe/1.0",
    })
    try:
        with opener.open(req, timeout=8) as response:
            if response.status != 200:
                item["reason"] = "unexpected_http_status"
                item["http_status"] = response.status
                return item
            content_type = response.headers.get("Content-Type", "").lower()
            if not content_type.startswith("application/json"):
                item["reason"] = "not_json_response"
                return item
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            item["reason"] = "response_over_size_limit"
            return item
        value = parse_strict(raw)
        if not isinstance(value, dict) or not value or "error" in value:
            item["reason"] = "unexpected_json_shape"
            return item
        if key == "offer_card":
            if not isinstance(value.get("skills"), list) or not isinstance(value.get("supportedInterfaces"), list):
                item["reason"] = "invalid_agent_card"
                return item
        elif service.get("id") == "work_covenant_free":
            if not {"contract", "contract_id", "sample_submission"}.issubset(value):
                item["reason"] = "invalid_work_covenant_demo"
                return item
        item["status"] = "REACHABLE_DEMO_ONLY"
        item["http_status"] = 200
    except HTTPError as exc:
        item["reason"] = "http_error"
        item["http_status"] = exc.code
    except (URLError, TimeoutError, ValueError, UnicodeError, OSError) as exc:
        item["reason"] = "transport_or_json_error"
        item["exception_type"] = type(exc).__name__
    return item


def run(catalog_path=CATALOG, opener=None):
    opener = opener or build_opener(NoRedirect())
    data = parse_strict(Path(catalog_path).read_bytes())
    if not isinstance(data, dict) or not isinstance(data.get("services"), list):
        raise ValueError("catalog_missing_services")
    services = {}
    for item in data["services"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("invalid_catalog_service")
        if item["id"] in services:
            raise ValueError("duplicate_catalog_service")
        services[item["id"]] = item
    checked = []
    for service_id, key, url in CHECKS:
        if service_id not in services:
            checked.append({"service": service_id, "check": key, "status": "UNVERIFIED",
                            "reason": "missing_catalog_service", "payment_attempted": False})
            continue
        checked.append(inspect_target(services[service_id], key, url, opener))
    ok = all(x["status"] == "REACHABLE_DEMO_ONLY" for x in checked)
    return {"schema": "agent-economy.discovery-smoke.v1",
            "ok": ok, "checks": checked,
            "paid_requests_attempted": 0,
            "purchase_authorized": False,
            "commercial_revenue_verified": False,
            "disclaimer": "Demo reachability is not paid delivery, buyer acceptance, independent customers, or a live x402 payment validation."}


def main():
    parser = argparse.ArgumentParser(description="Probe five allowlisted free demo/discovery URLs; never pay")
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    args = parser.parse_args()
    try:
        report = run(args.catalog)
    except (OSError, UnicodeError, ValueError) as exc:
        report = {"schema": "agent-economy.discovery-smoke.v1",
                  "ok": False, "checks": [], "paid_requests_attempted": 0,
                  "purchase_authorized": False, "reason": type(exc).__name__}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

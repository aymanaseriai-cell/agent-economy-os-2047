#!/usr/bin/env python3
"""Read-only x402 seller-availability audit. No paid calls, wallet signing or outreach."""
import argparse
import base64
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AGENT402 = "https://agent402.tools"
SUPABASE = "https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1"
PAYEE = "0x935ad91b70c6d0769871416c5904d06fbf9ef586"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CHAIN = "eip155:8453"
QUERY = "Verify a native USDC transfer on Base using 2 of 3 independent RPC providers with transaction hash"
BOUNTY_QUERY = "Check if a paid GitHub bounty issue has real USDC escrow, unsafe instructions or false payout claims"
ROUTES = (("agent-usdc-receipt-lite", 5000, "/api/v1/receipt"),
          ("agent-usdc-receipt", 10000, "/api/v1/receipt"),
          ("agent-bounty-truth-gate", 5000, "/api/v1/audit"))
LIMIT = 700000

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        return None

def http(url, body=None):
    """Only caller-constructed, publicly documented URLs are ever used."""
    headers = {"User-Agent": "AgentEconomy-SellerAudit/1.0", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method="POST" if body is not None else "GET")
    try:
        res = urllib.request.build_opener(NoRedirect).open(req, timeout=14)
    except urllib.error.HTTPError as exc:
        res = exc
    with res:
        data = res.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError("oversized_response")
        return res.status, {k.lower(): v for k, v in res.headers.items()}, data

def check_quote(status, headers, expected_amount):
    """Check the actual 402 challenge, never perform its requested payment."""
    if status != 402 or "payment-required" not in headers:
        return {"ok": False, "reason": "missing_payment_challenge", "http": status}
    encoded = headers["payment-required"]
    if not isinstance(encoded, str) or not 32 <= len(encoded) <= 12000:
        return {"ok": False, "reason": "bad_challenge_size", "http": status}
    try:
        challenge = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (ValueError, TypeError):
        return {"ok": False, "reason": "invalid_challenge", "http": status}
    accepts = challenge.get("accepts", [])
    if challenge.get("x402Version") != 2 or not isinstance(accepts, list) or len(accepts) != 1:
        return {"ok": False, "reason": "invalid_x402_terms", "http": status}
    data = accepts[0]
    if not isinstance(data, dict):
        return {"ok": False, "reason": "invalid_accept", "http": status}
    assertions = {
        "network": data.get("network") == CHAIN,
        "asset": str(data.get("asset", "")).lower() == USDC.lower(),
        "payee": str(data.get("payTo", "")).lower() == PAYEE.lower(),
        "amount": str(data.get("amount")) == str(expected_amount),
        "scheme": data.get("scheme") == "exact",
    }
    return {"ok": all(assertions.values()), "checks": assertions, "http": status,
            "price_usdc": expected_amount / 1_000_000, "payment_submitted": False}

def check_index(index, origin, amount, route="/api/v1/receipt"):
    if not isinstance(index, dict) or index.get("origin") != origin:
        return {"ok": False, "reason": "index_origin_mismatch"}
    tools = index.get("tools", [])
    if not isinstance(tools, list):
        return {"ok": False, "reason": "invalid_tools"}
    rows = [x for x in tools if isinstance(x, dict)
            and x.get("method") == "GET" and x.get("route") == route
            and x.get("price") == amount / 1_000_000]
    if len(rows) != 1:
        return {"ok": False, "reason": "missing_or_duplicate_paid_tool"}
    tool = rows[0]
    layer = (tool.get("routerDispatchByChain") or {}).get("base") or {}
    checks = {
        "healthy": index.get("health") == 1,
        "routable": index.get("routable") is True,
        "callable_now": tool.get("executeViaCallableNow") is True,
        "unproven_lane": tool.get("executeViaLane") == "unproven",
        "unproven_tier": layer.get("unprovenTier") is True,
    }
    return {"ok": all(checks.values()), "checks": checks,
            "origin_level_dispatch_eligible": index.get("routerDispatchEligible"),
            "origin_dispatch_reason": index.get("routerDispatchReason"),
            "tool_level_execute_lane": tool.get("executeViaLane"),
            "unproven_max_usd": layer.get("unprovenMaxUsd"),
            "request_runtime_verified": ((tool.get("requestContract") or {}).get("runtimeVerified") is True)}

def find_rank(route_result, origin, route="/api/v1/receipt"):
    rows = route_result.get("results", []) if isinstance(route_result, dict) else []
    if not isinstance(rows, list):
        return None
    return next((i for i, x in enumerate(rows, 1)
                 if isinstance(x, dict) and x.get("seller") == origin
                 and x.get("route") == route), None)

def inspect():
    report = {"schema": "agent-economy.agent402-seller-watch.v1",
              "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "mode": "read_only", "buyer_purchases_performed": 0,
              "sales_verified": False,
              "sales_verification_scope": "NOT_CHECKED",
              "notes": "Tool callable via unproven lane may coexist with origin-level settlement_required. A ready tool is not a sale.",
              "routes": []}
    for slug, amount, route in ROUTES:
        origin = SUPABASE + "/" + slug
        row = {"slug": slug, "route": route, "origin": origin, "expected_price_usdc": amount / 1_000_000}
        try:
            indexed_url = AGENT402 + "/api/index?" + urllib.parse.urlencode({"seller": origin})
            status, _, body = http(indexed_url)
            if status != 200:
                raise ValueError("index_not_200")
            row["index"] = check_index(json.loads(body), origin, amount, route)
            quote_url = origin + (route + "?tx=0x" + "0" * 64 if route == "/api/v1/receipt" else route)
            status, headers, _ = http(quote_url)
            row["quote"] = check_quote(status, headers, amount)
        except (OSError, ValueError, urllib.error.URLError, UnicodeError) as exc:
            row["probe_error_type"] = type(exc).__name__
        row["ready_for_unproven_route"] = (
            row.get("index", {}).get("ok") is True
            and row.get("quote", {}).get("ok") is True
        )
        report["routes"].append(row)
    try:
        status, _, raw = http(AGENT402 + "/api/route", json.dumps({"query": QUERY}).encode())
        if status != 200:
            raise ValueError("route_not_200")
        routed = json.loads(raw)
        report["free_router_discovery"] = {
            "query": QUERY, "http": status,
            "ranks_among_returned": {
                row["slug"]: find_rank(routed, row["origin"], row["route"]) for row in report["routes"]
            },
            "result_count": routed.get("count"),
            "payment_executed": False,
        }
    except (OSError, ValueError, urllib.error.URLError, UnicodeError) as exc:
        report["router_error_type"] = type(exc).__name__
    try:
        status, _, raw = http(AGENT402 + "/api/route", json.dumps({"query": BOUNTY_QUERY, "top": 25}).encode())
        if status != 200:
            raise ValueError("bounty_route_not_200")
        routed = json.loads(raw)
        bounty_origin = SUPABASE + "/agent-bounty-truth-gate"
        report["bounty_router_discovery"] = {
            "query": BOUNTY_QUERY,
            "rank_among_returned": find_rank(routed, bounty_origin, "/api/v1/audit"),
            "returned": routed.get("returned"),
            "payment_executed": False,
        }
    except (OSError, ValueError, urllib.error.URLError, UnicodeError) as exc:
        report["bounty_router_error_type"] = type(exc).__name__
    report["all_ready"] = all(row["ready_for_unproven_route"] for row in report["routes"])
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="agent402-seller-status.json")
    args = parser.parse_args()
    report = inspect()
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ready": report["all_ready"], "ranks": report.get("free_router_discovery", {}).get("ranks_among_returned"),
                      "report": args.output}))
    return 0 if report["all_ready"] else 1

if __name__ == "__main__":
    raise SystemExit(main())

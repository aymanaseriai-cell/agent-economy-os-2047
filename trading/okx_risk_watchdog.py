#!/usr/bin/env python3
"""Independent read-only OKX position-risk watchdog.

No order submission, leverage adjustment, cancellation, or trading authorization.
This watchdog can run on a schedule even after the live execution workflow fails.
Only coarse status codes go to public GitHub Actions logs.
"""
from __future__ import annotations

import os
import sys

from trading.okx_live_executor import OKX, ExecutionBlocked
from trading.okx_portfolio_guard import UnsafePortfolio, snapshot

READ_ENDPOINTS = frozenset({
    "/api/v5/account/config",
    "/api/v5/account/positions",
    "/api/v5/account/balance",
    "/api/v5/trade/orders-pending",
    "/api/v5/trade/orders-algo-pending",
})
STATUS_HEALTHY = "PORTFOLIO_PROTECTED_WITHIN_POLICY"
STATUS_FLAT = "NO_OPEN_SWAP_POSITIONS"
STATUS_RISK = "RISK_LIMIT_EXCEEDED"
STATUS_UNKNOWN = "ACCOUNT_OR_PROTECTION_UNVERIFIABLE"
STATUS_CONNECTION = "READ_ONLY_CONNECTION_FAILED"


class ReadOnlyOKX(OKX):
    """Enforce a GET-only allowlist below the existing authenticated client."""

    def request(self, method, path, *, params=None, body=None, auth=True):
        if method != "GET" or path not in READ_ENDPOINTS or body is not None or auth is not True:
            raise ExecutionBlocked("Read-only watchdog forbids this request")
        return super().request(method, path, params=params, auth=True)


def assess(client):
    """Return a coarse outcome and exit code; do not expose private account data."""
    try:
        # Requiring actual leverage prevents a silent 20x fallback on a
        # 10x-100x account. All risk-limit and TP/SL checks remain intact.
        state = snapshot(client, require_position_leverage=True)
    except UnsafePortfolio as exc:
        if str(exc) == "Existing aggregate risk above permitted limits":
            return STATUS_RISK, 2
        return STATUS_UNKNOWN, 3
    return (STATUS_HEALTHY if state["symbols"] else STATUS_FLAT), 0


def main():
    env = dict(os.environ)
    if not all(env.get(x) for x in ("OKX_API_KEY", "OKX_SECRET_KEY", "OKX_PASSPHRASE")):
        print("OKX SAFETY WATCHDOG: " + STATUS_CONNECTION, flush=True)
        return 3
    # Force real account read-only checks even if unrelated execution mode is demo.
    env["OKX_EXECUTION_MODE"] = "live"
    try:
        status, code = assess(ReadOnlyOKX(env))
    except Exception:
        # Do not echo sensitive HTTP payloads, balances or symbols.
        status, code = STATUS_CONNECTION, 3
    print("OKX SAFETY WATCHDOG: " + status, flush=True)
    if code != 0:
        print("::error::OKX risk state requires attention. NO ORDERS were attempted.",
              file=sys.stderr, flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

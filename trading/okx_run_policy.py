#!/usr/bin/env python3
"""Fail-closed GitHub Actions dispatcher preflight.

This command never calls OKX and never places an order. Trading is disarmed
unless explicitly unlocked by independent live/stop switches and confirmations.
Research mode is intrinsically public, credential-free, and no-order.
"""
from __future__ import annotations

import argparse
import os
import sys

PURPOSES = frozenset(("validate", "risk_check", "research", "run"))


def preflight(purpose: str, env: dict[str, str]) -> str:
    """Return a non-sensitive status string or raise ValueError before worker."""
    if purpose not in PURPOSES:
        raise ValueError("Unsupported workflow purpose")
    if purpose == "research":
        return "RESEARCH_ONLY_PUBLIC_NO_ORDERS"
    if purpose == "validate":
        return "READ_ONLY_OKX_CONNECTION_CHECK_NO_ORDERS"
    if purpose == "risk_check":
        return "READ_ONLY_OKX_PORTFOLIO_CHECK_NO_ORDERS"
    blockers = []
    if env.get("OKX_ENABLE_REAL_TRADING") != "YES":
        blockers.append(
            "STOP INTERLOCK: OKX_ENABLE_REAL_TRADING=NO. Live orders remain disabled."
        )
    if env.get("OKX_STOP_CONTINUOUS") == "YES":
        blockers.append(
            "STOP INTERLOCK: OKX_STOP_CONTINUOUS=YES. Owner's stop request is still in force."
        )
    if env.get("OKX_EXECUTION_MODE") != "live":
        blockers.append(
            "Live purpose requires independently configured OKX_EXECUTION_MODE=live."
        )
    if blockers:
        raise ValueError(" | ".join(blockers)
                         + " Use purpose=research for no-order testing. "
                         + "Do not disable protective controls merely to make a job green.")
    return "LIVE_ARMING_PREFLIGHT_PASSED"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--purpose", required=True, choices=sorted(PURPOSES))
    args = p.parse_args()
    try:
        result = preflight(args.purpose, dict(os.environ))
        print("OKX WORKFLOW PREFLIGHT: " + result, flush=True)
        return 0
    except ValueError as exc:
        print("::error::" + str(exc), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

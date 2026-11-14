#!/usr/bin/env python3
"""Offline unlimited-risk stress simulator. No brokerage credentials or trading I/O.

This is NOT a live trading configuration. It deliberately imposes no risk,
position-count, notional, or leverage ceilings on *hypothetical* inputs.
Exchange liquidation, maintenance margin, fees, slippage and funding are NOT
modeled, so negative simulated equity represents a stress shortfall, not an
executable promise of debt or an actual exchange liquidation price.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


class StressInputError(ValueError):
    pass


def decimal(value, label):
    try:
        number = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise StressInputError("Invalid " + label) from exc
    if not number.is_finite():
        raise StressInputError("Non-finite " + label)
    return number


def simulate(equity, positions, shocks):
    initial = decimal(equity, "equity")
    if initial <= 0:
        raise StressInputError("Equity must be positive")
    if not isinstance(positions, list) or not positions:
        raise StressInputError("At least one hypothetical position required")
    if not isinstance(shocks, (list, tuple)) or not shocks:
        raise StressInputError("At least one shock required")

    validated = []
    margin = Decimal("0")
    gross = Decimal("0")
    for item in positions:
        if not isinstance(item, dict):
            raise StressInputError("Invalid position")
        side = item.get("side")
        if side not in ("long", "short"):
            raise StressInputError("Side must be long or short")
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol or len(symbol) > 100:
            raise StressInputError("Invalid symbol")
        notional = decimal(item.get("notional"), "notional")
        leverage = decimal(item.get("leverage"), "leverage")
        if notional <= 0 or leverage <= 0:
            raise StressInputError("Notional and leverage must be positive")
        validated.append((symbol, side, notional, leverage))
        margin += notional / leverage
        gross += notional

    scenarios = []
    for raw in shocks:
        shock = decimal(raw, "shock")
        if shock < -1:
            raise StressInputError("Price cannot fall more than 100%")
        pnl = sum(
            (n * shock if side == "long" else -n * shock)
            for _, side, n, _ in validated
        )
        ending = initial + pnl
        scenarios.append({
            "common_market_move_fraction": str(shock),
            "hypothetical_pnl_usdt": str(pnl),
            "hypothetical_equity_usdt": str(ending),
            "equity_change_pct": str((pnl / initial) * 100),
            "equity_shortfall_below_zero": str(max(Decimal("0"), -ending)),
            "stress_insolvency": ending <= 0,
        })

    return {
        "mode": "OFFLINE_UNBOUNDED_RISK_STRESS_ONLY",
        "orders_sent": 0,
        "live_trading_enabled": False,
        "market_or_private_api_access": False,
        "starting_equity_usdt": str(initial),
        "hypothetical_position_count": len(validated),
        "gross_notional_usdt": str(gross),
        "gross_notional_multiple_of_equity": str(gross / initial),
        "sum_hypothetical_initial_margin_usdt": str(margin),
        "hypothetical_margin_exceeds_equity": margin > initial,
        "risk_limits_enforced_on_simulated_positions": False,
        "scenarios": scenarios,
        "warning": (
            "Hypothetical correlated price shocks only; no live orders, no OKX "
            "authorization, no liquidation engine, no fees, funding or slippage. "
            "Never use this result as a live execution or sizing instruction."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--equity", default="100", help="Hypothetical USDT equity")
    parser.add_argument("--positions-json", default=json.dumps([
        {"symbol": "SYNTHETIC-USDT-SWAP", "side": "long",
         "notional": "10000", "leverage": "100"}
    ]), help="JSON array of synthetic positions (no account API)")
    parser.add_argument("--shocks", default="-0.10,-0.05,-0.01,0.01,0.05,0.10",
                        help="Comma-separated fractional common price shocks")
    parser.add_argument("--out", help="Optional local JSON report path")
    args = parser.parse_args(argv)
    try:
        positions = json.loads(args.positions_json)
        result = simulate(args.equity, positions, args.shocks.split(","))
    except (StressInputError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    document = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(document, encoding="utf-8")
    else:
        print(document, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Exchange-aware 10x-100x leverage selector; no network access or order placement.

A heuristic stress gate, NOT a predictive model or a liquidation guarantee.
The account's leverage tier must be independently verified before using this.
"""
from decimal import Decimal, InvalidOperation

MIN_LEVERAGE = 10
MAX_LEVERAGE = 100

def _decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid dynamic leverage input") from exc
    if not result.is_finite():
        raise ValueError("Non-finite dynamic leverage input")
    return result

def select_leverage(stop_fraction, round_trip_cost_fraction, market_max, account_max):
    """Return an integer leverage in [10,100], or None when no candidate survives.

    Requires a current market instrument maximum AND account-specific tier cap.
    0.5% adverse shock budget / double-stop stress are heuristics, not hard losses.
    """
    stop, cost = _decimal(stop_fraction), _decimal(round_trip_cost_fraction)
    market, account = _decimal(market_max), _decimal(account_max)
    if not (Decimal("0") < stop < Decimal("1")):
        raise ValueError("Invalid stop distance")
    if not (Decimal("0") <= cost <= Decimal("0.02")):
        raise ValueError("Invalid round-trip cost")
    if min(market, account) <= 0:
        raise ValueError("Invalid exchange leverage cap")
    cap = min(MAX_LEVERAGE, int(market), int(account))
    for leverage in range(cap, MIN_LEVERAGE - 1, -1):
        x = Decimal(leverage)
        # Avoid automatic maximum-leverage selection merely because it exists.
        if (x * (Decimal("2") * stop + cost) <= Decimal("0.50")
                and x * (Decimal("0.005") + cost) <= Decimal("0.75")):
            return leverage
    return None

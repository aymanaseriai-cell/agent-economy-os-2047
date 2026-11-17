#!/usr/bin/env python3
"""TITAN REGIME LAB: offline, locked-parameter shadow strategies.

Two competing hypotheses are scored on frozen completed 15m OHLC only.
Signals at close(t) execute no sooner than open(t+1). No order endpoints,
API keys, live trading, parameter sweep, or evidence of profitable execution.
This DOES NOT reconstruct TITAN Omega orderbook/derivative/NVIDIA gates.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

from trading.edge_lab import (
    BAR_MS, DEFAULT_SYMBOLS, TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE,
    STRESS_SLIPPAGE, FUNDING_PER_8H, TRAIN_FRACTION,
    ema_series, rsi_simple, atr_simple, signals, trade_simulation,
)

CANDIDATES = ("regime_breakout", "regime_pullback")
BASELINES = ("ema_rsi", "breakout")
START_BALANCE_USDT = 4.15
GOAL_BALANCE_USDT = 8.30
WARMUP_BARS = 192
HISTORY_BARS = 32
TREND_FAST_EMA = 24
TREND_SLOW_EMA = 96
ATR_PERIOD = 14
# Predeclared values. Do not tune against the held-out period.
MIN_ATR_FRACTION = 0.0015
MAX_ATR_FRACTION = 0.04
MIN_VOL_RATIO = 0.6
MAX_VOL_RATIO = 2.2
MIN_TREND_SEPARATION_FRACTION = 0.0005


def validate_frozen(bars):
    if not isinstance(bars, list) or len(bars) < 400:
        raise ValueError("Need at least 400 frozen complete bars")
    previous = None
    for row in bars:
        if not isinstance(row, dict):
            raise ValueError("Bad bar")
        try:
            ts = int(row["ts"])
            op, hi, lo, close = (float(row[k]) for k in ("open", "high", "low", "close"))
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            raise ValueError("Invalid frozen OHLC") from exc
        if (not all(math.isfinite(v) for v in (op, hi, lo, close))
                or not (0 < lo <= op <= hi and lo <= close <= hi)
                or (previous is not None and ts - previous != BAR_MS)):
            raise ValueError("Malformed or incomplete OHLC chronology")
        previous = ts


def regime_signals(bars, variant):
    """Locked, future-free decisions. Uses only OHLC through signal bar i."""
    if variant not in CANDIDATES:
        raise ValueError("Unrecognized locked strategy")
    validate_frozen(bars)
    closes = [float(row["close"]) for row in bars]
    ema_fast = ema_series(closes, TREND_FAST_EMA)
    ema_slow = ema_series(closes, TREND_SLOW_EMA)
    atr = [None] * len(bars)
    for i in range(ATR_PERIOD, len(bars)):
        atr[i] = atr_simple(bars, i, ATR_PERIOD)
    outcomes = []
    # The base simulator uses 1.5 ATR stops and 2.5 ATR targets.
    # Reject low-volatility trades whose illustrative target cannot pay
    # at least twice the reserved round-trip fee+slippage friction.
    roundtrip_cost = 2 * (TAKER_FEE + BASE_SLIPPAGE)
    for i in range(WARMUP_BARS, len(bars) - 1):
        close = closes[i]
        tr = atr[i]
        prior_vol = atr[i - HISTORY_BARS:i]
        if (not tr or any(x is None for x in prior_vol)
                or not (MIN_ATR_FRACTION <= tr / close <= MAX_ATR_FRACTION)
                or 2.5 * tr / close <= 2 * roundtrip_cost):
            continue
        ratio = tr / statistics.median(prior_vol)
        if not MIN_VOL_RATIO <= ratio <= MAX_VOL_RATIO:
            continue
        slow_up = (ema_fast[i] > ema_slow[i] * (1 + MIN_TREND_SEPARATION_FRACTION)
                   and ema_slow[i] > ema_slow[i - 16])
        slow_down = (ema_fast[i] < ema_slow[i] * (1 - MIN_TREND_SEPARATION_FRACTION)
                     and ema_slow[i] < ema_slow[i - 16])
        direction = 0
        rsi = rsi_simple(closes, i)
        if variant == "regime_breakout":
            old_high = max(float(b["high"]) for b in bars[i-HISTORY_BARS:i])
            old_low = min(float(b["low"]) for b in bars[i-HISTORY_BARS:i])
            if slow_up and close > old_high and 51 <= rsi <= 78:
                direction = 1
            elif slow_down and close < old_low and 22 <= rsi <= 49:
                direction = -1
        else:
            # First completed-candle EMA24 recross after trend pullback.
            if (slow_up and closes[i-1] <= ema_fast[i-1]
                    and close > ema_fast[i] and 44 <= rsi <= 70):
                direction = 1
            elif (slow_down and closes[i-1] >= ema_fast[i-1]
                    and close < ema_fast[i] and 30 <= rsi <= 56):
                direction = -1
        if direction:
            outcomes.append((i, direction, tr))
    return outcomes


def audit(symbols, *, snapshot_hashes=None):
    """Keep base/holdout boundaries fixed; never select strategy on holdout."""
    if not isinstance(symbols, dict) or not symbols:
        raise ValueError("Missing frozen market histories")
    result = {
        "mode": "OFFLINE_LOCKED_REGIME_EXPERIMENT_NO_ORDERS",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_hypotheses": list(CANDIDATES),
        "existing_candle_baselines": list(BASELINES),
        "predeclared_train_fraction": TRAIN_FRACTION,
        "starting_account_usdt": START_BALANCE_USDT,
        "target_account_usdt": GOAL_BALANCE_USDT,
        "required_net_account_gain_pct": 100.0,
        "actual_account_equity_checked": False,
        "actual_exchange_min_size_checked": False,
        "estimated_probability_of_doubling": None,
        "estimated_probability_of_ruin": None,
        "live_orders_authorized": False,
        "orders_placed": 0,
        "model": {
            "basis": "one position per synthetic symbol, 1000 USDT initial model account",
            "fill": "completed bar signal, next 15m open, first stop if both hit",
            "fee_each_side": TAKER_FEE, "slippage_each_side": BASE_SLIPPAGE,
            "stress_fee_each_side": STRESS_FEE,
            "stress_slippage_each_side": STRESS_SLIPPAGE,
            "funding_debit_per_8h_assumption": FUNDING_PER_8H,
        },
        "limitations": [
            "These are new unvalidated hypotheses, not full TITAN Omega signals",
            "Futures liquidation, tiny-account lot minimums and actual fills are not modeled",
            "Historical sample and six correlated markets cannot establish 2x success probability",
            "Trading friction is assumed rather than verified from the user's OKX account",
            "Any selection on these holdouts would require a new untouched future sample",
        ],
        "data_sha256": snapshot_hashes or {},
        "symbols": {},
    }
    for symbol, bars in sorted(symbols.items()):
        if symbol not in DEFAULT_SYMBOLS:
            raise ValueError("Unexpected frozen symbol")
        validate_frozen(bars)
        boundary = int(len(bars) * TRAIN_FRACTION)
        if not (WARMUP_BARS < boundary < len(bars) - 20):
            raise ValueError("Invalid chronological holdout split")
        one = {"bars": len(bars), "holdout_start_ms": bars[boundary]["ts"],
               "strategies": {}}
        for name in BASELINES + CANDIDATES:
            choices = signals(bars, name) if name in BASELINES else regime_signals(bars, name)
            train = trade_simulation(bars, choices, start_index=WARMUP_BARS,
                                     end_index=boundary)
            hold = trade_simulation(bars, choices, start_index=boundary,
                                    end_index=len(bars))
            stress = trade_simulation(bars, choices, start_index=boundary,
                                      end_index=len(bars),fee=STRESS_FEE,
                                      slip=STRESS_SLIPPAGE)
            one["strategies"][name] = {
                "train_trades": train["trades"],
                "train_return_pct": train["return_pct"],
                "holdout_trades": hold["trades"],
                "holdout_return_pct": hold["return_pct"],
                "holdout_win_rate_pct": hold["win_rate_pct"],
                "holdout_profit_factor": hold["profit_factor"],
                "holdout_max_drawdown_pct": hold["max_drawdown_pct"],
                "holdout_stress_return_pct": stress["return_pct"],
                "net_positive_holdout": hold["return_pct"] > 0,
                "net_positive_stress": stress["return_pct"] > 0,
            }
        result["symbols"][symbol] = one
    result["summary"] = {}
    for name in BASELINES + CANDIDATES:
        rows = [one["strategies"][name] for one in result["symbols"].values()]
        result["summary"][name] = {
            "markets": len(rows),
            "holdout_trades": sum(x["holdout_trades"] for x in rows),
            "equal_weight_symbol_return_pct": round(statistics.mean(
                x["holdout_return_pct"] for x in rows), 4),
            "equal_weight_stress_return_pct": round(statistics.mean(
                x["holdout_stress_return_pct"] for x in rows), 4),
            "positive_markets": sum(x["net_positive_holdout"] for x in rows),
            "positive_stress_markets": sum(x["net_positive_stress"] for x in rows),
            "live_readiness": "NOT_VALIDATED_DO_NOT_TRADE",
        }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-dir", required=True,
                        help="Required local frozen gzipped OHLC source; never fetches the web")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    folder = Path(args.offline_dir)
    snapshots, fingerprints = {}, {}
    for symbol in DEFAULT_SYMBOLS:
        path = folder / (symbol + ".candles.json.gz")
        if not path.is_file():
            parser.error("Missing frozen file for " + symbol)
        with gzip.open(path, "rt", encoding="utf-8") as source:
            bars = json.load(source)
        snapshots[symbol] = bars
        fingerprints[symbol] = hashlib.sha256(
            json.dumps(bars, separators=(",", ":")).encode()).hexdigest()
    report = audit(snapshots, snapshot_hashes=fingerprints)
    out = Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for name, s in report["summary"].items():
        print("SHADOW OOS",name,"trades=",s["holdout_trades"],
              "equal_weight_net_pct=",s["equal_weight_symbol_return_pct"],
              "stress_pct=",s["equal_weight_stress_return_pct"],
              "positive_markets=",s["positive_markets"], "/",s["markets"],
              "LIVE=NO",flush=True)
    print("TITAN 4.15 to 8.30: probability UNVERIFIED; no orders",flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

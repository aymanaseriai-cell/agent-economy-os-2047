"""Public 3-timescale momentum, volatility compression and order-flow ranking.

This is a deterministic descriptive research overlay. It provides no predicted
probability, quantum speed-up, guaranteed alpha, or independent trade permission.
Only FULLY COMPLETED 15m/1h/4h candle arrays are accepted from the scanner.
"""
from __future__ import annotations

import math
import statistics

VERSION = "TITAN_SPEED_MATRIX_1"
MINIMUM = 0.50
MAXIMUM = 1.50


def _number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite public quote")
    return result


def _ema(values, n):
    if len(values) < n:
        raise ValueError("insufficient candles for EMA")
    factor = 2.0 / (n + 1)
    value = statistics.mean(values[:n])
    for price in values[n:]:
        value = factor * price + (1 - factor) * value
    return value


def _slope(bars):
    closes = [_number(x["close"]) for x in bars]
    if len(closes) < 30 or min(closes) <= 0:
        raise ValueError("insufficient completed timeframe closes")
    fast, slow = _ema(closes, 9), _ema(closes, 21)
    return max(-1.0, min(1.0, (fast - slow) / max(slow * .005, 1e-8)))


def _true_range(bars):
    out = []
    for idx in range(1, len(bars)):
        last = _number(bars[idx - 1]["close"])
        candle = bars[idx]
        h, l = _number(candle["high"]), _number(candle["low"])
        if not (last > 0 and 0 < l <= h):
            raise ValueError("invalid candle geometry")
        out.append(max(h - l, abs(h - last), abs(l - last)) / last)
    return out


def _depth_flow(book, trades):
    bids, asks = book["bids"][:20], book["asks"][:20]
    if not bids or not asks or not trades:
        raise ValueError("missing book/tape")
    bid_vol = sum(_number(x[1]) for x in bids)
    ask_vol = sum(_number(x[1]) for x in asks)
    buy = sum(_number(t["sz"]) for t in trades if t["side"] == "buy")
    sell = sum(_number(t["sz"]) for t in trades if t["side"] == "sell")
    if min(bid_vol, ask_vol) < 0 or bid_vol + ask_vol <= 0 or buy + sell <= 0:
        raise ValueError("invalid book/tape volume")
    return ((bid_vol - ask_vol) / (bid_vol + ask_vol),
            (buy - sell) / (buy + sell))


def evaluate_speed_matrix(bars15, bars1h, bars4h, book, trades, record):
    """Return bounded *rank multiplier*, never buy/sell order or approval."""
    result = {"speed_matrix_version": VERSION,
              "speed_matrix_rank_factor": 1.0,
              "speed_matrix_status": "WAIT",
              "speed_matrix_live_permission": False}
    direction = record.get("signal")
    if direction not in ("LONG", "SHORT"):
        return result
    try:
        if len(bars15) < 44 or len(bars1h) < 30 or len(bars4h) < 30:
            return {**result, "speed_matrix_status": "INSUFFICIENT_DATA"}
        side = 1 if direction == "LONG" else -1
        s15, s1h, s4h = (_slope(bars) for bars in (bars15, bars1h, bars4h))
        tr = _true_range(bars15[-44:])
        atr_recent = statistics.mean(tr[-14:])
        atr_previous = statistics.mean(tr[-28:-14])
        if atr_previous <= 0:
            return {**result, "speed_matrix_status": "NO_VOLATILITY"}
        compression = max(.1, min(5.0, atr_recent / atr_previous))
        depth, tape = _depth_flow(book, trades)
        # Penalize false 'breakouts' with opposing order flow and unusually
        # extended ranges. No look-ahead, no claimed predictive probability.
        align = (side * s15 + side * s1h + side * s4h) / 3
        flow = (side * depth + side * tape) / 2
        burst = min(.25, max(0.0, (compression - 1.0) * .20))
        chaos = max(0.0, compression - 2.0) * .15
        score = max(MINIMUM, min(MAXIMUM, 1.0 + .24 * align + .18 * flow + burst - chaos))
        return {**result, "speed_matrix_status": "RANK_ONLY",
                "speed_matrix_rank_factor": round(score, 6),
                "speed_matrix_evidence": {
                    "ema_alignment_15m": round(side * s15, 4),
                    "ema_alignment_1h": round(side * s1h, 4),
                    "ema_alignment_4h": round(side * s4h, 4),
                    "normalized_orderbook_imbalance": round(depth, 4),
                    "normalized_trade_delta": round(tape, 4),
                    "relative_atr_regime": round(compression, 4)},
                "speed_matrix_warning": "Historical rank heuristic; no proven edge or fast-profit guarantee"}
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, ZeroDivisionError):
        return {**result, "speed_matrix_status": "INVALID_PUBLIC_DATA"}

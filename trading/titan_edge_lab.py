"""TITAN EDGE LAB: eight reproducible, read-only quantitative market diagnostics.

Public COMPLETED OHLCV candles and book depth only. No orders, private API,
auto-leverage, external dependencies, claims of an edge, or entry authorization.
Inputs are chronological; Donchian breakouts EXCLUDE the signal candle.
"""
from __future__ import annotations

import math
import statistics

SYSTEMS = (
    "01_kaufman_trend_efficiency",
    "02_ema_12_26_trend_alignment",
    "03_donchian_prior_20_breakout",
    "04_average_true_range_regime",
    "05_directional_movement_dx14",
    "06_choppiness_index_14",
    "07_bollinger_bandwidth_squeeze",
    "08_robust_volume_surprise_and_depth",
)


def validate_bars(bars, minimum=120):
    if not isinstance(bars, list) or len(bars) < minimum:
        raise ValueError("Insufficient completed candles")
    result = []
    prev_ts = None
    for row in bars:
        if not isinstance(row, dict):
            raise ValueError("Invalid OHLCV row")
        ts = int(row["ts"])
        if prev_ts is not None and ts <= prev_ts:
            raise ValueError("Non-monotonic candle timestamp")
        prev_ts = ts
        op, hi, lo, cl, vol = (float(row[k]) for k in
                               ("open", "high", "low", "close", "quote_vol"))
        if (not all(math.isfinite(v) for v in (op, hi, lo, cl, vol))
                or min(op, hi, lo, cl) <= 0 or vol < 0
                or lo > min(op, cl) or hi < max(op, cl) or hi < lo):
            raise ValueError("Inconsistent candle geometry")
        result.append((op, hi, lo, cl, vol))
    return result


def ema(values, window):
    if len(values) < window or window < 2:
        raise ValueError("Insufficient EMA history")
    value = statistics.fmean(values[:window])
    alpha = 2 / (window + 1)
    for v in values[window:]:
        value += alpha * (v - value)
    return value


def signal_at_close(bars, end, strategy):
    """Signal at close of bar end; never references bar end+1 or later."""
    if strategy not in ("ema_trend", "donchian_breakout", "bollinger_reversion"):
        raise ValueError("Unsupported shadow strategy")
    if end < 50 or end >= len(bars):
        return 0
    rows = bars[:end+1]
    closes = [float(b["close"]) for b in rows]
    if strategy == "ema_trend":
        fast, slow = ema(closes, 12), ema(closes, 26)
        return 1 if fast > slow and closes[-1] > fast else -1 if fast < slow and closes[-1] < fast else 0
    if strategy == "donchian_breakout":
        prev = rows[-21:-1]  # Exclude the current signal candle.
        return (1 if closes[-1] > max(float(b["high"]) for b in prev)
                else -1 if closes[-1] < min(float(b["low"]) for b in prev) else 0)
    recent = closes[-20:]
    avg = statistics.fmean(recent)
    std = statistics.pstdev(recent)
    if std <= 1e-12:
        return 0
    z = (closes[-1] - avg) / std
    return -1 if z >= 1.75 else 1 if z <= -1.75 else 0


def _true_ranges(rows):
    ranges = []
    for i, (_, hi, lo, cl, _) in enumerate(rows):
        prev = cl if i == 0 else rows[i-1][3]
        ranges.append(max(hi-lo, abs(hi-prev), abs(lo-prev)))
    return ranges


def _directional_dx(rows):
    plus = minus = 0.0
    for i in range(len(rows)-14, len(rows)):
        prev, curr = rows[i-1], rows[i]
        up = curr[1]-prev[1]
        down = prev[2]-curr[2]
        if up > down and up > 0:
            plus += up
        elif down > up and down > 0:
            minus += down
    return 100 * abs(plus-minus)/(plus+minus) if plus+minus > 1e-12 else 0.0


def _finite(value):
    if value is None:
        return None
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("Nonfinite calculated diagnostic")
    return round(x, 6)


def evaluate_edge_lab(bars15, bars1h, bars4h, book):
    """All diagnostics observational; never changes an existing trade signal."""
    try:
        rows = validate_bars(bars15, minimum=120)
        hour = validate_bars(bars1h, minimum=30)
        four = validate_bars(bars4h, minimum=15)
        closes = [r[3] for r in rows]
        tr = _true_ranges(rows)
        atr14 = statistics.fmean(tr[-14:])
        atr50 = statistics.fmean(tr[-50:])
        atr_ratio = atr14/atr50 if atr50 > 1e-12 else 0.0
        prior20 = rows[-21:-1]
        breakout = (1 if closes[-1] > max(b[1] for b in prior20)
                    else -1 if closes[-1] < min(b[2] for b in prior20) else 0)
        direction = lambda p: 1 if ema([r[3] for r in p],12)>ema([r[3] for r in p],26) else -1
        aligned = (direction(rows)+direction(hour)+direction(four))/3
        change = abs(closes[-1]-closes[-21])
        path = sum(abs(closes[j]-closes[j-1]) for j in range(len(closes)-20,len(closes)))
        efficiency = change/path if path > 1e-12 else 0.0
        high14 = max(b[1] for b in rows[-14:])
        low14 = min(b[2] for b in rows[-14:])
        trsum = sum(tr[-14:])
        chop = (100 * math.log10(trsum/(high14-low14))/math.log10(14)
                if trsum > 0 and high14 > low14 else None)
        def width(seq):
            m = statistics.fmean(seq)
            return 4*statistics.pstdev(seq)/m if m > 0 else 0.0
        widths = [width(closes[i-20:i]) for i in range(len(closes)-79,len(closes)+1)]
        latest_width = widths[-1]
        squeeze_pct = sum(w <= latest_width for w in widths)/len(widths)
        volumes = [r[4] for r in rows]
        median = statistics.median(volumes[-49:-1])
        ratio = volumes[-1]/median if median > 0 else None
        bid=ask=0.0
        for side, key in (("bids","bid"),("asks","ask")):
            levels = book.get(side, [])[:20] if isinstance(book, dict) else []
            count = sum(float(v[1]) for v in levels)
            if not math.isfinite(count) or count < 0:
                raise ValueError("Invalid orderbook depth")
            if key=="bid": bid=count
            else: ask=count
        imbalance = (bid-ask)/(bid+ask) if bid+ask>0 else None
        data = [
            ("01_kaufman_trend_efficiency", {"efficiency_ratio20":efficiency}),
            ("02_ema_12_26_trend_alignment", {"three_timeframe_alignment":aligned}),
            ("03_donchian_prior_20_breakout", {"confirmed_breakout_direction":breakout}),
            ("04_average_true_range_regime", {"atr14_pct":100*atr14/closes[-1],"atr14_to_atr50":atr_ratio}),
            ("05_directional_movement_dx14", {"dx14":_directional_dx(rows)}),
            ("06_choppiness_index_14", {"choppiness14":chop}),
            ("07_bollinger_bandwidth_squeeze", {"current_width_pct":100*latest_width,"width_percentile80":squeeze_pct}),
            ("08_robust_volume_surprise_and_depth", {"volume_to_prior_median":ratio,"top20_depth_imbalance":imbalance}),
        ]
        return {"edge_system_count":len(SYSTEMS),"data_valid":True,"shadow_only":True,
                "systems":[{"name":name,"status":"OBSERVATION_ONLY",
                            "metrics":{key:_finite(value) for key,value in metrics.items()}}
                           for name,metrics in data],
                "errors":[],"orders_placed":0}
    except (TypeError, ValueError, KeyError, IndexError, OverflowError, ZeroDivisionError):
        return {"edge_system_count":len(SYSTEMS),"data_valid":False,"shadow_only":True,
                "systems":[],"errors":["BAD_OR_INSUFFICIENT_MARKET_DATA"],"orders_placed":0}

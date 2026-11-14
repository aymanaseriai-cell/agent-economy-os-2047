#!/usr/bin/env python3
"""TITAN Fast Entry Router: public-data startup LONG/SHORT opportunity research.

Strategies are experimental and intentionally NOT connected to the live order
executor. All market data is already fetched for the standard six-agent scan.
No private keys, POST requests, order placement or leverage live settings.
"""
from __future__ import annotations

import math
import statistics
import time

VERSION = "fast-entry-research-v1"
STRATEGIES = ("20_bar_breakout", "ema20_pullback", "10_bar_liquidity_sweep")
MAX_SPREAD_BP = 15.0
MIN_TURNOVER_USDT = 15_000_000
MAX_BOOK_AGE_S = 120
MIN_STOP_BP = 5
MAX_STOP_BP = 350


def _finite(value, name):
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Missing nonnumeric " + name) from exc
    if not math.isfinite(n):
        raise ValueError("Nonfinite " + name)
    return n


def _ema(values, n):
    if len(values) < n:
        raise ValueError("Not enough periods for EMA")
    alpha = 2.0 / (n + 1.0)
    result = sum(values[:n]) / n
    for x in values[n:]:
        result = alpha * x + (1 - alpha) * result
    return result


def _atr(bars, window=14):
    if len(bars) <= window:
        raise ValueError("Not enough candles for ATR")
    spans = []
    for index in range(len(bars) - window, len(bars)):
        p = bars[index-1]["close"]
        now = bars[index]
        spans.append(max(now["high"] - now["low"], abs(now["high"] - p),
                         abs(now["low"] - p)))
    return statistics.mean(spans)


def _flow(book, trades):
    bids = book["bids"][:20]
    asks = book["asks"][:20]
    bid = sum(_finite(x[1], "book bid quantity") for x in bids)
    ask = sum(_finite(x[1], "book ask quantity") for x in asks)
    buy = sum(_finite(x.get("sz"), "trade size") for x in trades if x.get("side") == "buy")
    sell = sum(_finite(x.get("sz"), "trade size") for x in trades if x.get("side") == "sell")
    depth = (bid - ask) / (bid + ask) if bid + ask else 0.0
    trade = (buy - sell) / (buy + sell) if buy + sell else 0.0
    return depth, trade


def _reject(reason, metrics=None):
    return {"model": VERSION, "permission": "RESEARCH_ONLY_NO_ORDERS",
            "direction": "WAIT", "strategy": None,
            "stop": None, "target": None,
            "reasons": [reason], "metrics": metrics or {},
            "order_count": 0, "live_execution_allowed": False}


def evaluate_fast_entry(bars15, bars1h, bars4h, book, trades, ticker, *,
                        derivatives_healthy, now_ms=None):
    """Deterministic, non-live proposals for strong setup archetypes.

    Uses only complete historical candles plus current PUBLIC top-of-book,
    public volume and completed-trade snapshots. Returns at most one proposal.
    It cannot mutate an existing six-agent consensus signal.
    """
    now = int(time.time()*1000) if now_ms is None else int(now_ms)
    if not derivatives_healthy:
        return _reject("derivatives_feed_unverified")
    if len(bars15) < 40 or len(bars1h) < 30 or len(bars4h) < 15:
        return _reject("insufficient_complete_candles")
    if len(trades) < 30:
        return _reject("insufficient_public_trades")
    try:
        # Inputs are already normalized from the exchange's completed candles.
        for bars in (bars15, bars1h, bars4h):
            for bar in bars:
                for key in ("open", "high", "low", "close"):
                    _finite(bar[key], "candle_"+key)
                if not 0 < bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]:
                    return _reject("invalid_candle_geometry")
        last = bars15[-1]
        price = _finite(last["close"], "closed_15m_price")
        quote = _finite(ticker["last"], "ticker")
        if price<=0 or quote<=0 or abs(quote/price-1)>0.012:
            return _reject("quote_away_from_last_complete_candle")
        ts = _finite(last["ts"], "complete_candle_timestamp")
        if not 0 <= now - (ts + 15*60_000) <= 15*60_000:
            return _reject("stale_or_future_complete_candle")
        book_ts = _finite(book["ts"], "book_timestamp")
        if not 0 <= now - book_ts <= MAX_BOOK_AGE_S*1000:
            return _reject("stale_book")
        spread = _finite(ticker["spread_bp"], "spread")
        turnover = _finite(ticker["turnover_usdt_est"], "turnover")
        if spread>MAX_SPREAD_BP or turnover<MIN_TURNOVER_USDT:
            return _reject("spread_or_liquidity_veto")
        if not book["bids"] or not book["asks"]:
            return _reject("empty_depth")
        depth, tape = _flow(book, trades)
        if abs(depth)>0.95:
            return _reject("orderbook_depth_unbalanced_unreliable")
        atr = _atr(bars15)
        if atr<=0:
            return _reject("zero_atr")
        volume = _finite(last["quote_vol"], "quote volume")
        history = [_finite(x["quote_vol"], "historic quote volume") for x in bars15[-21:-1]]
        median_volume = statistics.median(history)
        if median_volume<=0:
            return _reject("zero_historic_volume")
        vr = volume / median_volume
        h1 = [x["close"] for x in bars1h]
        h4 = [x["close"] for x in bars4h]
        h1_fast = _ema(h1,12)
        h1_slow = _ema(h1,26)
        h4_trend = 1 if h4[-1]>h4[-4] else (-1 if h4[-1]<h4[-4] else 0)
        long_trend = h1_fast>h1_slow and h4_trend==1
        short_trend = h1_fast<h1_slow and h4_trend==-1
        c15 = [b["close"] for b in bars15]
        ema20 = _ema(c15,20)
        prev_ema20 = _ema(c15[:-1],20)
        b = last
        prev = bars15[-2]
        previous_high = max(x["high"] for x in bars15[-21:-1])
        previous_low = min(x["low"] for x in bars15[-21:-1])
        sweep_high = max(x["high"] for x in bars15[-11:-1])
        sweep_low = min(x["low"] for x in bars15[-11:-1])
        alternatives = []
        # Per-strategy candidate scores are descriptive ranks, not probabilities.
        for side in ("LONG","SHORT"):
            sign = 1 if side=="LONG" else -1
            trend = long_trend if sign>0 else short_trend
            flow_ok = tape*sign>=0.05 and depth*sign>=-0.12
            breakout = (
                trend and flow_ok and vr>=1.3 and
                (price>previous_high if sign>0 else price<previous_low))
            pullback = (
                trend and flow_ok and vr>=1.05 and
                (prev["close"]<=prev_ema20 and price>ema20 if sign>0 else
                 prev["close"]>=prev_ema20 and price<ema20))
            sweep = (
                trend and flow_ok and vr>=1.05 and
                (b["low"]<sweep_low and price>sweep_low and price>b["open"] if sign>0
                 else b["high"]>sweep_high and price<sweep_high and price<b["open"]))
            for label, passes, base in (
                (STRATEGIES[0],breakout,30),
                (STRATEGIES[1],pullback,20),
                (STRATEGIES[2],sweep,25)):
                if not passes:
                    continue
                recent_low = min(x["low"] for x in bars15[-9:])
                recent_high = max(x["high"] for x in bars15[-9:])
                stop = min(price-1.2*atr,recent_low) if sign>0 else max(price+1.2*atr,recent_high)
                distance = abs(price-stop)
                stop_bp = 10000*distance/price
                if not MIN_STOP_BP<=stop_bp<=MAX_STOP_BP:
                    continue
                target = price + sign*2*distance
                if target<=0:
                    continue
                # Explicit two-way taker, observed spread, and impact reserve.
                # Cost burden is never allowed to exceed a quarter of the stop.
                cost_bp = 10 + spread + 6
                if cost_bp >= stop_bp/4:
                    continue
                score = base + min(vr,3)*3 + abs(tape)*10 + abs(depth)*4
                alternatives.append({"direction":side,"strategy":label,
                                     "stop":round(stop,9),"target":round(target,9),
                                     "score":round(score,5),"estimated_cost_bp":round(cost_bp,3),
                                     "stop_bp":round(stop_bp,3)})
        if not alternatives:
            return _reject("no_research_setup_qualified",{
                "volume_ratio":round(vr,3),"tape_delta":round(tape,3),
                "depth_imbalance":round(depth,3),
                "h1_h4_agree_long":long_trend,"h1_h4_agree_short":short_trend,
                "public_setup_count":0})
        winner=max(alternatives,key=lambda a:(a["score"],a["strategy"],a["direction"]))
        return {"model": VERSION, "permission": "RESEARCH_ONLY_NO_ORDERS",
                **winner, "reasons": [],
                "metrics":{"volume_ratio":round(vr,3),"tape_delta":round(tape,3),
                           "depth_imbalance":round(depth,3),
                           "public_setup_count":len(alternatives)},
                "order_count":0,"live_execution_allowed":False}
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as exc:
        # Malformed public snapshots cannot be guessed into a trade.
        return _reject("invalid_or_missing_public_data")

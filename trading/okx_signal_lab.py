#!/usr/bin/env python3
"""OKX USDT perpetual futures public-data signal scanner.

READ-ONLY BY DESIGN: does NOT load exchange credentials or submit orders.
Signals are deterministic research labels, not financial advice or expected profit.
"""
from __future__ import annotations
import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.okx.com"
MIN_VOLUME_USDT_EST = 20_000_000
MAX_SPREAD_PCT = 0.25
BAR = "15m"


def market_get(path: str, params: dict) -> list:
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "OKX-Public-Signal-Lab/1.0"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if payload.get("code") != "0" or not isinstance(payload.get("data"), list):
        raise RuntimeError("OKX market API returned an error: " + str(payload.get("msg", "unknown")))
    return payload["data"]


def ema(values: list[float], period: int) -> float:
    if not values or period < 1:
        raise ValueError("EMA requires nonempty prices and positive period")
    current = values[0]
    alpha = 2.0 / (period + 1)
    for value in values[1:]:
        current += alpha * (value - current)
    return current


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        raise ValueError("Insufficient bars for RSI")
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(x, 0.0) for x in changes[-period:]]
    losses = [max(-x, 0.0) for x in changes[-period:]]
    gain = sum(gains) / period
    loss = sum(losses) / period
    if gain == 0 and loss == 0:
        return 50.0
    if loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + gain / loss))


def atr(bars: list[dict], period: int = 14) -> float:
    if len(bars) <= period:
        raise ValueError("Insufficient bars for ATR")
    true_ranges = []
    for idx in range(len(bars) - period, len(bars)):
        bar, prev = bars[idx], bars[idx - 1]
        true_ranges.append(max(bar["high"] - bar["low"],
                               abs(bar["high"] - prev["close"]),
                               abs(bar["low"] - prev["close"])))
    return sum(true_ranges) / period


def pick_liquid(tickers: list[dict], top: int) -> list[dict]:
    found = []
    for item in tickers:
        symbol = item.get("instId", "")
        if not symbol.endswith("-USDT-SWAP"):
            continue
        try:
            price = float(item.get("last", 0))
            base_volume = float(item.get("volCcy24h", 0))
            bid, ask = float(item.get("bidPx", 0)), float(item.get("askPx", 0))
            if min(price, bid, ask) <= 0 or ask < bid:
                continue
            spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
            volume_usdt_est = base_volume * price  # OKX derivative volCcy24h uses base currency
            if volume_usdt_est < MIN_VOLUME_USDT_EST or spread_pct > MAX_SPREAD_PCT:
                continue
            found.append({"symbol": symbol, "last": price, "volume_24h_usdt_est": round(volume_usdt_est),
                          "spread_pct": round(spread_pct, 4)})
        except (TypeError, ValueError, OverflowError):
            continue
    return sorted(found, key=lambda x: x["volume_24h_usdt_est"], reverse=True)[:top]


def parse_candles(rows: list[list[str]]) -> list[dict]:
    clean = []
    for row in rows:
        if len(row) < 9 or row[8] != "1":
            continue  # never base signals on unfinished 15m candles
        try:
            candle = {"ts": int(row[0]), "open": float(row[1]), "high": float(row[2]),
                      "low": float(row[3]), "close": float(row[4])}
            if candle["low"] > 0 and candle["high"] >= candle["low"] and candle["close"] > 0:
                clean.append(candle)
        except (TypeError, ValueError):
            continue
    return sorted(clean, key=lambda x: x["ts"])


def analyze(ticker: dict, bars: list[dict]) -> dict:
    if len(bars) < 35:
        raise ValueError("Need at least 35 completed 15m candles")
    closes = [row["close"] for row in bars]
    fast, slow = ema(closes, 9), ema(closes, 21)
    strength, volatility = rsi(closes), atr(bars)
    close = closes[-1]
    side = "WAIT"
    if fast > slow and close > fast and 53 <= strength <= 70:
        side = "LONG"
    elif fast < slow and close < fast and 30 <= strength <= 47:
        side = "SHORT"
    result = {**ticker, "timeframe": BAR, "last_closed_candle_ms": bars[-1]["ts"],
              "last_completed_close": close, "ema9": round(fast, 8), "ema21": round(slow, 8),
              "rsi14": round(strength, 2), "atr14": round(volatility, 8),
              "signal": side, "note": "Research-only; no order placed; not a profit forecast"}
    if side != "WAIT" and volatility > 0:
        sign = 1 if side == "LONG" else -1
        result["illustrative_stop"] = round(close - sign * 1.5 * volatility, 8)
        result["illustrative_target"] = round(close + sign * 2.5 * volatility, 8)
        result["illustrative_reward_risk"] = 1.67
    return result


def scan(top: int = 8) -> dict:
    tickers = market_get("/api/v5/market/tickers", {"instType": "SWAP"})
    candidates = pick_liquid(tickers, top=top)
    results, errors = [], []
    for ticker in candidates:
        symbol = ticker["symbol"]
        try:
            candles = parse_candles(market_get("/api/v5/market/candles", {
                "instId": symbol, "bar": BAR, "limit": "100"
            }))
            results.append(analyze(ticker, candles))
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)[:240]})
        time.sleep(0.15)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "exchange": "OKX", "market": "USDT perpetual SWAP", "timeframe": BAR,
        "mode": "READ_ONLY_SIGNALS", "orders_placed": 0,
        "volume_filter_usdt_est": MIN_VOLUME_USDT_EST,
        "note": "NOT a live trading bot. No credentials, balance access, or order execution. No guaranteed profits.",
        "candidates_checked": len(candidates), "signal_count": sum(x["signal"] != "WAIT" for x in results),
        "results": results, "errors": errors
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="reports/okx_15m_signals.json")
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.top <= 20:
        parser.error("--top must be between 1 and 20")
    try:
        report = scan(args.top)
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("OKX read-only scan: candidates =", report["candidates_checked"],
              "signals =", report["signal_count"], "errors =", len(report["errors"]))
        for row in report["results"]:
            print(row["symbol"], row["signal"], "RSI =", row["rsi14"])
        print("Report:", destination)
        if report["candidates_checked"] and len(report["errors"]) == report["candidates_checked"]:
            return 2
        return 0
    except Exception as exc:
        print("Scan failed, no trades attempted:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

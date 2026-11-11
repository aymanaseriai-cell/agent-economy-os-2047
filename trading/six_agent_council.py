#!/usr/bin/env python3
"""Six independent quantitative research agents for OKX USDT perpetual swaps.

READ-ONLY: no keys, positions, order placement or leveraged execution.
Do not interpret the six agents as independent LLM processes or as predictive oracles.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Script and package invocation are both supported.
if __package__:
    from .quant2037 import evaluate_advanced
    from .titan_omega import evaluate_omega, qubo_pick
else:
    from quant2037 import evaluate_advanced
    from titan_omega import evaluate_omega, qubo_pick
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://www.okx.com"
MIN_TURNOVER_USDT_EST = 15_000_000
MAX_SPREAD_BP = 25.0
ALLOWED_CRYPTO = frozenset("BTC ETH SOL XRP DOGE ADA LINK AVAX DOT LTC TRX BCH ETC ATOM UNI APT ARB SUI NEAR HYPE ZEC PEPE SHIB WLD TON OP INJ TIA SEI XLM FIL JUP ENA AAVE TAO PYTH RENDER FET GRT LDO ONDO ICP ETHFI PENDLE WIF BONK BNB SKY SAND MANA CRV COMP MKR GALA ENS RUNE FTM KAS".split())


def number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def okx_get(path, params):
    """Public GET only; network errors are handled per-market by the caller."""
    url = API + path + "?" + urlencode(params)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Six-Agent-Research/1.0"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=16) as response:
                data = json.load(response)
            if data.get("code") != "0" or not isinstance(data.get("data"), list):
                raise ValueError("OKX " + str(data.get("code")) + ": " + str(data.get("msg", ""))[:120])
            return data["data"]
        except (HTTPError, URLError, TimeoutError) as exc:
            if attempt >= 2:
                raise RuntimeError("OKX API unreachable") from exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def candles(data):
    bars = []
    for row in data:
        if len(row) < 9 or row[8] != "1":
            continue
        try:
            bar = {
                "ts": int(row[0]), "open": float(row[1]), "high": float(row[2]),
                "low": float(row[3]), "close": float(row[4]), "quote_vol": float(row[7]),
            }
            if bar["low"] <= 0 or not (bar["low"] <= bar["close"] <= bar["high"]):
                continue
            if bar["quote_vol"] < 0:
                continue
            bars.append(bar)
        except (ValueError, TypeError):
            continue
    by_ts = {b["ts"]: b for b in bars}
    return sorted(by_ts.values(), key=lambda b: b["ts"])


def select_markets(rows, count):
    result = []
    for ticker in rows:
        instrument = ticker.get("instId", "")
        parts = instrument.split("-")
        if len(parts) != 3 or parts[1:] != ["USDT", "SWAP"] or parts[0] not in ALLOWED_CRYPTO:
            continue
        last, bid, ask = (number(ticker.get(key)) for key in ("last", "bidPx", "askPx"))
        if last <= 0 or bid <= 0 or ask < bid:
            continue
        turnover = number(ticker.get("volCcy24h")) * last  # base-ccy volume * last price (estimate)
        spread_bp = 10000 * (ask - bid) / ((ask + bid) / 2)
        if turnover < MIN_TURNOVER_USDT_EST or spread_bp > MAX_SPREAD_BP:
            continue
        result.append({"symbol": instrument, "last": last, "bid": bid, "ask": ask,
                       "turnover_usdt_est": round(turnover), "spread_bp": round(spread_bp, 3)})
    # A liquid universe is scanned first; Omega ranks *qualified* targets afterward.
    return sorted(result, key=lambda z: z["turnover_usdt_est"], reverse=True)[:count]


def result(name, vote, strength, detail, veto=False):
    if vote not in (-1, 0, 1) or strength not in (0, 1, 2):
        raise ValueError("Invalid vote")
    return {"agent": name, "vote": vote, "strength": strength,
            "signal": "LONG" if vote == 1 else "SHORT" if vote == -1 else "ABSTAIN",
            "veto": veto, "evidence": detail}


# AGENT 1: LIQUIDITY SENTINEL - mandatory market quality veto.
def liquidity_sentinel(ticker, book, *, asof_epoch=None):
    bids, asks = book.get("bids", []), book.get("asks", [])
    bid_depth = sum(number(level[1]) for level in bids[:20])
    ask_depth = sum(number(level[1]) for level in asks[:20])
    book_ts = number(book.get("ts"))
    age_sec = max(0, (time.time() if asof_epoch is None else asof_epoch) - book_ts / 1000) if book_ts else None
    veto = (ticker["turnover_usdt_est"] < MIN_TURNOVER_USDT_EST or
            ticker["spread_bp"] > MAX_SPREAD_BP or not min(bid_depth, ask_depth) > 0 or
            age_sec is None or age_sec > 120)
    return result("01_liquidity_sentinel", 0, 0, {
        "turnover_usdt_est": ticker["turnover_usdt_est"], "spread_bp": ticker["spread_bp"],
        "bid_depth_contracts_20_levels": round(bid_depth, 4),
        "ask_depth_contracts_20_levels": round(ask_depth, 4),
        "orderbook_age_sec": round(age_sec, 1) if age_sec is not None else None,
        "status": "REJECT" if veto else "PASS"}, veto=veto)


# AGENT 2: AUCTION CARTOGRAPHER - approximate 48h volume profile & sweeps.
def volume_profile(bars, bins=40, value_fraction=0.70):
    if len(bars) < 80:
        raise ValueError("Need 80+ complete candles for profile")
    frame = bars[-192:]
    low = min(b["low"] for b in frame)
    high = max(b["high"] for b in frame)
    if high <= low:
        raise ValueError("Flat price profile")
    step = (high - low) / bins
    volumes = [0.0] * bins
    for candle in frame:
        left = max(0, min(bins - 1, int((candle["low"] - low) / step)))
        right = max(0, min(bins - 1, int((candle["high"] - low) / step)))
        # **Approximation**: distribute candle quote volume evenly over its price span.
        # Exact exchange tick-level Fixed Volume Profile is not available from OHLCV.
        weight = candle["quote_vol"] / (right - left + 1)
        for idx in range(left, right + 1):
            volumes[idx] += weight
    total = sum(volumes)
    if total <= 0:
        raise ValueError("Zero quote volume")
    poc_i = max(range(bins), key=lambda i: volumes[i])
    left = right = poc_i
    included = volumes[poc_i]
    while included < value_fraction * total and (left > 0 or right < bins - 1):
        left_candidate = volumes[left - 1] if left > 0 else -1.0
        right_candidate = volumes[right + 1] if right < bins - 1 else -1.0
        if right_candidate > left_candidate:
            right += 1
            included += volumes[right]
        else:
            left -= 1
            included += volumes[left]
    return {"VAL_approx": round(low + left * step, 9),
            "POC_approx": round(low + (poc_i + 0.5) * step, 9),
            "VAH_approx": round(low + (right + 1) * step, 9),
            "profile_lookback_bars": len(frame), "value_fraction": value_fraction,
            "method": "OHLCV price-bin approximation; NOT tick-level fixed volume profile"}


def auction_cartographer(bars):
    profile = volume_profile(bars)
    latest, prev = bars[-1], bars[-2]
    val, vah = profile["VAL_approx"], profile["VAH_approx"]
    vote, strength, event = 0, 0, "inside_value_area"
    if latest["low"] < val and latest["close"] > val and latest["close"] > latest["open"]:
        vote, strength, event = 1, 2, "VAL_sweep_reclaim"
    elif latest["high"] > vah and latest["close"] < vah and latest["close"] < latest["open"]:
        vote, strength, event = -1, 2, "VAH_sweep_reject"
    elif latest["close"] > vah and prev["close"] > vah:
        vote, strength, event = 1, 1, "two_closes_above_VAH"
    elif latest["close"] < val and prev["close"] < val:
        vote, strength, event = -1, 1, "two_closes_below_VAL"
    return result("02_auction_cartographer", vote, strength,
                  {**profile, "event": event, "last_closed_price": latest["close"]})


# AGENT 3: TAPE DETECTIVE - orderbook imbalance + aggressor trade flow.
def tape_detective(book, trades):
    bids, asks = book.get("bids", []), book.get("asks", [])
    bid = sum(number(x[1]) for x in bids[:20])
    ask = sum(number(x[1]) for x in asks[:20])
    depth_imbalance = (bid - ask) / (bid + ask) if bid + ask else 0.0
    buy = sum(number(x.get("sz")) for x in trades if x.get("side") == "buy")
    sell = sum(number(x.get("sz")) for x in trades if x.get("side") == "sell")
    trade_delta = (buy - sell) / (buy + sell) if buy + sell else 0.0
    vote, strength = 0, 0
    if len(trades) >= 30 and depth_imbalance > 0.08 and trade_delta > 0.12:
        vote, strength = 1, 2 if min(depth_imbalance, trade_delta) >= 0.25 else 1
    elif len(trades) >= 30 and depth_imbalance < -0.08 and trade_delta < -0.12:
        vote, strength = -1, 2 if max(depth_imbalance, trade_delta) <= -0.25 else 1
    return result("03_tape_detective", vote, strength, {
        "book_imbalance_20_levels": round(depth_imbalance, 4),
        "recent_trades_aggressor_delta": round(trade_delta, 4),
        "recent_trade_sample_size": len(trades),
        "caveat": "One-time sample; no historical cumulative volume delta or proof of whales"})


# AGENT 4: DERIVATIVES INTELLIGENCE - funding crowding + mark-premium sanity.
def derivatives_intelligence(funding, interest, mark, last):
    rate = number(funding.get("fundingRate"))
    mark_price = number(mark.get("markPx"))
    premium_bp = (mark_price / last - 1) * 10000 if mark_price and last else None
    oi_usd = number(interest.get("oiUsd"))
    oi_ccy = number(interest.get("oiCcy"))
    vote, strength = 0, 0
    if rate >= 0.0005 and premium_bp is not None and premium_bp >= 0:
        vote, strength = -1, 1
    elif rate <= -0.0005 and premium_bp is not None and premium_bp <= 0:
        vote, strength = 1, 1
    return result("04_derivatives_intelligence", vote, strength, {
        "funding_rate": rate, "mark_minus_last_bp": round(premium_bp, 3) if premium_bp is not None else None,
        "open_interest_usd_snapshot": round(oi_usd) if oi_usd else None,
        "open_interest_base_snapshot": oi_ccy or None,
        "caveat": "No OI change inferred from a single open-interest snapshot"})


# AGENT 5: STRUCTURE NAVIGATOR - higher-timeframe regime and breaks, no EMA/RSI.
def structure_navigator(h1, h4):
    if len(h1) < 30 or len(h4) < 15:
        raise ValueError("Insufficient completed 1h/4h candles")
    h1_close = h1[-1]["close"]
    h4_close = h4[-1]["close"]
    prior_high = max(x["high"] for x in h1[-17:-1])
    prior_low = min(x["low"] for x in h1[-17:-1])
    h4_direction = 1 if h4_close > h4[-4]["close"] else (-1 if h4_close < h4[-4]["close"] else 0)
    high_break = h1_close > prior_high
    low_break = h1_close < prior_low
    h1_direction = 1 if h1_close > h1[-7]["close"] else (-1 if h1_close < h1[-7]["close"] else 0)
    vote, strength, event = 0, 0, "mixed_or_range"
    if h1_direction == 1 and h4_direction == 1:
        vote, strength, event = 1, 2 if high_break else 1, "multi_timeframe_up"
    elif h1_direction == -1 and h4_direction == -1:
        vote, strength, event = -1, 2 if low_break else 1, "multi_timeframe_down"
    return result("05_structure_navigator", vote, strength,
                  {"event": event, "h1_break_prior_16h_high": high_break,
                   "h1_break_prior_16h_low": low_break, "h1_direction": h1_direction,
                   "h4_direction": h4_direction})


# AGENT 6: RISK MARSHAL - hard veto and illustrative price structure; no orders.
def risk_marshal(ticker, bars, proposed, profile):
    previous = bars[-16:]
    ranges = [max(x["high"] - x["low"], 1e-15) for x in previous]
    median_range = statistics.median(ranges)
    entry = bars[-1]["close"]
    volatility_bp = 10000 * median_range / entry
    spread_bp = ticker["spread_bp"]
    veto_reasons = []
    if spread_bp > 15:
        veto_reasons.append("spread_over_15bp")
    if volatility_bp > 500:
        veto_reasons.append("15m_median_range_over_5pct")
    if proposed == 0:
        veto_reasons.append("insufficient_agent_consensus")
    stop = target = reward_risk = None
    if proposed:
        # Stops use actual recent extreme and volatility reserve (research-only).
        if proposed > 0:
            stop = min(min(b["low"] for b in bars[-8:]), entry - 1.1 * median_range)
            distance = entry - stop
            # The measured next value-area edge is preferred when it supports >=1.8R.
            profile_target = profile.get("VAH_approx", 0)
            target = max(entry + 2 * distance, profile_target)
        else:
            stop = max(max(b["high"] for b in bars[-8:]), entry + 1.1 * median_range)
            distance = stop - entry
            profile_target = profile.get("VAL_approx", 0)
            target = min(entry - 2 * distance, profile_target) if profile_target else entry - 2 * distance
        distance_bp = 10000 * distance / entry
        if distance_bp > 350 or distance_bp < 5:
            veto_reasons.append("stop_distance_outside_5_to_350bp")
        if target <= 0:
            veto_reasons.append("nonpositive_target")
        else:
            reward_risk = abs(target - entry) / distance if distance else None
    veto = bool(veto_reasons)
    return result("06_risk_marshal", 0, 0, {
        "proposed_direction": "LONG" if proposed == 1 else "SHORT" if proposed == -1 else "WAIT",
        "median_15m_range_bp": round(volatility_bp, 1),
        "indicative_entry_not_an_order": entry,
        "indicative_stop_not_an_order": round(stop, 9) if stop else None,
        "indicative_target_not_an_order": round(target, 9) if target and target > 0 else None,
        "illustrative_reward_to_risk": round(reward_risk, 2) if reward_risk else None,
        "reasons": veto_reasons, "max_example_account_risk_per_trade_pct": 0.5,
        "warning": "No leverage or exposure applied. Targets are examples and not forecasts."}, veto=veto)


def summarize_agents(ticker, bars, hourly, four_hourly, book, trades, funding, interest, mark, *, asof_epoch=None):
    checks = [liquidity_sentinel(ticker, book, asof_epoch=asof_epoch), auction_cartographer(bars),
              tape_detective(book, trades), derivatives_intelligence(funding, interest, mark, ticker["last"]),
              structure_navigator(hourly, four_hourly)]
    votes = checks[1:]
    bullish = sum(x["strength"] for x in votes if x["vote"] == 1)
    bearish = sum(x["strength"] for x in votes if x["vote"] == -1)
    bullish_agents = sum(x["vote"] == 1 for x in votes)
    bearish_agents = sum(x["vote"] == -1 for x in votes)
    proposal = 0
    # Score is an ordinal heuristic, NEVER a calibrated probability of winning.
    if bullish >= 3 and bullish_agents >= 2 and bullish - bearish >= 2:
        proposal = 1
    elif bearish >= 3 and bearish_agents >= 2 and bearish - bullish >= 2:
        proposal = -1
    profile = checks[1]["evidence"]
    risk = risk_marshal(ticker, bars, proposal, profile)
    checks.append(risk)
    if any(agent["veto"] for agent in checks):
        signal = "WAIT"
    else:
        signal = "LONG" if proposal == 1 else "SHORT" if proposal == -1 else "WAIT"
    return {
        "symbol": ticker["symbol"], "signal": signal,
        "ordinal_buy_points": bullish, "ordinal_sell_points": bearish,
        "num_bullish_agents": bullish_agents, "num_bearish_agents": bearish_agents,
        "quote_price": ticker["last"], "last_complete_15m_candle_ms": bars[-1]["ts"],
        "execution": "DISABLED", "order_count": 0, "agents": checks,
    }


def grab(symbol, path, params):
    return okx_get(path, {"instId": symbol, **params})


def analyze_market(ticker):
    symbol = ticker["symbol"]
    bars15 = candles(grab(symbol, "/api/v5/market/candles", {"bar": "15m", "limit": "210"}))
    bars1h = candles(grab(symbol, "/api/v5/market/candles", {"bar": "1H", "limit": "80"}))
    bars4h = candles(grab(symbol, "/api/v5/market/candles", {"bar": "4H", "limit": "50"}))
    if len(bars15) < 192 or len(bars1h) < 30 or len(bars4h) < 15:
        raise ValueError("Insufficient completed multi-timeframe candles")
    book_rows = grab(symbol, "/api/v5/market/books", {"sz": "50"})
    trade_rows = grab(symbol, "/api/v5/market/trades", {"limit": "200"})
    if not book_rows:
        raise ValueError("Orderbook unavailable")
    # Risk-critical feeds: missing derivatives data causes abstention rather than made-up votes.
    try:
        funding_rows = grab(symbol, "/api/v5/public/funding-rate", {})
        oi_rows = okx_get("/api/v5/public/open-interest", {"instType": "SWAP", "instId": symbol})
        mark_rows = okx_get("/api/v5/public/mark-price", {"instType": "SWAP", "instId": symbol})
        derivatives_errors = []
    except (RuntimeError, ValueError) as exc:
        funding_rows, oi_rows, mark_rows = [], [], []
        derivatives_errors = [str(exc)[:120]]
    record = summarize_agents(ticker, bars15, bars1h, bars4h, book_rows[0], trade_rows,
                              funding_rows[0] if funding_rows else {},
                              oi_rows[0] if oi_rows else {}, mark_rows[0] if mark_rows else {})
    # Seven quantitative diagnostic systems now validate the original six-agent consensus.
    advanced = evaluate_advanced(bars15, book_rows[0], trade_rows, record)
    record.update(advanced)
    # Ten Omega research diagnostics inspect risk and rank expected target speed.
    # Existing six-agent and seven-system vetoes remain mandatory.
    omega = evaluate_omega(bars15, bars1h, bars4h, book_rows[0], trade_rows,
                           ticker, funding_rows[0] if funding_rows else {},
                           oi_rows[0] if oi_rows else {}, mark_rows[0] if mark_rows else {}, record)
    record.update(omega)
    if record["signal"] in ("LONG", "SHORT") and omega["omega_veto_reasons"]:
        record["signal"] = "WAIT"
    if derivatives_errors or not funding_rows or not oi_rows or not mark_rows:
        record["advanced_veto_reasons"].append("missing_or_unavailable_derivatives_data")
        record["signal"] = "WAIT"
    record["derivatives_data_warnings"] = derivatives_errors
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=6)
    parser.add_argument("--out", default="reports/okx_six_agents.json")
    args = parser.parse_args()
    if not 1 <= args.top <= 12:
        parser.error("--top must be in 1..12")
    try:
        pool = select_markets(okx_get("/api/v5/market/tickers", {"instType": "SWAP"}), args.top)
        results, errors = [], []
        for market in pool:
            try:
                results.append(analyze_market(market))
            except Exception as exc:
                errors.append({"symbol": market["symbol"], "reason": str(exc)[:160]})
            time.sleep(0.4)
        report = {"utc_timestamp": datetime.now(timezone.utc).isoformat(),
                  "mode": "SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY", "genuine_llm_agents": 0,
                  "core_specialist_agents": 6, "advanced_quant_systems": 7,
                  "omega_system_count": 10, "omega_qubo_best_symbol": qubo_pick(results),
                  "orders_placed": 0, "timeframe_main": "15m", "volume_profile_window": "48h_approx",
                  "minimum_estimated_turnover_usdt": MIN_TURNOVER_USDT_EST,
                  "markets_selected": len(pool), "markets_analyzed": len(results),
                  "actionable_research_labels": sum(x["signal"] != "WAIT" for x in results),
                  "results": results, "errors": errors,
                  "risk_notice": "Heuristic signals only, no proven edge, no order execution, no guaranteed profit."}
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("SIX AGENTS + QUANT2037: selected=", len(pool), "analyzed=", len(results),
              "signals=", report["actionable_research_labels"], "errors=", len(errors))
        for x in results:
            print(x["symbol"], x["signal"], "bull=", x["ordinal_buy_points"],
                  "bear=", x["ordinal_sell_points"], "agents=", len(x["agents"]))
        for err in errors:
            print("DATA ERROR", err["symbol"], err["reason"])
        print("Full evidence report:", path)
        return 0 if results else 2
    except Exception as exc:
        print("Public scan error, no trades attempted:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

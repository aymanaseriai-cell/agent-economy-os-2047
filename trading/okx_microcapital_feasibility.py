#!/usr/bin/env python3
"""Public, read-only OKX minimum swap notional scan for very small accounts.

Never signs in, sends orders, sets leverage or touches a trading account.
Screening is preliminary: actual account eligibility needs exchange prechecks.
"""
from __future__ import annotations
import argparse
import json
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://www.okx.com"

def positive_decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid decimal") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError("expected positive finite decimal")
    return result

def minimum_notional(inst, price):
    """Minimum linear USDT-SWAP order notional, or None if unsupported."""
    symbol = inst.get("instId", "")
    parts = symbol.split("-")
    if (len(parts) != 3 or parts[1:] != ["USDT", "SWAP"]
            or inst.get("state") != "live"
            or inst.get("settleCcy") != "USDT"
            or inst.get("ctValCcy") != parts[0]):
        return None
    try:
        min_size = positive_decimal(inst.get("minSz"))
        lot = positive_decimal(inst.get("lotSz"))
        contract_value = positive_decimal(inst.get("ctVal"))
        last = positive_decimal(price)
    except ValueError:
        return None
    order_size = (min_size / lot).to_integral_value(rounding=ROUND_CEILING) * lot
    return order_size * contract_value * last

def evaluate(instruments, tickers, *, equity, leverage=20,
             max_notional_fraction=Decimal("0.20"),
             max_margin_fraction=Decimal("0.05")):
    equity = positive_decimal(equity)
    leverage = positive_decimal(leverage)
    max_notional_fraction = positive_decimal(max_notional_fraction)
    max_margin_fraction = positive_decimal(max_margin_fraction)
    cap = min(equity * max_notional_fraction,
              equity * max_margin_fraction * leverage)
    prices = {x.get("instId"): x.get("last") for x in tickers}
    rows = []
    for instrument in instruments:
        inst_id = instrument.get("instId", "")
        if inst_id not in prices:
            continue
        value = minimum_notional(instrument, prices[inst_id])
        if value is None:
            continue
        rows.append({"instrument": inst_id, "min_notional_usdt": str(value),
                     "within_budget": value <= cap})
    rows.sort(key=lambda x: Decimal(x["min_notional_usdt"]))
    eligible = [row for row in rows if row["within_budget"]]
    return {"equity_usdt": str(equity), "max_notional_budget_usdt": str(cap),
            "examined": len(rows), "preliminarily_within_budget": len(eligible),
            "closest": rows[:15],
            "warning": "READ ONLY: preliminary public contract screen, not an account order precheck. Fees, account max-size, margin, spread and liquidation can still block orders."}

def fetch_public(path, params):
    url = API + path + "?" + urlencode(params)
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "titan-research-only/1.0"})
    with urlopen(req, timeout=20) as response:
        payload = json.load(response)
    if payload.get("code") != "0" or not isinstance(payload.get("data"), list):
        raise RuntimeError("Invalid OKX public response; no assumed eligibility")
    return payload["data"]

def main():
    parser = argparse.ArgumentParser(description="Public OKX micro-equity swap prefilter; NO ORDERS")
    parser.add_argument("--equity", default="4.14")
    parser.add_argument("--leverage", default="20")
    args = parser.parse_args()
    instruments = fetch_public("/api/v5/public/instruments", {"instType": "SWAP"})
    tickers = fetch_public("/api/v5/market/tickers", {"instType": "SWAP"})
    result = evaluate(instruments, tickers, equity=args.equity, leverage=args.leverage)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()

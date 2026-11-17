#!/usr/bin/env python3
"""TITAN Omega: explicit operator-selected one-shot OKX USDT-SWAP execution.

No strategy or symbol selection occurs here. preflight = GET only.
execute = explicitly armed manual dispatch, full second preflight, then one
market entry with attached TP/SL; emergency reduce-only exits are possible.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP, InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request, urlopen

D = Decimal
ALLOWED_DOMAINS = frozenset(("https://www.okx.com", "https://eea.okx.com", "https://us.okx.com"))
ARM = "I_ACCEPT_REAL_MONEY_LOSS"
DYNAMIC_ARM = "I_ACCEPT_VARIABLE_10_TO_100X_LIQUIDATION_RISK"
CONFIRM = "I_AUTHORIZE_ONE_REAL_OKX_SWAP"
MAX_QUOTE_AGE_MS = 120_000
COOLDOWN_MS = 300_000
MAX_COST_FRACTION = D("0.0025")  # stress allowance: fees+slippage; actual can exceed
MAX_PLANNED_RISK_FRACTION = D("0.02")  # 2% estimated USDT equity at SL including cost stress
MAX_MARGIN_FRACTION = D("0.20")  # no more than 20% available USDT equity
MAX_NOTIONAL_FRACTION = D("4")


class Blocked(RuntimeError):
    pass


def num(value):
    try:
        x = D(str(value))
        if not x.is_finite():
            raise ValueError("non-finite")
        return x
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise Blocked("INVALID_NUMERIC_DATA") from exc


def neat(x):
    return format(x.normalize(), "f") if x else "0"


def round_step(x, step, rounding=ROUND_DOWN):
    if step <= 0:
        raise Blocked("INVALID_CONTRACT_STEP")
    return (x / step).to_integral_value(rounding=rounding) * step


@dataclass(frozen=True)
class Plan:
    symbol: str
    direction: str
    leverage: int
    margin_cap: str
    observed_price: str
    observed_ms: int
    take_profit: str
    stop_loss: str
    plan_id: str

    def validate(self, now_ms):
        if re.fullmatch(r"[A-Z0-9]{2,22}-USDT-SWAP", self.symbol) is None:
            raise Blocked("INVALID_SYMBOL")
        if self.direction not in ("LONG", "SHORT"):
            raise Blocked("INVALID_DIRECTION")
        if type(self.leverage) is not int or not 1 <= self.leverage <= 100:
            raise Blocked("INVALID_LEVERAGE")
        if re.fullmatch(r"[A-Za-z0-9_-]{12,32}", self.plan_id) is None:
            raise Blocked("INVALID_PLAN_ID")
        if not 0 <= now_ms - self.observed_ms <= MAX_QUOTE_AGE_MS:
            raise Blocked("OPERATOR_QUOTE_EXPIRED")
        ref, cap, target, stop = map(num, (self.observed_price, self.margin_cap, self.take_profit, self.stop_loss))
        if min(ref, cap, target, stop) <= 0:
            raise Blocked("NON_POSITIVE_PRICE_OR_BUDGET")
        if self.direction == "LONG" and not stop < ref < target:
            raise Blocked("INVALID_LONG_TP_SL")
        if self.direction == "SHORT" and not target < ref < stop:
            raise Blocked("INVALID_SHORT_TP_SL")
        return ref, cap, target, stop


class OKXClient:
    """Authenticated OKX client; block every POST in read-only preflight."""

    def __init__(self, env, *, read_only=True, transport=None):
        self.env = env
        self.read_only = read_only
        self.transport = transport
        self.domain = env.get("OKX_API_DOMAIN", "https://www.okx.com").rstrip("/")
        if self.domain not in ALLOWED_DOMAINS:
            raise Blocked("UNTRUSTED_API_DOMAIN")
        self.key = env.get("OKX_API_KEY", "")
        self.secret = env.get("OKX_SECRET_KEY", "")
        self.passphrase = env.get("OKX_PASSPHRASE", "")

    def request(self, method, path, *, params=None, body=None, auth=True):
        if method not in ("GET", "POST") or not path.startswith("/api/v5/"):
            raise Blocked("INVALID_API_METHOD_OR_PATH")
        if self.read_only and method != "GET":
            raise Blocked("PREFLIGHT_FORBIDS_POST")
        if method == "POST" and (not auth or path not in {
                "/api/v5/account/set-leverage", "/api/v5/trade/order",
                "/api/v5/trade/cancel-order"}):
            raise Blocked("UNAUTHORIZED_WRITE_ENDPOINT")
        if auth and not all((self.key, self.secret, self.passphrase)):
            raise Blocked("MISSING_OKX_API_CREDENTIALS")
        query = "?" + urlencode(params) if params else ""
        req_path = path + query
        body_s = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if body is not None else ""
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "User-Agent": "TitanOmega-DirectGated/1.0"}
        if auth:
            ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            digest = hmac.new(self.secret.encode(), (ts + method + req_path + body_s).encode(), hashlib.sha256).digest()
            headers.update({"OK-ACCESS-KEY": self.key,
                            "OK-ACCESS-SIGN": base64.b64encode(digest).decode(),
                            "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": self.passphrase})
        request = {"method": method, "path": path, "params": params,
                   "body": body, "auth": auth, "url": self.domain + req_path}
        try:
            if self.transport:
                result = self.transport(request)
            else:
                data = body_s.encode() if body is not None else None
                raw = Request(request["url"], method=method, data=data, headers=headers)
                with urlopen(raw, timeout=15) as response:
                    result = json.load(response)
        except Exception as exc:
            # POST may have reached OKX: NEVER retry based on a network error.
            raise Blocked("OKX_IO_UNCERTAIN_CHECK_ACCOUNT_MANUALLY") from exc
        if not isinstance(result, dict) or str(result.get("code")) != "0" or not isinstance(result.get("data"), list):
            raise Blocked("OKX_API_REJECTED_REQUEST")
        return result["data"]

    def get(self, path, params=None, *, auth=True):
        return self.request("GET", path, params=params, auth=auth)

    def post(self, path, body):
        return self.request("POST", path, body=body, auth=True)


def single(rows, error):
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise Blocked(error)
    return rows[0]


def cooldown_check(client, now_ms):
    rows = client.get("/api/v5/account/positions-history", {"instType": "SWAP", "limit": "100"})
    if len(rows) > 100:
        raise Blocked("POSITION_HISTORY_UNVERIFIABLE")
    stamps = []
    for row in rows:
        if not isinstance(row, dict):
            raise Blocked("POSITION_HISTORY_UNVERIFIABLE")
        try:
            t = int(row.get("uTime", ""))
        except (ValueError, TypeError):
            raise Blocked("POSITION_HISTORY_UNVERIFIABLE")
        if t <= 0 or t > now_ms + 60_000:
            raise Blocked("POSITION_HISTORY_UNVERIFIABLE")
        stamps.append(t)
        if str(row.get("type")) in ("2", "3", "6") and t > now_ms - COOLDOWN_MS:
            raise Blocked("300_SECOND_EXIT_COOLDOWN_ACTIVE")
    if len(rows) == 100 and stamps and min(stamps) > now_ms - COOLDOWN_MS:
        raise Blocked("POSITION_HISTORY_REQUIRES_PAGINATION")


def account_state(client, now_ms):
    cfg = single(client.get("/api/v5/account/config"), "ACCOUNT_CONFIG_UNVERIFIABLE")
    if cfg.get("posMode") != "net_mode":
        raise Blocked("ACCOUNT_NOT_NET_MODE")
    positions = client.get("/api/v5/account/positions", {"instType": "SWAP"})
    if any(num(z.get("pos", "0")) != 0 for z in positions):
        raise Blocked("EXISTING_SWAP_POSITION")
    pending = client.get("/api/v5/trade/orders-pending", {"instType": "SWAP"})
    if pending:
        raise Blocked("EXISTING_SWAP_ORDER")
    for k in ("conditional", "oco", "trigger", "move_order_stop"):
        pending_algo = client.get("/api/v5/trade/orders-algo-pending", {"ordType": k})
        if any(str(z.get("instId", "")).endswith("-SWAP") for z in pending_algo):
            raise Blocked("EXISTING_SWAP_ALGO_ORDER")
    bal = single(client.get("/api/v5/account/balance", {"ccy": "USDT"}), "BALANCE_UNVERIFIABLE")
    details = [z for z in bal.get("details", []) if z.get("ccy") == "USDT"]
    if len(details) != 1:
        raise Blocked("USDT_EQUITY_UNVERIFIABLE")
    row = details[0]
    # Use currency-specific equity, not totalEq including other currencies.
    eq = num(row.get("eq"))
    free = num(row.get("availEq") or row.get("availBal"))
    if eq <= 0 or free <= 0:
        raise Blocked("NO_AVAILABLE_USDT")
    cooldown_check(client, now_ms)
    return min(eq, free)


def public_market(client, p: Plan, now_ms):
    tick = single(client.get("/api/v5/market/ticker", {"instId": p.symbol}, auth=False), "NO_FRESH_TICKER")
    inst = single(client.get("/api/v5/public/instruments", {"instType": "SWAP", "instId": p.symbol}, auth=False), "NO_INSTRUMENT")
    if (tick.get("instId") != p.symbol or inst.get("instId") != p.symbol
            or inst.get("state") != "live" or inst.get("ctType") != "linear"
            or inst.get("settleCcy") != "USDT" or inst.get("ctValCcy") != p.symbol.split("-")[0]
            or str(inst.get("instCategory", "")) != "1"):
        raise Blocked("INELIGIBLE_SWAP_INSTRUMENT")
    if num(inst.get("lever")) < p.leverage:
        raise Blocked("EXCEEDS_INSTRUMENT_MAX_LEVERAGE")
    ts = int(tick.get("ts") or 0)
    if not 0 <= now_ms - ts <= 15000:
        raise Blocked("TICKER_STALE")
    last, bid, ask = (num(tick.get(k)) for k in ("last", "bidPx", "askPx"))
    if min(last, bid, ask) <= 0 or bid > ask:
        raise Blocked("INVALID_LIVE_SPREAD")
    if (ask - bid) / ((ask + bid) / 2) > D("0.0015"):
        raise Blocked("SPREAD_OVER_15_BPS")
    if num(tick.get("volCcy24h")) * last < D("15000000"):
        raise Blocked("LOW_USDT_TURNOVER")
    ref, budget, target, stop = p.validate(now_ms)
    entry = ask if p.direction == "LONG" else bid
    if abs(entry / ref - 1) > D("0.005"):
        raise Blocked("PRICE_MOVED_FROM_OPERATOR_QUOTE")
    tick_size = num(inst.get("tickSz"))
    stop = round_step(stop, tick_size, ROUND_DOWN if p.direction == "LONG" else ROUND_UP)
    target = round_step(target, tick_size, ROUND_UP if p.direction == "LONG" else ROUND_DOWN)
    if (p.direction == "LONG" and not stop < entry < target) or (p.direction == "SHORT" and not target < entry < stop):
        raise Blocked("PRICE_LEVELS_INVALID_AFTER_TICKS")
    stop_frac = abs(entry - stop) / entry
    reward_ratio = abs(target - entry) / abs(entry - stop)
    if not D("0.001") <= stop_frac <= D("0.035") or reward_ratio < D("2.5"):
        raise Blocked("STOP_DISTANCE_OR_RR_UNSAFE")
    # This is a buffer against a theoretical bankruptcy threshold, NOT an
    # exchange-estimated liquidation price. Exact liquidation remains unknown
    # before a real position opens; MMR, fees and volatility can worsen it.
    if stop_frac + D("0.015") >= D(1) / p.leverage:
        raise Blocked("STOP_TOO_CLOSE_TO_THEORETICAL_BANKRUPTCY")
    book = single(client.get("/api/v5/market/books", {"instId": p.symbol, "sz": "20"}, auth=False), "ORDERBOOK_MISSING")
    if not 0 <= now_ms - int(book.get("ts") or 0) <= 15000:
        raise Blocked("ORDERBOOK_STALE")
    funding = single(client.get("/api/v5/public/funding-rate", {"instId": p.symbol}, auth=False), "FUNDING_MISSING")
    if abs(num(funding.get("fundingRate"))) > D("0.002"):
        raise Blocked("EXCESSIVE_FUNDING")
    candles = client.get("/api/v5/market/candles", {"instId": p.symbol, "bar": "5m", "limit": "30"}, auth=False)
    closed = sorted([row for row in candles if len(row) >= 9 and str(row[8]) == "1"],
                    key=lambda r: int(r[0]), reverse=True)
    if len(closed) < 12:
        raise Blocked("INSUFFICIENT_COMPLETED_CANDLES")
    if not 0 <= now_ms - int(closed[0][0]) - 300_000 <= 600_000:
        raise Blocked("COMPLETED_CANDLES_STALE")
    momentum = num(closed[0][4]) / num(closed[6][4]) - 1
    if (p.direction == "LONG" and momentum < D("0.001")) or (p.direction == "SHORT" and momentum > D("-0.001")):
        raise Blocked("OPERATOR_DIRECTION_CONTRADICTED_BY_MOMENTUM")
    swing = max(num(z[2]) for z in closed[:8]) / min(num(z[3]) for z in closed[:8]) - 1
    if swing > D("0.08"):
        raise Blocked("EXCESSIVE_5M_VOLATILITY")
    return inst, entry, stop, target, stop_frac, book


def account_leverage(client, p):
    result = single(client.get("/api/v5/account/adjust-leverage-info", {
        "instType": "SWAP", "mgnMode": "isolated", "instId": p.symbol,
        "lever": str(p.leverage), "posSide": "net"}), "LEVERAGE_TIER_UNVERIFIABLE")
    if num(result.get("maxLever")) < p.leverage:
        raise Blocked("EXCEEDS_ACCOUNT_LEVERAGE_TIER")


def max_contracts(client, p):
    result = single(client.get("/api/v5/account/max-size", {
        "instId": p.symbol, "tdMode": "isolated"}), "MAX_SIZE_UNVERIFIABLE")
    return num(result.get("maxBuy" if p.direction == "LONG" else "maxSell"))


def size_order(p, equity, inst, entry, stop_frac, book, max_allowed=None):
    budget = num(p.margin_cap)
    ctval, minimum, lot = (num(inst.get(k)) for k in ("ctVal", "minSz", "lotSz"))
    if min(ctval, minimum, lot) <= 0:
        raise Blocked("INVALID_CONTRACT_SPEC")
    per_contract = entry * ctval
    # Independent caps: user margin ceiling, 20% equity margin, 4x notional,
    # and 2%-equity estimated loss including a 25bps fee/slippage stress.
    notional_budget = min(
        min(budget, equity * MAX_MARGIN_FRACTION) * p.leverage,
        equity * MAX_NOTIONAL_FRACTION,
        equity * MAX_PLANNED_RISK_FRACTION / (stop_frac + MAX_COST_FRACTION))
    if max_allowed is not None:
        notional_budget = min(notional_budget, max_allowed * per_contract)
    qty = round_step(notional_budget / per_contract, lot)
    if qty < minimum or qty <= 0:
        raise Blocked("MIN_CONTRACT_EXCEEDS_RISK_BUDGET")
    notional = qty * per_contract
    if (notional / p.leverage > min(budget, equity * MAX_MARGIN_FRACTION)
            or notional * (stop_frac + MAX_COST_FRACTION) > equity * MAX_PLANNED_RISK_FRACTION):
        raise Blocked("SIZING_RISK_INVARIANT_FAILED")
    levels = book.get("asks" if p.direction == "LONG" else "bids")
    if not isinstance(levels, list) or not levels:
        raise Blocked("EMPTY_ORDERBOOK_SIDE")
    remain, value = qty, D("0")
    for level in levels:
        if len(level) < 2:
            raise Blocked("INVALID_ORDERBOOK_LEVEL")
        px, contracts = num(level[0]), num(level[1])
        if px <= 0 or contracts < 0:
            raise Blocked("INVALID_ORDERBOOK_LEVEL")
        take = min(remain, contracts)
        remain -= take
        value += take * px
        if remain <= 0:
            break
    if remain > 0:
        raise Blocked("INSUFFICIENT_BOOK_DEPTH")
    avg = value / qty
    adverse = avg / entry - 1 if p.direction == "LONG" else 1 - avg / entry
    if adverse > D("0.0015"):
        raise Blocked("BOOK_SLIPPAGE_OVER_15_BPS")
    return qty


def client_id(p):
    # Deterministic across retries for duplicate avoidance (<= 32 OKX chars).
    message = "|".join((p.plan_id, p.symbol, p.direction, str(p.observed_ms)))
    return "Q37DIRECT" + hashlib.sha256(message.encode()).hexdigest()[:23]


def no_duplicate(client, order_id, now_ms):
    cutoff = now_ms - 86400000
    cursor = None
    for _ in range(20):
        params = {"instType": "SWAP", "limit": "100"}
        if cursor:
            params["after"] = cursor
        rows = client.get("/api/v5/trade/orders-history", params)
        if not rows:
            return
        for x in rows:
            if x.get("clOrdId") == order_id:
                raise Blocked("DUPLICATE_DIRECT_PLAN")
        last_time = min(int(x.get("cTime") or x.get("uTime") or 0) for x in rows)
        if last_time <= 0:
            raise Blocked("ORDER_HISTORY_UNVERIFIABLE")
        if len(rows) < 100 or last_time < cutoff:
            return
        cursor = rows[-1].get("ordId")
        if not cursor:
            raise Blocked("ORDER_HISTORY_UNVERIFIABLE")
    raise Blocked("ORDER_HISTORY_PAGINATION_INCOMPLETE")


def is_live_authorized(env, confirmation):
    if confirmation != CONFIRM:
        raise Blocked("ONE_OFF_LIVE_APPROVAL_MISSING")
    if (env.get("OKX_EXECUTION_MODE") != "live" or
            env.get("OKX_ENABLE_REAL_TRADING") != "YES" or
            env.get("OKX_STOP_CONTINUOUS", "YES") != "NO" or
            env.get("OKX_EXECUTION_ARM") != ARM or
            env.get("OKX_DYNAMIC_LEVERAGE_ARM") != DYNAMIC_ARM or
            env.get("OKX_LEVERAGE_MODE") != "dynamic" or
            env.get("OKX_CAPITAL_MODE") != "adaptive_guarded" or
            env.get("OKX_MAX_ACTIVE_POSITIONS") != "1" or
            env.get("OKX_AUTOREENTRY_ENABLED", "NO") != "NO"):
        raise Blocked("LIVE_ACCOUNT_SETTINGS_NOT_FULLY_ARMED")
    if not all(env.get(k) for k in ("OKX_API_KEY", "OKX_SECRET_KEY", "OKX_PASSPHRASE")):
        raise Blocked("MISSING_PRIVATE_CREDENTIALS")


def preflight(p, client, now_ms):
    # No order POST or leverage POST during preflight.
    p.validate(now_ms)
    inst, entry, sl, tp, fraction, book = public_market(client, p, now_ms)
    equity = account_state(client, now_ms)
    account_leverage(client, p)
    qty = size_order(p, equity, inst, entry, fraction, book)
    return {"qty": qty, "entry": entry, "tp": tp, "sl": sl,
            "eq": equity, "inst": inst, "fraction": fraction,
            "book": book, "symbol": p.symbol}


def emergency_close(client, p):
    positions = client.get("/api/v5/account/positions", {"instType": "SWAP", "instId": p.symbol})
    qty = sum((abs(num(x.get("pos", "0"))) for x in positions), D("0"))
    if qty <= 0:
        raise Blocked("EMERGENCY_POSITION_NOT_FOUND_CHECK_OKX")
    result = client.post("/api/v5/trade/order", {
        "instId": p.symbol, "tdMode": "isolated", "posSide": "net",
        "side": "sell" if p.direction == "LONG" else "buy", "ordType": "market",
        "reduceOnly": True, "sz": neat(qty)})
    if len(result) != 1 or result[0].get("sCode") != "0":
        raise Blocked("EMERGENCY_CLOSE_REJECTED_CHECK_OKX")
    raise Blocked("EMERGENCY_CLOSE_SENT_VERIFY_IN_OKX")


def verify_after_entry(client, p, cid, expected_qty, planned_entry, planned_stop, planned_tp,
                       *, sleeper=time.sleep):
    order = None
    for _ in range(5):
        try:
            rows = client.get("/api/v5/trade/order", {"instId": p.symbol, "clOrdId": cid})
        except Exception:
            emergency_close(client, p)
        if len(rows) == 1 and rows[0].get("state") in ("filled", "canceled"):
            order = rows[0]
            break
        sleeper(1)
    if not order or order.get("state") != "filled":
        # Never assume a partially filled order has no exposure.
        try:
            client.post("/api/v5/trade/cancel-order", {"instId": p.symbol, "clOrdId": cid})
        except Exception:
            pass
        emergency_close(client, p)
    if (order.get("instId") != p.symbol or order.get("clOrdId") != cid
            or order.get("side") != ("buy" if p.direction == "LONG" else "sell")
            or num(order.get("sz")) != expected_qty
            or num(order.get("accFillSz")) != expected_qty):
        emergency_close(client, p)
    fill_px = num(order.get("avgPx"))
    if fill_px <= 0 or abs(fill_px / planned_entry - 1) > D("0.005"):
        emergency_close(client, p)
    if (p.direction == "LONG" and not planned_stop < fill_px < planned_tp) or (
            p.direction == "SHORT" and not planned_tp < fill_px < planned_stop):
        emergency_close(client, p)
    verified_position = False
    for _ in range(5):
        try:
            positions = client.get("/api/v5/account/positions", {"instType": "SWAP", "instId": p.symbol})
        except Exception:
            emergency_close(client, p)
        active = [z for z in positions if num(z.get("pos", "0")) != 0]
        if (len(active) == 1 and active[0].get("instId") == p.symbol
                and active[0].get("mgnMode") == "isolated"
                and num(active[0]["pos"]) ==
                (expected_qty if p.direction == "LONG" else -expected_qty)):
            verified_position = True
            break
        sleeper(1)
    if not verified_position:
        emergency_close(client, p)
    for _ in range(5):
        try:
            algos = (client.get("/api/v5/trade/orders-algo-pending", {"ordType": "oco"}) +
                     client.get("/api/v5/trade/orders-algo-pending", {"ordType": "conditional"}))
        except Exception:
            emergency_close(client, p)
        if any(z.get("instId") == p.symbol and z.get("tpTriggerPx") and z.get("slTriggerPx") for z in algos):
            return "FILLED_AND_TPSL_VISIBLE_IN_OKX"
        sleeper(1)
    emergency_close(client, p)


def execute(p, env, confirmation, *, client=None, now_ms=None):
    # Fail BEFORE any API call if explicit per-order live arming is absent.
    is_live_authorized(env, confirmation)
    now = int(time.time() * 1000) if now_ms is None else now_ms
    # Read-only preflight uses its own GET-only client.
    readonly = OKXClient(env, read_only=True, transport=client.transport if client else None)
    preflight(p, readonly, now)
    trading = client or OKXClient(env, read_only=False)
    cid = client_id(p)
    no_duplicate(trading, cid, now)
    result = trading.post("/api/v5/account/set-leverage", {
        "instId": p.symbol, "lever": str(p.leverage), "mgnMode": "isolated"})
    if len(result) != 1 or num(result[0].get("lever")) != p.leverage:
        raise Blocked("EXCHANGE_LEVERAGE_CONFIRMATION_FAILED")
    # Recheck latest available balance, positions, market and 300s cooldown
    # after the leverage change, then the exchange-specific maximum order size.
    now = int(time.time() * 1000) if now_ms is None else now_ms
    safe = preflight(p, readonly, now)
    qty = size_order(p, safe["eq"], safe["inst"], safe["entry"], safe["fraction"], safe["book"],
                     max_allowed=max_contracts(trading, p))
    no_duplicate(trading, cid, now)
    # No automatic re-entry, retry or alternate symbol. Emergency exits possible.
    response = trading.post("/api/v5/trade/order", {
        "instId": p.symbol, "tdMode": "isolated", "posSide": "net",
        "side": "buy" if p.direction == "LONG" else "sell",
        "ordType": "market", "sz": neat(qty), "clOrdId": cid,
        "attachAlgoOrds": [{"tpTriggerPx": neat(safe["tp"]), "tpOrdPx": "-1",
                            "tpTriggerPxType": "mark", "slTriggerPx": neat(safe["sl"]),
                            "slOrdPx": "-1", "slTriggerPxType": "mark"}]})
    if len(response) != 1 or response[0].get("sCode") != "0":
        raise Blocked("EXCHANGE_REJECTED_ORDER_NO_BLIND_RETRY")
    # Public GitHub log never prints private order ID, collateral or size.
    return verify_after_entry(trading, p, cid, qty, safe["entry"], safe["sl"], safe["tp"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "execute"), required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    try:
        if len(args.plan_json) > 3000:
            raise Blocked("PLAN_TOO_LONG")
        fields = json.loads(args.plan_json)
        if not isinstance(fields, dict):
            raise Blocked("MALFORMED_OPERATOR_PLAN")
        p = Plan(**fields)
        if args.mode == "preflight":
            # Strict read-only GET guard, regardless of env live settings.
            preflight(p, OKXClient(dict(os.environ), read_only=True),
                      int(time.time() * 1000))
            print("TITAN DIRECT: READ_ONLY_PREFLIGHT_PASSED; NO ORDERS")
        else:
            result = execute(p, dict(os.environ), args.confirm)
            print("TITAN DIRECT: " + result)
        return 0
    except Blocked as exc:
        print("TITAN DIRECT NO TRADE: " + str(exc), file=sys.stderr)
        return 2
    except Exception:
        # Do not leak private account values or raw API payloads into Actions logs.
        print("TITAN DIRECT: UNCERTAIN_STATE_INSPECT_OKX_MANUALLY", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

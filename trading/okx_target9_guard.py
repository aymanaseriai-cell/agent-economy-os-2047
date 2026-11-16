"""One-way, explicitly armed 9 USDT equity exit for OKX USDT-SWAP.

This module cannot promise 9 USDT after realized fills, fees, slippage or funding.
No entries are made here. Every uncertain exchange state blocks the trade worker.
"""
import os
import sys
import time
from decimal import Decimal, InvalidOperation
from trading.okx_live_executor import OKX, ExecutionBlocked, check_mode

TARGET = Decimal("9")
ARM = "I_AUTHORIZE_CLOSE_USDT_SWAPS_AT_9_USDT"
ALGO_TYPES = ("conditional", "oco", "trigger", "move_order_stop")


def _num(value):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ExecutionBlocked("Target9: invalid equity/position") from exc
    if not value.is_finite():
        raise ExecutionBlocked("Target9: non-finite equity/position")
    return value


def usdt_equity(client):
    rows = client.request("GET", "/api/v5/account/balance", params={"ccy": "USDT"})
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ExecutionBlocked("Target9: balance unknown")
    entries = rows[0].get("details")
    if not isinstance(entries, list):
        raise ExecutionBlocked("Target9: missing currency details")
    matches = [x for x in entries if isinstance(x, dict) and x.get("ccy") == "USDT"]
    if len(matches) != 1:
        raise ExecutionBlocked("Target9: ambiguous USDT equity")
    value = _num(matches[0].get("eq"))
    if value < 0:
        raise ExecutionBlocked("Target9: negative USDT equity")
    return value


def _is_usdt_swap(symbol):
    return isinstance(symbol, str) and symbol.endswith("-USDT-SWAP") and len(symbol) > 10


def _listing(client, endpoint, params):
    rows = client.request("GET", endpoint, params=params)
    # At the maximum page size further items may be hidden: fail closed.
    if not isinstance(rows, list) or len(rows) >= 100 or not all(isinstance(x, dict) for x in rows):
        raise ExecutionBlocked("Target9: invalid or truncated listing")
    return rows


def active_swaps(client, mode="net_mode"):
    rows = _listing(client, "/api/v5/account/positions", {"instType": "SWAP"})
    out, seen = [], set()
    sides = ("net",) if mode == "net_mode" else ("long", "short")
    for row in rows:
        if _num(row.get("pos", "0")) == 0:
            continue
        symbol, margin, side = row.get("instId"), row.get("mgnMode"), row.get("posSide")
        if not _is_usdt_swap(symbol) or margin not in ("cross", "isolated") or side not in sides:
            raise ExecutionBlocked("Target9: unsupported exposure; manual closure required")
        key = (symbol, margin, side)
        if key in seen:
            raise ExecutionBlocked("Target9: duplicate active exposure")
        seen.add(key)
        out.append({"instId": symbol, "mgnMode": margin, "posSide": side})
    return out


def pending_orders(client):
    rows = _listing(client, "/api/v5/trade/orders-pending", {"instType": "SWAP"})
    if any(not _is_usdt_swap(row.get("instId")) or not row.get("ordId") for row in rows):
        raise ExecutionBlocked("Target9: unidentified or unsupported pending SWAP order")
    return rows


def pending_algos(client):
    result = {}
    for kind in ALGO_TYPES:
        rows = _listing(client, "/api/v5/trade/orders-algo-pending", {"ordType": kind})
        for row in rows:
            symbol = row.get("instId")
            if not isinstance(symbol, str) or not symbol:
                raise ExecutionBlocked("Target9: unidentifiable algo exposure")
            if not symbol.endswith("-SWAP"):
                continue
            if not _is_usdt_swap(symbol) or not row.get("algoId"):
                raise ExecutionBlocked("Target9: unsupported or unidentified SWAP algo")
            ident = str(row["algoId"])
            result[(symbol, ident)] = {"instId": symbol, "algoId": ident}
    return list(result.values())


def _single_ack(rows, name, expected=None, field=None):
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ExecutionBlocked("Target9: ambiguous " + name + " acknowledgement")
    ack = rows[0]
    if ack.get("sCode", "0") != "0":
        raise ExecutionBlocked("Target9: rejected " + name)
    if expected is not None and str(ack.get(field, "")) != str(expected):
        raise ExecutionBlocked("Target9: mismatched " + name + " acknowledgement")
    return ack


def _verify_empty(get_remaining, pause):
    for attempt in range(5):
        if not get_remaining():
            pause(0.2)
            if not get_remaining():
                return
        if attempt < 4:
            pause(0.5)
    raise ExecutionBlocked("Target9: residual or uncertain exchange exposure; stop")


def check_target(client, *, close_armed=False, pause=time.sleep):
    if usdt_equity(client) < TARGET:
        return "BELOW_TARGET"
    if not close_armed:
        raise ExecutionBlocked("Target9: no explicit close authorization")
    cfg = client.request("GET", "/api/v5/account/config")
    if len(cfg) != 1 or not isinstance(cfg[0], dict):
        raise ExecutionBlocked("Target9: missing position mode")
    mode = cfg[0].get("posMode")
    if mode not in ("net_mode", "long_short_mode"):
        raise ExecutionBlocked("Target9: unsupported position mode")

    positions = active_swaps(client, mode)
    orders = pending_orders(client)
    # Cancel normal pending orders first, so one cannot open exposure during exit.
    for row in orders:
        ident = str(row["ordId"])
        ack = client.request("POST", "/api/v5/trade/cancel-order",
                             body={"instId": row["instId"], "ordId": ident})
        _single_ack(ack, "order cancel", ident, "ordId")
    if orders:
        _verify_empty(lambda: pending_orders(client), pause)

    # Close each supported position. Do not retry an ambiguous POST.
    for p in positions:
        ack = client.request("POST", "/api/v5/trade/close-position",
                             body={**p, "autoCxl": True})
        item = _single_ack(ack, "position close", p["instId"], "instId")
        if item.get("posSide") not in (None, p["posSide"]):
            raise ExecutionBlocked("Target9: close side mismatch")
    _verify_empty(lambda: active_swaps(client, mode), pause)

    # Orphan triggers can remain even if no position is open.
    algos = pending_algos(client)
    for start in range(0, len(algos), 10):
        batch = algos[start:start + 10]
        ack = client.request("POST", "/api/v5/trade/cancel-algos", body=batch)
        if not isinstance(ack, list) or len(ack) != len(batch):
            raise ExecutionBlocked("Target9: ambiguous algo cancellation")
        expected = {x["algoId"] for x in batch}
        received = {str(x.get("algoId")) for x in ack if isinstance(x, dict) and x.get("sCode") == "0"}
        if expected != received or len(received) != len(batch):
            raise ExecutionBlocked("Target9: algo cancellation not confirmed")
    if algos:
        _verify_empty(lambda: pending_algos(client), pause)
    _verify_empty(lambda: active_swaps(client, mode) or pending_orders(client) or pending_algos(client),
                  pause)
    return "TARGET9_FLAT"


def main():
    try:
        env = dict(os.environ)
        if env.get("OKX_EXECUTION_MODE") != "live":
            raise ExecutionBlocked("Target9: no live access outside explicitly selected LIVE")
        check_mode("live", env)
        if env.get("OKX_TARGET9_ENABLED") != "YES":
            raise ExecutionBlocked("Target9: not enabled")
        state = check_target(OKX(env), close_armed=env.get("OKX_TARGET9_CLOSE_ARM") == ARM)
        print("OKX TARGET9 RESULT: " + state, flush=True)
        return 78 if state == "TARGET9_FLAT" else 0
    except ExecutionBlocked as exc:
        print("OKX TARGET9 BLOCKED: " + str(exc), file=sys.stderr, flush=True)
        return 2
    except Exception:
        print("OKX TARGET9 ERROR: uncertain exchange state; manual review",
              file=sys.stderr, flush=True)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

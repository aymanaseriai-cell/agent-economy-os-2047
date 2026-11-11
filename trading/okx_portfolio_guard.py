"""Read-only account-wide position protection and aggregate risk for 20x swaps.

Never places, changes, or closes orders. Requires per-symbol combined TP and
SL; missing metadata or ambiguous protection stops all new entries.
"""
from decimal import Decimal, InvalidOperation

class UnsafePortfolio(RuntimeError):
    pass

MAX_POSITIONS = 2
RISK_CAP = Decimal("0.05")
MARGIN_CAP = Decimal("0.50")
LEVERAGE = Decimal("20")

def num(value, field):
    try:
        v = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise UnsafePortfolio("Missing or invalid "+field) from exc
    if not v.is_finite():
        raise UnsafePortfolio("Non-finite "+field)
    return v

def snapshot(client):
    cfg = client.request("GET","/api/v5/account/config")
    if len(cfg) != 1 or cfg[0].get("posMode") != "net_mode":
        raise UnsafePortfolio("Only OKX net_mode permitted")
    rows = client.request("GET","/api/v5/account/positions",params={"instType":"SWAP"})
    if not isinstance(rows,list):
        raise UnsafePortfolio("Position feed not verifiable")
    active = [p for p in rows if num(p.get("pos","0"),"pos") != 0]
    if len(active)>MAX_POSITIONS:
        raise UnsafePortfolio("Too many existing positions")
    symbols=[p.get("instId","") for p in active]
    if len(set(symbols))!=len(symbols):
        raise UnsafePortfolio("Duplicate symbol exposure")
    if any(not s.endswith("-USDT-SWAP") or p.get("mgnMode")!="isolated"
           for s,p in zip(symbols,active)):
        raise UnsafePortfolio("Non-isolated or non-USDT swap")
    if client.request("GET","/api/v5/trade/orders-pending",params={"instType":"SWAP"}):
        raise UnsafePortfolio("Outstanding orders require inspection")
    algos=[]
    for typ in ("conditional","oco","trigger","move_order_stop"):
        q=client.request("GET","/api/v5/trade/orders-algo-pending",params={"ordType":typ})
        if not isinstance(q,list):
            raise UnsafePortfolio("Unable to verify protection")
        algos.extend(a for a in q if str(a.get("instId","")).endswith("-SWAP"))
    if any(a.get("instId") not in symbols for a in algos):
        raise UnsafePortfolio("Orphan or unrelated protective order")
    used=Decimal("0"); planned=Decimal("0")
    for pos in active:
        sym=pos["instId"]
        paired=[a for a in algos if a.get("instId")==sym and
                a.get("slTriggerPx") and a.get("tpTriggerPx")]
        if len(paired)!=1:
            raise UnsafePortfolio("One confirmed TP/SL pair required per position")
        sl=num(paired[0]["slTriggerPx"],"stop"); mark=num(pos.get("markPx"),"mark")
        value=num(pos.get("notionalUsd"),"notional")
        if sl<=0 or mark<=0 or value<=0:
            raise UnsafePortfolio("Bad positive market value")
        qty=num(pos["pos"],"position")
        fraction=(max(Decimal("0"), mark-sl)/mark if qty>0 else
                  max(Decimal("0"), sl-mark)/mark)
        used+=value
        planned+=value*fraction
    bal=client.request("GET","/api/v5/account/balance",params={"ccy":"USDT"})
    if len(bal)!=1:
        raise UnsafePortfolio("Balance unavailable")
    total=num(bal[0].get("totalEq"),"totalEq")
    usd=next((d for d in bal[0].get("details",[]) if d.get("ccy")=="USDT"),None)
    if usd is None:
        raise UnsafePortfolio("USDT balance missing")
    free=num(usd.get("availEq") or usd.get("availBal"),"free collateral")
    if total<=0 or free<=0:
        raise UnsafePortfolio("No available equity")
    if planned>total*RISK_CAP or used/LEVERAGE>total*MARGIN_CAP:
        raise UnsafePortfolio("Existing aggregate risk above permitted limits")
    return {"symbols":frozenset(symbols),"total":total,"free":min(free,total),
            "planned":planned,"notional":used}

def sizing_equity(snap):
    """Max equity input for the existing 2%-stop, 20%-margin adaptive sizer."""
    from trading.okx_live_executor import ADAPTIVE_EQUITY_RISK_FRACTION, ADAPTIVE_MARGIN_CAP_FRACTION
    risk_left=snap["total"]*RISK_CAP-snap["planned"]
    margin_left=snap["total"]*MARGIN_CAP-snap["notional"]/LEVERAGE
    if risk_left<=0 or margin_left<=0:
        return Decimal("0")
    return min(snap["free"],risk_left/ADAPTIVE_EQUITY_RISK_FRACTION,
               margin_left/ADAPTIVE_MARGIN_CAP_FRACTION)

def check_new(snap, notional, stop_fraction):
    if snap["planned"]+notional*stop_fraction>snap["total"]*RISK_CAP:
        raise UnsafePortfolio("Aggregate stop risk would exceed limit")
    if (snap["notional"]+notional)/LEVERAGE>snap["total"]*MARGIN_CAP:
        raise UnsafePortfolio("Aggregate margin would exceed limit")

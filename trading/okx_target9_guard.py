"""Explicitly armed OKX USDT equity target and isolated net SWAP exit.

At >=9 USDT details[].eq: stop new entries, close all supported isolated
USDT-SWAP net positions via official market close-position, verify flat.
Fail closed on unsupported positions, pending orders or uncertain fills.
No promise of >=9 realized after fees and slippage.
"""
import os
import sys
from decimal import Decimal, InvalidOperation
from trading.okx_live_executor import OKX, ExecutionBlocked, check_mode

TARGET = Decimal("9")
ARM = "I_AUTHORIZE_CLOSE_USDT_SWAPS_AT_9_USDT"

def _num(x):
    try: v=Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ExecutionBlocked("Target9: malformed equity/position") from exc
    if not v.is_finite(): raise ExecutionBlocked("Target9: nonfinite numeric data")
    return v

def usdt_equity(client):
    rows=client.request("GET","/api/v5/account/balance",params={"ccy":"USDT"})
    if len(rows)!=1 or not isinstance(rows[0],dict):
        raise ExecutionBlocked("Target9: balance unavailable")
    entries=[x for x in rows[0].get("details",[])
             if isinstance(x,dict) and x.get("ccy")=="USDT"]
    if len(entries)!=1:
        raise ExecutionBlocked("Target9: unambiguous USDT currency equity missing")
    value=_num(entries[0].get("eq"))
    if value<0: raise ExecutionBlocked("Target9: negative USDT equity")
    return value

def active_swaps(client):
    rows=client.request("GET","/api/v5/account/positions",params={"instType":"SWAP"})
    if not isinstance(rows,list): raise ExecutionBlocked("Target9: missing SWAP positions")
    result=[]
    for x in rows:
        if not isinstance(x,dict): raise ExecutionBlocked("Target9: bad SWAP record")
        if _num(x.get("pos","0"))==0: continue
        if (not str(x.get("instId","")).endswith("-USDT-SWAP")
                or x.get("mgnMode")!="isolated"
                or x.get("posSide","net")!="net"):
            raise ExecutionBlocked("Target9: unsupported open exposure; manual review")
        result.append(x["instId"])
    if len(result)!=len(set(result)):
        raise ExecutionBlocked("Target9: duplicate SWAP exposure")
    return result

def check_target(client, *, close_armed=False):
    if usdt_equity(client)<TARGET: return "BELOW_TARGET"
    if not close_armed:
        raise ExecutionBlocked("Target9: exchange close is not explicitly armed")
    cfg=client.request("GET","/api/v5/account/config")
    if len(cfg)!=1 or cfg[0].get("posMode")!="net_mode":
        raise ExecutionBlocked("Target9: expected net_mode")
    positions=active_swaps(client)
    if client.request("GET","/api/v5/trade/orders-pending",params={"instType":"SWAP"}):
        raise ExecutionBlocked("Target9: pending SWAP orders require manual cancellation")
    for symbol in positions:
        reply=client.request("POST","/api/v5/trade/close-position",
             body={"instId":symbol,"mgnMode":"isolated","posSide":"net","autoCxl":True})
        if len(reply)!=1 or reply[0].get("sCode") not in (None,"0"):
            raise ExecutionBlocked("Target9: unconfirmed close outcome")
    if active_swaps(client):
        raise ExecutionBlocked("Target9: residual open SWAP; no blind retry")
    if client.request("GET","/api/v5/trade/orders-pending",params={"instType":"SWAP"}):
        raise ExecutionBlocked("Target9: residual normal SWAP orders; manual review")
    # An orphan TP/SL could become dangerous after closing the position.
    for typ in ("conditional","oco","trigger","move_order_stop"):
        algos=client.request("GET","/api/v5/trade/orders-algo-pending",
                             params={"ordType":typ})
        if not isinstance(algos,list) or any(
                str(row.get("instId","")).endswith("-SWAP")
                for row in algos if isinstance(row,dict)):
            raise ExecutionBlocked("Target9: pending SWAP algo after close; manual review")
    return "TARGET9_FLAT"

def main():
    try:
        env=dict(os.environ)
        if env.get("OKX_EXECUTION_MODE")!="live":
            raise ExecutionBlocked("Target9: no private actions outside LIVE")
        check_mode("live",env)
        if env.get("OKX_TARGET9_ENABLED")!="YES":
            raise ExecutionBlocked("Target9: feature not enabled")
        state=check_target(OKX(env),close_armed=env.get("OKX_TARGET9_CLOSE_ARM")==ARM)
        print("OKX TARGET9 RESULT: "+state,flush=True)
        return 78 if state=="TARGET9_FLAT" else 0
    except ExecutionBlocked as exc:
        print("OKX TARGET9 BLOCKED: "+str(exc),file=sys.stderr,flush=True)
        return 2
    except Exception:
        print("OKX TARGET9 ERROR: unknown state; manual review",file=sys.stderr,flush=True)
        return 3

if __name__=="__main__":
    raise SystemExit(main())

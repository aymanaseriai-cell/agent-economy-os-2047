#!/usr/bin/env python3
"""TITAN Ω Infinite12: PUBLIC-ONLY, NO-ORDER, development paper replay.

Does NOT access exchange accounts, balances, trading keys, ccxt, or any POST API.
The exposed 2026 calendar is NOT a new sealed independent holdout.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from statistics import pstdev
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from trading.titan_omega_infinite12_models import STRATEGIES, NAMES

START_USDT = 4.15
TARGET_USDT = 8.30
CANDLE_MS = 900_000
WINDOW_BARS = 48
SYMBOLS = ("BTC-USDT-SWAP","ETH-USDT-SWAP","SOL-USDT-SWAP","XRP-USDT-SWAP")
COSTS = {
    "ordinary": {"taker":0.0005,"spread_slip":0.0005,"fund8h_proxy":0.0001},
    "stress": {"taker":0.0015,"spread_slip":0.0020,"fund8h_proxy":0.0005},
}
VERSION = "OMEGA-INFINITE12-V1-20261117"
HOLD_BARS = 4
MARGIN_FRACTION = 0.25
VOLUME_PARTICIPATION = 0.001
MMR_PROXY = 0.005


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",",":"),
            allow_nan=False).encode("utf-8")).hexdigest()


def get_okx(endpoint, params):
    """Read ONLY OKX public market endpoints, never authenticated orders."""
    if endpoint not in ("/api/v5/market/history-candles",
                        "/api/v5/public/instruments",
                        "/api/v5/public/funding-rate-history"):
        raise ValueError("Forbidden endpoint")
    url = "https://www.okx.com"+endpoint+"?"+urlencode(params)
    with urlopen(Request(url, headers={"User-Agent":"TITAN-OMEGA-PAPER-NO-ORDERS"}),timeout=20) as resp:
        payload = json.load(resp)
    if payload.get("code") != "0" or not isinstance(payload.get("data"),list):
        raise RuntimeError("OKX public error: "+str(payload.get("msg")))
    return payload["data"]


def validate_bars(bars):
    if len(bars) < 33+WINDOW_BARS:
        raise ValueError("Too few complete 15m candles")
    for i, b in enumerate(bars):
        v = [float(b[k]) for k in ("open","high","low","close","quote")]
        if not all(math.isfinite(x) for x in v) or not (0<v[2]<=min(v[0],v[3])<=max(v[0],v[3])<=v[1]) or v[4]<0:
            raise ValueError("Invalid completed candle OHLC/volume")
        if i and b["ts"]-bars[i-1]["ts"] != CANDLE_MS:
            raise ValueError("Discontinuous or unordered time series")


def collect_market(symbol, limit_bars=1000):
    if symbol not in SYMBOLS:
        raise ValueError("Unpredeclared instrument")
    rows={}
    cursor=None
    for _ in range(math.ceil(limit_bars/100)+2):
        params={"instId":symbol,"bar":"15m","limit":"100"}
        if cursor is not None:
            params["after"]=str(cursor)
        batch = get_okx("/api/v5/market/history-candles",params)
        if not batch:
            break
        stamps=[int(x[0]) for x in batch]
        if cursor is not None and min(stamps)>=cursor:
            raise ValueError("Pagination stalled")
        cursor=min(stamps)
        for x in batch:
            if len(x)<9 or str(x[8])!="1":
                continue
            vals=[float(x[k]) for k in (1,2,3,4,7)]
            rows[int(x[0])]={"ts":int(x[0]),"open":vals[0],
                       "high":vals[1],"low":vals[2],"close":vals[3],"quote":vals[4]}
        if len(rows)>=limit_bars:
            break
    bars=[rows[t] for t in sorted(rows)][-limit_bars:]
    validate_bars(bars)
    raw_specs=get_okx("/api/v5/public/instruments",{"instType":"SWAP","instId":symbol})
    matched=[s for s in raw_specs if s.get("instId")==symbol and s.get("settleCcy")=="USDT"]
    if len(matched)!=1:
        raise ValueError("USDT linear contract specification missing")
    spec=matched[0]
    record={k:spec.get(k) for k in ("instId","minSz","lotSz","ctVal","ctValCcy","lever","ctType","state")}
    funding_raw=get_okx("/api/v5/public/funding-rate-history",{"instId":symbol,"limit":"100"})
    funding=[]
    for row in funding_raw:
        try:
            ts=int(row["fundingTime"])
            rate=float(row.get("realizedRate") or row["fundingRate"])
            if math.isfinite(rate):
                funding.append({"ts":ts,"rate":rate})
        except (KeyError,ValueError,TypeError):
            pass
    funding=sorted({r["ts"]:r for r in funding}.values(),key=lambda r:r["ts"])
    return {"bars":bars,"spec":record,"funding":funding,
            "bar_sha256":digest(bars),"funding_sha256":digest(funding),
            "spec_sha256":digest(record)}


def capture(limit_bars=1000):
    out={"study":VERSION,"captured_at_ms":int(time.time()*1000),"origin":"OKX public REST only",
         "period_status":"CONSUMED_2026_DEVELOPMENT_NOT_INDEPENDENT",
         "timeframe":"15m","declared_symbols":list(SYMBOLS),"real_orders":0,"markets":{}}
    for sym in SYMBOLS:
        out["markets"][sym]=collect_market(sym,limit_bars)
    out["seal_sha256"]=digest({k:v for k,v in out.items() if k!="seal_sha256"})
    return out


def valid_spec(spec):
    """Strictly fail closed if OKX omits public max leverage or lot metadata."""
    try:
        if spec.get("state")!="live" or spec.get("ctType")!="linear":
            return None
        if spec.get("ctValCcy") in ("USDT","USD"):
            return None # these require a different contract-value dimensional model
        mn,step,val,cap=(float(spec[k]) for k in ("minSz","lotSz","ctVal","lever"))
        if not all(math.isfinite(v) and v>0 for v in (mn,step,val,cap)) or cap<10:
            return None
        return mn,step,val,min(100.0,cap)
    except (ValueError,KeyError,TypeError):
        return None


def contracts(equity, open_price, prev_quote, lev, spec_tuple):
    mn,step,val,_=spec_tuple
    notional_cap=min(equity*MARGIN_FRACTION*lev, max(0.,prev_quote)*VOLUME_PARTICIPATION)
    qty=math.floor((notional_cap/(open_price*val)+1e-10)/step)*step
    qty=round(qty,9)
    return qty if qty+1e-10>=mn else 0.0


def leverage(bars, prev, maximum):
    returns=[math.log(bars[j]["close"]/bars[j-1]["close"]) for j in range(prev-19,prev+1)]
    vol=max(0.0005,pstdev(returns))
    return min(maximum, max(10.0,min(100.0,0.06/vol)))


def simulate(bars, spec, funding, name, start, case):
    """Each 48-bar window starts with fresh 4.15. Only CLOSED PnL compounds."""
    validate_bars(bars)
    if name not in STRATEGIES or case not in COSTS or start<33 or start+WINDOW_BARS>len(bars):
        raise ValueError("Bad fixed experiment parameters")
    stop=start+WINDOW_BARS
    sp=valid_spec(spec)
    ledger=[]
    equity=START_USDT
    blocked=0
    costs=COSTS[case]
    if sp is None:
        return {"model":name,"cost":case,"start_idx":start,"end_idx":stop,
                "start_ts":bars[start]["ts"],"end_ts":bars[stop-1]["ts"]+CANDLE_MS,
                "start_equity":START_USDT,"end_equity":START_USDT,"trades":ledger,
                "blocked":WINDOW_BARS,"liquidations":0,"status":"UNVERIFIED_CONTRACT_SPEC"}
    t=start
    while t<stop and equity>0:
        # No access to the t-th candle in the decision function.
        side=STRATEGIES[name](bars,t-1)
        if side not in (-1,0,1):
            raise ValueError("Invalid strategy output")
        if side==0:
            t+=1
            continue
        lev=leverage(bars,t-1,sp[3])
        px=float(bars[t]["open"])
        qty=contracts(equity,px*(1+costs["spread_slip"]),float(bars[t-1]["quote"]),lev,sp)
        if qty<=0:
            blocked+=1
            t+=1
            continue
        entry_px=px*(1+side*costs["spread_slip"])
        nominal=qty*sp[2]*entry_px
        margin=nominal/lev
        if margin>equity*MARGIN_FRACTION*(1+1e-8):
            raise AssertionError("Margin over cap")
        finish=min(t+HOLD_BARS,stop)
        exit_px=None
        exit_type="time"
        exit_bar=finish-1
        liquidation_at=entry_px*(1-side*(1/lev-MMR_PROXY))
        stop_at=entry_px*(1-side*min(.02,.65/lev))
        for j in range(t,finish):
            bar=bars[j]
            liq=(bar["low"]<=liquidation_at if side==1 else bar["high"]>=liquidation_at)
            stp=(bar["low"]<=stop_at if side==1 else bar["high"]>=stop_at)
            if liq:
                exit_px=(min(bar["open"],liquidation_at) if side==1
                         else max(bar["open"],liquidation_at))
                exit_type="liquidation_proxy"
                exit_bar=j
                break
            if stp:
                exit_px=(min(bar["open"],stop_at) if side==1
                         else max(bar["open"],stop_at))
                exit_type="stop"
                exit_bar=j
                break
        if exit_px is None:
            exit_px=bars[exit_bar]["close"]
        exit_px *= (1-side*costs["spread_slip"])
        gross=side*(exit_px-entry_px)*qty*sp[2]
        fee=costs["taker"]*qty*sp[2]*(entry_px+exit_px)
        event_rates=[x["rate"] for x in funding if bars[t]["ts"]<x["ts"]<=bars[exit_bar]["ts"]+CANDLE_MS]
        if event_rates:
            funding_cost=nominal*side*sum(event_rates)
            funding_basis="original_realized_public_events"
        else:
            funding_cost=nominal*costs["fund8h_proxy"]*((exit_bar-t+1)*CANDLE_MS/28_800_000)
            funding_basis="conservative_assumption_not_observed"
        net=gross-fee-funding_cost
        after=max(0.0,equity+net)
        record={"symbol":spec["instId"],"model":name,"cost":case,"side":side,
                "signal_last_completed_ts":bars[t-1]["ts"],
                "entry_ts":bars[t]["ts"],"exit_ts":bars[exit_bar]["ts"]+CANDLE_MS,
                "entry_idx":t,"exit_idx":exit_bar,"entry_px":entry_px,"exit_px":exit_px,
                "qty_contracts":qty,"ct_val":sp[2],"lot_sz":sp[1],"min_sz":sp[0],
                "leverage":lev,"contract_leverage_cap":sp[3],"margin":margin,
                "previous_quote_volume":bars[t-1]["quote"],"equity_before":equity,
                "gross_usdt":gross,"fees_usdt":fee,"funding_usdt":funding_cost,
                "funding_basis":funding_basis,"net_usdt":net,"equity_after":after,
                "exit_type":exit_type,"liquidation_proxy_not_actual_mark":exit_type=="liquidation_proxy"}
        ledger.append(record)
        equity=after
        t=exit_bar+1
    return {"model":name,"cost":case,"start_idx":start,"end_idx":stop,
            "start_ts":bars[start]["ts"],"end_ts":bars[stop-1]["ts"]+CANDLE_MS,
            "start_equity":START_USDT,"end_equity":equity,"trades":ledger,
            "blocked":blocked,"liquidations":sum(x["exit_type"]=="liquidation_proxy" for x in ledger),
            "status":"DEVELOPMENT_PROXY_NOT_VERIFIED"}


def evaluate(raw):
    payload={k:v for k,v in raw.items() if k!="seal_sha256"}
    if raw["seal_sha256"]!=digest(payload) or raw.get("declared_symbols")!=list(SYMBOLS) or raw.get("real_orders")!=0:
        raise ValueError("Data seal or no-order contract invalid")
    results=[]
    for symbol in SYMBOLS:
        market=raw["markets"][symbol]
        bars=market["bars"]
        validate_bars(bars)
        for field, value in (("bar_sha256",bars),("funding_sha256",market["funding"]),
                             ("spec_sha256",market["spec"])):
            if market[field]!=digest(value):
                raise ValueError("Tampered source "+symbol+" "+field)
        for start in range(33,len(bars)-WINDOW_BARS+1,WINDOW_BARS):
            for model in NAMES:
                for case in COSTS:
                    x=simulate(bars,market["spec"],market["funding"],model,start,case)
                    x["symbol"]=symbol
                    results.append(x)
    summary={}
    for name in NAMES:
        for case in COSTS:
            subset=[x for x in results if x["model"]==name and x["cost"]==case]
            equities=[x["end_equity"] for x in subset]
            fills=sum(len(x["trades"]) for x in subset)
            summary[name+"/"+case]={
                "windows":len(subset),"filled_trades":fills,
                "target_hit_windows":sum(e>=TARGET_USDT for e in equities),
                "descriptive_hit_rate":sum(e>=TARGET_USDT for e in equities)/len(equities) if equities else None,
                "median_net_pct":sorted([(e/START_USDT-1)*100 for e in equities])[len(equities)//2] if equities else None,
                "best_dev_net_pct":max([(e/START_USDT-1)*100 for e in equities],default=None),
                "liquidation_proxy_events":sum(x["liquidations"] for x in subset),
                "unverified_spec_windows":sum(x["status"]=="UNVERIFIED_CONTRACT_SPEC" for x in subset)
            }
    return {"study":VERSION,"source_seal_sha256":raw["seal_sha256"],
            "scope":"ALL_FIXED_NONOVERLAPPING_CONSUMED_2026_DEVELOPMENT_WINDOWS",
            "start_usdt":START_USDT,"target_usdt":TARGET_USDT,
            "window_bar_count":WINDOW_BARS,"bar_minutes":15,
            "models":list(NAMES),"summary":summary,"windows":results,
            "real_orders":0,"quantum_hardware_used":False,
            "best_independent_net_pct":None,"independent_hit_rate":None,
            "scientific_verdict":"NO_NEW_INDEPENDENT_OUT_OF_SAMPLE_PROOF",
            "constraints":["Historical spreads/L2/mark-price liquidation tiers unavailable",
                           "Public leverage caps may be absent; such contracts are blocked",
                           "Financing not aligned to settlement events uses labelled proxy",
                           "All sampled dates are already consumed by V1-V5 or prior TITAN research"]}


def main():
    p=argparse.ArgumentParser()
    mode=p.add_subparsers(dest="mode",required=True)
    a=mode.add_parser("collect");a.add_argument("--out",required=True);a.add_argument("--limit-bars",type=int,default=1000)
    b=mode.add_parser("replay");b.add_argument("--input",required=True);b.add_argument("--out",required=True)
    o=p.parse_args()
    result=capture(o.limit_bars) if o.mode=="collect" else evaluate(json.loads(Path(o.input).read_text()))
    dest=Path(o.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"mode":o.mode,"study":VERSION,"hash":digest(result),"real_orders":0,
           "summary":result.get("summary"),"scientific_verdict":result.get("scientific_verdict")},
            sort_keys=True))


if __name__=="__main__":
    main()

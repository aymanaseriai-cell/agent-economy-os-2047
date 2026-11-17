#!/usr/bin/env python3
"""Future-only quantum-vs-classical OKX PAPER evidence. NO ORDERS."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from trading import titan_quantum_gate as q

STUDY = "TITAN-QF128-PRECOMMIT-20261117-V1"
SYMBOLS = ("ADA-USDT-SWAP","AVAX-USDT-SWAP","LINK-USDT-SWAP",
           "ARB-USDT-SWAP","INJ-USDT-SWAP","AAVE-USDT-SWAP")
BAR_MS = 900000
HORIZONS = (4,16)
MODELS = ("quantum","quantum_zero_phase","classical")
COSTS = {"ordinary":(.0005,.0003),"stress":(.0008,.001)}
MARGIN = .10
LEVERAGE = 3.
START = 4.15
TARGET = 9.462

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,
        separators=(",",":"),allow_nan=False).encode()).hexdigest()

def public_history(symbol, earliest=None):
    """Historical read-only completed 15m bars, with deterministic pagination."""
    if symbol not in SYMBOLS: raise ValueError("Unknown fixed market")
    all_rows={}; cursor=None
    for _ in range(40):
        params={"instId":symbol,"bar":"15m","limit":"100"}
        if cursor is not None: params["after"]=str(cursor)
        url="https://www.okx.com/api/v5/market/history-candles?"+urlencode(params)
        with urlopen(Request(url,headers={"User-Agent":"TITAN-QF128-NO-ORDERS"}),
                     timeout=25) as response:
            blob=json.load(response)
        if blob.get("code")!="0": raise ValueError("OKX public history failure")
        raw=blob.get("data",[])
        if not raw: break
        timestamps=[]
        for item in raw:
            if len(item)<9: raise ValueError("Missing confirmed candle state")
            ts=int(item[0]); timestamps.append(ts)
            if str(item[8])!="1": continue
            op,hi,lo,cl=map(float,item[1:5])
            if not all(math.isfinite(x) for x in (op,hi,lo,cl)):
                raise ValueError("Invalid market float")
            if not 0<lo<=op<=hi or not lo<=cl<=hi:
                raise ValueError("Malformed public OHLC")
            all_rows[ts]={"ts":ts,"open":op,"high":hi,"low":lo,"close":cl}
        oldest=min(timestamps)
        if cursor is not None and oldest>=cursor:
            raise ValueError("Pagination cursor stalled")
        cursor=oldest
        if earliest is None and len(all_rows)>=97: break
        if earliest is not None and all_rows and min(all_rows)<=earliest: break
    return [all_rows[k] for k in sorted(all_rows)]

def complete_window(rows, now_ms):
    candles=[dict(r) for r in rows if r["ts"]+BAR_MS<=now_ms]
    if len(candles)<97: raise ValueError("Need 97 completed candles")
    candles=candles[-97:]
    if any(b["ts"]-a["ts"]!=BAR_MS for a,b in zip(candles,candles[1:])):
        raise ValueError("Discontinuous public candles")
    if now_ms-(candles[-1]["ts"]+BAR_MS)>2*BAR_MS:
        raise ValueError("Stale market data")
    return candles

def predict(window):
    """All three models consume exactly the same 97 completed candles."""
    features=q.completed_causal_features(window,96)
    p=q.quantum_and_control(features)
    zero=p["quantum_zero_phase"]
    return {
        "signals":{"quantum":p["quantum_signal"],
                   "classical":p["classical_signal"],
                   "quantum_zero_phase":1 if zero>=q.CUTOFF else (
                       -1 if zero<=1-q.CUTOFF else 0)},
        "probabilities":{k:round(p[k],12) for k in MODELS},
        "quantum_hardware_used":False
    }

def capture(*,get=public_history,now_ms=None,run_id="unknown",sha="unknown"):
    now=int(time.time()*1000) if now_ms is None else int(now_ms)
    if now<=0: raise ValueError("Clock error")
    records=[]
    for symbol in SYMBOLS:
        window=complete_window(get(symbol),now)
        records.append({"symbol":symbol,
                        "last_completed_candle":window[-1]["ts"],
                        "observed_sha256":digest(window),**predict(window)})
    sealed=int(time.time()*1000) if now_ms is None else now
    if sealed<now: raise ValueError("Clock shifted backward")
    future=(sealed//BAR_MS+2)*BAR_MS
    body={"study":STUDY,"sealed_ms":sealed,"source_run":str(run_id),
          "source_sha":str(sha),"entry_ms":future,
          "mature_ms":future+max(HORIZONS)*BAR_MS,
          "horizons":list(HORIZONS),"symbols":list(SYMBOLS),
          "models":list(MODELS),
          "costs":{k:list(v) for k,v in COSTS.items()},
          "margin_each":MARGIN,"leverage":LEVERAGE,
          "start_usdt":START,"target_usdt":TARGET,
          "real_orders":0,"quantum_hardware_used":False,
          "records":records}
    body["seal_sha256"]=digest(body)
    return body

def verify(seal):
    if not isinstance(seal,dict): raise ValueError("No source seal")
    payload={k:v for k,v in seal.items() if k!="seal_sha256"}
    if digest(payload)!=seal.get("seal_sha256"):
        raise ValueError("Seal hash mismatch")
    if (seal.get("study")!=STUDY
        or seal.get("symbols")!=list(SYMBOLS)
        or seal.get("models")!=list(MODELS)
        or seal.get("horizons")!=list(HORIZONS)
        or seal.get("costs")!={k:list(v) for k,v in COSTS.items()}
        or seal.get("margin_each")!=MARGIN
        or seal.get("leverage")!=LEVERAGE
        or seal.get("start_usdt")!=START
        or seal.get("target_usdt")!=TARGET
        or seal.get("real_orders")!=0
        or seal.get("quantum_hardware_used") is not False):
        raise ValueError("Immutable study contract changed")
    created,entry,maturity=seal["sealed_ms"],seal["entry_ms"],seal["mature_ms"]
    if (any(type(x)!=int or x<=0 for x in (created,entry,maturity))
        or entry-created < BAR_MS or entry%BAR_MS
        or maturity!=entry+16*BAR_MS):
        raise ValueError("Not strictly prospective")
    rows=seal.get("records")
    if not isinstance(rows,list) or [r.get("symbol") for r in rows]!=list(SYMBOLS):
        raise ValueError("Incomplete six-symbol fixed universe")
    for r in rows:
        if (r.get("last_completed_candle",10**20)+BAR_MS>created
            or not isinstance(r.get("observed_sha256"),str)
            or len(r["observed_sha256"])!=64
            or r.get("quantum_hardware_used") is not False
            or set(r.get("signals",{}))!=set(MODELS)
            or any(type(v)!=int or v not in (-1,0,1)
                   for v in r["signals"].values())):
            raise ValueError("Invalid observed or predicted record")
    return True

def trade_return(side,entry,exit,fee,slip):
    if side==0: return 0.
    if side not in (-1,1) or min(entry,exit)<=0:
        raise ValueError("Invalid paper trade")
    p_entry=entry*(1+side*slip)
    p_exit=exit*(1-side*slip)
    return side*(p_exit/p_entry-1)-fee*(1+p_exit/p_entry)

def score(seal,*,get=public_history,now_ms=None):
    """Use only the immutable prior signals and future completed OHLC."""
    verify(seal)
    now=int(time.time()*1000) if now_ms is None else int(now_ms)
    if now<seal["mature_ms"]:
        raise ValueError("Future candles not matured")
    start=seal["entry_ms"]; data={}
    for sym in SYMBOLS:
        rows=get(sym,earliest=start)
        by_time={r["ts"]:r for r in rows if r["ts"]+BAR_MS<=now}
        if any(t not in by_time for t in range(start,start+16*BAR_MS,BAR_MS)):
            raise ValueError("Required future bars incomplete for "+sym)
        data[sym]=by_time
    results={}
    for horizon in HORIZONS:
        model_scores={}
        for model in MODELS:
            cost_scores={}
            for label,(fee,slip) in COSTS.items():
                net=0.; count=0
                for frozen in seal["records"]:
                    sym=frozen["symbol"];side=frozen["signals"][model]
                    entry=data[sym][start]["open"]
                    close=data[sym][start+(horizon-1)*BAR_MS]["close"]
                    net+=MARGIN*LEVERAGE*trade_return(side,entry,close,fee,slip)
                    if side: count+=1
                end=max(0.,START*(1+net))
                cost_scores[label]={"net_return_pct":round(100*net,6),
                                    "paper_equity_usdt":round(end,8),
                                    "paper_trades":count,
                                    "paper_target_hit":end>=TARGET}
            model_scores[model]=cost_scores
        results[str(horizon)+"_bars"]=model_scores
    return {"study":STUDY,"original_seal_sha256":seal["seal_sha256"],
            "original_run_id":seal["source_run"],
            "original_commit":seal["source_sha"],
            "scored_at_ms":now,"results":results,
            "real_orders":0,"verified_real_128":False,
            "conclusion":"SINGLE_PROSPECTIVE_SHADOW_SAMPLE_NOT_PROOF_OF_REPEATABLE_RETURN",
            "limitations":["No real fills or user account balances",
                           "No orderbook depth, mark-price liquidation, funding or stop fills",
                           "Quantum circuit simulated on a classical CPU"]}

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="phase",required=True)
    a=sub.add_parser("capture");a.add_argument("--out",required=True)
    b=sub.add_parser("score");b.add_argument("--sealed",required=True);b.add_argument("--out",required=True)
    opts=p.parse_args()
    if opts.phase=="capture":
        result=capture(run_id=os.environ.get("GITHUB_RUN_ID","unknown"),
                       sha=os.environ.get("GITHUB_SHA","unknown"))
        verify(result)
        if int(time.time()*1000)>=result["entry_ms"]:
            raise ValueError("Future entry already started before artifact write")
        print("QF128 SEALED",result["seal_sha256"],"RUN",result["source_run"],
              "ENTRY_MS",result["entry_ms"],"MATURE_MS",result["mature_ms"],"NO ORDERS")
    else:
        result=score(json.loads(Path(opts.sealed).read_text()))
        print("QF128 SCORED",result["original_seal_sha256"],
              result["conclusion"],"NO ORDERS")
    path=Path(opts.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")

if __name__=="__main__": main()

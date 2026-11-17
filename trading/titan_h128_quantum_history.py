#!/usr/bin/env python3
"""TITAN H128: actual OKX historical 15m quantum/classical PAPER challenge.
Frozen six-market hash selection, 50/25/25 chronological split, stress costs.
No orders, API secrets, physical quantum processor or guaranteed returns.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from trading import titan_quantum_survival_interferometer as qsi
from trading import titan_quantum_gate as qg
from trading import titan128_breakout_blind as prior
from trading.edge_lab import fetch_history,ema_series,TAKER_FEE,BASE_SLIPPAGE,STRESS_FEE,STRESS_SLIPPAGE
from trading.titan_regime_research import validate_frozen

STUDY="TITAN-H128-FROZEN-20261117-REAL-HISTORY-V1"
START=4.15
GOAL=9.462
RUIN=.83
DAYS=60
MIN_BARS=5600
N=6
LEVERAGES=(3.,10.)
UNIVERSE=set(("SUI APT ATOM DOT LTC HBAR OP ONDO XLM TIA SEI WLD ENS LDO ADA AVAX "
              "LINK INJ UNI PEPE SHIB TON TRX AAVE BCH NEAR ZRX JUP ARB FIL ALGO "
              "ETC GMT IMX NEO DASH CELO PYTH").split())
PRIOR_MARKETS=set(("IMX NEO DASH GMT CELO PYTH AAVE ALGO ARB TRX FIL ETC BCH JUP ZRX NEAR").split())
POLICIES=("quantum_phase_robust","quantum_interference","quantum_zero_phase",
          "classical_same_features","classical_breakout","quantum_trend",
          "quantum_reversion","quantum_low_vol","quantum_high_vol",
          "quantum_breakout_confirmed")
QUANTUM_POLICIES=tuple(p for p in POLICIES if p.startswith("quantum_"))

def catalogue():
    url="https://www.okx.com/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-H128-READONLY"}),timeout=35) as h:
        data=json.load(h)
    if data.get("code")!="0":raise ValueError("Public OKX instruments unavailable")
    cutoff=int(time.time()*1000)-90*86400000
    eligible=[]
    for x in data.get("data",[]):
        sym=x.get("instId","")
        if not sym.endswith("-USDT-SWAP"):continue
        coin=sym[:-10]
        if (coin not in UNIVERSE or coin in PRIOR_MARKETS or x.get("state")!="live"
            or x.get("ctType")!="linear" or x.get("ctValCcy")!=coin):continue
        try:
            if int(x["listTime"])>cutoff:continue
            values=[float(x[k]) for k in ("ctVal","lotSz","minSz")]
            if not all(math.isfinite(v) and v>0 for v in values):continue
        except (KeyError,TypeError,ValueError):continue
        eligible.append(x)
    eligible.sort(key=lambda x:hashlib.sha256((STUDY+"|"+x["instId"]).encode()).hexdigest())
    if len(eligible)<N:raise ValueError("Fewer than six valid frozen markets")
    return eligible[:N],len(eligible)

def signals(bars):
    validate_frozen(bars)
    quantum=qsi.candidate_stream(bars)
    breakout=prior.breakout_signals(bars)
    close=[x["close"] for x in bars]
    fast,slow=ema_series(close,24),ema_series(close,96)
    out={k:list(quantum[k]) if k in quantum else [] for k in POLICIES}
    out["classical_breakout"]=list(breakout)
    for i,side,atr,conf in quantum["quantum_phase_robust"]:
        if side*(fast[i]-slow[i])>.2*atr and side*(close[i]-close[i-16])>0:
            out["quantum_trend"].append((i,side,atr,conf))
        if side*(fast[i]-slow[i])<-.25*atr and side*(close[i]-slow[i])<-.5*atr:
            out["quantum_reversion"].append((i,side,atr,conf))
        bucket="quantum_low_vol" if atr/close[i]<.009 else "quantum_high_vol"
        out[bucket].append((i,side,atr,conf))
    for i,side,atr,conf in breakout:
        features=qg.completed_causal_features(bars,i)
        if qg.quantum_and_control(features)["quantum_signal"]==side:
            out["quantum_breakout_confirmed"].append((i,side,atr,conf))
    return out

def evaluate(markets,specs,hashes):
    if len(markets)!=N or set(markets)!=set(specs) or set(markets)!=set(hashes):
        raise ValueError("Frozen six-market public panel mandatory")
    if any(s[:-10] not in UNIVERSE or s[:-10] in PRIOR_MARKETS for s in markets):
        raise ValueError("Old-cohort contamination")
    n=min(len(v) for v in markets.values())
    if n<MIN_BARS:raise ValueError("Incomplete 60d history")
    times=[x["ts"] for x in next(iter(markets.values()))[:n]]
    for rows in markets.values():
        validate_frozen(rows)
        if [x["ts"] for x in rows[:n]]!=times:
            raise ValueError("Unaligned public OHLC timestamps")
    vote={s:signals(rows[:n]) for s,rows in markets.items()}
    t=n//2;m=t+(n-t)//2
    phases={"train":(qsi.WARMUP,t),"holdout_1":(t,m),"holdout_2":(m,n)}
    all_results={}
    for name in POLICIES:
        # An immutable signal stream is injected into a proven public-lot paper
        # replay slot; no policy chooses based on future realised returns.
        votes={s:{"quantum_phase_robust":vote[s][name]} for s in markets}
        for lev in LEVERAGES:
            key=name+"_"+str(int(lev))+"x"
            all_results[key]={}
            for phase,(start,end) in phases.items():
                all_results[key][phase]={}
                for label,fee,slip in (("ordinary",TAKER_FEE,BASE_SLIPPAGE),
                                       ("stress",STRESS_FEE,STRESS_SLIPPAGE)):
                    all_results[key][phase][label]=prior.paper(
                        markets,specs,votes,policy="quantum_phase_robust",
                        leverage=lev,start=start,end=end,fee=fee,slip=slip)
    def train_pass(k):
        a=all_results[k]["train"]["ordinary"]
        z=all_results[k]["train"]["stress"]
        return (z["trades"]>=16 and a["return_pct"]>0 and z["return_pct"]>0
                and z["max_drawdown_pct"]<=35
                and not z["ruin_at_closed_equity"])
    chosen_candidates=[k for k in all_results if
                       k.rsplit("_",1)[0] in QUANTUM_POLICIES and train_pass(k)]
    chosen=max(chosen_candidates,key=lambda k:
               all_results[k]["train"]["stress"]["return_pct"]) if chosen_candidates else None
    pass_2=bool(chosen) and all(
        all_results[chosen][phase][c]["return_pct"]>0 and
        not all_results[chosen][phase][c]["ruin_at_closed_equity"]
        for phase in ("holdout_1","holdout_2") for c in ("ordinary","stress"))
    hit128=pass_2 and all(
        all_results[chosen][phase][c]["reached128_on_closed_paper_trade"]
        for phase in ("holdout_1","holdout_2") for c in ("ordinary","stress"))
    candidates=[(k,p,c,all_results[k][p][c]["return_pct"])
                for k in all_results for p in ("holdout_1","holdout_2")
                for c in ("ordinary","stress")]
    peak=max(candidates,key=lambda x:x[3])
    hits=sum(all_results[k][p][c]["reached128_on_closed_paper_trade"]
             for k in all_results for p in ("holdout_1","holdout_2")
             for c in ("ordinary","stress"))
    return {"study":STUDY,"data":"real public completed OKX USDT SWAP 15m",
        "start_usdt":START,"goal_usdt":GOAL,"ruin_usdt":RUIN,
        "markets":sorted(markets),"sha256":hashes,"bars_per_market":n,
        "total_completed_market_bars":n*N,
        "model_count":len(all_results),"train_only_candidates":chosen_candidates,
        "selected_on_training_only":chosen,"holdout_both_costs_positive":bool(pass_2),
        "selected_replicated_128_in_both_holdouts_and_costs":bool(hit128),
        "posthoc_128_hits_not_validated":hits,
        "posthoc_highest_window_not_recommendation":{
            "model":peak[0],"period":peak[1],"cost":peak[2],"return_pct":peak[3]},
        "verdict":("HISTORICAL_ONLY_FURTHER_PROSPECTIVE_PROOF_REQUIRED" if hit128
                   else "NO_VALIDATED_REPEATED_128_HISTORICAL_EDGE"),
        "results":all_results,"real_orders":0,"quantum_hardware_used":False,
        "limitations":["Retrospective backtest, not actual account performance",
                       "True historical OHLC but hypothetical market fills and fee/slippage",
                       "No true order-book, mark-price liquidation or historical funding",
                       "Multiple old studies increase false-discovery risk",
                       "No result is a guarantee of future profits"]}

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="reports/titan_h128_quantum_history.json")
    ap.add_argument("--raw-dir",default="reports/titan_h128_quantum_history_raw")
    args=ap.parse_args(argv)
    basket,count=catalogue()
    print("H128 HISTORICAL PRECOMMITTED MARKET PANEL",count,[x["instId"] for x in basket],flush=True)
    now=int(time.time()*1000)
    markets={};specs={};hashes={};raw=Path(args.raw_dir)
    raw.mkdir(parents=True,exist_ok=True)
    for spec in basket:
        sym=spec["instId"]
        bars=fetch_history(sym,DAYS,now_ms=now)
        if len(bars)<MIN_BARS:raise ValueError("Missing completed true price history: "+sym)
        payload=json.dumps(bars,separators=(",",":")).encode()
        hashes[sym]=hashlib.sha256(payload).hexdigest()
        with gzip.open(raw/(sym+".json.gz"),"wb") as handle:handle.write(payload)
        markets[sym]=bars;specs[sym]=spec
        print("H128 HISTORICAL SHA",sym,len(bars),hashes[sym],flush=True)
    report=evaluate(markets,specs,hashes)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    for name,periods in report["results"].items():
        print("H128 BACKTEST",name,
              "TRAIN",periods["train"]["ordinary"]["return_pct"],
              "TRAIN_STRESS",periods["train"]["stress"]["return_pct"],
              "H1",periods["holdout_1"]["ordinary"]["return_pct"],
              "H1_STRESS",periods["holdout_1"]["stress"]["return_pct"],
              "H2",periods["holdout_2"]["ordinary"]["return_pct"],
              "H2_STRESS",periods["holdout_2"]["stress"]["return_pct"],flush=True)
    print("H128 FINAL",report["verdict"],"TRAIN_SELECTED",
          report["selected_on_training_only"],"POSTHOC_HITS",
          report["posthoc_128_hits_not_validated"],"NO ORDERS",flush=True)

if __name__=="__main__":main()

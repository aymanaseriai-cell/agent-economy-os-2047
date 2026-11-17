#!/usr/bin/env python3
"""TITAN Ω Q5: novel 5-qubit interference + coherence abstention research.

100% historical public completed OKX 15m OHLC. The quantum-like amplitudes are
simulated with CPU complex arithmetic, NOT quantum hardware. Goal: +128% net
closed-paper equity from 4.15 to 9.462 USDT. No orders or private APIs.

A genuinely NEW cohort and 5-qubit circuit, fixed prior to downloading prices.
Evaluate candidate on train only, then THREE untouched 20% chronological
holdouts and a combined 60% out-of-sample contiguous investment.
"""
from __future__ import annotations
import argparse, cmath, gzip, hashlib, json, math, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from trading import titan_quantum_survival_interferometer as qsi
from trading import titan128_breakout_blind as prior
from trading.edge_lab import (
    BAR_MS, atr_simple, ema_series, fetch_history,
    TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE, STRESS_SLIPPAGE,
)
from trading.titan_regime_research import validate_frozen

STUDY = "TITAN-Q5-LOSS-AVERSION-COHERENCE-128-20261117-V1-UNSEEN-MARKETS"
UNIVERSE = set(("AR AXS BLUR BONK CFX DYDX ETHFI FET FLOW JTO KAS LPT "
                "MINA PENGU RUNE STX XTZ YGG ZIL 1INCH TWT").split())
EXCLUDED = set(("BTC ETH SOL XRP DOGE HYPE ZEC BNB GRT RENDER CHZ WIF ZK "
                "MASK ATOM ONDO WLD LTC AVAX OP").split())
N_MARKETS = 6
DAYS = 90
MIN_BARS = 8450
START = 4.15
TARGET = 9.462
RUIN = .83
PHASES = (.6, 1.0, 1.4)
LEVERAGES = (3.,10.)
POLICIES = (
    "q5_coherent_breakout", "q5_regime_momentum", "q5_phase_unanimous",
    "q5_volatility_survival", "q5_countertrend", "q5_zero_phase",
    "classical_same_features", "classical_breakout",
)
QUANTUM = tuple(x for x in POLICIES if x.startswith("q5_"))
STRESS_CASES = {
    "ordinary": (TAKER_FEE, BASE_SLIPPAGE),
    "stress": (STRESS_FEE, STRESS_SLIPPAGE),
}
CUTOFF=.59

def catalogue():
    """Pre-commit index selection by hash of market name, never its returns."""
    u="https://www.okx.com/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(u,headers={"User-Agent":"TITAN-Q5-READONLY-RESEARCH"}),
                 timeout=35) as h: obj=json.load(h)
    if obj.get("code")!="0": raise ValueError("Exchange public instruments unavailable")
    cutoff=int(time.time()*1000)-120*86400000
    found=[]
    for x in obj.get("data",[]):
        s=x.get("instId","")
        if not s.endswith("-USDT-SWAP"): continue
        coin=s[:-10]
        if (coin not in UNIVERSE or coin in EXCLUDED or x.get("state")!="live"
            or x.get("ctType")!="linear" or x.get("ctValCcy")!=coin): continue
        try:
            if int(x["listTime"])>cutoff:continue
            info=[float(x[k]) for k in ("ctVal","lotSz","minSz")]
            if not all(math.isfinite(v) and v>0 for v in info):continue
        except (ValueError,TypeError,KeyError):continue
        found.append(x)
    found.sort(key=lambda x:hashlib.sha256(
        (STUDY+":"+x["instId"]).encode()).hexdigest())
    if len(found)<N_MARKETS: raise ValueError("Too few real crypto markets eligible")
    return found[:N_MARKETS],len(found)

def _ry(v,b,theta):
    out=list(v);mask=1<<b
    c=math.cos(theta/2);s=math.sin(theta/2)
    for i in range(32):
        if i&mask:continue
        a,beta=v[i],v[i|mask]
        out[i]=c*a-s*beta;out[i|mask]=s*a+c*beta
    return out

def _h(v,b):
    out=list(v);mask=1<<b;t=math.sqrt(.5)
    for i in range(32):
        if i&mask:continue
        a,beta=v[i],v[i|mask]
        out[i]=(a+beta)*t;out[i|mask]=(a-beta)*t
    return out

def q5_probability(features,phase=1.):
    """Unitary 32-complex-amplitude gate with all five data input features."""
    if (len(features)!=5 or not all(math.isfinite(float(x)) for x in features)
        or not math.isfinite(phase) or not 0<=phase<=2):
        raise ValueError("Five finite causal features and bounded phase required")
    f=tuple(math.tanh(float(v)) for v in features)
    state=[0j]*32;state[0]=1.+0j
    for bit,x in enumerate(f):state=_ry(state,bit,1.4*x)
    for i in range(32):
        z=[1 if i&(1<<k) else -1 for k in range(5)]
        coupling=(.43*z[0]*z[1]+.27*z[1]*z[2]-.36*z[2]*z[3]+
                  .31*z[3]*z[4]-.22*z[4]*z[0])
        field=.13*sum(z[k]*f[k] for k in range(5))
        state[i]*=cmath.exp(1j*phase*(coupling+field))
    for bit in range(5):state=_h(state,bit)
    for bit,x in enumerate(f):state=_ry(state,bit,.67*x)
    state=_h(state,1);state=_h(state,3)
    norm=sum(abs(a)**2 for a in state)
    if abs(norm-1)>1e-9:raise ArithmeticError("Nonunitary five-qubit model")
    # Project majority-1 states rather than maximize a single arbitrary bit.
    born=sum(abs(a)**2 for i,a in enumerate(state) if i.bit_count()>=3)
    if not -.000000001<=born<=1.000000001:raise ArithmeticError("Invalid quantum distribution")
    return max(0.,min(1.,born))

def classic_probability(features):
    if len(features)!=5 or not all(math.isfinite(float(x)) for x in features):
        raise ValueError("Bad same-input classical vector")
    p=sum(w*math.tanh(v) for w,v in zip(
        (.55,.45,.35,-.20,.20),features))
    return 1/(1+math.exp(-p))

def side(p):
    return 1 if p>=CUTOFF else -1 if p<=1-CUTOFF else 0

def past_features(bars,i,closes,ema_fast,ema_slow):
    if i<224 or i>=len(bars):raise ValueError("Too little causal price history")
    atr14=atr_simple(bars,i,14)
    atr56=atr_simple(bars,i,56)
    p=closes[i]
    if min(p,atr14,atr56)<=0:raise ValueError("Invalid causal volatility")
    norm=max(atr14/p,1e-8)
    mom8=math.log(p/closes[i-8])/(norm*math.sqrt(8))
    mom48=math.log(p/closes[i-48])/(norm*math.sqrt(48))
    trend=(ema_fast[i]-ema_slow[i])/max(atr14,1e-8)
    compression=math.log(atr14/atr56)*2
    pressure=sum((bars[k]["close"]-bars[k]["open"])/max(
        bars[k]["high"]-bars[k]["low"],1e-9) for k in range(i-11,i+1))/12*3
    return (tuple(max(-3.,min(3.,v))
                   for v in (mom8,mom48,trend,compression,pressure)),atr14)

def frozen_stream(bars):
    """All decisions use current COMPLETED candle; fills at next bar open."""
    validate_frozen(bars)
    closes=[x["close"] for x in bars]
    e24,e96=ema_series(closes,24),ema_series(closes,96)
    outputs={name:[] for name in POLICIES}
    for i in range(224,len(bars)-1,4):
        f,atr=past_features(bars,i,closes,e24,e96)
        if not .0012<=atr/closes[i]<=.05:continue
        ps=tuple(q5_probability(f,phase) for phase in PHASES)
        nominal=ps[1]
        zero=q5_probability(f,0)
        classic=classic_probability(f)
        direction=side(nominal)
        trend=1 if e24[i]>e96[i] else -1
        if min(ps)>=CUTOFF:robust=1;conf=min(ps)-.5
        elif max(ps)<=1-CUTOFF:robust=-1;conf=.5-max(ps)
        else:robust=0;conf=0
        recent_hi=max(b["high"] for b in bars[i-48:i])
        recent_lo=min(b["low"] for b in bars[i-48:i])
        breakout = (1 if closes[i]>recent_hi else
                    -1 if closes[i]<recent_lo else 0)
        vola=atr_simple(bars,i,14)/atr_simple(bars,i,56)
        def push(label,d,strength):
            if d:
                outputs[label].append((i,d,atr,round(
                    max(0.,min(.5,strength)),8)))
        push("q5_phase_unanimous",robust,conf)
        push("q5_zero_phase",side(zero),abs(zero-.5))
        push("classical_same_features",side(classic),abs(classic-.5))
        if robust and breakout==robust and trend==robust and vola<=1.2:
            push("q5_coherent_breakout",robust,conf)
        if direction and direction==trend and (
            (direction>0 and f[1]>.6) or (direction<0 and f[1]<-.6)
        ) and vola<=1.5:
            push("q5_regime_momentum",direction,abs(nominal-.5))
        if robust and robust==trend and vola<=.85:
            push("q5_volatility_survival",robust,conf)
        if direction and trend==-direction and abs(f[2])>1.2 and vola<1.3:
            push("q5_countertrend",direction,abs(nominal-.5))
    outputs["classical_breakout"]=prior.breakout_signals(bars)
    return outputs

def evaluate(markets,specs,hashes):
    if len(markets)!=N_MARKETS or set(markets)!=set(specs) or set(markets)!=set(hashes):
        raise ValueError("Missing frozen real markets/specs/hash")
    if any(s[:-10] not in UNIVERSE or s[:-10] in EXCLUDED for s in markets):
        raise ValueError("Unregistered crypto-market selected")
    n=min(len(rows) for rows in markets.values())
    if n<MIN_BARS:raise ValueError("Incomplete 90-day history")
    times=[x["ts"] for x in next(iter(markets.values()))[:n]]
    for rows in markets.values():
        validate_frozen(rows)
        if [x["ts"] for x in rows[:n]]!=times:
            raise ValueError("Misaligned chronological candles")
    policies={s:frozen_stream(rows[:n]) for s,rows in markets.items()}
    t1=int(n*.4);t2=int(n*.6);t3=int(n*.8)
    slices={
        "train":(qsi.WARMUP,t1),"holdout_1":(t1,t2),
        "holdout_2":(t2,t3),"holdout_3":(t3,n),
        "all_holdouts":(t1,n),
    }
    scores={}
    for label in POLICIES:
        signs={symbol:rows[label] for symbol,rows in policies.items()}
        for lever in LEVERAGES:
            key=label+"_"+str(int(lever))+"x"
            scores[key]={}
            for segment,(a,b) in slices.items():
                scores[key][segment]={
                    name:prior.paper(markets,specs,signs,leverage=lever,
                                     start=a,end=b,fee=costs[0],slip=costs[1])
                    for name,costs in STRESS_CASES.items()
                }
    # Commit train-only model selection; no observing the 3 untouched holdouts.
    eligible=[]
    for k,periods in scores.items():
        if k.rsplit("_",1)[0] not in QUANTUM:continue
        ordinary=periods["train"]["ordinary"]
        stress=periods["train"]["stress"]
        if (stress["trades"]>=12 and stress["return_pct"]>0
            and ordinary["return_pct"]>0 and stress["max_drawdown_pct"]<=30
            and not stress["ruin_at_closed_equity"]):
            eligible.append(k)
    selected=max(eligible,key=lambda k:scores[k]["train"]["stress"]["return_pct"]) if eligible else None
    parts=("holdout_1","holdout_2","holdout_3")
    repeated=selected is not None and all(
        scores[selected][part][fee]["reached128_on_closed_paper_trade"]
        and not scores[selected][part][fee]["ruin_at_closed_equity"]
        for part in parts for fee in STRESS_CASES)
    combined=selected is not None and all(
        scores[selected]["all_holdouts"][fee]["reached128_on_closed_paper_trade"]
        and not scores[selected]["all_holdouts"][fee]["ruin_at_closed_equity"]
        for fee in STRESS_CASES)
    posthoc=sum(scores[k][p][fee]["reached128_on_closed_paper_trade"]
                for k in scores for p in parts for fee in STRESS_CASES)
    all_rets=[(k,p,fee,scores[k][p][fee]["return_pct"]) for k in scores
              for p in parts for fee in STRESS_CASES]
    top=max(all_rets,key=lambda z:z[3])
    return {
        "study":STUDY,"start_usdt":START,"target_usdt":TARGET,
        "actual_data":"Verified public OKX completed 15m history",
        "markets":sorted(markets),"sha256":hashes,
        "market_bars_per_symbol":n,"total_market_candles":n*N_MARKETS,
        "periods":slices,"hypothesis_count":len(scores),
        "training_qualified":eligible,
        "selected_using_training_alone":selected,
        "three_independent_holdouts_hit_128_both_costs":bool(repeated),
        "combined_untouched_60pct_hit_128_both_costs":bool(combined),
        "posthoc_128_hits_NOT_reliable":posthoc,
        "retrospective_maximum_not_selection":{
            "model":top[0],"period":top[1],
            "cost":top[2],"return_pct":top[3]},
        "results":scores,
        "verdict":("HISTORICAL_PAPER_CANDIDATE_NOT_LIVE_VALIDATION"
                    if repeated and combined else "NO_VALIDATED_REPEATED_128_EDGE"),
        "real_orders":0,"actual_quantum_processor":False,
        "limitations":[
            "Historical-market OHLC are real; fills and execution are simulated",
            "Contract specifications are current, not point-in-time historical",
            "Fees, funding, slippage and liquidation are conservative proxies",
            "Multiple iterative historical studies raise selection-bias risk",
            "An observed return cannot guarantee repeated or live profitability",
        ],
    }

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out",required=True)
    ap.add_argument("--raw-dir",required=True)
    opts=ap.parse_args(argv)
    basket,total=catalogue()
    print("Q5 HASH-SELECTED BEFORE MARKET RETURNS",total,
          [x["instId"] for x in basket],flush=True)
    now=int(time.time()*1000)
    specs={};markets={};hashes={}
    output=Path(opts.raw_dir);output.mkdir(parents=True,exist_ok=True)
    for spec in basket:
        symbol=spec["instId"]
        bars=fetch_history(symbol,DAYS,now_ms=now)
        if len(bars)<MIN_BARS:raise ValueError("Too few frozen historical prices "+symbol)
        content=json.dumps(bars,separators=(",",":")).encode()
        sha=hashlib.sha256(content).hexdigest()
        with gzip.open(output/(symbol+".json.gz"),"wb") as handle:
            handle.write(content)
        specs[symbol]=spec;markets[symbol]=bars;hashes[symbol]=sha
        print("Q5 REAL OHLC SHA",symbol,len(bars),sha,flush=True)
    report=evaluate(markets,specs,hashes)
    path=Path(opts.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    for k,p in report["results"].items():
        print("Q5 RETURN",k,
              "TRAIN",p["train"]["stress"]["return_pct"],
              "H1",p["holdout_1"]["stress"]["return_pct"],
              "H2",p["holdout_2"]["stress"]["return_pct"],
              "H3",p["holdout_3"]["stress"]["return_pct"],
              "ALL",p["all_holdouts"]["stress"]["return_pct"],flush=True)
    print("Q5 FINAL",report["verdict"],
          "SELECTED",report["selected_using_training_alone"],
          "HIT128",report["three_independent_holdouts_hit_128_both_costs"],
          "POSTHOC_HITS",report["posthoc_128_hits_NOT_reliable"],
          "NO ORDERS",flush=True)

if __name__=="__main__":
    main()

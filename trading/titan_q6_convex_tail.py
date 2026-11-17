#!/usr/bin/env python3
"""TITAN Q6 Convex Tail: six-qubit phase coherence / breakout research.

Public real completed OKX 15-minute candles; no secrets, no live orders.
CPU simulator of six mathematical qubits, NOT physical quantum hardware.
Trades are PAPER: next-bar entry, public-lot sizing, costs, conservative
intrabar order, approximate liquidation, trailing exits to capture rare tails.
Goal remains +128% CLOSED paper equity (4.15 => 9.462 USDT), not guaranteed.
"""
from __future__ import annotations
import argparse, cmath, gzip, hashlib, json, math, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from trading import titan_quantum_survival_interferometer as qsi
from trading.edge_lab import (BAR_MS, atr_simple, ema_series, fetch_history,
    TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE, STRESS_SLIPPAGE,
    FUNDING_PER_8H)
from trading.titan_regime_research import validate_frozen

STUDY = "TITAN-Q6-CONVEX-TAIL-128-LOCKED-20261117-V2"
UNIVERSE = set(("AXS BONK CFX DYDX FET FLOW JTO KAS RUNE STX XTZ ZIL 1INCH "
                "TWT CRV IMX NEO CELO GALA SAND ARKM LDO PENDLE TIA").split())
EXCLUDE = set(("BTC ETH SOL XRP DOGE HYPE ZEC BNB BLUR MINA ETHFI AR YGG LPT "
               "GRT RENDER CHZ WIF ZK MASK ATOM ONDO WLD LTC AVAX OP").split())
MARKETS=6
DAYS=90
MIN_BARS=8450
START=4.15
TARGET=9.462
RUIN=.83
LEVERAGES=(3.,10.)
PHASES=(.6,1.,1.4)
CUTOFF=.60
STRIDE=4
MAX_HOLD_BARS=96
INITIAL_ATR_STOP=2.
TRAIL_ATR_STOP=2.8
POLICIES=("q6_tail_breakout","q6_phase_consensus","q6_trend_coherent",
          "q6_volatility_expansion","q6_squeeze_release","q6_zero_phase",
          "classical_same_six_features","classical_donchian_breakout")
QUANTUM=tuple(k for k in POLICIES if k.startswith("q6_"))
COSTS={"ordinary":(TAKER_FEE,BASE_SLIPPAGE),
       "stress":(STRESS_FEE,STRESS_SLIPPAGE)}

def public_catalogue():
    url="https://www.okx.com/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-Q6-READONLY"}),
                 timeout=35) as h: raw=json.load(h)
    if raw.get("code")!="0": raise ValueError("Unverified public OKX swap catalogue")
    cutoff=int(time.time()*1000)-120*86400000
    eligible=[]
    for row in raw.get("data",[]):
        symbol=row.get("instId","")
        if not symbol.endswith("-USDT-SWAP"):continue
        base=symbol[:-10]
        if (base not in UNIVERSE or base in EXCLUDE or row.get("state")!="live"
            or row.get("ctType")!="linear" or row.get("ctValCcy")!=base):continue
        try:
            if int(row["listTime"])>cutoff:continue
            contract=[float(row[k]) for k in ("ctVal","lotSz","minSz")]
            if not all(math.isfinite(x) and x>0 for x in contract):continue
        except (ValueError,TypeError,KeyError):continue
        eligible.append(row)
    eligible.sort(key=lambda x:hashlib.sha256((STUDY+"|"+x["instId"]).encode()).hexdigest())
    if len(eligible)<MARKETS:raise ValueError("Not enough predetermined eligible public swaps")
    return eligible[:MARKETS],len(eligible)

def _ry(v,bit,angle):
    out=list(v);mask=1<<bit
    c=math.cos(angle/2);s=math.sin(angle/2)
    for i in range(64):
        if i&mask:continue
        a,b=v[i],v[i|mask]
        out[i]=c*a-s*b;out[i|mask]=s*a+c*b
    return out

def _h(v,bit):
    out=list(v);mask=1<<bit;inv=math.sqrt(.5)
    for i in range(64):
        if i&mask:continue
        a,b=v[i],v[i|mask]
        out[i]=(a+b)*inv;out[i|mask]=(a-b)*inv
    return out

def q6_probability(features,phase=1.):
    """64-complex-amplitude unitary Born probability, computed on classical CPU."""
    if (len(features)!=6 or any(not math.isfinite(float(v)) for v in features)
        or not math.isfinite(phase) or not 0<=phase<=2):
        raise ValueError("Six finite already-observed features required")
    f=tuple(math.tanh(float(x)) for x in features)
    state=[0j]*64;state[0]=1+0j
    for bit,x in enumerate(f):state=_ry(state,bit,1.3*x)
    for i in range(64):
        z=tuple(1 if i&(1<<k) else -1 for k in range(6))
        coupling=(.39*z[0]*z[1]+.21*z[1]*z[2]-.28*z[2]*z[3]+
                  .24*z[3]*z[4]-.30*z[4]*z[5]+.22*z[5]*z[0])
        local=.12*sum(f[k]*z[k] for k in range(6))
        state[i]*=cmath.exp(1j*phase*(coupling+local))
    for bit in range(6):state=_h(state,bit)
    for bit,x in enumerate(f):state=_ry(state,bit,.57*x)
    for bit in (1,3,5):state=_h(state,bit)
    norm=sum(abs(x)**2 for x in state)
    if abs(norm-1)>1e-9:raise ArithmeticError("Six-qubit simulator unitarity violation")
    # Balanced six-qubit readout: states with three 1s vote half-long.
    # Avoid a structural always-short bias from the >=4 majority rule.
    value=sum(abs(x)**2*(1 if i.bit_count()>3 else
                           .5 if i.bit_count()==3 else 0)
              for i,x in enumerate(state))
    if not -1e-9<=value<=1+1e-9:raise ArithmeticError("Born probability invalid")
    return min(1.,max(0.,value))

def classical_same_features(f):
    if len(f)!=6 or any(not math.isfinite(float(x)) for x in f):
        raise ValueError("Identical six causal inputs required")
    score=sum(w*math.tanh(x) for w,x in zip(
        (.55,.4,.3,.24,-.27,.21),f))
    return 1/(1+math.exp(-score))

def side(p):
    return 1 if p>=CUTOFF else -1 if p<=1-CUTOFF else 0

def completed_features(bars,i,cl,fast,slow):
    if i<224 or i>=len(bars):raise ValueError("Missing causal 224-bar warmup")
    atr14=atr_simple(bars,i,14);atr56=atr_simple(bars,i,56)
    if min(cl[i],atr14,atr56)<=0:raise ValueError("Invalid observed ATR")
    scale=max(atr14/cl[i],1e-8)
    momentum=lambda lag: math.log(cl[i]/cl[i-lag])/(scale*math.sqrt(lag))
    trend=(fast[i]-slow[i])/atr14
    compress=math.log(atr14/atr56)*2
    pressure=sum((bars[k]["close"]-bars[k]["open"])/max(
        bars[k]["high"]-bars[k]["low"],1e-10) for k in range(i-11,i+1))/12*3
    f=tuple(max(-3.,min(3.,v)) for v in
            (momentum(8),momentum(32),momentum(96),trend,compress,pressure))
    return f,atr14,atr14/atr56

def signals(bars):
    """Every signal produced on a completed candle, entry no earlier than i+1."""
    validate_frozen(bars)
    cl=[float(row["close"]) for row in bars]
    fast,slow=ema_series(cl,24),ema_series(cl,96)
    out={k:[] for k in POLICIES}
    for i in range(224,len(bars)-1,STRIDE):
        f,atr,ratio=completed_features(bars,i,cl,fast,slow)
        if not .0012<=atr/cl[i]<=.05:continue
        probs=tuple(q6_probability(f,phase) for phase in PHASES)
        p=probs[1];quant=side(p)
        z=q6_probability(f,0)
        base=classical_same_features(f)
        if min(probs)>=CUTOFF:robust=1;conf=min(probs)-.5
        elif max(probs)<=1-CUTOFF:robust=-1;conf=.5-max(probs)
        else:robust=0;conf=0
        trend=1 if fast[i]>slow[i] and cl[i]>cl[i-32] else (
              -1 if fast[i]<slow[i] and cl[i]<cl[i-32] else 0)
        hi48=max(x["high"] for x in bars[i-48:i])
        lo48=min(x["low"] for x in bars[i-48:i])
        hi96=max(x["high"] for x in bars[i-96:i])
        lo96=min(x["low"] for x in bars[i-96:i])
        br48=1 if cl[i]>hi48 else -1 if cl[i]<lo48 else 0
        br96=1 if cl[i]>hi96 else -1 if cl[i]<lo96 else 0
        def put(name,d,confidence):
            if d:out[name].append((i,d,atr,round(max(0.,min(.5,confidence)),8)))
        put("q6_phase_consensus",robust,conf)
        put("q6_zero_phase",side(z),abs(z-.5))
        put("classical_same_six_features",side(base),abs(base-.5))
        put("classical_donchian_breakout",br96 if br96==trend else 0,
            min(.5,abs(cl[i]-(hi96 if br96>0 else lo96))/atr) if br96 else 0)
        if robust==br96==trend and robust and .60<=ratio<=1.4:
            put("q6_tail_breakout",robust,conf)
        if robust==trend and robust and f[1]*robust>=.4 and .70<=ratio<=1.4:
            put("q6_trend_coherent",robust,conf)
        if quant==br48==trend and quant and 1.1<=ratio<=1.8:
            put("q6_volatility_expansion",quant,abs(p-.5))
        if robust==br48==trend and robust and .65<=ratio<.95:
            put("q6_squeeze_release",robust,conf)
    return out

def paper_one(bars,signal,spec,*,equity,leverage,fee,slip,end):
    """NEXT-OPEN lot-quantized stop-first trailing exit, no peek ahead."""
    i,d,atr,confidence=signal
    j=i+1
    if j>=end:return None
    entry=bars[j]["open"]*(1+d*slip)
    qty,notional=qsi.affordable_contracts(spec,entry,atr,equity,leverage)
    if qty<=0:return None
    ctval=float(spec["ctVal"])
    step=float(spec["lotSz"])
    min_qty=math.ceil(float(spec["minSz"])/step-1e-10)*step
    # The borrowed lot allocator assumes a 1.5 ATR planned stop.
    # Re-quantize for our own wider 2 ATR stop: max 10% planned equity loss.
    qty=min(qty,math.floor((equity*.10/
                 (INITIAL_ATR_STOP*atr*ctval))/step+1e-10)*step)
    if qty+1e-10<min_qty:return None
    notional=qty*ctval*entry
    margin=notional/leverage
    enter_fee=notional*fee
    if margin+enter_fee>=equity:return None
    stop=entry-d*INITIAL_ATR_STOP*atr
    if stop<=0:return None
    barrier=max(.001,1/leverage-qsi.MAINTENANCE_PROXY)
    liq=entry*(1-d*barrier)
    if liq<=0:return None
    last=min(end-1,j+MAX_HOLD_BARS-1)
    close=bars[last]["close"];status="time_exit";exit_i=last
    for k in range(j,last+1):
        b=bars[k]
        adverse=b["low"] if d==1 else b["high"]
        gap_liq=(b["open"]<=liq if d==1 else b["open"]>=liq)
        touch_liq=(adverse<=liq if d==1 else adverse>=liq)
        if gap_liq or touch_liq:
            close=b["open"] if gap_liq else liq
            status="liquidation_proxy";exit_i=k;break
        gap_stop=(b["open"]<=stop if d==1 else b["open"]>=stop)
        hit_stop=(adverse<=stop if d==1 else adverse>=stop)
        if gap_stop or hit_stop:
            close=b["open"] if gap_stop else stop
            status="stop_gap" if gap_stop else "stop";exit_i=k;break
        # CRITICAL: the updated trail becomes active ONLY NEXT candle.
        if k<last:
            if d==1:stop=max(stop,b["close"]-TRAIL_ATR_STOP*atr)
            else:stop=min(stop,b["close"]+TRAIL_ATR_STOP*atr)
    exit_fill=close*(1-d*slip)
    gross=d*(exit_fill-entry)*qty*ctval
    exit_fee=abs(qty*ctval*exit_fill)*fee
    funding=notional*FUNDING_PER_8H*(exit_i-j+1)/32
    pnl=gross-enter_fee-exit_fee-funding
    if status=="liquidation_proxy":
        pnl=min(pnl,-margin-enter_fee-exit_fee)
    pnl=max(-equity,pnl)
    return {"exit_i":exit_i,"equity_after":round(max(0,equity+pnl),9),
        "net_usdt":round(pnl,9),"status":status,
        "entry_fee_usdt":round(enter_fee,9),
        "exit_fee_usdt":round(exit_fee,9),
        "confidence":confidence,"day":bars[exit_i]["ts"]//86400000}

def paper(markets,specs,predictions,*,start,end,leverage,fee,slip):
    if (leverage not in LEVERAGES or set(markets)!=set(specs) or
        set(markets)!=set(predictions)):
        raise ValueError("Unregistered replay inputs")
    events={}
    for sym,rows in predictions.items():
        for signal in rows:
            i=signal[0]
            if start<=i and i+1<end:
                events.setdefault(i,[]).append((signal[3],sym,signal))
    equity=START;peak=START;dd=0;available=start
    count=0;liquidated=0;goal=False
    for i in sorted(events):
        if i<available or equity<=RUIN or equity>=TARGET:continue
        for _,sym,signal in sorted(events[i],key=lambda z:(-z[0],z[1])):
            t=paper_one(markets[sym],signal,specs[sym],equity=equity,
                        leverage=leverage,fee=fee,slip=slip,end=end)
            if t is None:continue
            equity=t["equity_after"];available=t["exit_i"]+1
            peak=max(peak,equity)
            dd=max(dd,(peak-equity)/peak*100)
            count+=1;liquidated+=t["status"]=="liquidation_proxy"
            goal=goal or equity>=TARGET
            break
        if goal:break
    return {"return_pct":round((equity/START-1)*100,5),
            "closed_equity_usdt":round(equity,8),
            "closed_trades":count,"max_drawdown_pct":round(dd,5),
            "liquidation_proxy_events":liquidated,
            "hit_128_closed":bool(goal),
            "ruin":equity<=RUIN}

def evaluate(markets,specs,sha):
    if len(markets)!=MARKETS or set(markets)!=set(specs) or set(markets)!=set(sha):
        raise ValueError("Six fixed verified markets required")
    if any(s[:-10] not in UNIVERSE or s[:-10] in EXCLUDE for s in markets):
        raise ValueError("Non-predeclared market")
    n=min(len(x) for x in markets.values())
    if n<MIN_BARS:raise ValueError("Too few historical bars")
    grid=[x["ts"] for x in next(iter(markets.values()))[:n]]
    for data in markets.values():
        validate_frozen(data)
        if [x["ts"] for x in data[:n]]!=grid:
            raise ValueError("Misaligned candles")
    streams={sym:signals(data[:n]) for sym,data in markets.items()}
    a,b,c=int(n*.4),int(n*.6),int(n*.8)
    periods={"train":(224,a),"holdout_1":(a,b),"holdout_2":(b,c),
             "holdout_3":(c,n),"combined_untouched":(a,n)}
    results={}
    for policy in POLICIES:
        votes={sym:s[policy] for sym,s in streams.items()}
        for lev in LEVERAGES:
            name=policy+"_"+str(int(lev))+"x"
            results[name]={}
            for period,(start,end) in periods.items():
                results[name][period]={}
                for cost,(fee,slip) in COSTS.items():
                    results[name][period][cost]=paper(markets,specs,votes,
                        start=start,end=end,leverage=lev,fee=fee,slip=slip)
    eligible=[]
    for name,rows in results.items():
        if name.rsplit("_",1)[0] not in QUANTUM:continue
        normal=rows["train"]["ordinary"]
        stress=rows["train"]["stress"]
        if (stress["closed_trades"]>=12 and stress["return_pct"]>0
            and normal["return_pct"]>0
            and stress["max_drawdown_pct"]<=30 and not stress["ruin"]):
            eligible.append(name)
    chosen=max(eligible,key=lambda s:results[s]["train"]["stress"]["return_pct"]
               ) if eligible else None
    periods_hold=("holdout_1","holdout_2","holdout_3")
    repeated=bool(chosen) and all(
        results[chosen][t][cost]["hit_128_closed"] and
        not results[chosen][t][cost]["ruin"]
        for t in periods_hold for cost in COSTS)
    combined=bool(chosen) and all(
        results[chosen]["combined_untouched"][cost]["hit_128_closed"] and
        not results[chosen]["combined_untouched"][cost]["ruin"]
        for cost in COSTS)
    best=max([(name,p,c,x["return_pct"]) for name,parts in results.items()
              for p in periods_hold for c,x in parts[p].items()],
             key=lambda row:row[-1])
    return {"study":STUDY,"actual_data":"true public completed OKX 15m OHLC",
            "start":START,"target":TARGET,"bars_each":n,
            "total_completed_bars":n*MARKETS,"markets":sorted(markets),
            "sha256":sha,"candidate_models":len(results),
            "train_qualified":eligible,"selected_train_only":chosen,
            "success_both_costs_three_holdouts":bool(repeated),
            "success_both_costs_combined_holdout":bool(combined),
            "best_retrospective_holdout_NOT_VALIDATED":{
                "model":best[0],"period":best[1],
                "cost":best[2],"return_pct":best[3]},
            "results":results,
            "verdict":("PAPER_ONLY_NEEDS_NEW_UNTOUCHED_EVIDENCE"
                if repeated and combined else "NO_REPLICATED_PLUS_128_EDGE"),
            "orders":0,"quantum_hardware_used":False,
            "caveats":["Real OHLC but no live trading fills",
                "Current exchange contract metadata not historical snapshots",
                "Approximate mark-price liquidation, assumed funding, no order book",
                "Multiple previous studies mean exploratory model search bias"]}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    p.add_argument("--raw-dir",required=True)
    args=p.parse_args(argv)
    specs_list,total=public_catalogue()
    print("Q6 FROZEN MARKETS",total,[x["instId"] for x in specs_list],flush=True)
    now=int(time.time()*1000)
    markets={};specs={};shas={}
    folder=Path(args.raw_dir);folder.mkdir(parents=True,exist_ok=True)
    for spec in specs_list:
        sym=spec["instId"]
        bars=fetch_history(sym,DAYS,now_ms=now)
        if len(bars)<MIN_BARS:raise ValueError("History too short "+sym)
        raw=json.dumps(bars,separators=(",",":")).encode()
        sha=hashlib.sha256(raw).hexdigest()
        with gzip.open(folder/(sym+".json.gz"),"wb") as out:out.write(raw)
        specs[sym]=spec;markets[sym]=bars;shas[sym]=sha
        print("Q6 MARKET SHA",sym,len(bars),sha,flush=True)
    report=evaluate(markets,specs,shas)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    for model,r in report["results"].items():
        print("Q6 BACKTEST",model,
          "TRAIN",r["train"]["stress"]["return_pct"],
          "H1",r["holdout_1"]["stress"]["return_pct"],
          "H2",r["holdout_2"]["stress"]["return_pct"],
          "H3",r["holdout_3"]["stress"]["return_pct"],
          "COMBINED",r["combined_untouched"]["stress"]["return_pct"],flush=True)
    print("Q6 FINAL",report["verdict"],"TRAIN_SELECTED",
          report["selected_train_only"],"BEST_EXPLORATORY",
          report["best_retrospective_holdout_NOT_VALIDATED"],"NO ORDERS",flush=True)

if __name__=="__main__":
    main()

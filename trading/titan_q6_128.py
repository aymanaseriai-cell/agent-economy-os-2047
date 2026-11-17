#!/usr/bin/env python3
"""TITAN Ω Q6 — six-qubit anti-churn +128% research on real OKX history.

A brand-new 64-state classical CPU quantum-circuit simulation (NO QPU).
Longer-horizon trend/volatility coherence and selective trading. Historical
crypto OHLC is REAL; trades, fills, and liquidation are PAPER approximations.
No API keys, no order endpoints, no real financial transactions.
"""
from __future__ import annotations
import argparse,cmath,gzip,hashlib,json,math,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from trading.edge_lab import (
    BAR_MS,atr_simple,ema_series,fetch_history,
    TAKER_FEE,BASE_SLIPPAGE,STRESS_FEE,STRESS_SLIPPAGE,
    FUNDING_PER_8H,
)
from trading.titan_regime_research import validate_frozen

STUDY="TITAN-Q6-LONG-HORIZON-CONTROL-128-20261117-PREDECLARED-V1"
UNIVERSE=set(("BONK CFX DYDX FET FLOW JTO KAS PENGU RUNE STX TWT XTZ "
              "ZIL 1INCH AXS JASMY LDO ENS GALA SAND").split())
EXCLUDED=set(("BTC ETH SOL XRP DOGE HYPE ZEC BNB GRT RENDER CHZ WIF ZK "
              "MASK ATOM ONDO WLD LTC AVAX OP BLUR MINA ETHFI AR YGG LPT").split())
MARKETS=6
DAYS=90
MIN_BARS=8450
START=4.15
TARGET=9.462
RUIN=.83
LEVERAGES=(3.,10.)
COSTS={"ordinary":(TAKER_FEE,BASE_SLIPPAGE),
       "stress":(STRESS_FEE,STRESS_SLIPPAGE)}
PHASES=(.55,1.,1.45)
CUTOFF=.59
SCAN_EVERY=8
POLICIES=(
    "q6_phase_robust","q6_trend_coherence","q6_breakout_coherence",
    "q6_anti_churn","q6_countertrend","q6_zero_phase",
    "classical_same_features","classical_breakout"
)
QUANTUM=tuple(x for x in POLICIES if x.startswith("q6_"))
STOP_ATR=2.1
TARGET_ATR=6.0
MAX_HOLD=96
COOLDOWN=16
MAINTENANCE=.015
MAX_MARGIN=.40
MAX_RISK_AT_STOP=.08


def catalogue():
    """Frozen SHA-256 ranking uses names only, independent of historical PnL."""
    url="https://www.okx.com/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-Q6-PUBLIC-RESEARCH"}),
                 timeout=35) as handle:obj=json.load(handle)
    if obj.get("code")!="0":raise ValueError("Cannot verify public instrument catalogue")
    cutoff=int(time.time()*1000)-120*86400000
    choices=[]
    for spec in obj.get("data",[]):
        sym=spec.get("instId","")
        if not sym.endswith("-USDT-SWAP"):continue
        coin=sym[:-10]
        if (coin not in UNIVERSE or coin in EXCLUDED
            or spec.get("state")!="live" or spec.get("ctType")!="linear"
            or spec.get("ctValCcy")!=coin):
            continue
        try:
            if int(spec["listTime"])>cutoff:continue
            fields=[float(spec[k]) for k in ("ctVal","lotSz","minSz")]
            if not all(math.isfinite(v) and v>0 for v in fields):continue
        except (KeyError,ValueError,TypeError):continue
        choices.append(spec)
    choices.sort(key=lambda z:hashlib.sha256(
        (STUDY+"|"+z["instId"]).encode()).hexdigest())
    if len(choices)<MARKETS:raise ValueError("Insufficient frozen eligible instruments")
    return choices[:MARKETS],len(choices)


def ry(psi,bit,theta):
    out=list(psi)
    k=1<<bit;c=math.cos(theta/2);s=math.sin(theta/2)
    for i in range(64):
        if i&k:continue
        a,b=psi[i],psi[i|k]
        out[i]=c*a-s*b
        out[i|k]=s*a+c*b
    return out


def hadamard(psi,bit):
    out=list(psi);k=1<<bit;c=math.sqrt(.5)
    for i in range(64):
        if i&k:continue
        a,b=psi[i],psi[i|k]
        out[i]=(a+b)*c;out[i|k]=(a-b)*c
    return out


def q6_probability(features,phase=1.):
    """Unitary six-qubit statevector and 32-state Born readout (classical CPU)."""
    if (len(features)!=6 or any(not math.isfinite(float(x)) for x in features)
        or not math.isfinite(phase) or not 0<=phase<=2):
        raise ValueError("Need 6 finite features and bounded phase")
    f=[math.tanh(float(x)) for x in features]
    psi=[0j]*64;psi[0]=1+0j
    for bit in range(6):psi=ry(psi,bit,1.3*f[bit])
    for i in range(64):
        z=[1 if i&(1<<k) else -1 for k in range(6)]
        ring=sum((.28 if k%2 else -.34)*z[k]*z[(k+1)%6]
                 for k in range(6))
        cross=.23*z[0]*z[3]-.17*z[1]*z[4]+.19*z[2]*z[5]
        field=.12*sum(z[j]*f[j] for j in range(6))
        psi[i]*=cmath.exp(1j*phase*(ring+cross+field))
    for bit in range(6):psi=hadamard(psi,bit)
    for bit in range(6):psi=ry(psi,bit,.65*f[bit])
    for bit in (1,3,4):psi=hadamard(psi,bit)
    norm=sum(abs(a)**2 for a in psi)
    if abs(norm-1)>1e-9:raise ArithmeticError("Invalid nonunitary Q6 circuit")
    return max(0.,min(1.,sum(abs(a)**2 for i,a in enumerate(psi)
                            if i&(1<<5))))


def classic_probability(f):
    if len(f)!=6 or any(not math.isfinite(float(x)) for x in f):
        raise ValueError("Same-input classical control needs six causal features")
    total=sum(w*math.tanh(v) for w,v in zip(
        (.42,.43,.31,.26,-.24,.17),f))
    return 1/(1+math.exp(-total))


def direction(p):
    return 1 if p>=CUTOFF else -1 if p<=1-CUTOFF else 0


def features(bars,i,closes,e20,e96):
    if i<224 or i>=len(bars):raise ValueError("Missing observed lookback")
    atr14=atr_simple(bars,i,14)
    atr56=atr_simple(bars,i,56)
    price=closes[i]
    if min(price,atr14,atr56)<=0:raise ValueError("Bad ATR")
    norm=max(atr14/price,1e-8)
    lag8=math.log(price/closes[i-8])/(norm*math.sqrt(8))
    lag96=math.log(price/closes[i-96])/(norm*math.sqrt(96))
    ema_position=(e20[i]-e96[i])/atr14
    body=sum((bars[k]["close"]-bars[k]["open"])/max(
        bars[k]["high"]-bars[k]["low"],1e-8) for k in range(i-15,i+1))/16*3
    compression=math.log(atr14/atr56)*2
    prev_hi=max(z["high"] for z in bars[i-48:i])
    prev_lo=min(z["low"] for z in bars[i-48:i])
    breakout_strength=((price-prev_hi)/atr14 if price>prev_hi else
                       (price-prev_lo)/atr14 if price<prev_lo else 0.)
    values=(lag8,lag96,ema_position,body,compression,breakout_strength)
    return tuple(max(-3.,min(3.,x)) for x in values),atr14,atr14/atr56


def signal_stream(bars):
    validate_frozen(bars)
    close=[v["close"] for v in bars]
    ema20,ema96=ema_series(close,20),ema_series(close,96)
    out={label:[] for label in POLICIES}
    for i in range(224,len(bars)-1,SCAN_EVERY):
        f,atr,vol=features(bars,i,close,ema20,ema96)
        if not .0012<=atr/close[i]<=.050:continue
        p=[q6_probability(f,phase) for phase in PHASES]
        no_phase=q6_probability(f,0)
        classic=classic_probability(f)
        d=direction(p[1])
        if min(p)>=CUTOFF:robust=1;strength=min(p)-.5
        elif max(p)<=1-CUTOFF:robust=-1;strength=.5-max(p)
        else:robust=0;strength=0
        trend=(1 if ema20[i]>ema96[i] and close[i]>close[i-32] else
               -1 if ema20[i]<ema96[i] and close[i]<close[i-32] else 0)
        previous_hi=max(z["high"] for z in bars[i-48:i])
        previous_lo=min(z["low"] for z in bars[i-48:i])
        breakout=1 if close[i]>previous_hi else (
            -1 if close[i]<previous_lo else 0)
        def add(name,side,confidence):
            if side:out[name].append((i,side,atr,round(min(.5,max(0.,confidence)),8)))
        add("q6_phase_robust",robust,strength)
        add("q6_zero_phase",direction(no_phase),abs(no_phase-.5))
        add("classical_same_features",direction(classic),abs(classic-.5))
        if robust==trend and robust:
            add("q6_trend_coherence",robust,strength)
        if robust and breakout==robust and robust==trend:
            add("q6_breakout_coherence",robust,strength)
        if robust and breakout==robust and trend==robust and vol<=.90:
            add("q6_anti_churn",robust,strength)
        if d and trend==-d and abs(f[2])>=1.5 and vol<=1.2:
            add("q6_countertrend",d,abs(p[1]-.5))
    # Independent classical control uses the same completed OHLC only.
    out["classical_breakout"]=[]
    for i in range(224,len(bars)-1,SCAN_EVERY):
        previous_hi=max(z["high"] for z in bars[i-64:i])
        previous_lo=min(z["low"] for z in bars[i-64:i])
        atr=atr_simple(bars,i,14)
        side=(1 if close[i]>previous_hi and ema20[i]>ema96[i] else
              -1 if close[i]<previous_lo and ema20[i]<ema96[i] else 0)
        if side:
            out["classical_breakout"].append((i,side,atr,round(
                min(.5,abs(close[i]-(previous_hi if side==1 else previous_lo))
                    /max(atr,1e-8)*.1),8)))
    return out


def contract_quantity(spec,entry,atr,equity,leverage):
    """Round *down* to OKX contract lot, honoring minSz and collateral."""
    if min(entry,atr,equity)<=0 or equity<=RUIN:
        return 0.,0.
    if leverage not in LEVERAGES:raise ValueError("Unsupported research leverage")
    if (spec.get("ctType")!="linear" or spec.get("state")!="live"
        or spec.get("ctValCcy")!=spec["instId"].split("-")[0]):
        return 0.,0.
    ctval=float(spec["ctVal"]);step=float(spec["lotSz"]);minimum=float(spec["minSz"])
    if min(ctval,step,minimum)<=0:return 0.,0.
    max_notional=min(MAX_MARGIN*equity*leverage,
                     MAX_RISK_AT_STOP*equity/(STOP_ATR*atr/entry))
    qty=math.floor((max_notional/(ctval*entry))/step+1e-9)*step
    smallest=math.ceil(minimum/step-1e-9)*step
    if qty+1e-9<smallest:return 0.,0.
    return round(qty,10),qty*ctval*entry


def simulate_one(bars,spec,signal,equity,leverage,fee,slip,period_end):
    """Order-free stop-FIRST OHLC simulation of a multiday trend candidate."""
    i,side,atr,_=signal
    j=i+1
    if j>=period_end:return None
    entry=bars[j]["open"]*(1+side*slip)
    qty,notional=contract_quantity(spec,entry,atr,equity,leverage)
    if qty<=0:return None
    margin=notional/leverage
    entry_fee=notional*fee
    if entry_fee>=equity-margin:return None
    stop=entry-side*STOP_ATR*atr
    target=entry+side*TARGET_ATR*atr
    liqdist=max(.001,1/leverage-MAINTENANCE)
    liq=entry*(1-side*liqdist)
    if min(stop,target,liq)<=0:return None
    last=min(period_end-1,j+MAX_HOLD-1)
    close=bars[last]["close"]
    status="timeout"
    for k in range(j,last+1):
        b=bars[k]
        bad=b["low"] if side==1 else b["high"]
        gap=b["open"]<=liq if side==1 else b["open"]>=liq
        if gap or (bad<=liq if side==1 else bad>=liq):
            close=b["open"] if gap else liq;last=k
            status="liquidation_proxy";break
        if b["open"]<=stop if side==1 else b["open"]>=stop:
            close=b["open"];last=k;status="stop_gap";break
        if bad<=stop if side==1 else bad>=stop:
            close=stop;last=k;status="stop";break
        good=b["high"] if side==1 else b["low"]
        if good>=target if side==1 else good<=target:
            close=target;last=k;status="target";break
    actual_exit=close*(1-side*slip)
    gross=side*(actual_exit-entry)*qty*float(spec["ctVal"])
    exit_fee=abs(actual_exit*qty*float(spec["ctVal"]))*fee
    funding=notional*FUNDING_PER_8H*(last-j+1)/32
    pnl=gross-entry_fee-exit_fee-funding
    if status=="liquidation_proxy":pnl=min(pnl,-margin-entry_fee-exit_fee)
    pnl=max(-equity,pnl)
    return {"exit_i":last,"equity_after":max(0.,equity+pnl),
            "status":status,"pnl":pnl,"fees":entry_fee+exit_fee}


def replay(markets,specs,signals,*,start,end,leverage,fee,slip):
    """One position at a time, no relabels, skip 16 bars after each exit."""
    events={}
    for sym,rows in signals.items():
        for signal in rows:
            if start<=signal[0] and signal[0]+1<end:
                events.setdefault(signal[0],[]).append(
                    (signal[3],sym,signal))
    equity=START;peak=START;max_dd=0;next_allowed=start
    trades=0;liquidations=0;fees=0.;target_hit=False
    for i in sorted(events):
        if i<next_allowed or equity<=RUIN or equity>=TARGET:continue
        for _,sym,signal in sorted(events[i],key=lambda x:(-x[0],x[1])):
            result=simulate_one(markets[sym],specs[sym],signal,equity,
                                leverage,fee,slip,end)
            if result is None:continue
            equity=result["equity_after"]
            next_allowed=result["exit_i"]+1+COOLDOWN
            peak=max(peak,equity)
            max_dd=max(max_dd,(peak-equity)/peak*100)
            fees+=result["fees"];trades+=1
            liquidations+=result["status"]=="liquidation_proxy"
            target_hit=target_hit or equity>=TARGET
            break
        if target_hit:break
    return {
        "closed_trades":trades,"end_closed_usdt":round(equity,8),
        "return_pct":round((equity/START-1)*100,5),
        "max_drawdown_pct":round(max_dd,5),
        "hit128_on_closed_paper_equity":target_hit,
        "ruin":equity<=RUIN,
        "liquidation_proxy_events":liquidations,
        "fee_usdt":round(fees,7),
    }


def evaluate(markets,specs,hashes):
    if len(markets)!=MARKETS or set(markets)!=set(specs) or set(markets)!=set(hashes):
        raise ValueError("Need six separate frozen true history datasets")
    n=min(len(v) for v in markets.values())
    if n<MIN_BARS:raise ValueError("Insufficient real public 90d candles")
    ts=[x["ts"] for x in next(iter(markets.values()))[:n]]
    for sym,rows in markets.items():
        if sym[:-10] not in UNIVERSE or sym[:-10] in EXCLUDED:
            raise ValueError("Unexpected crypto selection")
        validate_frozen(rows)
        if [x["ts"] for x in rows[:n]]!=ts:
            raise ValueError("Non-aligned original OHLC")
    rows={sym:signal_stream(bars[:n]) for sym,bars in markets.items()}
    a=int(n*.4);b=int(n*.6);c=int(n*.8)
    periods={"train":(224,a),
             "holdout_1":(a,b),"holdout_2":(b,c),"holdout_3":(c,n),
             "combined_untouched":(a,n)}
    results={}
    for policy in POLICIES:
        signals={sym:rows[sym][policy] for sym in markets}
        for lev in LEVERAGES:
            name=policy+"_"+str(int(lev))+"x"
            results[name]={}
            for period,(start,end) in periods.items():
                results[name][period]={
                    label:replay(markets,specs,signals,start=start,end=end,
                                 leverage=lev,fee=pair[0],slip=pair[1])
                    for label,pair in COSTS.items()}
    candidates=[]
    for key,values in results.items():
        if key.rsplit("_",1)[0] not in QUANTUM:continue
        train=values["train"]["ordinary"]
        stress=values["train"]["stress"]
        if (train["return_pct"]>0 and stress["return_pct"]>0
            and stress["closed_trades"]>=10
            and stress["max_drawdown_pct"]<=35 and not stress["ruin"]):
            candidates.append(key)
    selected=max(candidates,key=lambda k:
                 results[k]["train"]["stress"]["return_pct"]) if candidates else None
    untouched=("holdout_1","holdout_2","holdout_3")
    repeated=bool(selected) and all(
        results[selected][p][cost]["hit128_on_closed_paper_equity"]
        and not results[selected][p][cost]["ruin"]
        for p in untouched for cost in COSTS)
    combined=bool(selected) and all(
        results[selected]["combined_untouched"][cost]["hit128_on_closed_paper_equity"]
        and not results[selected]["combined_untouched"][cost]["ruin"]
        for cost in COSTS)
    history_extrema=[(key,p,c,
        results[key][p][c]["return_pct"]) for key in results
        for p in untouched for c in COSTS]
    peak=max(history_extrema,key=lambda x:x[3])
    posthoc=sum(results[k][p][cost]["hit128_on_closed_paper_equity"]
                for k in results for p in untouched for cost in COSTS)
    return {
        "study":STUDY,"source":"REAL completed OKX 15m historical candles",
        "start_usdt":START,"goal_usdt":TARGET,"required_return_pct":128,
        "market_count":MARKETS,"markets":sorted(markets),
        "bars_per_market":n,"total_real_candles":n*MARKETS,
        "raw_ohlc_sha256":hashes,"hypotheses_count":len(results),
        "segments":periods,"train_only_candidates":candidates,
        "selected_on_train_only":selected,
        "repeated_128_all_three_holdouts_and_costs":bool(repeated),
        "combined_untouched_128_both_costs":bool(combined),
        "posthoc_128_hits_not_robust_proof":posthoc,
        "best_holdout_posthoc_NOT_selection":{
            "model":peak[0],"period":peak[1],
            "cost":peak[2],"return_pct":peak[3]},
        "verdict":("HISTORICAL_PAPER_CANDIDATE_REQUIRES_UNSEEN_FORWARD_TEST"
                   if repeated and combined
                   else "NO_REPEATED_PLUS128_HISTORICAL_EDGE"),
        "results":results,"real_orders":0,"physical_quantum_processor":False,
        "limitations":[
            "Historical OHLC is real, fills and liquidations are simulated",
            "Current public contract specs may differ from historical values",
            "Funding proxy and slippage are assumed, not actual book fills",
            "Prior iterative tests create multiple-hypothesis selection bias",
            "No historical outcome guarantees a future live return",
        ],
    }


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    p.add_argument("--raw-dir",required=True)
    a=p.parse_args(argv)
    specs,total=catalogue()
    print("Q6 PRE-FROZEN MARKET COHORT",total,
          [x["instId"] for x in specs],flush=True)
    now=int(time.time()*1000);data={};metadata={};sha={}
    raw=Path(a.raw_dir);raw.mkdir(parents=True,exist_ok=True)
    for spec in specs:
        sym=spec["instId"]
        candles=fetch_history(sym,DAYS,now_ms=now)
        if len(candles)<MIN_BARS:
            raise ValueError("Public OKX incomplete 90d sample "+sym)
        original=json.dumps(candles,separators=(",",":")).encode()
        sha[sym]=hashlib.sha256(original).hexdigest()
        with gzip.open(raw/(sym+".json.gz"),"wb") as h:h.write(original)
        data[sym]=candles;metadata[sym]=spec
        print("Q6 OHLC SHA",sym,len(candles),sha[sym],flush=True)
    report=evaluate(data,metadata,sha)
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    for model,byperiod in report["results"].items():
        print("Q6 RESULT",model,
              "TRAIN",byperiod["train"]["stress"]["return_pct"],
              "H1",byperiod["holdout_1"]["stress"]["return_pct"],
              "H2",byperiod["holdout_2"]["stress"]["return_pct"],
              "H3",byperiod["holdout_3"]["stress"]["return_pct"],
              "OOS",byperiod["combined_untouched"]["stress"]["return_pct"],
              flush=True)
    print("Q6 VERDICT",report["verdict"],
          "SELECTED",report["selected_on_train_only"],
          "POSTHOC128",report["posthoc_128_hits_not_robust_proof"],
          "NO ORDERS",flush=True)


if __name__=="__main__":
    main()

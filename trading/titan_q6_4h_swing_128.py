#!/usr/bin/env python3
"""TITAN Q6: original 4-hour quantum regime strategy / 15-minute fills.

Research only. Completed public OKX OHLC; imaginary fills and proxy liquidation.
The quantum statevector is simulated on CPU, not physical quantum hardware.
Target +128% from 4.15 to 9.462 USDT, cannot be guaranteed.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, math, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from trading import titan_q5_coherence_128 as q5
from trading.edge_lab import (
    BAR_MS, fetch_history, TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE,
    STRESS_SLIPPAGE, FUNDING_PER_8H, ema_series,
)
from trading.titan_regime_research import validate_frozen

STUDY="TITAN-Q6-4H-QUANTUM-SWING-128-20261117-FROZEN-V1"
UNIVERSE=set(("AXS BONK CFX DYDX FET FLOW JTO KAS PENGU RUNE STX XTZ "
              "ZIL 1INCH TWT CHZ MASK IMX NEO NMR KAVA CKB FTM").split())
FORBIDDEN=set(("BTC ETH SOL XRP DOGE HYPE ZEC BNB BLUR MINA ETHFI AR "
               "YGG LPT GRT RENDER WIF ZK ATOM ONDO WLD LTC AVAX OP").split())
N_MARKETS=6
DAYS=90
MIN_BARS=8450
BLOCK=16
START=4.15
TARGET=9.462
RUIN=.83
LEVERAGES=(3.,10.)
POLICIES=("q6_phase_swing","q6_coherent_breakout","q6_volatility_coil",
          "q6_wave_trend","q6_countertrend","q6_zero_phase",
          "classical_same_features","classical_breakout")
QUANTUM=tuple(k for k in POLICIES if k.startswith("q6_"))
COSTS={"ordinary":(TAKER_FEE,BASE_SLIPPAGE),
       "stress":(STRESS_FEE,STRESS_SLIPPAGE)}
PHASES=(.65,1.0,1.35)
CUTOFF=.58
MARGIN_CAP=.35
STOP_EQUITY_CAP=.14
STOP_ATR=1.9
PROFIT_ATR=7.0
TRAIL_ATR=2.1
MAX_HOLD_15M=16*40
MAINTENANCE_PROXY=.015

def catalogue():
    u="https://www.okx.com/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(u,headers={"User-Agent":"TITAN-Q6-90D-HISTORY-NO-ORDERS"}),
                 timeout=35) as response: raw=json.load(response)
    if raw.get("code")!="0":raise ValueError("Public OKX instrument list unavailable")
    cutoff=int(time.time()*1000)-120*86400000
    markets=[]
    for spec in raw.get("data",[]):
        s=spec.get("instId","")
        if not s.endswith("-USDT-SWAP"):continue
        coin=s[:-10]
        if (coin not in UNIVERSE or coin in FORBIDDEN or
            spec.get("state")!="live" or spec.get("ctType")!="linear" or
            spec.get("ctValCcy")!=coin):continue
        try:
            if int(spec["listTime"])>cutoff:continue
            nums=[float(spec[k]) for k in ("ctVal","lotSz","minSz")]
            if not all(math.isfinite(v) and v>0 for v in nums):continue
        except (KeyError,ValueError,TypeError):continue
        markets.append(spec)
    markets.sort(key=lambda v:hashlib.sha256(
        (STUDY+"|"+v["instId"]).encode()).hexdigest())
    if len(markets)<N_MARKETS:raise ValueError("Not enough old liquid listed eligible contracts")
    return markets[:N_MARKETS],len(markets)

def four_hour_bars(bars):
    """Exactly 16 contiguous completed 15m candles per UTC-aligned 4h bar."""
    validate_frozen(bars)
    output=[]
    group=[]
    for index,bar in enumerate(bars):
        if bar["ts"] % (BAR_MS*BLOCK)==0:
            group=[]
        group.append((index,bar))
        if len(group)==BLOCK and group[0][1]["ts"]%(BAR_MS*BLOCK)==0:
            output.append({"signal_i":index,"open":group[0][1]["open"],
                           "high":max(x["high"] for _,x in group),
                           "low":min(x["low"] for _,x in group),
                           "close":group[-1][1]["close"],
                           "start_ms":group[0][1]["ts"]})
            group=[]
    return output

def rolling_atr(hours,i,n):
    if i<n:raise ValueError("Insufficient completed 4h history")
    return sum(max(hours[k]["high"]-hours[k]["low"],
                   abs(hours[k]["high"]-hours[k-1]["close"]),
                   abs(hours[k]["low"]-hours[k-1]["close"]))
               for k in range(i-n+1,i+1))/n

def hour_features(hours,i,e9,e27):
    """Five observed 4h inputs, no future OHLC."""
    if i<48 or i>=len(hours):raise ValueError("Insufficient 4h signal history")
    p=hours[i]["close"];atr=rolling_atr(hours,i,14)
    longatr=rolling_atr(hours,i,35)
    if min(p,atr,longatr)<=0:raise ValueError("Zero price / ATR")
    scale=max(atr/p,1e-8)
    m1=math.log(p/hours[i-6]["close"])/(scale*math.sqrt(6))
    m3=math.log(p/hours[i-18]["close"])/(scale*math.sqrt(18))
    trend=(e9[i]-e27[i])/atr
    compression=math.log(atr/longatr)*2
    pressure=sum((hours[k]["close"]-hours[k]["open"])/
                 max(hours[k]["high"]-hours[k]["low"],1e-10)
                 for k in range(i-5,i+1))
    features=tuple(max(-3.,min(3.,x)) for x in
                   (m1,m3,trend,compression,pressure/6*3))
    return features,atr,atr/longatr

def direction(p):
    return 1 if p>=CUTOFF else -1 if p<=1-CUTOFF else 0

def causal_signals(bars):
    hours=four_hour_bars(bars)
    if len(hours)<56:raise ValueError("4h signals unavailable")
    e9,e27=(ema_series([x["close"] for x in hours],k) for k in (9,27))
    found={k:[] for k in POLICIES}
    # Last bar is intentionally unused: no prediction can read future.
    for k in range(48,len(hours)-1):
        f,atr,ratio=hour_features(hours,k,e9,e27)
        if not .003<=atr/hours[k]["close"]<=.13:continue
        probs=tuple(q5.q5_probability(f,phase) for phase in PHASES)
        nominal=direction(probs[1])
        zero=direction(q5.q5_probability(f,0))
        classic=direction(q5.classic_probability(f))
        robust=(1 if min(probs)>=CUTOFF else
                -1 if max(probs)<=1-CUTOFF else 0)
        amp=min(abs(p-.5) for p in probs)
        trend=1 if e9[k]>e27[k] else -1
        high=max(x["high"] for x in hours[k-18:k])
        low=min(x["low"] for x in hours[k-18:k])
        breakout=(1 if hours[k]["close"]>high else
                  -1 if hours[k]["close"]<low else 0)
        i=hours[k]["signal_i"]
        def place(label,side,strength):
            if side:
                found[label].append((i,side,atr,
                    round(max(0.,min(.5,strength)),8)))
        place("classical_same_features",
              classic if classic==trend else 0,
              abs(q5.classic_probability(f)-.5))
        place("classical_breakout",breakout,.2+min(.3,abs(f[1])*.08))
        place("q6_zero_phase",zero if zero==trend else 0,
              abs(q5.q5_probability(f,0)-.5))
        place("q6_phase_swing",
              nominal if nominal==trend and abs(f[1])>.65 and ratio<1.5 else 0,
              abs(probs[1]-.5))
        place("q6_coherent_breakout",
              robust if robust==breakout and breakout==trend else 0,
              amp)
        place("q6_volatility_coil",
              robust if robust==trend and ratio<.85 and abs(f[1])>.5 else 0,
              amp)
        place("q6_wave_trend",
              robust if robust==trend and abs(f[0])>.8 and abs(f[1])>.6 else 0,
              amp)
        place("q6_countertrend",
              robust if robust==-trend and abs(f[2])>1.4 and ratio<1.2 else 0,
              amp)
    return found

def contracts(spec,equity,price,atr,leverage):
    """Public ctVal/lotSz/minSz, no fractional contract fantasy."""
    try:
        cv,step,minqty=(float(spec[k]) for k in ("ctVal","lotSz","minSz"))
        if (min(cv,step,minqty,price,atr,equity)<=0 or
            spec.get("state")!="live" or
            spec.get("ctValCcy")!=spec["instId"].split("-")[0]):
            return 0.,0.
        stop_distance=STOP_ATR*atr/price
        if not 0<stop_distance<.20:return 0.,0.
        budget=min(equity*MARGIN_CAP*leverage,equity*STOP_EQUITY_CAP/stop_distance)
        q=math.floor(budget/(price*cv)/step+1e-9)*step
        actual_min=math.ceil(minqty/step-1e-9)*step
        if q<actual_min-1e-10:return 0.,0.
        return round(q,9),q*cv*price
    except (KeyError,ValueError,TypeError,OverflowError,ZeroDivisionError):
        return 0.,0.

def sim_trade(bars,signal,spec,equity,leverage,fee,slip,period_end):
    """Entry next 15m open. Mark liquidation proxy first, then stop, then TP.

    Dynamic trailing stop moves at previous close, never using current high
    as an advance-known fill. Exit only on actual completed historical candle.
    """
    i,side,atr,_=signal;j=i+1
    if j>=period_end:return None
    entry=bars[j]["open"]*(1+side*slip)
    qty,notional=contracts(spec,equity,entry,atr,leverage)
    if qty<=0:return None
    margin=notional/leverage;entry_fee=fee*notional
    if entry_fee>=equity-margin:return None
    stop=entry-side*STOP_ATR*atr
    target=entry+side*PROFIT_ATR*atr
    liq=entry*(1-side*max(.001,1/leverage-MAINTENANCE_PROXY))
    if min(stop,target,liq)<=0:return None
    close_at=min(period_end-1,j+MAX_HOLD_15M-1)
    filled=bars[close_at]["close"];status="timeout"
    for k in range(j,close_at+1):
        b=bars[k];bad=b["low"] if side>0 else b["high"]
        if ((b["open"]<=liq if side>0 else b["open"]>=liq) or
            (bad<=liq if side>0 else bad>=liq)):
            filled=b["open"] if (b["open"]<=liq if side>0 else b["open"]>=liq) else liq
            status="liq_proxy";close_at=k;break
        if (b["open"]<=stop if side>0 else b["open"]>=stop):
            filled=b["open"];status="stop_gap";close_at=k;break
        if bad<=stop if side>0 else bad>=stop:
            filled=stop;status="stop";close_at=k;break
        good=b["high"] if side>0 else b["low"]
        if good>=target if side>0 else good<=target:
            filled=target;status="target";close_at=k;break
        if side>0 and b["close"]>entry+2*atr:
            stop=max(stop,b["close"]-TRAIL_ATR*atr)
        elif side<0 and b["close"]<entry-2*atr:
            stop=min(stop,b["close"]+TRAIL_ATR*atr)
    outfill=filled*(1-side*slip)
    exit_fee=abs(qty*float(spec["ctVal"])*outfill)*fee
    funding=notional*FUNDING_PER_8H*(close_at-j+1)/32
    pnl=side*(outfill-entry)*qty*float(spec["ctVal"])-entry_fee-exit_fee-funding
    if status=="liq_proxy":pnl=min(pnl,-margin-entry_fee-exit_fee)
    end=max(0.,equity+max(-equity,pnl))
    return {"exit_i":close_at,"equity_after":end,"net_usdt":pnl,
            "fees":entry_fee+exit_fee,"status":status,"symbol":spec["instId"]}

def paper(markets,specs,streams,lev,start,end,fee,slip):
    if set(markets)!=set(specs) or set(markets)!=set(streams):
        raise ValueError("Cohort missing")
    events={}
    for sym,signals in streams.items():
        for sig in signals:
            if start<=sig[0] and sig[0]+1<end:
                events.setdefault(sig[0],[]).append((sig[3],sym,sig))
    equity=START;peak=START;dd=0.;available=start;trades=0;liq=0;fees=0.;hit=False
    for i in sorted(events):
        if i<available or equity<=RUIN or hit:continue
        for strength,sym,signal in sorted(events[i],key=lambda x:(-x[0],x[1])):
            result=sim_trade(markets[sym],signal,specs[sym],
                             equity,lev,fee,slip,end)
            if result is None:continue
            equity=result["equity_after"];available=result["exit_i"]+1
            peak=max(peak,equity);dd=max(dd,100*(peak-equity)/peak)
            trades+=1;fees+=result["fees"];liq+=(result["status"]=="liq_proxy")
            if equity>=TARGET:hit=True
            break
    return {"trades":trades,"end_usdt":round(equity,8),
            "return_pct":round(100*(equity/START-1),5),
            "max_dd_pct":round(dd,5),"fees_usdt":round(fees,7),
            "liq_proxy_count":liq,
            "hit_128_closed_paper":hit,
            "ruin":equity<=RUIN}

def evaluate(markets,specs,sha):
    if len(markets)!=N_MARKETS or set(markets)!=set(specs) or set(markets)!=set(sha):
        raise ValueError("Exactly six independent public historical data series required")
    if any(s[:-10] not in UNIVERSE or s[:-10] in FORBIDDEN for s in markets):
        raise ValueError("Contaminated universe")
    length=min(len(x) for x in markets.values())
    if length<MIN_BARS:raise ValueError("Missing 90-day OHLC")
    grid=[r["ts"] for r in next(iter(markets.values()))[:length]]
    for rows in markets.values():
        validate_frozen(rows)
        if [r["ts"] for r in rows[:length]]!=grid:
            raise ValueError("Misaligned OHLC")
    sign={sym:causal_signals(rows[:length]) for sym,rows in markets.items()}
    cuts=(int(length*.5),int(length*.75),length)
    splits={"train":(16*50,cuts[0]),
            "holdout_1":(cuts[0],cuts[1]),
            "holdout_2":(cuts[1],length),
            "all_holdouts":(cuts[0],length)}
    result={}
    for label in POLICIES:
        streams={s:sign[s][label] for s in markets}
        for lev in LEVERAGES:
            key=label+"_"+str(int(lev))+"x"
            result[key]={}
            for period,(a,b) in splits.items():
                result[key][period]={}
                for mode,(fee,slip) in COSTS.items():
                    result[key][period][mode]=paper(
                        markets,specs,streams,lev,a,b,fee,slip)
    qualifying=[k for k in result if k.rsplit("_",1)[0] in QUANTUM
                and result[k]["train"]["stress"]["trades"]>=3
                and result[k]["train"]["ordinary"]["return_pct"]>0
                and result[k]["train"]["stress"]["return_pct"]>0
                and result[k]["train"]["stress"]["max_dd_pct"]<=40
                and not result[k]["train"]["stress"]["ruin"]]
    selected=max(qualifying,key=lambda k:result[k]["train"]["stress"]["return_pct"]
                 ) if qualifying else None
    repeated=bool(selected) and all(
        result[selected][p][m]["hit_128_closed_paper"] and
        not result[selected][p][m]["ruin"] for p in ("holdout_1","holdout_2")
        for m in COSTS)
    combined=bool(selected) and all(
        result[selected]["all_holdouts"][m]["hit_128_closed_paper"]
        and not result[selected]["all_holdouts"][m]["ruin"] for m in COSTS)
    top=max(((k,p,m,result[k][p][m]["return_pct"]) for k in result
             for p in ("holdout_1","holdout_2") for m in COSTS),
            key=lambda x:x[3])
    return {"study":STUDY,"start_usdt":START,"target_usdt":TARGET,
            "source":"public real OKX completed 15m historical trade candles",
            "signals":"completed UTC-aligned 4-hour OHLC",
            "markets":sorted(markets),"sha256":sha,
            "bars_per_market":length,"total_market_bars":length*N_MARKETS,
            "candidate_model_count":len(result),"splits":splits,
            "training_qualified":qualifying,"train_only_selected":selected,
            "hit128_twice_in_untouched_periods_both_costs":bool(repeated),
            "hit128_on_combined_untouched_history_both_costs":bool(combined),
            "retrospective_best_not_trading_recommendation":{
                "model":top[0],"period":top[1],"cost":top[2],"return_pct":top[3]},
            "verdict":("HISTORICAL_PAPER_ONLY_NEEDS_FORWARD_VALIDATION"
                       if combined and repeated else "NO_REPLICATED_PLUS128_HISTORICAL_EDGE"),
            "results":result,"real_orders":0,"quantum_hardware_used":False,
            "limitations":[
                "All prices genuine, but fills and funding/liquidation are assumed",
                "Public current contract specifications may differ in the historical interval",
                "Previously explored hypothesis families can induce selection bias",
                "A +128% historical simulation would not guarantee live profits",
            ]}

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out",required=True)
    ap.add_argument("--raw-dir",required=True)
    a=ap.parse_args(argv)
    basket,pool=catalogue()
    print("Q6 FROZEN SELECTION",pool,[s["instId"] for s in basket],flush=True)
    now=int(time.time()*1000);markets={};specs={};sha={}
    out=Path(a.raw_dir);out.mkdir(parents=True,exist_ok=True)
    for spec in basket:
        sym=spec["instId"]
        bars=fetch_history(sym,DAYS,now_ms=now)
        if len(bars)<MIN_BARS:raise ValueError("Incomplete real OHLC: "+sym)
        raw=json.dumps(bars,separators=(",",":")).encode()
        hash_=hashlib.sha256(raw).hexdigest()
        with gzip.open(out/(sym+".json.gz"),"wb") as f:f.write(raw)
        markets[sym]=bars;specs[sym]=spec;sha[sym]=hash_
        print("Q6 REAL OHLC",sym,len(bars),hash_,flush=True)
    report=evaluate(markets,specs,sha)
    target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    for k,v in report["results"].items():
        print("Q6 RETURN",k,
              "TRAIN",v["train"]["stress"]["return_pct"],
              "H1",v["holdout_1"]["stress"]["return_pct"],
              "H2",v["holdout_2"]["stress"]["return_pct"],
              "ALL",v["all_holdouts"]["stress"]["return_pct"],flush=True)
    print("Q6 FINAL",report["verdict"],"SELECTED",
          report["train_only_selected"],"NO ORDERS",flush=True)

if __name__=="__main__":main()

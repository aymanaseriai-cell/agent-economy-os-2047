#!/usr/bin/env python3
"""TITAN Q7: NEW six-qubit cross-market phase-interference research.

A deliberately different regime-aware six-qubit quantum-inspired simulated
tensor circuit, precommitted before retrieving public completed OKX candles.
Measures repeatability of +128% closed-PAPER PnL, NOT real exchange profits.
No orders, credentials, physical quantum computer, or adaptive peek at OOS.
"""
from __future__ import annotations
import argparse, cmath, gzip, hashlib, json, math, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from trading.edge_lab import (
    BAR_MS, ema_series, fetch_history,
    TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE, STRESS_SLIPPAGE,
    FUNDING_PER_8H,
)
from trading.titan_regime_research import validate_frozen

STUDY="TITAN-Q7-6Q-MARKET-INTERFERENCE-4x30D-20261117-PRECOMMITTED"
PREVIOUS=set(("BTC ETH SOL XRP DOGE HYPE ZEC BNB ATOM ONDO WLD LTC AVAX OP "
              "GRT RENDER CHZ WIF ZK MASK BLUR MINA ETHFI AR YGG LPT "
              "ZIL STX BONK PENGU IMX DYDX JTO XTZ AXS CFX NMR "
              "COMP IOST UMA LDO CELO FIL "
              "ARB BCH ETC JUP ZRX NEAR").split())
UNIVERSE=set(("1INCH ACH AEVO AKT ALT API3 ARKM ASTR BAL BAND BAT CKB "
              "COTI CTSI DASH DCR DENT ENJ FET FLOW FXS GMX IOTA KAS "
              "KAVA KNC LSK QTUM RLC RUNE SNX SSV STORJ SUSHI THETA "
              "TWT VET XEC ZEN PENDLE CRV TRB RSR ZETA OGN NKN "
              "ORDI JASMY CVC GLM LRC AUDIO GALA SXP YFI").split())
MARKETS=6
DAYS=180
MIN_BARS=17100
BLOCK=16
START=4.15
GOAL=9.462
LEVS=(3.,10.)
PHASES=(.7,1.0,1.3)
THRESHOLD=.535
POLICIES=("q7_phase_consensus","q7_breadth_echo","q7_entropy_collapse",
          "q7_momentum_overlap","q7_reversal_veto","q7_phase_zero",
          "classical_same_features","classical_swing_breakout")
QMODELS=tuple(x for x in POLICIES if x.startswith("q7_"))
MARGIN_FRAC=.30
EQUITY_STOP_RISK=.12
STOP_ATR=1.8
TP_ATR=6.5
TRAIL_ATR=2.2
MAX_HOLD=16*35
MAINTENANCE=.015
COSTS={"ordinary":(TAKER_FEE,BASE_SLIPPAGE),
       "stress":(STRESS_FEE,STRESS_SLIPPAGE)}
PARTS=("holdout_1","holdout_2","holdout_3","holdout_4")

def catalogue():
    url="https://www.okx.com/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-Q7-PUBLIC-ONLY"}),
                 timeout=35) as h:data=json.load(h)
    if data.get("code")!="0":raise ValueError("Cannot verify public OKX catalogue")
    date=int(time.time()*1000)-210*86400000
    specs=[]
    for s in data.get("data",[]):
        name=s.get("instId","")
        if not name.endswith("-USDT-SWAP"):continue
        coin=name[:-10]
        if (coin not in UNIVERSE or coin in PREVIOUS or
            s.get("state")!="live" or s.get("ctType")!="linear" or
            s.get("ctValCcy")!=coin):continue
        try:
            if int(s["listTime"])>date:continue
            vals=[float(s[k]) for k in ("ctVal","lotSz","minSz")]
            if any(not math.isfinite(x) or x<=0 for x in vals):continue
        except (TypeError,KeyError,ValueError):continue
        specs.append(s)
    # Hash identifiers ONLY; no future or even historical returns used.
    specs.sort(key=lambda s:hashlib.sha256(
        (STUDY+"|"+s["instId"]).encode()).hexdigest())
    if len(specs)<MARKETS:raise ValueError("Too few distinct eligible old swap markets")
    return specs[:MARKETS],len(specs)

def ry(v,bit,t):
    mask=1<<bit;c=math.cos(t/2);s=math.sin(t/2);out=list(v)
    for i in range(64):
        if i&mask:continue
        a,b=v[i],v[i|mask]
        out[i]=c*a-s*b;out[i|mask]=s*a+c*b
    return out

def hgate(v,bit):
    mask=1<<bit;c=math.sqrt(.5);out=list(v)
    for i in range(64):
        if i&mask:continue
        a,b=v[i],v[i|mask]
        out[i]=(a+b)*c;out[i|mask]=(a-b)*c
    return out

def quantum_probability(features,phase=1.):
    """Six complex-amplitude qubits, six observable causal features."""
    if (len(features)!=6 or not all(math.isfinite(float(x)) for x in features)
        or not math.isfinite(phase) or not 0<=phase<=2):
        raise ValueError("Six finite observed inputs and bounded phase required")
    x=tuple(math.tanh(float(v)) for v in features)
    wave=[0j]*64;wave[0]=1+0j
    for b in range(6):
        wave=ry(wave,b,1.6*x[b])
    # Two noncommuting entanglement layers; ZZ coupling plus rotations.
    for j in range(64):
        z=[1 if j&(1<<b) else -1 for b in range(6)]
        ring=sum((.16+.05*b)*z[b]*z[(b+1)%6] for b in range(6))
        bridge=.3*z[0]*z[3]-.25*z[1]*z[4]+.21*z[2]*z[5]
        field=.15*sum(z[b]*x[b] for b in range(6))
        wave[j]*=cmath.exp(1j*phase*(ring+bridge+field))
    for b in range(6):wave=hgate(wave,b)
    for b in range(6):wave=ry(wave,b,.68*x[(b+2)%6])
    for b in (0,2,4):wave=hgate(wave,b)
    norm=sum(abs(z)**2 for z in wave)
    if abs(norm-1)>1e-9:raise ArithmeticError("Unphysical loss of wave norm")
    # Signed probability of qubit 5 = 1 (Born rule)
    p=sum(abs(z)**2 for i,z in enumerate(wave) if i&32)
    if not 0-1e-9<=p<=1+1e-9:raise ArithmeticError("Invalid probability")
    return max(0.,min(1.,p))

def classical_probability(features):
    if len(features)!=6 or any(not math.isfinite(float(x)) for x in features):
        raise ValueError("Wrong classical same-feature control")
    score=sum(w*math.tanh(float(v)) for v,w in zip(
        features,(.5,.4,.3,-.3,.4,.35)))
    return 1/(1+math.exp(-score))

def side(p):
    return 1 if p>=THRESHOLD else -1 if p<=1-THRESHOLD else 0

def four_hour_bars(bars):
    validate_frozen(bars)
    result=[];group=[]
    for i,b in enumerate(bars):
        if b["ts"]%(BAR_MS*BLOCK)==0:group=[]
        group.append((i,b))
        if len(group)==BLOCK and group[0][1]["ts"]%(BAR_MS*BLOCK)==0:
            result.append({"signal_i":i,"ts":group[0][1]["ts"],
                           "open":group[0][1]["open"],
                           "high":max(x["high"] for _,x in group),
                           "low":min(x["low"] for _,x in group),
                           "close":group[-1][1]["close"]})
            group=[]
    return result

def atr(hours,i,n):
    if i<n:raise ValueError("Causal ATR lookback unavailable")
    return sum(max(hours[k]["high"]-hours[k]["low"],
                   abs(hours[k]["high"]-hours[k-1]["close"]),
                   abs(hours[k]["low"]-hours[k-1]["close"]))
               for k in range(i-n+1,i+1))/n

def get_features(hours,i,ema9,ema27,breadth):
    if i<56:raise ValueError("Insufficient 4h lookback")
    p=hours[i]["close"];a=atr(hours,i,14);long=atr(hours,i,35)
    if min(p,a,long)<=0:raise ValueError("Nonpositive market observation")
    norm=max(a/p,1e-8)
    ret2=math.log(p/hours[i-3]["close"])/max(norm*math.sqrt(3),1e-8)
    ret12=math.log(p/hours[i-18]["close"])/max(norm*math.sqrt(18),1e-8)
    trend=(ema9[i]-ema27[i])/a
    vol=math.log(a/long)*2
    pressure=sum((hours[j]["close"]-hours[j]["open"])/max(
        hours[j]["high"]-hours[j]["low"],1e-9)
        for j in range(i-5,i+1))*.5
    f=tuple(max(-3.,min(3.,z)) for z in
            (ret2,ret12,trend,vol,pressure,breadth*3))
    return f,a,a/long

def signals(markets):
    if len(markets)!=MARKETS:raise ValueError("Expected precisely 6 markets")
    panel={symbol:four_hour_bars(b) for symbol,b in markets.items()}
    n=min(map(len,panel.values()))
    if n<600:raise ValueError("Too few complete four-hour bars")
    axis=[x["ts"] for x in next(iter(panel.values()))[:n]]
    if any([x["ts"] for x in rows[:n]]!=axis for rows in panel.values()):
        raise ValueError("Non-aligned market breadth, refuses future data")
    spans={}
    for sym,rows in panel.items():
        closes=[x["close"] for x in rows]
        spans[sym]=(ema_series(closes,9),ema_series(closes,27))
    output={sym:{k:[] for k in POLICIES} for sym in markets}
    for t in range(56,n-1):
        breadth=sum(1 if b[t]["close"]>b[t-6]["close"] else -1
                    for b in panel.values())/MARKETS
        for sym,rows in panel.items():
            e9,e27=spans[sym]
            f,a,ratio=get_features(rows,t,e9,e27,breadth)
            if not .003<=a/rows[t]["close"]<=.14:continue
            p=tuple(quantum_probability(f,ph) for ph in PHASES)
            p0=quantum_probability(f,0.)
            pc=classical_probability(f)
            base=side(p[1])
            robust=1 if min(p)>=THRESHOLD else -1 if max(p)<=1-THRESHOLD else 0
            regime=1 if e9[t]>e27[t] else -1
            swing=1 if rows[t]["close"]>rows[t-18]["close"] else -1
            boundary_hi=max(x["high"] for x in rows[t-12:t])
            boundary_lo=min(x["low"] for x in rows[t-12:t])
            breakout=(1 if rows[t]["close"]>boundary_hi else
                      -1 if rows[t]["close"]<boundary_lo else 0)
            strength=min(abs(x-.5) for x in p)
            i=rows[t]["signal_i"]
            def put(name,d,confidence):
                if d:
                    output[sym][name].append(
                        (i,d,a,round(min(.5,abs(confidence)),8)))
            put("q7_phase_consensus",robust if robust==regime else 0,strength)
            put("q7_breadth_echo",base if base==regime and
                base*breadth>.3 and ratio<1.4 else 0,abs(p[1]-.5))
            put("q7_entropy_collapse",robust if robust==breakout and
                ratio<1.05 else 0,strength)
            put("q7_momentum_overlap",base if base==regime and
                base==swing and abs(f[1])>.4 else 0,abs(p[1]-.5))
            put("q7_reversal_veto",robust if robust==-regime and
                ratio<.85 and abs(f[2])>1.4 else 0,strength)
            put("q7_phase_zero",side(p0) if side(p0)==regime else 0,
                abs(p0-.5))
            put("classical_same_features",
                side(pc) if side(pc)==regime else 0,abs(pc-.5))
            put("classical_swing_breakout",breakout if breakout==regime
                else 0,.1+min(.4,abs(f[1])*.05))
    return output

def contracts(spec,eq,price,atr4,lev):
    if eq<=.83 or min(eq,price,atr4,lev)<=0:return 0.,0.
    try:
        cv,step,minimum=(float(spec[k]) for k in ("ctVal","lotSz","minSz"))
        if (min(cv,step,minimum)<=0 or spec.get("state")!="live" or
            spec.get("ctValCcy")!=spec["instId"].split("-")[0]):
            return 0.,0.
        stopfrac=STOP_ATR*atr4/price
        if not 0<stopfrac<.25:return 0.,0.
        exposure=min(eq*MARGIN_FRAC*lev,eq*EQUITY_STOP_RISK/stopfrac)
        qty=math.floor(exposure/(cv*price)/step+1e-9)*step
        minqty=math.ceil(minimum/step-1e-9)*step
        if qty<minqty-1e-10:return 0.,0.
        return round(qty,9),qty*cv*price
    except (KeyError,ValueError,TypeError,OverflowError,ZeroDivisionError):
        return 0.,0.

def sim_one(bars,sig,spec,eq,lev,fee,slip,end):
    """Next-15m-open fill; liquidation proxy, gap stop, stop, then target."""
    i,sgn,a,_=sig;j=i+1
    if j>=end:return None
    entry=bars[j]["open"]*(1+sgn*slip)
    qty,notional=contracts(spec,eq,entry,a,lev)
    if qty<=0:return None
    margin=notional/lev;fee_open=notional*fee
    if margin+fee_open>=eq:return None
    stop=entry-sgn*STOP_ATR*a;target=entry+sgn*TP_ATR*a
    liq=entry*(1-sgn*max(.001,1/lev-MAINTENANCE))
    if min(stop,target,liq)<=0:return None
    final=min(end-1,j+MAX_HOLD-1);fill=bars[final]["close"];status="timeout"
    for k in range(j,final+1):
        b=bars[k];bad=b["low"] if sgn==1 else b["high"]
        gap=(b["open"]<=liq if sgn==1 else b["open"]>=liq)
        if gap or (bad<=liq if sgn==1 else bad>=liq):
            fill=b["open"] if gap else liq;status="liq_proxy";final=k;break
        if b["open"]<=stop if sgn==1 else b["open"]>=stop:
            fill=b["open"];status="stop_gap";final=k;break
        if bad<=stop if sgn==1 else bad>=stop:
            fill=stop;status="stop";final=k;break
        good=b["high"] if sgn==1 else b["low"]
        if good>=target if sgn==1 else good<=target:
            fill=target;status="target";final=k;break
        # Future bars only see trailing threshold revised AFTER this bar closes.
        if sgn==1 and b["close"]>entry+2*a:
            stop=max(stop,b["close"]-TRAIL_ATR*a)
        if sgn==-1 and b["close"]<entry-2*a:
            stop=min(stop,b["close"]+TRAIL_ATR*a)
    exit_fill=fill*(1-sgn*slip)
    fee_exit=abs(qty*float(spec["ctVal"])*exit_fill)*fee
    funding=notional*FUNDING_PER_8H*(final-j+1)/32
    gross=sgn*(exit_fill-entry)*qty*float(spec["ctVal"])
    pnl=gross-fee_open-fee_exit-funding
    if status=="liq_proxy":pnl=min(pnl,-margin-fee_open-fee_exit)
    new_eq=max(0.,eq+max(-eq,pnl))
    return {"exit_i":final,"equity":new_eq,"pnl":pnl,
            "fees":fee_open+fee_exit,"status":status}

def paper(markets,specs,streams,lev,start,end,fee,slip):
    event={}
    for sym,rows in streams.items():
        for sig in rows:
            if start<=sig[0] and sig[0]+1<end:
                event.setdefault(sig[0],[]).append((sig[3],sym,sig))
    eq=START;peak=START;max_dd=0.;available=start;count=0;liq=0;fees=0.;hit=False
    for i in sorted(event):
        if i<available or eq<=.83 or hit:continue
        for conf,sym,sig in sorted(event[i],key=lambda v:(-v[0],v[1])):
            trade=sim_one(markets[sym],sig,specs[sym],eq,lev,fee,slip,end)
            if trade is None:continue
            eq=trade["equity"];available=trade["exit_i"]+1
            peak=max(peak,eq);max_dd=max(max_dd,(peak-eq)/peak)
            count+=1;fees+=trade["fees"];liq+=trade["status"]=="liq_proxy"
            hit=eq>=GOAL
            break
    return {"trades":count,"end_usdt":round(eq,6),
            "return_pct":round(100*(eq/START-1),5),
            "max_dd_pct":round(100*max_dd,5),
            "fees_usdt":round(fees,7),"liquidation_proxy_events":liq,
            "hit128_closed_paper":hit,"ruin":eq<=.83}

def splits(n):
    if n<MIN_BARS:raise ValueError("Less than 180 days genuine complete OHLC")
    initial=int(n/3)
    stride=(n-initial)//4
    cuts=[initial+i*stride for i in range(4)]+[n]
    if min(b-a for a,b in zip(cuts,cuts[1:]))<2500:
        raise ValueError("Independent month-scale windows too short")
    spans={"train":(16*56,initial)}
    for i in range(4):spans[PARTS[i]]=(cuts[i],cuts[i+1])
    spans["combined_holdouts"]=(initial,n)
    return spans

def evaluate(markets,specs,hashes):
    if len(markets)!=MARKETS or set(markets)!=set(specs) or set(markets)!=set(hashes):
        raise ValueError("Exactly six genuine OHLC markets with specs required")
    if any(x[:-10] not in UNIVERSE or x[:-10] in PREVIOUS for x in markets):
        raise ValueError("Prior researched market in precommitted universe")
    n=min(map(len,markets.values()));parts=splits(n)
    axis=[b["ts"] for b in next(iter(markets.values()))[:n]]
    for b in markets.values():
        validate_frozen(b)
        if [x["ts"] for x in b[:n]]!=axis:
            raise ValueError("Misaligned actual history")
    data={sym:b[:n] for sym,b in markets.items()}
    voices=signals(data)
    outcomes={}
    for p in POLICIES:
        for lev in LEVS:
            model=p+"_"+str(int(lev))+"x"
            v={sym:voices[sym][p] for sym in markets}
            outcomes[model]={}
            for period,(lo,hi) in parts.items():
                outcomes[model][period]={}
                for mode,(fee,slip) in COSTS.items():
                    outcomes[model][period][mode]=paper(
                        data,specs,v,lev,lo,hi,fee,slip)
    candidates=[k for k,score in outcomes.items() if
                k.rsplit("_",1)[0] in QMODELS and
                score["train"]["stress"]["trades"]>=5 and
                score["train"]["stress"]["return_pct"]>0 and
                score["train"]["ordinary"]["return_pct"]>0 and
                score["train"]["stress"]["max_dd_pct"]<=35 and
                not score["train"]["stress"]["ruin"]]
    selected=(max(candidates,key=lambda k:outcomes[k]["train"]["stress"]["return_pct"])
              if candidates else None)
    flags={}
    for k,model in outcomes.items():
        hits=[all(model[h][c]["hit128_closed_paper"] and
                  not model[h][c]["ruin"] for c in COSTS) for h in PARTS]
        flags[k]={"holdout_hit128_both_costs":hits,
                  "repeat_count":sum(hits),
                  "combined_hit128_both_costs":all(
                      model["combined_holdouts"][c]["hit128_closed_paper"]
                      for c in COSTS)}
    confirmed=(selected is not None and flags[selected]["repeat_count"]==4 and
               flags[selected]["combined_hit128_both_costs"] and
               all(outcomes[selected][h]["stress"]["max_dd_pct"]<=40
                   for h in PARTS))
    retrospective_max=max(
        ((key,h,mode,row[h][mode]["return_pct"])
         for key,row in outcomes.items() for h in PARTS for mode in COSTS),
        key=lambda z:z[3])
    return {
        "study":STUDY,"target_pct":128.,"starting_usdt":START,
        "target_usdt":GOAL,"source":"OKX real publicly available completed 15-minute OHLC",
        "signal_timeframe":"completed UTC-aligned 4-hour candles",
        "market_data_sha256":hashes,"markets":sorted(markets),
        "candles_per_market":n,"total_candles":n*MARKETS,
        "partitions":parts,"tested_hypotheses":len(outcomes),
        "train_qualified":candidates,"train_only_selected":selected,
        "by_model_repeated_128_diagnostic_NOT_proof":flags,
        "selected_validated_128_four_times":bool(confirmed),
        "retrospective_highest_single_window_NOT_proof":{
            "model":retrospective_max[0],"holdout":retrospective_max[1],
            "cost":retrospective_max[2],"return_pct":retrospective_max[3]},
        "verdict":("HISTORICAL_PAPER_REPEATED_NOT_LIVE_PROOF" if confirmed
                   else "NO_VALIDATED_PLUS128_REPEATED_FOUR_WINDOWS"),
        "results":outcomes,"real_orders":0,
        "physical_quantum_hardware":False,
        "limitations":[
            "Public OHLC genuine; simulation fills, funding, liquidation are approximate",
            "Current contract specs not historically point-in-time reconstructed",
            "Four 30-day intervals share historical market and coin correlations",
            "Series of prior model attempts constitutes multiple-testing exposure",
            "Even four simulated +128 windows could not guarantee future live outcome",
        ],
    }

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True)
    ap.add_argument("--raw-dir",required=True)
    a=ap.parse_args(argv)
    basket,pool=catalogue()
    print("Q7 FROZEN BASKET BEFORE LOOKING AT HISTORY",pool,
          [s["instId"] for s in basket],flush=True)
    now=int(time.time()*1000)
    specmap={};market={};sha={}
    raw=Path(a.raw_dir);raw.mkdir(parents=True,exist_ok=True)
    for s in basket:
        name=s["instId"]
        rows=fetch_history(name,DAYS,now_ms=now)
        if len(rows)<MIN_BARS:raise ValueError("Missing real 180-day history "+name)
        payload=json.dumps(rows,separators=(",",":")).encode()
        key=hashlib.sha256(payload).hexdigest()
        with gzip.open(raw/(name+".json.gz"),"wb") as f:f.write(payload)
        specmap[name]=s;market[name]=rows;sha[name]=key
        print("Q7 REAL HISTORICAL OHLC",name,len(rows),key,flush=True)
    output=evaluate(market,specmap,sha)
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(output,sort_keys=True,indent=2)+"\n")
    for name,res in output["results"].items():
        print("Q7 RETURN",name,"TRAIN",res["train"]["stress"]["return_pct"],
              "H1",res["holdout_1"]["stress"]["return_pct"],
              "H2",res["holdout_2"]["stress"]["return_pct"],
              "H3",res["holdout_3"]["stress"]["return_pct"],
              "H4",res["holdout_4"]["stress"]["return_pct"],
              "COMBINED",res["combined_holdouts"]["stress"]["return_pct"],flush=True)
    print("Q7 PROOF",output["verdict"],
          "TRAIN_SELECTED",output["train_only_selected"],
          "REPEATED_FOUR",output["selected_validated_128_four_times"],
          "TOP",output["retrospective_highest_single_window_NOT_proof"],
          "NO ORDERS",flush=True)

if __name__=="__main__":main()

#!/usr/bin/env python3
"""TITAN Ω Quantum Kernel Evidence Lab (QKEL) — RESEARCH ONLY.

Novel project-specific design: a 2-qubit entangled phase-feature map encodes
causal completed-candle features. Historical strategy payoffs from the FIRST
45% only act as calibration labels. Quantum fidelity kernel estimates
net-after-STRESSED-cost conditional utility; a lower confidence bound must
be positive. An identical-data classical radial-basis kernel is the negative
control. Select strategies on NEXT 15% only; evaluate on two untouched final
20% periods. NO private API, real orders, or quantum hardware.

This tests a hypothesis, not a system with guaranteed repeated profits.
"""
from __future__ import annotations
import argparse
import cmath
import gzip
import hashlib
import json
import math
import statistics
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

from trading.edge_lab import (
    BAR_MS,START_EQUITY,STRESS_FEE,STRESS_SLIPPAGE,
    FUNDING_PER_8H,ema_series,atr_simple,rsi_simple,
    fetch_history,trade_simulation
)
from trading.titan_regime_research import validate_frozen
from trading.titan_quantum_recurrence import capital_feasibility

# Different six instruments from every earlier 36-market research run.
SYMBOLS=("ALGO-USDT-SWAP","APE-USDT-SWAP","ENA-USDT-SWAP",
         "ENS-USDT-SWAP","LDO-USDT-SWAP","ONDO-USDT-SWAP")
DAYS=60
MIN_BARS=5600
WARMUP=256
STEP=8
FIT_FRAC=.45
VALIDATION_FRAC=.15
FIT_MIN=20
EFFECTIVE_NEIGHBORS_MIN=16
CONFIDENCE_SIGMA=1.40
EDGE_FLOOR=0.00025
MAX_CALIBRATION=550
HOLD_BARS=24
STOP_ATR=1.5
TARGET_ATR=2.5
MIN_VALIDATION_TRADES=30
MIN_VALIDATION_POSITIVE_MARKETS=4
MIN_TEST_TRADES=40
MIN_TEST_POSITIVE_MARKETS=4
MIN_TEST_POSITIVE_DAYS=6
POLICIES=("quantum_kernel_trend","quantum_kernel_reversion",
          "classical_rbf_trend","classical_rbf_reversion",
          "unfiltered_trend","unfiltered_reversion")


def norm2(vec):
    return sum(abs(x)**2 for x in vec)


def qmap(features):
    """2-qubit normalized pure state from two rotations plus entangling ZZ.

    Step 1: RY(x0) ⊗ RY(x1) applied to |00>.
    Step 2: exp(i*(x2+0.6*x3)*Z⊗Z) diagonal coupling.
    Step 3: Hadamard on first qubit and RZ(0.7*x0*x1) on second.
    ALL operations are unitary; the 2-qubit pure state may be entangled.
    """
    if (len(features)!=4 or
            not all(isinstance(x,(int,float)) and math.isfinite(x) for x in features)):
        raise ValueError("Invalid normalized features")
    f0,f1,f2,f3=features
    th0=1.8*f0+math.pi/2
    th1=1.5*f1+math.pi/2
    a,b=math.cos(th0/2),math.sin(th0/2)
    c,d=math.cos(th1/2),math.sin(th1/2)
    psi=[complex(a*c),complex(a*d),complex(b*c),complex(b*d)]
    phase=1.3*f2+.6*f3
    psi=[z*cmath.exp(1j*phase*(1 if k in (0,3) else -1))
         for k,z in enumerate(psi)]
    h=1/math.sqrt(2)
    # Hadamard on MSB.
    psi=[(psi[0]+psi[2])*h,(psi[1]+psi[3])*h,
         (psi[0]-psi[2])*h,(psi[1]-psi[3])*h]
    rz=.7*f0*f1
    psi=[z*cmath.exp(1j*rz*(1 if k%2==0 else -1))
         for k,z in enumerate(psi)]
    if abs(norm2(psi)-1)>1e-9:
        raise ArithmeticError("Unitary embedding is not normalized")
    return tuple(psi)


def fidelity(a,b):
    if len(a)!=4 or len(b)!=4:
        raise ValueError("Expected two-qubit states")
    v=sum(u.conjugate()*w for u,w in zip(a,b))
    return max(0.,min(1.,abs(v)**2))


def rbfsim(a,b):
    if len(a)!=4 or len(b)!=4:raise ValueError("Invalid classical features")
    return math.exp(-.8*sum((x-y)**2 for x,y in zip(a,b)))


def precompute(bars):
    validate_frozen(bars)
    close=[float(b["close"]) for b in bars]
    e24=ema_series(close,24)
    e96=ema_series(close,96)
    data=[]
    for i in range(WARMUP,len(bars)-1,STEP):
        atr=atr_simple(bars,i,14)
        v=atr/close[i]
        if not .0012<=v<=.05:continue
        moment=math.log(close[i]/close[i-12])/max(v*math.sqrt(12),1e-8)
        slow=math.log(close[i]/close[i-48])/max(v*math.sqrt(48),1e-8)
        pressure=statistics.mean((b["close"]-b["open"])/max(
            b["high"]-b["low"],1e-9) for b in bars[i-7:i+1])
        rsi=rsi_simple(close,i)
        trend=(1 if e24[i]>e96[i]+.3*atr and moment>0
               else -1 if e24[i]<e96[i]-.3*atr and moment<0 else 0)
        reversion=(1 if rsi<=34 and moment<0
                   else -1 if rsi>=66 and moment>0 else 0)
        for family,side in (("trend",trend),("reversion",reversion)):
            if not side:continue
            feat=(math.tanh(side*moment),math.tanh(side*slow),
                  math.tanh(side*pressure*2),math.tanh(v*45-1))
            data.append((i,family,side,atr,feat,qmap(feat)))
    return sorted(data,key=lambda item:item[0])


def stressed_label(bars,c):
    """Forward realization ONLY on fit-period training observations.

    The label uses i+1..i+24; caller guarantees i+HOLD_BARS < fit_end.
    Directly models a 1x-notional net-return fraction with stress costs.
    The *final* performance evaluation uses the common portfolio simulator.
    """
    i,family,side,atr,feature,state=c
    j=i+1
    if j+HOLD_BARS>len(bars):
        raise ValueError("Insufficient known outcome")
    entry=bars[j]["open"]*(1+side*STRESS_SLIPPAGE)
    stop=entry-side*STOP_ATR*atr
    target=entry+side*TARGET_ATR*atr
    if min(stop,target)<=0:raise ValueError("Invalid stop/target")
    end=min(j+HOLD_BARS-1,len(bars)-1)
    raw=bars[end]["close"]
    for k in range(j,end+1):
        row=bars[k]
        if side>0:
            if row["open"]<=stop:raw=row["open"];end=k;break
            if row["low"]<=stop:raw=stop;end=k;break
            if row["high"]>=target:raw=target;end=k;break
        else:
            if row["open"]>=stop:raw=row["open"];end=k;break
            if row["high"]>=stop:raw=stop;end=k;break
            if row["low"]<=target:raw=target;end=k;break
    exit_fill=raw*(1-side*STRESS_SLIPPAGE)
    net=side*(exit_fill-entry)/entry
    net-=STRESS_FEE*(1+exit_fill/entry)
    net-=FUNDING_PER_8H*(end-j+1)/32
    return max(-1.,net)


def calibration_group(bars,candidates,fit_end,family):
    train=[c for c in candidates if c[1]==family and
           c[0]+HOLD_BARS+1 < fit_end]
    if len(train)>MAX_CALIBRATION:
        step=len(train)/MAX_CALIBRATION
        train=[train[int(n*step)] for n in range(MAX_CALIBRATION)]
    return [(x[4],x[5],stressed_label(bars,x)) for x in train]


def estimate(candidate,group,*,quantum):
    """Kernel weighted 1-sided statistical lower bound from TRAINING ONLY.

    This is a heuristic conditional utility bound, NOT a calibrated 95% CI.
    Confidence multiplier, effective N and floor are frozen before seeing
    any new market history. No market data after the fit split is used.
    """
    if len(group)<FIT_MIN:return (False,None,0)
    feat,state=candidate[4],candidate[5]
    scores=[]
    labels=[]
    for train_feat,train_state,net in group:
        w=(fidelity(state,train_state) if quantum
           else rbfsim(feat,train_feat))
        scores.append(w)
        labels.append(net)
    total=sum(scores)
    total2=sum(w*w for w in scores)
    if total<1e-12 or total2<=0:return (False,None,0)
    effective=total*total/total2
    if effective<EFFECTIVE_NEIGHBORS_MIN:return (False,None,effective)
    mean=sum(w*v for w,v in zip(scores,labels))/total
    variance=sum(w*(v-mean)**2 for w,v in zip(scores,labels))/total
    lower=mean-CONFIDENCE_SIGMA*math.sqrt(max(variance,0.)/effective)
    return (lower>EDGE_FLOOR,lower,effective)


def signals_for_market(bars):
    data=precompute(bars)
    fit_end=int(len(bars)*FIT_FRAC)
    groups={family:calibration_group(bars,data,fit_end,family)
            for family in ("trend","reversion")}
    output={name:[] for name in POLICIES}
    audits={"fit_end_bar":fit_end,
            "training_label_samples":{k:len(v) for k,v in groups.items()},
            "accepted_count":{k:0 for k in POLICIES},
            "rejected":0}
    for c in data:
        i,family,side,atr,features,state=c
        if i<fit_end:continue
        output["unfiltered_"+family].append((i,side,atr))
        for quantum,name in ((True,"quantum_kernel_"+family),
                              (False,"classical_rbf_"+family)):
            allowed,lower,eff=estimate(c,groups[family],quantum=quantum)
            if allowed:
                output[name].append((i,side,atr))
                audits["accepted_count"][name]+=1
            else:audits["rejected"]+=1
    return output,audits


def metrics(bars,rows,a,b):
    norm=trade_simulation(bars,rows,start_index=a,end_index=b)
    stress=trade_simulation(bars,rows,start_index=a,end_index=b,
                            fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
    daily={}
    for trade in norm["trade_log"]:
        day=trade["exit_ts"]//86_400_000
        daily[day]=daily.get(day,0.)+float(trade["net_usd"])
    return {
        "trades":norm["trades"],"net_pct":norm["return_pct"],
        "stress_net_pct":stress["return_pct"],
        "win_rate_pct":norm["win_rate_pct"],
        "drawdown_pct":norm["max_drawdown_pct"],
        "positive_exit_days":sum(v>0 for v in daily.values()),
        "negative_exit_days":sum(v<0 for v in daily.values()),
        "total_fees_usdt":norm["fees_usd"]
    }


def _mean_summary(market,name,period):
    values=[market[s]["policies"][name][period] for s in SYMBOLS]
    return {
        "trades":sum(v["trades"] for v in values),
        "mean_net_pct":round(statistics.mean(v["net_pct"] for v in values),5),
        "mean_stress_net_pct":round(statistics.mean(
            v["stress_net_pct"] for v in values),5),
        "positive_markets":sum(v["net_pct"]>0 for v in values),
        "positive_exit_days":sum(v["positive_exit_days"] for v in values),
        "negative_exit_days":sum(v["negative_exit_days"] for v in values),
        "max_market_drawdown_pct":max(v["drawdown_pct"] for v in values)
    }


def evaluate(markets,specs,*,hashes=None,at_ms=None):
    if set(markets)!=set(SYMBOLS):
        raise ValueError("Incomplete precommitted six-market group")
    result={}
    for symbol,bars in markets.items():
        validate_frozen(bars)
        if len(bars)<MIN_BARS:raise ValueError("Insufficient complete 15m history")
        signals,diagnostics=signals_for_market(bars)
        n=len(bars)
        fit=int(n*FIT_FRAC)
        validation=int(n*(FIT_FRAC+VALIDATION_FRAC))
        middle=validation+(n-validation)//2
        windows={"validation":(fit,validation),
                 "holdout_1":(validation,middle),
                 "holdout_2":(middle,n)}
        result[symbol]={
            "bars":len(bars),"training":diagnostics,
            "public_contract_viability_on_4_15_budget":
                capital_feasibility(symbol,bars,specs.get(symbol)),
            "policies":{
                name:{period:metrics(bars,rows,*bounds)
                      for period,bounds in windows.items()}
                for name,rows in signals.items()
            }
        }
    scores={name:{part:_mean_summary(result,name,part)
                  for part in ("validation","holdout_1","holdout_2")}
            for name in POLICIES}
    eligible=[]
    for name in POLICIES:
        v=scores[name]["validation"]
        if (v["trades"]>=MIN_VALIDATION_TRADES and
            v["mean_net_pct"]>0 and v["mean_stress_net_pct"]>0
            and v["positive_markets"]>=MIN_VALIDATION_POSITIVE_MARKETS
            and v["positive_exit_days"]>=9):
            eligible.append(name)
    winner=(max(eligible,key=lambda name:scores[name]["validation"][
        "mean_stress_net_pct"]) if eligible else None)
    reasons=[]
    if winner is None:
        reasons.append("NO_POSITIVE_MULTIMARKET_VALIDATION_EDGE")
    else:
        h1,h2=scores[winner]["holdout_1"],scores[winner]["holdout_2"]
        if h1["trades"]+h2["trades"]<MIN_TEST_TRADES:
            reasons.append("TOO_FEW_HOLDOUT_TRADES")
        for name,x in (("H1",h1),("H2",h2)):
            if (x["mean_net_pct"]<=0 or x["mean_stress_net_pct"]<=0 or
                x["positive_exit_days"]<MIN_TEST_POSITIVE_DAYS):
                reasons.append(name+"_DOES_NOT_REPEAT_NET_PROFIT")
        markets_positive=sum(
            result[s]["policies"][winner]["holdout_1"]["net_pct"]+
            result[s]["policies"][winner]["holdout_2"]["net_pct"]>0
            for s in SYMBOLS)
        if markets_positive<MIN_TEST_POSITIVE_MARKETS:
            reasons.append("LESS_THAN_FOUR_POSITIVE_OUT_OF_SIX_MARKETS")
    possible=sum(
        result[s]["public_contract_viability_on_4_15_budget"].get(
            "can_place_guarded_min_lot",False) for s in SYMBOLS)
    if possible==0:reasons.append("PUBLIC_MIN_ORDER_TOO_LARGE_FOR_4_15")
    return {
        "experiment":"TITAN_QKEL_NEW_TWO_QUBIT_CONDITIONAL_UTILITY_NO_ORDERS",
        "quantum_hardware":False,
        "method":"Classically simulated 2-qubit entangled feature map, fidelity vs RBF; train-only stressed net payoff calibration",
        "source":"OKX public 15m historical candles",
        "precommitted_markets":list(SYMBOLS),
        "lookback_days":DAYS,"bar_count":sum(len(x) for x in markets.values()),
        "hashes":hashes or {},
        "retrieved_at_utc":datetime.fromtimestamp(
            at_ms/1000,timezone.utc).isoformat() if at_ms else None,
        "fit_fraction":FIT_FRAC,"validation_fraction":VALIDATION_FRAC,
        "holdout_halves":2,"selected_on_validation_only":winner,
        "eligible_validation_policies":eligible,
        "theoretical_small_account_contract_count":possible,
        "reference_user_balance_usdt_not_read":4.15,
        "reference_target_balance_usdt_not_read":8.30,
        "simulation_start_equity_per_symbol_usdt":START_EQUITY,
        "zero_trade_baseline_pct":0.,
        "no_private_apis":True,"no_orders":True,
        "result":("HISTORICAL_ONLY_FUTURE_PROOF_REQUIRED"
                  if not reasons else "NO_TRADE_NO_REPEATED_PROVEN_NET_EDGE"),
        "rejection_reasons":reasons,
        "aggregates":scores,"per_market":result,
        "limitations":[
            "2-qubit circuit is a classical simulation; no computational quantum advantage",
            "Conditional payoff confidence bound is a heuristic, not an empirically calibrated probability",
            "Separate accounts are each 1000 USDT, not an actual 4.15 USDT futures account",
            "No historical orderbook, exact funding settlement or mark-price liquidation modeling",
            "OHLC stop-first model and indicative costs cannot establish actual executable PnL",
            "This study is not permission to enable real trading"
        ]
    }


def public_specs(symbol):
    if symbol not in SYMBOLS:raise ValueError("Unexpected market")
    url="https://www.okx.com/api/v5/public/instruments?"+urlencode(
        {"instType":"SWAP","instId":symbol})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-QKEL/1.0"}),
                 timeout=20) as handle:
        raw=json.load(handle)
    items=raw.get("data",[])
    if raw.get("code")!="0" or len(items)!=1:
        raise ValueError("Cannot verify public swap minimum")
    item=items[0]
    if item.get("instId")!=symbol or item.get("ctType")!="linear":
        raise ValueError("Not a supported linear swap")
    return {k:item.get(k) for k in
            ("instId","ctVal","ctValCcy","lotSz","minSz","state","ctType")}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",default="reports/titan_qkel_60d.json")
    parser.add_argument("--raw-dir",default="reports/titan_qkel_60d_raw")
    args=parser.parse_args(argv)
    now=int(time.time()*1000)
    out=Path(args.out);raw=Path(args.raw_dir)
    out.parent.mkdir(parents=True,exist_ok=True)
    raw.mkdir(parents=True,exist_ok=True)
    markets={};hashes={};specs={}
    for symbol in SYMBOLS:
        print("QKEL PUBLIC OKX 60D",symbol,flush=True)
        bars=fetch_history(symbol,DAYS,now_ms=now)
        if len(bars)<MIN_BARS:
            raise ValueError("Unverified/incomplete 60-day history for "+symbol)
        snapshot=json.dumps(bars,separators=(",",":")).encode()
        hashes[symbol]=hashlib.sha256(snapshot).hexdigest()
        with gzip.open(raw/(symbol+".json.gz"),"wb",compresslevel=6) as fd:
            fd.write(snapshot)
        markets[symbol]=bars
        try:specs[symbol]=public_specs(symbol)
        except (OSError,ValueError,TimeoutError) as exc:
            specs[symbol]={"instId":symbol,"error_type":type(exc).__name__}
        print("QKEL REAL BARS",symbol,len(bars),"sha256",hashes[symbol],
              "minSz",specs[symbol].get("minSz","UNAVAILABLE"),flush=True)
    result=evaluate(markets,specs,hashes=hashes,at_ms=now)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",
                   encoding="utf-8")
    for name in POLICIES:
        print("QKEL NET",name,
              "VALIDATION",result["aggregates"][name]["validation"],
              "H1",result["aggregates"][name]["holdout_1"],
              "H2",result["aggregates"][name]["holdout_2"],flush=True)
    print("QKEL FINAL",result["result"],
          "VALIDATION_WINNER",result["selected_on_validation_only"],
          "PUBLIC_MIN_LOT_FITS",result["theoretical_small_account_contract_count"],
          "NO ORDERS",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())

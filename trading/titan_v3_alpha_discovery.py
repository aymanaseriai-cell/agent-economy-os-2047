#!/usr/bin/env python3
"""TITAN V3 ALPHA DISCOVERY ENGINE: economically motivated testable signals.

The core is NOT a basket of renamed TA indicators. We study event-defined
risk transfer, relative shocks, trade-volume absorption, crash aftershocks,
and volatility dislocations. A hypothesis is only eligible if its
TRAIN-frozen slope/threshold survives withheld DEVELOPMENT after-cost
block-signflip with Holm correction. FINAL may never tune anything.
All OHLCV genuine; no L2/orderflow, causal identification or QPU claims.
"""
from __future__ import annotations
import hashlib,itertools,math,random,statistics
from collections import defaultdict

VERSION="TITAN-V3-ALPHA-20261117-CODE-FROZEN-01"
SEED=25000003
BASE_COST_LOG=.0026
ALPHA=.10
HYPOTHESES=(
    "cross_market_spillover",
    "residual_mean_reversion",
    "crash_aftershock",
    "volume_absorption",
    "volatility_repricing",
    "breakout_failure",
    "cross_sectional_dispersion",
    "price_volume_decoupling",
)
BASELINES=("simple_momentum","always_flat")
ALL=HYPOTHESES+BASELINES

def quantile(v,p):
    if not v or not 0<=p<=1:raise ValueError("Empty train or bad quantile")
    a=sorted(v);return a[min(len(a)-1,max(0,math.ceil(p*len(a))-1))]

def ema(vals,n):
    out=[vals[0]];alpha=2/(n+1)
    for x in vals[1:]:out.append(out[-1]+alpha*(x-out[-1]))
    return out

def _bar_4h(rows):
    """Completed UTC-anchored four-hour candles from true 15m exchange OHLCV."""
    result=[];group=[];bar_ms=900000
    for i,r in enumerate(rows):
        if r["ts"]%(16*bar_ms)==0:group=[]
        group.append((i,r))
        if len(group)==16 and group[0][1]["ts"]%(16*bar_ms)==0:
            result.append({
                "i":i,"ts":group[0][1]["ts"],"open":group[0][1]["open"],
                "close":group[-1][1]["close"],
                "high":max(v["high"] for _,v in group),
                "low":min(v["low"] for _,v in group),
                "vol":sum(v["vol_quote"] for _,v in group),
            })
            group=[]
    return result

def observations(markets):
    """Returns one row per 4h-close and market incl *future label* for TRAIN.

    Caller MUST filter labels by chronological end boundary before fitting.
    Signals NEVER read the returned future_y except inside the fitting gate.
    """
    if len(markets)<6:raise ValueError("At least six real correlated assets required")
    four={s:_bar_4h(v) for s,v in markets.items()}
    n=min(len(v) for v in four.values())
    clock=[v["ts"] for v in next(iter(four.values()))[:n]]
    if any([x["ts"] for x in f[:n]]!=clock for f in four.values()):
        raise ValueError("Cross-symbol 4h synchronization failure")
    rows=[]
    for t in range(75,n-1):
        logreturns={s:math.log(v[t]["close"]/v[t-1]["close"])
                    for s,v in four.items()}
        oldreturns={s:math.log(v[t-1]["close"]/v[t-2]["close"])
                    for s,v in four.items()}
        marketmean=statistics.mean(logreturns.values())
        oldmean=statistics.mean(oldreturns.values())
        marketshock=abs(oldmean)/(1e-6+statistics.pstdev(list(oldreturns.values())))
        dispersion=statistics.pstdev(logreturns.values())+1e-6
        for sym in sorted(four):
            v=four[sym]
            b=v[t];last=v[t-1]
            current=logreturns[sym]
            prev=oldreturns[sym]
            sigma=statistics.pstdev([
                math.log(v[k]["close"]/v[k-1]["close"])
                for k in range(t-48,t)])+1e-6
            own_vol=statistics.mean(x["vol"] for x in v[t-30:t])
            volratio=math.log((b["vol"]+1)/(own_vol+1))
            atr=statistics.mean(max(v[k]["high"]-v[k]["low"],
                          abs(v[k]["high"]-v[k-1]["close"]),
                          abs(v[k]["low"]-v[k-1]["close"]))
                          for k in range(t-14,t+1))
            close_gap=(b["close"]-b["open"])/max(atr,1e-9)
            wick=1-abs(b["close"]-b["open"])/max(b["high"]-b["low"],1e-9)
            range_ratio=(b["high"]-b["low"])/max(atr,1e-8)
            hi=max(x["high"] for x in v[t-24:t])
            lo=min(x["low"] for x in v[t-24:t])
            breakout=(1. if b["close"]>hi else
                      -1. if b["close"]<lo else 0.)
            failed_break=(-math.copysign(1,last["close"]-last["open"])
                           if last["high"]>max(x["high"] for x in v[t-24:t-1])
                           and b["close"]<last["open"] else 0.)
            z={
               # A delayed leader→follower economic hypothesis. No current/future cross-asset labels.
               "cross_market_spillover":oldmean/sigma,
               # Weak mean reversion of the coin around the contemporaneous basket.
               "residual_mean_reversion":(marketmean-current)/sigma,
               # Jump/price shock followed by aftershock or overshoot.
               "crash_aftershock":-math.copysign(max(0.,abs(prev)/sigma-1.8),prev),
               # Volume trapped in candle wicks suggests passive absorption.
               "volume_absorption":-close_gap*max(0.,volratio)*max(0.,wick),
               # High realized range may foreshadow volatility regime repricing.
               "volatility_repricing":-close_gap*max(0.,range_ratio-1.5),
               # Failed tests of 24 completed-bar range.
               "breakout_failure":failed_break,
               # Cross-sectional relative reversal under large dispersion.
               "cross_sectional_dispersion":(marketmean-current)/dispersion if dispersion>.0001 else 0.,
               # Price volume divergence: high turnover but little net motion.
               "price_volume_decoupling":-(current/sigma)*max(0.,volratio)*max(0.,wick-.5),
               "simple_momentum":current/sigma,
               "always_flat":0.,
            }
            z={k:max(-4.,min(4.,float(x))) for k,x in z.items()}
            nextbar=v[t+1]
            label=math.log(nextbar["close"]/nextbar["open"])
            rows.append({"sym":sym,"ts":b["ts"],"i":b["i"],
                         "future_idx":nextbar["i"],"future_y":label,
                         "atr":atr,"price":b["close"],"sigma":sigma,
                         "features":z,"volume_quote":b["vol"],
                         "marketshock":marketshock,"regime_vol":range_ratio})
    return rows

def _week_signflip_p(weekly,seed=SEED):
    # Exact sign enumeration at <=14 week observations; Monte Carlo otherwise.
    vals=list(weekly.values())
    if len(vals)<5:return 1.
    s=sum(vals);k=len(vals)
    if k<=14:
        outcomes=2**k
        extreme=0
        for signs in itertools.product((-1,1),repeat=k):
            extreme+=sum(signs[j]*vals[j] for j in range(k))>=s-1e-14
        return max(1/outcomes,extreme/outcomes)
    rng=random.Random(seed);hits=0;draws=4095
    for _ in range(draws):
        if sum(v*(1 if rng.randrange(2) else -1) for v in vals)>=s-1e-14:
            hits+=1
    return (hits+1)/(draws+1)

def holm(p):
    ordered=sorted(p,key=lambda k:(p[k],k));adj={}
    running=0.
    for j,name in enumerate(ordered):
        running=max(running,min(1.,p[name]*(len(ordered)-j)))
        adj[name]=running
    return adj

def frozen_discovery(samples,train_end,dev_lo,dev_hi):
    """Train-only slope/score-activation; dev-only falsification; never reads final y."""
    train=[x for x in samples if x["future_idx"]+32<train_end]
    dev=[x for x in samples if dev_lo<=x["i"] and x["future_idx"]+32<dev_hi]
    if len(train)<500 or len(dev)<200:
        raise ValueError("Insufficient causally separated training/development observations")
    fitted={};unadjusted={};dev_stats={}
    for h in HYPOTHESES+("simple_momentum",):
        usable=[x for x in train if abs(x["features"][h])>.01]
        if len(usable)<30:
            fitted[h]={"beta":0.,"threshold":4.,"sigma":1.,"n":len(usable)}
            unadjusted[h]=1.;dev_stats[h]={"events":0,"direction_hit":None,
                                           "net_proxy":0.,"weeks":0}
            continue
        xs=[x["features"][h] for x in usable]
        ys=[x["future_y"] for x in usable]
        # Ridge stabilizes tiny wins; no retrospective hyperparam tuning.
        beta=sum(a*b for a,b in zip(xs,ys))/(25.+sum(a*a for a in xs))
        sigma=max(.001,statistics.pstdev(ys))
        threshold=quantile([abs(x) for x in xs],.70)
        fitted[h]={"beta":beta,"threshold":threshold,"sigma":sigma,"n":len(usable)}
        eligible=[x for x in dev if abs(x["features"][h])>=max(.01,threshold)
                  and x["i"]%(96)<16] # at most one candidate per symbol/day
        weeks=defaultdict(float)
        hits=0;gain=0.
        for x in eligible:
            sgn=1 if beta*x["features"][h]>0 else -1
            profit=sgn*x["future_y"]-BASE_COST_LOG
            gain+=profit;weeks[x["ts"]//(7*86400000)]+=profit
            hits+=(sgn*x["future_y"])>0
        unadjusted[h]=_week_signflip_p(weeks)
        dev_stats[h]={"events":len(eligible),
                      "direction_hit":hits/len(eligible) if eligible else None,
                      "net_proxy":gain,"weeks":len(weeks),
                      "train_abs_predictive_beta":abs(beta)}
    adjusted=holm(unadjusted)
    for h,row in fitted.items():
        row["adjusted_p"]=adjusted[h]
        row["development_events"]=dev_stats[h]["events"]
        row["development_net_proxy"]=dev_stats[h]["net_proxy"]
        row["development_direction_accuracy"]=dev_stats[h]["direction_hit"]
        row["development_weeks"]=dev_stats[h]["weeks"]
        row["screen_eligible"]=(h!="simple_momentum" and
            row["adjusted_p"]<=ALPHA and
            row["development_events"]>=12 and
            row["development_net_proxy"]>0 and
            row["development_weeks"]>=6 and
            abs(row["beta"])*row["threshold"]>=BASE_COST_LOG*.6)
    fitted["always_flat"]={"beta":0.,"threshold":float("inf"),
                           "screen_eligible":True,"adjusted_p":1.}
    return {"fit":fitted,"unadjusted_week_signflip_p":unadjusted,
            "holm_adjusted_p":adjusted,
            "train_obs":len(train),"development_obs":len(dev),
            "family_count_with_baselines":len(ALL),
            "economic_screen_passed":[h for h in HYPOTHESES
                                      if fitted[h]["screen_eligible"]],
            "research_attempts_count":len(HYPOTHESES),
            "limitations":[
                "Development weekly returns are correlated within symbols and markets",
                "Holm correction covers 9 named family tests in THIS study, not all prior studies",
                "Daily candidate sampling and future 4h close use development labels only",
                "Candle volume is true OKX quote volume; not L2 order-flow imbalance",
                "Cross-market association is not causal identification",
            ]}

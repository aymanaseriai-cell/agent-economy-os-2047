#!/usr/bin/env python3
"""TITAN Omega24: causal Hamiltonian research, OKX PUBLIC data, NO ORDERS.

Historical 2026 calendar has been seen by prior TITAN studies; chronological
holdout here is a diagnostic, NOT a fresh independent prospective sample.
"""
from __future__ import annotations
import argparse
import cmath
import json
import math
from pathlib import Path
from statistics import median, pstdev
from trading import titan_omega_infinite12 as old
from trading import titan_omega_infinite12_models as previous

START, TARGET, N, WARM = 4.15, 8.30, 96, 33
SYMBOLS = old.SYMBOLS
COSTS = old.COSTS
MODELS = ("causal_hamiltonian_phasewalk", "fisher_bayes_regime", "classical_momentum")
VERSION = "TITAN-OMEGA24-CAUSAL-HAMILTONIAN-20261117-V1"


def _history(bars, i):
    if i < 32 or i >= len(bars):
        raise ValueError("At least 33 completed causal candles required")
    close = [float(bars[j]["close"]) for j in range(i-32, i+1)]
    if min(close) <= 0 or not all(math.isfinite(x) for x in close):
        raise ValueError("Invalid causal closes")
    return [math.log(b/a) for a,b in zip(close, close[1:])]


def _js(p, q):
    m = [(a+b)/2 for a,b in zip(p,q)]
    return .5*sum(a*math.log(a/c)+b*math.log(b/c) for a,b,c in zip(p,q,m))


def _prob(x, vol):
    counts = [1.,1.,1.]  # Dirichlet prior, causal empirical regime
    for z in x:
        counts[0 if z < -.25*vol else (2 if z > .25*vol else 1)] += 1.
    s = sum(counts)
    return [c/s for c in counts]


def causal_hamiltonian_phasewalk(bars, i):
    """Two-state SU(2) Hamiltonian evolution with spectral and JS regime gate.

    H = [[m,kappa],[kappa,-m]], U=cos(omega*tau)I-i*sin(omega*tau)H/omega;
    an entirely classical CPU calculation, not quantum hardware.
    """
    r = _history(bars,i)
    vol = max(.0001,pstdev(r))
    momentum = math.tanh(sum(r[-8:])/(vol*math.sqrt(8)))
    a,b = _prob(r[:16],vol),_prob(r[16:],vol)
    js = _js(a,b)
    spectral = sum(v*math.cos(2*math.pi*k/16) for k,v in enumerate(r[-16:]))/(16*vol)
    kappa = .28 + .16*math.tanh(spectral)
    p = min(.95,max(.05,.5+.38*momentum))
    x,y = complex(math.sqrt(p)),complex(0,math.sqrt(1-p))
    omega = math.hypot(momentum,kappa)
    tau = .75 + .3*math.tanh(sum(r[-4:])/(4*vol))
    c,s = math.cos(omega*tau),math.sin(omega*tau)/omega
    nx = c*x-1j*s*(momentum*x+kappa*y)
    ny = c*y-1j*s*(kappa*x-momentum*y)
    norm = abs(nx)**2 + abs(ny)**2
    if abs(norm-1)>1e-9:
        raise ArithmeticError("Hamiltonian walk violated unitarity")
    score = 2*abs(nx)**2 - 1 + .25*momentum - .3*js
    if js>.22 or abs(score)<.33:
        return 0
    return 1 if score>0 else -1


def fisher_bayes_regime(bars,i):
    """Dirichlet directional posterior, Fisher-scaled confidence, JS gate."""
    r = _history(bars,i)
    vol = max(.0001,pstdev(r))
    a,b = _prob(r[:16],vol),_prob(r[16:],vol)
    shift = _js(a,b)
    ups = sum(1 for v in r[-24:] if v>.25*vol)
    downs = sum(1 for v in r[-24:] if v<-.25*vol)
    n = ups+downs+2
    mu = (ups-downs)/n
    p = (ups+1)/n
    fisher_se = math.sqrt(max(1e-9,p*(1-p)/n))
    confidence = abs(mu)/(2*fisher_se)
    if shift>.16 or confidence<1.3 or abs(mu)<.13:
        return 0
    return 1 if mu>0 else -1


STRATEGIES = {
    "causal_hamiltonian_phasewalk": causal_hamiltonian_phasewalk,
    "fisher_bayes_regime": fisher_bayes_regime,
    "classical_momentum": previous.classical_momentum,
}


def simulate(bars, spec, funding, model, start, case):
    """96 disjoint 15-minute bars; equity changes ONLY on closed positions."""
    old.validate_bars(bars)
    if model not in STRATEGIES or case not in COSTS or start < WARM or start+N > len(bars):
        raise ValueError("Outside frozen experiment")
    finish = start+N
    eq, peak, max_dd, blocked, ledger = START,START,0.,0,[]
    sp = old.valid_spec(spec)
    if sp is None:
        return dict(model=model,cost=case,start_idx=start,end_idx=finish,
                    start_equity=START,end_equity=START,max_dd_pct=0.,
                    trades=[],blocked=N,liquidations=0,feasible=False,
                    status="UNVERIFIED_SPEC")
    cfg = COSTS[case]
    t = start
    while t < finish and eq > 0:
        side = STRATEGIES[model](bars,t-1)
        if side not in (-1,0,1):
            raise ValueError("Invalid causal signal")
        if not side:
            t+=1
            continue
        lev = old.leverage(bars,t-1,sp[3])
        entry = float(bars[t]["open"])*(1+side*cfg["spread_slip"])
        qty = old.contracts(eq,entry,float(bars[t-1]["quote"]),lev,sp)
        if qty<=0:
            blocked+=1
            t+=1
            continue
        notion = qty*sp[2]*entry
        margin = notion/lev
        if margin>eq*old.MARGIN_FRACTION*(1+1e-7):
            raise AssertionError("Margin exceeds 25% of closed equity")
        close_idx = min(t+old.HOLD_BARS,finish)-1
        exit_type="time"
        exit_ = float(bars[close_idx]["close"])
        liq_at=entry*(1-side*(1/lev-old.MMR_PROXY))
        stop_at=entry*(1-side*min(.02,.65/lev))
        for j in range(t,close_idx+1):
            bar=bars[j]
            liq = bar["low"]<=liq_at if side==1 else bar["high"]>=liq_at
            stp = bar["low"]<=stop_at if side==1 else bar["high"]>=stop_at
            if liq or stp:
                close_idx=j
                exit_type="liquidation_proxy" if liq else "stop"
                at=liq_at if liq else stop_at
                exit_=min(bar["open"],at) if side==1 else max(bar["open"],at)
                break
        exit_ *= (1-side*cfg["spread_slip"])
        gross=side*(exit_-entry)*qty*sp[2]
        fee=cfg["taker"]*qty*sp[2]*(entry+exit_)
        events=[f["rate"] for f in funding if bars[t]["ts"]<f["ts"]<=bars[close_idx]["ts"]+old.CANDLE_MS]
        if events:
            financing=notion*side*sum(events)
            source="observed_public_events"
        else:
            financing=notion*cfg["fund8h_proxy"]*((close_idx-t+1)*old.CANDLE_MS/28_800_000)
            source="conservative_proxy"
        regular_net=gross-fee-financing
        # Proxy liquidation forfeits at least isolated margin; not an actual OKX mark fill.
        net=min(regular_net,-margin-fee-financing) if exit_type=="liquidation_proxy" else regular_net
        after=max(0.,eq+net)
        ledger.append(dict(model=model,cost=case,side=side,entry_idx=t,exit_idx=close_idx,
                           signal_idx=t-1,entry=entry,exit=exit_,qty=qty,ct_val=sp[2],
                           min_sz=sp[0],lot_sz=sp[1],lev=lev,lev_cap=sp[3],
                           margin=margin,previous_quote=bars[t-1]["quote"],
                           equity_before=eq,gross=gross,fee=fee,financing=financing,
                           financing_source=source,net=net,equity_after=after,
                           exit_type=exit_type))
        eq=after
        peak=max(peak,eq)
        max_dd=max(max_dd,1-eq/peak)
        t=close_idx+1
    return dict(model=model,cost=case,start_idx=start,end_idx=finish,
                start_equity=START,end_equity=eq,max_dd_pct=100*max_dd,
                trades=ledger,blocked=blocked,liquidations=sum(t["exit_type"]=="liquidation_proxy" for t in ledger),
                feasible=True,status="HISTORICAL_DEVELOPMENT_ONLY")


def evaluate(raw):
    body={k:v for k,v in raw.items() if k!="seal_sha256"}
    if (raw.get("seal_sha256")!=old.digest(body) or raw.get("real_orders")!=0
            or raw.get("declared_symbols")!=list(SYMBOLS)):
        raise ValueError("Source integrity or paper-only contract invalid")
    windows=[]
    for symbol in SYMBOLS:
        data=raw["markets"][symbol]
        for key,obj in (("bar_sha256",data["bars"]),("spec_sha256",data["spec"]),
                        ("funding_sha256",data["funding"])):
            if data[key]!=old.digest(obj):
                raise ValueError("Original OKX source hash mismatch")
        bars=data["bars"]
        old.validate_bars(bars)
        starts=list(range(WARM,len(bars)-N+1,N))
        cutoff=max(1,int(.6*len(starts)))
        for num,start in enumerate(starts):
            fold="train" if num<cutoff else "chronological_holdout_consumed"
            for model in MODELS:
                for case in COSTS:
                    x=simulate(bars,data["spec"],data["funding"],model,start,case)
                    x.update(symbol=symbol,fold=fold,
                             start_ts=bars[start]["ts"],end_ts=bars[start+N-1]["ts"]+old.CANDLE_MS)
                    windows.append(x)
    if not windows:
        raise ValueError("No complete 24h windows")
    # Choose ONLY by development train stress; never use the held-out windows.
    metrics={}
    for model in MODELS:
        r=[x["end_equity"] for x in windows
           if x["fold"]=="train" and x["cost"]=="stress" and x["model"]==model]
        metrics[model]=sum(r)/len(r) if r else 0.
    choice=max(MODELS,key=lambda m:(metrics[m],-MODELS.index(m)))
    summary={}
    for fold in ("train","chronological_holdout_consumed"):
        for model in MODELS:
            for case in COSTS:
                subset=[x for x in windows if x["fold"]==fold and x["model"]==model and x["cost"]==case]
                if not subset:
                    continue
                equity=[x["end_equity"] for x in subset]
                key=fold+"/"+model+"/"+case
                summary[key]=dict(windows=len(subset),hits=sum(e>=TARGET for e in equity),
                    failures=sum(e<TARGET for e in equity),
                    fills=sum(len(x["trades"]) for x in subset),
                    liquidations=sum(x["liquidations"] for x in subset),
                    blocked=sum(x["blocked"] for x in subset),
                    median_net_pct=round(100*(median(equity)/START-1),6),
                    best_net_pct=round(100*(max(equity)/START-1),6),
                    max_dd_pct=round(max(x["max_dd_pct"] for x in subset),6))
    return dict(study=VERSION,source_seal=raw["seal_sha256"],
        scope="ALL_FIXED_DISJOINT_24H_CONSUMED_DEVELOPMENT_WINDOWS",
        start_usdt=START,target_usdt=TARGET,window_bars=N,
        leverage_range=[10,100],real_orders=0,quantum_hardware=False,
        fresh_independent_prospective=False,independent_hit_rate=None,
        selected_using_train_only=choice,training_stress_mean_equity=metrics,
        summary=summary,windows=windows,
        limitations=["Holdout historical dates already seen by prior research",
          "Historical instrument spec is CURRENT not point-in-time",
          "Intrabar OHLC stops/liquidations and spread are proxies",
          "Real mark-price liquidation tier, L2 depth and exact fees unavailable"])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    report=evaluate(json.loads(Path(args.input).read_text()))
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+"\n")
    print(json.dumps(dict(study=VERSION,selected=report["selected_using_train_only"],
          summary=report["summary"],no_real_orders=True,independent_verified=False)))


if __name__=="__main__":
    main()

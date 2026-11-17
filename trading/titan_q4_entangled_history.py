#!/usr/bin/env python3
"""TITAN Q4 entangled-regime historical research: genuine OKX OHLC, NO ORDERS.

A new four-qubit (16-amplitude) classical statevector quantum-inspired filter
with volatility/price-pressure features, inter-qubit phase entanglement and
phase-robust gating. Predeclared crypto basket + walk-forward train/3 holdouts.
Q4 math is NOT executed on physical quantum hardware; no profit guarantees.
"""
from __future__ import annotations
import argparse
import cmath
import gzip
import hashlib
import json
import math
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading import titan_quantum_survival_interferometer as qsi
from trading import titan128_breakout_blind as previous
from trading.edge_lab import (
    BAR_MS, TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE, STRESS_SLIPPAGE,
    atr_simple, ema_series, fetch_history,
)
from trading.titan_regime_research import validate_frozen

STUDY = "TITAN-Q4-ENTANGLED-REGIME-128-20261117-FROZEN-V1"
UNIVERSE = set(("AR AXS BLUR BONK CFX CHZ DYDX ETHFI FET FLOW GRT JTO KAS LPT "
                "MASK MINA PENGU RENDER RUNE STX WIF XTZ YGG ZIL 1INCH ZK TWT").split())
FORBIDDEN = set(("BTC ETH SOL XRP DOGE HYPE ZEC BNB").split())
MARKETS = 6
DAYS = 90
MIN_HISTORY = 8450
START = 4.15
TARGET = 9.462
RUIN = 0.83
LEVERAGES = (3., 10.)
PHASES = (0.7, 1.0, 1.3)
SIGNAL_CUTOFF = .62
POLICIES = (
    "q4_phase_interference", "q4_phase_robust", "q4_trend_regime",
    "q4_countertrend", "q4_compressed_breakout", "q4_zero_phase",
    "classical_same_features", "classical_breakout",
)
QUANTUM_POLICIES = tuple(k for k in POLICIES if k.startswith("q4_"))


def catalogue():
    with urlopen(Request("https://www.okx.com/api/v5/public/instruments?" +
                         urlencode({"instType": "SWAP"}),
                         headers={"User-Agent": "TITAN-Q4-RESEARCH-NO-ORDERS"}),
                 timeout=35) as conn:
        data = json.load(conn)
    if data.get("code") != "0":
        raise ValueError("Unverified public swap catalogue")
    cutoff = int(time.time()*1000) - 120*86400000
    eligible = []
    for s in data.get("data", []):
        symbol = s.get("instId", "")
        if not symbol.endswith("-USDT-SWAP"):
            continue
        coin = symbol[:-10]
        if (coin not in UNIVERSE or coin in FORBIDDEN
            or s.get("state") != "live" or s.get("ctType") != "linear"
            or s.get("ctValCcy") != coin):
            continue
        try:
            if int(s["listTime"]) > cutoff:
                continue
            contract = [float(s[x]) for x in ("ctVal", "lotSz", "minSz")]
            if not all(math.isfinite(v) and v > 0 for v in contract):
                continue
        except (TypeError, KeyError, ValueError):
            continue
        eligible.append(s)
    # Selection decided by public identifiers and frozen study string, not PnL.
    eligible.sort(key=lambda s: hashlib.sha256(
        (STUDY + "|" + s["instId"]).encode()).hexdigest())
    if len(eligible) < MARKETS:
        raise ValueError("Insufficient previously frozen crypto-only market universe")
    return eligible[:MARKETS], len(eligible)


def _ry(state, bit, angle):
    out = list(state)
    m = 1 << bit
    c, s = math.cos(angle/2), math.sin(angle/2)
    for i in range(16):
        if i & m:
            continue
        a, b = state[i], state[i|m]
        out[i] = c*a - s*b
        out[i|m] = s*a + c*b
    return out


def _hadamard(state, bit):
    out = list(state)
    m = 1 << bit
    k = 1/math.sqrt(2)
    for i in range(16):
        if i & m:
            continue
        a, b = state[i], state[i|m]
        out[i] = k*(a+b)
        out[i|m] = k*(a-b)
    return out


def q4_born_probability(features, phase=1.0):
    """16 amplitudes, unitary RY + coupled ZZ phase + H + RY decoder."""
    if (len(features) != 4 or not all(math.isfinite(float(x)) for x in features)
        or not math.isfinite(phase) or not 0 <= phase <= 2):
        raise ValueError("Four finite causal features and bounded phase required")
    f = tuple(math.tanh(float(x)) for x in features)
    psi = [0j]*16
    psi[0] = 1+0j
    for bit in range(4):
        psi = _ry(psi, bit, 1.5*f[bit])
    for i in range(16):
        z = tuple(1 if i&(1<<k) else -1 for k in range(4))
        couplings = (.43*z[0]*z[1] + .32*z[1]*z[2]
                     - .27*z[2]*z[3] + .23*z[3]*z[0])
        field = .19*sum(z[k]*f[k] for k in range(4))
        psi[i] *= cmath.exp(1j*phase*(couplings+field))
    for bit in range(4):
        psi = _hadamard(psi, bit)
    for bit in range(4):
        psi = _ry(psi, bit, .72*f[bit])
    for bit in (0, 2):
        psi = _hadamard(psi, bit)
    norm = sum(abs(x)**2 for x in psi)
    if abs(norm-1)>1e-9:
        raise ArithmeticError("Non-unitary four-qubit circuit")
    born = sum(abs(x)**2 for i,x in enumerate(psi) if i&8)
    if not 0 <= born <= 1+1e-9:
        raise ArithmeticError("Invalid Born distribution")
    return min(1., max(0.,born))


def classical_same_inputs(features):
    """Predeclared logistic comparator on precisely the same four features."""
    if len(features)!=4 or any(not math.isfinite(float(f)) for f in features):
        raise ValueError("Invalid inputs to classical control")
    score = (.75*math.tanh(features[0]) + .45*math.tanh(features[1])
             + .30*math.tanh(features[2]) - .25*math.tanh(features[3]))
    return 1/(1+math.exp(-score))


def completed_features(bars, i, fast, slow):
    """Only history <= i; no use of future candles, returns causal ATR."""
    if i < 120 or i >= len(bars):
        raise ValueError("Need 121 completed historical bars")
    closes = [float(x["close"]) for x in bars[i-120:i+1]]
    p = closes[-1]
    atr14 = atr_simple(bars,i,14)
    atr56 = atr_simple(bars,i,56)
    if p<=0 or not math.isfinite(atr14) or min(atr14,atr56)<=0:
        raise ValueError("Invalid ATR")
    volatility = atr14/p
    f0 = math.log(p/closes[-33]) / max(volatility*math.sqrt(32),1e-8)
    f1 = (p - slow[i])/max(atr14,1e-8)
    pressure = sum((bars[k]["close"]-bars[k]["open"])/
                   max(bars[k]["high"]-bars[k]["low"],1e-10)
                   for k in range(i-15,i+1))/16
    f2 = pressure*3
    f3 = math.log(atr14/atr56)*2
    f = tuple(max(-3.,min(3.,v)) for v in (f0,f1,f2,f3))
    return f, atr14, atr14/atr56


def direction(p):
    return 1 if p>=SIGNAL_CUTOFF else -1 if p<=1-SIGNAL_CUTOFF else 0


def signal_stream(bars):
    validate_frozen(bars)
    closes = [float(z["close"]) for z in bars]
    fast,slow = ema_series(closes,24),ema_series(closes,96)
    out = {name: [] for name in POLICIES}
    # Causality: no decision at last bar because entry must be i+1.
    for i in range(max(224,121),len(bars)-1,4):
        f,atr,ratio = completed_features(bars,i,fast,slow)
        if not .0012 <= atr/closes[i] <= .05:
            continue
        probs = tuple(q4_born_probability(f, p) for p in PHASES)
        p = probs[1]
        zero = q4_born_probability(f,0)
        classical = classical_same_inputs(f)
        qdir = direction(p)
        trend = 1 if fast[i]>slow[i] and closes[i]>closes[i-16] else (
                -1 if fast[i]<slow[i] and closes[i]<closes[i-16] else 0)
        def push(name,side,confidence):
            if side:
                out[name].append((i,side,atr,round(max(0,min(.5,confidence)),8)))
        push("q4_phase_interference",qdir,abs(p-.5))
        if min(probs)>=SIGNAL_CUTOFF:
            robust = 1
            strength = min(probs)-.5
        elif max(probs)<=1-SIGNAL_CUTOFF:
            robust = -1
            strength = .5-max(probs)
        else:
            robust=0
            strength=0
        push("q4_phase_robust",robust,strength)
        if robust and trend==robust:
            push("q4_trend_regime",robust,strength)
        if robust and abs(f[1])>=1.1 and f[1]*robust<0 and ratio<1.4:
            push("q4_countertrend",robust,strength)
        prev_hi = max(b["high"] for b in bars[i-24:i])
        prev_lo = min(b["low"] for b in bars[i-24:i])
        if ratio<.95 and ((robust>0 and closes[i]>prev_hi) or
                          (robust<0 and closes[i]<prev_lo)):
            push("q4_compressed_breakout",robust,strength)
        push("q4_zero_phase",direction(zero),abs(zero-.5))
        push("classical_same_features",direction(classical),abs(classical-.5))
    out["classical_breakout"]=previous.breakout_signals(bars)
    return out


def evaluate(markets,specs,hashes):
    if len(markets)!=MARKETS or set(markets)!=set(specs) or set(markets)!=set(hashes):
        raise ValueError("Need six predeclared market datasets and their hashes")
    if any(s[:-10] not in UNIVERSE for s in markets):
        raise ValueError("Non-predeclared market found")
    n=min(len(b) for b in markets.values())
    if n<MIN_HISTORY:
        raise ValueError("Incomplete 90-day market history")
    base=[x["ts"] for x in next(iter(markets.values()))[:n]]
    for b in markets.values():
        validate_frozen(b)
        if [x["ts"] for x in b[:n]]!=base:
            raise ValueError("Misaligned public OHLC")
    streams={s:signal_stream(b[:n]) for s,b in markets.items()}
    a=int(n*.40)
    b=int(n*.60)
    c=int(n*.80)
    spans={"train":(qsi.WARMUP,a),
           "holdout_1":(a,b),"holdout_2":(b,c),"holdout_3":(c,n),
           "unseen_combined":(a,n)}
    results={}
    for policy in POLICIES:
        votes={s:streams[s][policy] for s in markets}
        for lev in LEVERAGES:
            key=policy+"_"+str(int(lev))+"x"
            results[key]={}
            for span,(start,end) in spans.items():
                results[key][span]={}
                for label,fee,slip in (
                    ("ordinary",TAKER_FEE,BASE_SLIPPAGE),
                    ("stress",STRESS_FEE,STRESS_SLIPPAGE),
                ):
                    results[key][span][label]=previous.paper(
                        markets,specs,votes,leverage=lev,
                        start=start,end=end,fee=fee,slip=slip)
    candidates=[]
    for key,rows in results.items():
        if key.rsplit("_",1)[0] not in QUANTUM_POLICIES:
            continue
        norm=rows["train"]["ordinary"]
        stress=rows["train"]["stress"]
        if (stress["trades"]>=18
            and norm["return_pct"]>0 and stress["return_pct"]>0
            and stress["max_drawdown_pct"]<=35
            and not stress["ruin_at_closed_equity"]):
            candidates.append(key)
    winner=max(candidates,
               key=lambda k: results[k]["train"]["stress"]["return_pct"]
               ) if candidates else None
    holds=("holdout_1","holdout_2","holdout_3")
    repeated=bool(winner) and all(
        results[winner][p][cost]["reached128_on_closed_paper_trade"]
        and not results[winner][p][cost]["ruin_at_closed_equity"]
        for p in holds for cost in ("ordinary","stress"))
    combined=bool(winner) and all(
        results[winner]["unseen_combined"][cost]["reached128_on_closed_paper_trade"]
        and not results[winner]["unseen_combined"][cost]["ruin_at_closed_equity"]
        for cost in ("ordinary","stress"))
    all_rets=[(name,span,cost,row["return_pct"])
              for name,spec in results.items()
              for span,b in spec.items()
              for cost,row in b.items()]
    observed=max(all_rets,key=lambda k:k[3])
    hits=sum(results[k][h][cost]["reached128_on_closed_paper_trade"]
             for k in results for h in holds for cost in ("ordinary","stress"))
    return {
        "study":STUDY,"source":"REAL OKX public completed 15m crypto candles",
        "goal_return_pct":128,"start_usdt":START,"target_usdt":TARGET,
        "markets":sorted(markets),"market_sha256":hashes,"bars_per_market":n,
        "total_market_bars":n*MARKETS,"periods":spans,
        "models":list(results),"hypotheses_count":len(results),
        "train_only_candidates":candidates,
        "selected_on_train_only":winner,
        "selected_hit128_every_untouched_holdout_both_costs":bool(repeated),
        "selected_hit128_combined_unseen_both_costs":bool(combined),
        "retrospective_best_not_preselected":{
            "model":observed[0],"period":observed[1],
            "cost":observed[2],"return_pct":observed[3]},
        "posthoc_holdout_hits_not_proof":hits,
        "verdict":("PAPER_ONLY_REQUIRES_NEW_UNTOUCHED_DATA" if repeated and combined
                   else "NO_REPEATABLE_PLUS128_EDGE_VALIDATED"),
        "results":results,"real_orders":0,"physical_quantum_hardware":False,
        "caveats":[
            "Paper PnL only, not user's OKX account; no real money trades",
            "Fees, slippage, funding and liquidation are assumed or proxied",
            "Current public instrument specifications may differ from historical",
            "Repeated strategy experimentation incurs selection bias",
            "Quantum circuit is a classical simulation and cannot guarantee profit",
        ],
    }


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="reports/titan_q4_128_historical.json")
    ap.add_argument("--raw-dir",default="reports/titan_q4_128_history_raw")
    args=ap.parse_args(argv)
    basket,pool=catalogue()
    print("Q4 PREDECLARED UNIVERSE",pool,[x["instId"] for x in basket],flush=True)
    now=int(time.time()*1000)
    markets={};specs={};sha={}
    raw=Path(args.raw_dir)
    raw.mkdir(parents=True,exist_ok=True)
    for spec in basket:
        sym=spec["instId"]
        data=fetch_history(sym,DAYS,now_ms=now)
        if len(data)<MIN_HISTORY:
            raise ValueError("Incomplete public 90-day history "+sym)
        blob=json.dumps(data,separators=(",",":")).encode()
        dig=hashlib.sha256(blob).hexdigest()
        with gzip.open(raw/(sym+".json.gz"),"wb") as file:
            file.write(blob)
        sha[sym]=dig
        markets[sym]=data;specs[sym]=spec
        print("Q4 HISTORICAL MARKET SHA",sym,len(data),dig,flush=True)
    outcome=evaluate(markets,specs,sha)
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(outcome,sort_keys=True,indent=2)+"\n")
    for name,span in outcome["results"].items():
        print("Q4 SCORES",name,
              "TRAIN",span["train"]["stress"]["return_pct"],
              "H1",span["holdout_1"]["stress"]["return_pct"],
              "H2",span["holdout_2"]["stress"]["return_pct"],
              "H3",span["holdout_3"]["stress"]["return_pct"],
              "OOS",span["unseen_combined"]["stress"]["return_pct"],flush=True)
    print("Q4 VERDICT",outcome["verdict"],
          "SELECTED",outcome["selected_on_train_only"],
          "COMBINED128",outcome["selected_hit128_combined_unseen_both_costs"],
          "REPEATED128",outcome["selected_hit128_every_untouched_holdout_both_costs"],
          "POSTHOC_HITS",outcome["posthoc_holdout_hits_not_proof"],
          "NO ORDERS",flush=True)

if __name__=="__main__":
    main()

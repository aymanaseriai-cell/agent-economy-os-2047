#!/usr/bin/env python3
"""TITAN Omega Quantum Causal Walk (QCW) — original falsifiable hypothesis.

A *classically simulated* 2-coin x 9-site discrete-time unitary quantum walk
with causal market-return-dependent phase kicks. It tests whether constructive
interference carries predictive information AFTER realistic assumed fees.
Compare coherent phase kicks, a phase-free quantum ablation, a classical twin
using identical OHLC features, and a classical trade-frequency match selected
on TRAINING data only. Never uses real quantum hardware or exchanges orders.

All symbols/strategies/thresholds frozen in GitHub BEFORE public OKX data
fetch. Three chronological phases: train, historical holdout A and holdout B.
No guarantee of profit, no private user account access, no actual $4.15 fills.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
import random
import statistics
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

from trading.edge_lab import (
    BAR_MS,START_EQUITY,STRESS_FEE,STRESS_SLIPPAGE,
    ema_series,atr_simple,fetch_history,trade_simulation,
)
from trading.titan_regime_research import validate_frozen
from trading.titan_quantum_recurrence import capital_feasibility

# NEW 6-market group: did not appear among the first 30 researched symbols.
SYMBOLS=("PEPE-USDT-SWAP","SHIB-USDT-SWAP","TON-USDT-SWAP",
         "TIA-USDT-SWAP","SEI-USDT-SWAP","JUP-USDT-SWAP")
DAYS=75
TRAIN_SHARE=.60
WARMUP=300
MIN_BARS=7000
SCAN_STEP=4
WALK_SITES=9
WALK_STEPS=12
PHASE_SPREAD=.19
BASE_PHASE_MULTIPLIER=1.0
PREDICTION_THRESHOLD=.095
ROBUST_PREDICTION_THRESHOLD=.075
MAX_WALK_ENTROPY=.995
MIN_TRAIN_FILLS=50
MIN_HOLDOUT_FILLS=40
MIN_POSITIVE_MARKETS=4
MIN_POSITIVE_DAYS_PER_HOLDOUT=7
NAMES=("q_walk_coherent","q_walk_phase_robust",
       "q_walk_phase_free_ablation","classical_same_information",
       "classical_train_frequency_matched")
DAY_MS=86_400_000
SEED=8302047


def wavewalk(closes, i, atr_fraction, *, phase_multiplier=1.0):
    """A norm-preserving unitary coined quantum walk, simulated classically.

    The 2D quantum coin is Hadamard, phases are unitary diagonal operators,
    and conditional modulo-9 shift is a permutation; their product is unitary.
    Initial coin amplitudes encode the same completed price momentum used by
    the classical model. Return a measurable coin imbalance and site entropy.

    NO future input: all observed returns end at i, the completed candle.
    """
    if (not isinstance(i,int) or i<32 or i>=len(closes)
            or not math.isfinite(atr_fraction) or atr_fraction<=0
            or not math.isfinite(phase_multiplier) or
            not 0<=phase_multiplier<=2):
        raise ValueError("Invalid quantum walk inputs")
    momentum=math.log(closes[i]/closes[i-12])/max(atr_fraction*math.sqrt(12),1e-12)
    p_right=.5+.24*math.tanh(momentum)
    right=[0j]*WALK_SITES
    left=[0j]*WALK_SITES
    right[WALK_SITES//2]=complex(math.sqrt(p_right))
    left[WALK_SITES//2]=complex(math.sqrt(1-p_right))
    invsqrt=1/math.sqrt(2)
    for k in range(i-WALK_STEPS+1,i+1):
        step_ret=math.log(closes[k]/closes[k-1])
        scaled=max(-1.8,min(1.8,step_ret/atr_fraction))
        new_right=[0j]*WALK_SITES
        new_left=[0j]*WALK_SITES
        for site in range(WALK_SITES):
            phi=phase_multiplier*scaled*(.45+PHASE_SPREAD*(site-WALK_SITES//2))
            rot=complex(math.cos(phi),math.sin(phi))
            a=right[site]*rot
            b=left[site]*rot.conjugate()
            # Hadamard coin, then the conditional 1-site shift.
            new_right[(site+1)%WALK_SITES]+=(a+b)*invsqrt
            new_left[(site-1)%WALK_SITES]+=(a-b)*invsqrt
        right,left=new_right,new_left
    pr=sum(abs(z)**2 for z in right)
    pl=sum(abs(z)**2 for z in left)
    norm=pr+pl
    if abs(norm-1)>1e-8:raise ArithmeticError("Quantum walk lost unitary norm")
    sites=[abs(a)**2+abs(b)**2 for a,b in zip(right,left)]
    entropy=-sum(p*math.log(p) for p in sites if p>0)/math.log(WALK_SITES)
    return (pr-pl,entropy,norm)


def _pressure(bars,i):
    pieces=bars[i-7:i+1]
    return statistics.mean((x["close"]-x["open"])/max(
        x["high"]-x["low"],1e-12) for x in pieces)


def generate_signals(bars):
    """Phase witness vs identical-information classic, all strictly causal."""
    validate_frozen(bars)
    n=len(bars)
    close=[float(x["close"]) for x in bars]
    fast=ema_series(close,24)
    slow=ema_series(close,96)
    signals={n:[] for n in NAMES}
    diagnostics=[]
    for i in range(WARMUP,n-1,SCAN_STEP):
        price=close[i]
        atr=atr_simple(bars,i,14)
        if atr<=0:raise ValueError("Invalid ATR")
        atr_fraction=atr/price
        if not .0012<=atr_fraction<=.045:continue
        r16=math.log(price/close[i-16])
        pressure=_pressure(bars,i)
        classical=(1 if fast[i]>slow[i]+.40*atr and r16>0 and pressure>.008
                  else -1 if fast[i]<slow[i]-.40*atr and r16<0 and pressure<-.008
                  else 0)
        if not classical:continue
        signals["classical_same_information"].append((i,classical,atr))
        score,entropy,norm=wavewalk(close,i,atr_fraction)
        ablate,_,_=wavewalk(close,i,atr_fraction,phase_multiplier=0)
        if len(diagnostics)<8:
            diagnostics.append({"ts":bars[i]["ts"],
                                "quantum_coin_skew":round(score,6),
                                "spatial_entropy":round(entropy,6),
                                "norm":round(norm,10)})
        if classical*ablate>=PREDICTION_THRESHOLD and entropy<=MAX_WALK_ENTROPY:
            signals["q_walk_phase_free_ablation"].append((i,classical,atr))
        if classical*score>=PREDICTION_THRESHOLD and entropy<=MAX_WALK_ENTROPY:
            signals["q_walk_coherent"].append((i,classical,atr))
        weak_score,weak_entropy,_=wavewalk(close,i,atr_fraction,
                                           phase_multiplier=.75)
        strong_score,strong_entropy,_=wavewalk(close,i,atr_fraction,
                                               phase_multiplier=1.25)
        if (min(classical*score,classical*weak_score,
                classical*strong_score)>=ROBUST_PREDICTION_THRESHOLD
            and max(entropy,weak_entropy,strong_entropy)<=MAX_WALK_ENTROPY):
            signals["q_walk_phase_robust"].append((i,classical,atr))
    return signals,diagnostics


def train_frequency_match(classical,quantum,split,symbol):
    """TRAIN-ONLY relative frequency; deterministic HASH sampling of classical.

    This is a turnover control, not exact trade-count matching because
    overlapping holding periods change actual filled frequencies.
    """
    if not isinstance(split,int) or split<=0:raise ValueError("Invalid train split")
    train_q=sum(i<split for i,_,_ in quantum)
    train_c=sum(i<split for i,_,_ in classical)
    proportion=min(1.,train_q/train_c) if train_c else 0.
    output=[]
    for item in classical:
        digest=hashlib.sha256(
            (symbol+":"+str(item[0])).encode("utf-8")).digest()
        uniform=int.from_bytes(digest[:8],"big")/2**64
        if uniform<proportion:
            output.append(item)
    return output,round(proportion,6)


def _score_period(bars,signals,start,end):
    normal=trade_simulation(bars,signals,start_index=start,end_index=end)
    stress=trade_simulation(bars,signals,start_index=start,end_index=end,
                            fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
    days={}
    for t in normal["trade_log"]:
        d=int(t["exit_ts"])//DAY_MS
        days[d]=days.get(d,0)+float(t["net_usd"])
    return {
        "trades":normal["trades"],"net_pct":normal["return_pct"],
        "stress_pct":stress["return_pct"],
        "positive_days":sum(x>0 for x in days.values()),
        "negative_days":sum(x<0 for x in days.values()),
        "distinct_exit_days":len(days),
        "win_rate_pct":normal["win_rate_pct"],
        "max_drawdown_pct":normal["max_drawdown_pct"],
        "fees_usdt":normal["fees_usd"],
    }


def _merge_metrics(per,name,stage):
    vals=[per[s]["strategies"][name][stage] for s in SYMBOLS]
    return {
        "trades":sum(v["trades"] for v in vals),
        "mean_net_pct":round(statistics.mean(v["net_pct"] for v in vals),5),
        "mean_stress_pct":round(statistics.mean(v["stress_pct"] for v in vals),5),
        "positive_markets":sum(v["net_pct"]>0 for v in vals),
        "positive_days":sum(v["positive_days"] for v in vals),
        "negative_days":sum(v["negative_days"] for v in vals),
        "worst_market_drawdown_pct":max(v["max_drawdown_pct"] for v in vals)
    }


def evaluate(bars_by_symbol,specs,*,at_ms=None,hashes=None):
    if set(bars_by_symbol)!=set(SYMBOLS):
        raise ValueError("Missing precommitted public market")
    per={}
    for symbol in SYMBOLS:
        bars=bars_by_symbol[symbol]
        validate_frozen(bars)
        if len(bars)<MIN_BARS:raise ValueError("Insufficient real data: "+symbol)
        split=int(len(bars)*TRAIN_SHARE)
        middle=split+(len(bars)-split)//2
        signals,diag=generate_signals(bars)
        matched,rate=train_frequency_match(
            signals["classical_same_information"],
            signals["q_walk_coherent"],split,symbol)
        signals["classical_train_frequency_matched"]=matched
        periods={"train":(WARMUP,split),
                 "holdout_1":(split,middle),
                 "holdout_2":(middle,len(bars))}
        scores={name:{phase:_score_period(bars,rows,*bounds)
                      for phase,bounds in periods.items()}
                for name,rows in signals.items()}
        per[symbol]={
            "first_utc":datetime.fromtimestamp(
                bars[0]["ts"]/1000,timezone.utc).isoformat(),
            "last_utc":datetime.fromtimestamp(
                bars[-1]["ts"]/1000,timezone.utc).isoformat(),
            "bars":len(bars),
            "coherent_q_to_classical_train_signal_ratio":rate,
            "quantum_state_diagnostics":diag,
            "small_account_public_contract_feasibility":
                capital_feasibility(symbol,bars,specs.get(symbol)),
            "strategies":scores
        }
    agg={name:{phase:_merge_metrics(per,name,phase)
               for phase in ("train","holdout_1","holdout_2")}
         for name in NAMES}
    eligible=[]
    for name in NAMES:
        train=agg[name]["train"]
        if (train["trades"]>=MIN_TRAIN_FILLS and
            train["mean_net_pct"]>0 and train["mean_stress_pct"]>0 and
            train["positive_markets"]>=MIN_POSITIVE_MARKETS and
            train["positive_days"]>=12 and
            train["worst_market_drawdown_pct"]<=12):
            eligible.append(name)
    selected=(max(eligible,key=lambda n:agg[n]["train"]["mean_stress_pct"])
              if eligible else None)
    reasons=[]
    if not selected:
        reasons.append("NO_TRAINING_PROVEN_POSITIVE_AFTER_COST_EDGE")
    else:
        h1,h2=agg[selected]["holdout_1"],agg[selected]["holdout_2"]
        if h1["trades"]+h2["trades"]<MIN_HOLDOUT_FILLS:
            reasons.append("TOO_FEW_HOLDOUT_FILLS_TO_SHOW_RECURRENCE")
        for label,x in (("H1",h1),("H2",h2)):
            if (x["mean_net_pct"]<=0 or x["mean_stress_pct"]<=0 or
                x["positive_days"]<MIN_POSITIVE_DAYS_PER_HOLDOUT):
                reasons.append(label+"_NOT_REPEATEDLY_PROFITABLE")
        width=sum(per[s]["strategies"][selected]["holdout_1"]["net_pct"]+
                  per[s]["strategies"][selected]["holdout_2"]["net_pct"]>0
                  for s in SYMBOLS)
        if width<MIN_POSITIVE_MARKETS:reasons.append("INSUFFICIENT_MARKET_BREADTH")
    public_viable=sum(per[s]["small_account_public_contract_feasibility"][
        "can_place_guarded_min_lot"] for s in SYMBOLS)
    if public_viable==0:reasons.append("NO_4_15_USDT_SMALL_MARGIN_MIN_LOT")
    return {
        "experiment":"TITAN_OMEGA_QUANTUM_CAUSAL_UNITARY_WALK_NEW_MARKETS_RESEARCH_NO_ORDERS",
        "quantum_device_used":False,
        "quantum_computation_classically_simulated":True,
        "physical_unitary_state_norm_verified":True,
        "novelty":"Original project-specific coined quantum walk with candle phase kicks; not claimed world first",
        "public_history_source":"OKX GET /api/v5/market/history-candles",
        "market_symbols_frozen_before_data_fetch":list(SYMBOLS),
        "requested_lookback_days":DAYS,
        "completed_15m_market_bars":sum(len(b) for b in bars_by_symbol.values()),
        "sha256_market_history":hashes or {},
        "retrieved_at_utc":datetime.fromtimestamp(at_ms/1000,timezone.utc).isoformat() if at_ms else None,
        "training_fraction":TRAIN_SHARE,
        "separate_untouched_holdout_halves":2,
        "selected_on_training_only":selected,
        "train_positive_candidate_names":eligible,
        "guarded_small_account_public_minimum_possible_market_count":public_viable,
        "user_start_usdt_mentioned_not_read":4.15,
        "user_target_usdt_mentioned_not_read":8.30,
        "historical_sim_equity_per_symbol_usdt":START_EQUITY,
        "no_private_user_api_called":True,
        "no_orders":True,
        "result":("HISTORICAL_ONLY_NEEDS_INDEPENDENT_FUTURE_EXECUTION_PROOF"
                  if not reasons else "NO_TRADE_NO_PROVEN_REPEATED_NET_PROFIT"),
        "rejection_reasons":reasons,
        "zero_trade_baseline_pct":0,
        "aggregate":agg,
        "per_market":per,
        "limitations":[
            "No physical quantum hardware, quantum computational advantage, or demonstrated profitable trading",
            "Unitary walk is a speculative model not a physical quantum property of markets",
            "The classical turnover match uses a training-only SHA256 sampling rate; realized fills may differ",
            "Stops and targets on OHLC are ambiguous; the historical simulator uses stop-first fills",
            "True funding, mark-price liquidation, orderbook depth, latency, and user's fees are unavailable",
            "Six simulated 1000 USDT accounts are not an executable 4.15 USDT portfolio",
            "History alone does not establish predictive future advantage or daily compounding",
        ]
    }


def public_contract(symbol):
    if symbol not in SYMBOLS:raise ValueError("Unlisted market")
    url="https://www.okx.com/api/v5/public/instruments?"+urlencode(
        {"instType":"SWAP","instId":symbol})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-QCW-Research/1.0"}),
                 timeout=20) as response:
        obj=json.load(response)
    rows=obj.get("data",[])
    if obj.get("code")!="0" or len(rows)!=1 or rows[0].get("instId")!=symbol:
        raise ValueError("Public contract unavailable")
    if rows[0].get("ctType")!="linear":
        raise ValueError("Only linear public USDT perpetuals")
    return {k:rows[0].get(k) for k in
            ("instId","ctVal","ctValCcy","lotSz","minSz","lever","state","ctType")}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",default="reports/titan_qcw_75day_report.json")
    p.add_argument("--raw-dir",default="reports/titan_qcw_75day_public_candles")
    args=p.parse_args(argv)
    now_ms=int(time.time()*1000)
    out=Path(args.out);raw=Path(args.raw_dir)
    out.parent.mkdir(parents=True,exist_ok=True)
    raw.mkdir(parents=True,exist_ok=True)
    market={};specs={};hashes={}
    for symbol in SYMBOLS:
        print("QCW NEW PUBLIC OKX MARKET",symbol,flush=True)
        b=fetch_history(symbol,DAYS,now_ms=now_ms)
        if len(b)<MIN_BARS:raise ValueError("Historical series incomplete: "+symbol)
        market[symbol]=b
        snapshot=json.dumps(b,separators=(",",":")).encode()
        hashes[symbol]=hashlib.sha256(snapshot).hexdigest()
        with gzip.open(raw/(symbol+".json.gz"),"wb",compresslevel=6) as handle:
            handle.write(snapshot)
        try:
            specs[symbol]=public_contract(symbol)
        except (OSError,ValueError,TimeoutError) as exc:
            specs[symbol]={"instId":symbol,"meta_error":type(exc).__name__}
        print("QCW REAL 15m CANDLES",symbol,len(b),
              "sha256",hashes[symbol],
              "minSz",specs[symbol].get("minSz","unknown"),flush=True)
    result=evaluate(market,specs,at_ms=now_ms,hashes=hashes)
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    for name in NAMES:
        print("QCW NET",name,
              "TRAIN",result["aggregate"][name]["train"],
              "H1",result["aggregate"][name]["holdout_1"],
              "H2",result["aggregate"][name]["holdout_2"],flush=True)
    print("QCW FINAL",result["result"],
          "TRAIN_SELECTED",result["selected_on_training_only"],
          "MIN_LOT_VIABLE",result["guarded_small_account_public_minimum_possible_market_count"],
          "NO_ORDERS",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())

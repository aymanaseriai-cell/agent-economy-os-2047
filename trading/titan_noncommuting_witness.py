#!/usr/bin/env python3
"""TITAN Quantum Order-Paradox Witness (QOPW): original research hypothesis.

Two causally observed market facts are mapped to conditionally updated
noncommuting qubit POVM channels: a Z-axis multiscale trend measurement and
an X-axis completed-candle pressure measurement. Testing both measurement
orders produces a contextual disagreement witness, which can veto trades.
Physically valid CPTP instruments, classically EMULATED, never actual qubits.

Precommitted candidates compared on NEW public OKX 15m history with chronological
train, two adjacent chronological holdouts, strict repeatable-after-costs gate.
Private exchange endpoints and orders are NEVER used.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import statistics
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import urlopen,Request
from urllib.parse import urlencode

from trading.edge_lab import (
    BAR_MS,TAKER_FEE,BASE_SLIPPAGE,STRESS_FEE,STRESS_SLIPPAGE,
    FUNDING_PER_8H,START_EQUITY,fetch_history,trade_simulation,
    ema_series,atr_simple,
)
from trading.titan_regime_research import validate_frozen
from trading.titan_quantum_recurrence import capital_feasibility
from trading.titan_open_quantum_adversarial import minimax_expected_log

# These six markets are new versus the past 24-market series.
SYMBOLS=("HBAR-USDT-SWAP","ICP-USDT-SWAP","WLD-USDT-SWAP",
         "GALA-USDT-SWAP","SAND-USDT-SWAP","CRV-USDT-SWAP")
DAYS=60
TRAIN_FRAC=.60
WARMUP=320
MIN_BARS=5600
SCAN_STRIDE=4
TREND_MEASURE_STRENGTH=.62
IMPULSE_MEASURE_STRENGTH=.48
MAX_ORDER_DISAGREEMENT=.09
MIN_CONTEXTUAL_POLARIZATION=.58
MAX_SLIPPAGE_FEE_EXPECTATION_BP=50
MIN_TRAIN_TRADES=60
MIN_HOLDOUT_TRADES=40
MIN_TRAIN_PROFITABLE_MARKETS=4
MIN_HOLDOUT_PROFITABLE_MARKETS=4
MIN_POSITIVE_DAYS_PER_HALF=5
POLICIES=("q_fixed_order","q_noncommuting_witness",
          "q_adversarial_witness","classical_equal_information")


def physical_povm_bloch(r, *, axis, outcome, strength):
    """Normalized outcome of a physical unsharp Pauli POVM instrument.

    E_s=(I+s*eta*sigma_axis)/2, K_s=sqrt(E_s), rho'=K_s rho K_s/p_s.
    Formula for Bloch components: r_parallel'=(r_parallel+s*eta)/(1+s*eta*r_parallel);
    r_perp'=sqrt(1-eta**2) r_perp/(1+s*eta*r_parallel).
    Both outcomes give a CPTP instrument prior to conditioning.
    """
    if len(r)!=3 or not all(math.isfinite(float(z)) for z in r):
        raise ValueError("Invalid input density state")
    if sum(z*z for z in r)>1+1e-9:
        raise ValueError("Density operator is not positive")
    if axis not in (0,1,2) or outcome not in (-1,1):
        raise ValueError("Invalid measurement axis/outcome")
    if not 0<=strength<1 or not math.isfinite(strength):
        raise ValueError("Invalid measurement strength")
    a=outcome*strength
    denom=1+a*r[axis]
    if denom<=0:raise ValueError("Impossible conditional outcome")
    scale=math.sqrt(1-strength*strength)/denom
    out=[v*scale for v in r]
    out[axis]=(r[axis]+a)/denom
    if sum(v*v for v in out)>1+1e-8:
        raise ArithmeticError("Numerical density positivity violation")
    return tuple(out)


def witness(r,trend_side,impulse_side):
    """Order discrepancy in counterfactual post-measurement market states.

    Trend Z then impulse X vs impulse X then trend Z. Both use identical
    information and physical instrument operators, only order differs.
    """
    if trend_side not in (-1,1) or impulse_side not in (-1,1):
        raise ValueError("Missing causal signs")
    after_zx=physical_povm_bloch(
        physical_povm_bloch(r,axis=2,outcome=trend_side,
                            strength=TREND_MEASURE_STRENGTH),
        axis=0,outcome=impulse_side,strength=IMPULSE_MEASURE_STRENGTH)
    after_xz=physical_povm_bloch(
        physical_povm_bloch(r,axis=0,outcome=impulse_side,
                            strength=IMPULSE_MEASURE_STRENGTH),
        axis=2,outcome=trend_side,strength=TREND_MEASURE_STRENGTH)
    return {
        "order_gap":abs(after_zx[2]-after_xz[2]),
        "conservative_polarization":min(trend_side*after_zx[2],
                                        trend_side*after_xz[2]),
        "fixed_order_polarization":trend_side*after_zx[2],
        "actual_evolution_after_trend_then_impulse":after_zx,
        "counterfactual_after_impulse_then_trend":after_xz,
    }


def completed_pressure(bars,i):
    """Signed candle-body / high-low proxy, NOT real bid/ask pressure or volume."""
    parts=[]
    for b in bars[i-7:i+1]:
        delta=b["high"]-b["low"]
        parts.append((b["close"]-b["open"])/delta if delta>0 else 0.)
    return statistics.mean(parts)


def create_signals(bars):
    validate_frozen(bars)
    cl=[b["close"] for b in bars]
    fast=ema_series(cl,24)
    slow=ema_series(cl,96)
    slow2=ema_series(cl,192)
    r=(0.0,0.0,0.0)
    signals={k:[] for k in POLICIES}
    measured=0
    measured_witnesses=[]
    for i in range(96,len(bars)-1):
        price=cl[i]
        atr=atr_simple(bars,i,14)
        if atr<=0:raise ValueError("Missing volatility")
        v=atr/price
        # A small phase-space Y rotation + dephasing and mixing to I/2.
        # These operations are each CPTP, so the state stays physical.
        ret=math.log(price/cl[i-1])
        theta=max(-.5,min(.5,18*ret))
        c,s=math.cos(theta),math.sin(theta)
        r=((c*r[0]+s*r[2])*.88*.92,
           r[1]*.88*.92,
           (-s*r[0]+c*r[2])*.92)
        trend_side=(1 if fast[i]>slow[i]+.40*atr and
                           slow[i]>slow2[i] and cl[i]>cl[i-24]
                    else -1 if fast[i]<slow[i]-.40*atr and
                           slow[i]<slow2[i] and cl[i]<cl[i-24]
                    else 0)
        pressure=completed_pressure(bars,i)
        impulse_side=1 if pressure>.015 else -1 if pressure<-.015 else 0
        if not trend_side or not impulse_side:
            continue
        x=witness(r,trend_side,impulse_side)
        r=x["actual_evolution_after_trend_then_impulse"]
        measured+=1
        if len(measured_witnesses)<8:
            measured_witnesses.append(
                {"ts_ms":bars[i]["ts"],
                 "different_measurement_orders_gap":round(x["order_gap"],7),
                 "conservative_polarization":round(x["conservative_polarization"],7)})
        if i<WARMUP or i%SCAN_STRIDE or not .0012<=v<=.045:
            continue
        if trend_side!=impulse_side:
            continue
        # Identical trend/pressure filters across quantum and classical twins.
        signals["classical_equal_information"].append((i,trend_side,atr))
        if x["fixed_order_polarization"]>=MIN_CONTEXTUAL_POLARIZATION:
            signals["q_fixed_order"].append((i,trend_side,atr))
        if (x["conservative_polarization"]>=MIN_CONTEXTUAL_POLARIZATION
            and x["order_gap"]<=MAX_ORDER_DISAGREEMENT):
            signals["q_noncommuting_witness"].append((i,trend_side,atr))
            # An additional adversarial no-trade filter, computed ONLY from
            # non-overlapping PAST 8-bar returns ending at/before bar i.
            prior=[math.log(cl[k+8]/cl[k])
                   for k in range(i-256,i-8,8)]
            if (len(prior)>=16 and minimax_expected_log(
                trend_side,prior,atr_fraction=v)>0):
                signals["q_adversarial_witness"].append((i,trend_side,atr))
    return signals,{"number_of_valid_contexts":measured,
                    "first_context_witnesses":measured_witnesses,
                    "posterior_state_bloch":tuple(round(z,7) for z in r)}


def score(bars,votes):
    split=int(len(bars)*TRAIN_FRAC)
    middle=split+(len(bars)-split)//2
    periods=((WARMUP,split),(split,middle),(middle,len(bars)))
    results=[]
    for a,b in periods:
        x=trade_simulation(bars,votes,start_index=a,end_index=b)
        stress=trade_simulation(bars,votes,start_index=a,end_index=b,
                                fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
        daily={}
        for t in x["trade_log"]:
            d=t["exit_ts"]//86_400_000
            daily[d]=daily.get(d,0.)+float(t["net_usd"])
        results.append({
            "trades":x["trades"],
            "net_pct":x["return_pct"],
            "stress_net_pct":stress["return_pct"],
            "win_rate_pct":x["win_rate_pct"],
            "max_drawdown_pct":x["max_drawdown_pct"],
            "positive_exit_days":sum(v>0 for v in daily.values()),
            "negative_exit_days":sum(v<0 for v in daily.values()),
            "distinct_exit_days":len(daily),
            "gross_usd":x["gross_usd"],
            "fees_usd":x["fees_usd"],
            "funding_model_usd":x["funding_model_usd"]
        })
    return results


def _aggregate(per_market,name,phase):
    r=[per_market[s]["strategies"][name][phase] for s in SYMBOLS]
    return {"trades":sum(z["trades"] for z in r),
            "mean_net_pct":round(statistics.mean(z["net_pct"] for z in r),5),
            "mean_stress_net_pct":round(statistics.mean(z["stress_net_pct"] for z in r),5),
            "positive_markets":sum(z["net_pct"]>0 for z in r),
            "positive_exit_days":sum(z["positive_exit_days"] for z in r),
            "negative_exit_days":sum(z["negative_exit_days"] for z in r),
            "worst_symbol_drawdown_pct":max(z["max_drawdown_pct"] for z in r)}


def run_study(market,public_specs,*, data_hashes=None,at_ms=None):
    if set(market)!=set(SYMBOLS):
        raise ValueError("Missing a predeclared market")
    data={}
    for sym in SYMBOLS:
        bars=market[sym]
        validate_frozen(bars)
        if len(bars)<MIN_BARS:
            raise ValueError("Not enough historical candles for "+sym)
        votes,diag=create_signals(bars)
        per={k:dict(zip(("train","holdout_1","holdout_2"),score(bars,votes[k])))
             for k in POLICIES}
        data[sym]={
            "bars":len(bars),
            "first_utc":datetime.fromtimestamp(bars[0]["ts"]/1000,timezone.utc).isoformat(),
            "last_utc":datetime.fromtimestamp(bars[-1]["ts"]/1000,timezone.utc).isoformat(),
            "holdout_start_utc":datetime.fromtimestamp(
                bars[int(len(bars)*TRAIN_FRAC)]["ts"]/1000,timezone.utc).isoformat(),
            "context_diagnostics":diag,
            "public_4_15_usdt_guarded_contract_check":capital_feasibility(
                sym,bars,public_specs.get(sym)),
            "strategies":per}
    aggregate={name:{phase:_aggregate(data,name,phase)
                     for phase in ("train","holdout_1","holdout_2")}
               for name in POLICIES}
    qualified=[]
    for name in POLICIES:
        r=aggregate[name]["train"]
        if (r["trades"]>=MIN_TRAIN_TRADES and
            r["mean_net_pct"]>0 and r["mean_stress_net_pct"]>0 and
            r["positive_markets"]>=MIN_TRAIN_PROFITABLE_MARKETS
            and r["positive_exit_days"]>=12
            and r["worst_symbol_drawdown_pct"]<=12):
            qualified.append(name)
    # Holdout never enters the selection function.
    chosen=max(qualified,key=lambda name:aggregate[name]["train"][
        "mean_stress_net_pct"]) if qualified else None
    reasons=[]
    if chosen is None:
        reasons.append("NO_REPEATED_POSITIVE_TRAINING_EDGE")
    else:
        h1,h2=(aggregate[chosen][phase] for phase in ("holdout_1","holdout_2"))
        if h1["trades"]+h2["trades"]<MIN_HOLDOUT_TRADES:
            reasons.append("TOO_FEW_INDEPENDENT_HOLDOUT_TRADES")
        for tag,h in (("H1",h1),("H2",h2)):
            if (h["mean_net_pct"]<=0 or h["mean_stress_net_pct"]<=0 or
                h["positive_exit_days"]<MIN_POSITIVE_DAYS_PER_HALF):
                reasons.append(tag+"_NOT_REPEATEDLY_NET_PROFITABLE")
        positive=sum(
            data[s]["strategies"][chosen]["holdout_1"]["net_pct"]+
            data[s]["strategies"][chosen]["holdout_2"]["net_pct"]>0
            for s in SYMBOLS)
        if positive<MIN_HOLDOUT_PROFITABLE_MARKETS:
            reasons.append("TOO_FEW_POSITIVE_HOLDOUT_MARKETS")
    viable=sum(data[s]["public_4_15_usdt_guarded_contract_check"][
        "can_place_guarded_min_lot"] for s in SYMBOLS)
    if not viable:reasons.append("PUBLIC_4_15_USDT_CONTRACT_FEASIBILITY_REJECT")
    verdict=("HISTORICAL_ONLY_REQUIRES_INDEPENDENT_PROSPECTIVE_FILL_AUDIT"
             if not reasons else "NO_TRADE_NO_PROVEN_QUANTUM_EDGE")
    return {
        "experiment":"TITAN_QOPW_NONCOMMUTATIVE_MARKET_WITNESS_NO_ORDERS",
        "research_hypothesis":"Pauli-X and Pauli-Z conditional POVM order gap vetoes unstable direction",
        "novelty_claim":"Original project-specific experiment; no claim of unprecedented invention",
        "market_symbols_precommitted_before_retrieval":list(SYMBOLS),
        "sample_days_requested":DAYS,
        "completed_15m_candles_total":sum(len(z) for z in market.values()),
        "raw_data_sha256":data_hashes or {},
        "retrieved_at_utc":datetime.fromtimestamp(at_ms/1000,timezone.utc).isoformat() if at_ms else None,
        "quantum_hardware_used":False,
        "quantum_speedup_claim":False,
        "physical_povm_bloch_updates_simulated_classically":True,
        "no_lookahead_tests":True,
        "baseline_zero_trade_pct":0.0,
        "time_split":{"train_fraction":TRAIN_FRAC,"holdout_halves":2},
        "selected_only_on_training":chosen,
        "train_eligible_policies":qualified,
        "selected_historical_gate_pass":not reasons,
        "guarded_min_lot_possible_market_count_public_only":viable,
        "user_start_balance_unverified_usdt":4.15,
        "target_balance_unverified_usdt":8.30,
        "simulation_equity_per_symbol_usdt":START_EQUITY,
        "no_live_account_inspection":True,
        "no_orders":True,
        "verdict":verdict,
        "rejection_reasons":reasons,
        "aggregate":aggregate,
        "per_market":data,
        "limitations":[
            "A noncommuting two-level POVM is simulated on classical hardware; not quantum computing advantage",
            "Candle-body pressure proxy is NOT actual executed-order flow or L2 market depth",
            "Pauli measurement order significance is a model hypothesis not physical market qubits",
            "OHLC next-open/stop-first simulation omits mark liquidations, actual funding and execution",
            "1000 USDT per-symbol simulations are not the user's 4.15 USDT margin account",
            "Public min contract sizes cannot prove a live fill is available",
            "Positive holdouts require untouched prospective forward tests and statistical validation"
        ]
    }


def public_contract(symbol):
    if symbol not in SYMBOLS:raise ValueError("Unlisted market")
    path="https://www.okx.com/api/v5/public/instruments?"+urlencode(
        {"instType":"SWAP","instId":symbol})
    with urlopen(Request(path,headers={"User-Agent":"TITAN-QOPW/1.0"}),
                 timeout=20) as response:
        content=json.load(response)
    rows=content.get("data",[])
    if content.get("code")!="0" or len(rows)!=1:
        raise ValueError("Unverified public contract metadata")
    z=rows[0]
    if z.get("instId")!=symbol or z.get("ctType")!="linear":
        raise ValueError("Unexpected contract class")
    return {k:z.get(k) for k in ("instId","ctVal","ctValCcy",
                                  "lotSz","minSz","lever","state","ctType")}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",default="reports/titan_qopw_noncommutative.json")
    p.add_argument("--data-dir",default="reports/titan_qopw_new_market_data")
    args=p.parse_args(argv)
    now=int(time.time()*1000)
    out=Path(args.out);dest=Path(args.data_dir)
    out.parent.mkdir(parents=True,exist_ok=True)
    dest.mkdir(parents=True,exist_ok=True)
    market={};hashes={};specs={}
    for sym in SYMBOLS:
        print("QOPW REAL OKX FETCH",sym,flush=True)
        bars=fetch_history(sym,DAYS,now_ms=now)
        if len(bars)<MIN_BARS:raise ValueError("Incomplete public market bars "+sym)
        market[sym]=bars
        binary=json.dumps(bars,separators=(",",":")).encode()
        hashes[sym]=hashlib.sha256(binary).hexdigest()
        with gzip.open(dest/(sym+".json.gz"),"wb",compresslevel=6) as handle:
            handle.write(binary)
        try:
            specs[sym]=public_contract(sym)
        except (OSError,ValueError,TimeoutError) as exc:
            specs[sym]={"instId":sym,"error_type":type(exc).__name__}
        print("QOPW DATA",sym,len(bars),"sha256",hashes[sym],
              "minSz",specs[sym].get("minSz","UNKNOWN"),flush=True)
    result=run_study(market,specs,data_hashes=hashes,at_ms=now)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for name in POLICIES:
        print("QOPW PERFORMANCE",name,
              "TRAIN",result["aggregate"][name]["train"],
              "HOLDOUT1",result["aggregate"][name]["holdout_1"],
              "HOLDOUT2",result["aggregate"][name]["holdout_2"],flush=True)
    print("QOPW VERDICT",result["verdict"],
          "selected_on_training",result["selected_only_on_training"],
          "small_usdt_public_symbols",result["guarded_min_lot_possible_market_count_public_only"],
          "NO ORDERS",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())

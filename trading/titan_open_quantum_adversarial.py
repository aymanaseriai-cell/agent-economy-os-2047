#!/usr/bin/env python3
"""TITAN OMEGA Open Quantum Adversarial Survival — REAL OKX OHLC, NO ORDERS.

Mathematically valid one-qubit OPEN-SYSTEM density-matrix channel is simulated
CLASSICALLY (unitary Y rotation, physical dephasing, convex reset channel).
The quantum-state feature does NOT imply quantum hardware or advantage.
A train-independent minimax expected-log test faces historical tails,
transaction-cost stress and one-sided jump contaminations. Zero-trade WAIT is
the default. This is a falsifiable historical experiment, not a live policy.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from trading.edge_lab import (
    BAR_MS, START_EQUITY, TAKER_FEE, BASE_SLIPPAGE,
    STRESS_FEE, STRESS_SLIPPAGE, FUNDING_PER_8H,
    ema_series, atr_simple, signals, fetch_history, trade_simulation
)
from trading.titan_regime_research import validate_frozen

# New market set vs the two earlier six-market studies. Fixed BEFORE fetching.
SYMBOLS=("BCH-USDT-SWAP","ETC-USDT-SWAP","XLM-USDT-SWAP",
         "NEAR-USDT-SWAP","ATOM-USDT-SWAP","UNI-USDT-SWAP")
DAYS=45
TRAIN_FRAC=.60
WARMUP=320
MIN_CANDLES=3500
HORIZON_BARS=8
SAMPLE_LOOKBACK=256
SIGNAL_STRIDE=4
MIN_STATE_CONFIDENCE=.35
DEPHASING_BASE=.25
RESET_RATE=.18
SHOCK_FRACTION=.10
TAIL_FRACTION=.20
MAX_STRESS_ADDITIONAL_SLIPPAGE=.0015
REQUIRED_TRAIN_TRADES=40
REQUIRED_POSITIVE_TRAIN_MARKETS=4
MIN_TRAIN_NET_PCT=0.25
MIN_TRAIN_STRESS_PCT=0.0

NAMES=("open_quantum_density_unshielded","quantum_adversarial_survival",
       "classical_adversarial_survival","ema_rsi","breakout")


def clamp(x,a,b):
    return min(b,max(a,x))


def density_step(bloch, *, rotation, dephasing, reset, bias):
    """One-qubit CPTP dynamics on Bloch vector (x,y,z).

    R_y(theta) is unitary. Dephasing is a convex Pauli-Z channel:
    x,y -> (1-d)x,(1-d)y (0<=d<=1). Finally mix with replacement
    to valid diagonal rho_target=(I+bias*Z)/2, a CPTP reset.
    """
    if not (len(bloch)==3 and all(math.isfinite(v) for v in bloch)):
        raise ValueError("Invalid Bloch vector")
    if not all(math.isfinite(v) for v in (rotation,dephasing,reset,bias)):
        raise ValueError("Invalid channel parameters")
    if not(0<=dephasing<=1 and 0<=reset<=1 and -1<=bias<=1):
        raise ValueError("Nonphysical channel settings")
    x,y,z=bloch
    if x*x+y*y+z*z>1+1e-9:
        raise ValueError("Input is not a positive density matrix")
    c,s=math.cos(rotation),math.sin(rotation)
    # R_y under Bloch representation.
    xx=c*x+s*z
    zz=-s*x+c*z
    xx*=(1-dephasing)
    yy=y*(1-dephasing)
    return ((1-reset)*xx,(1-reset)*yy,(1-reset)*zz+reset*bias)


def density_mat(bloch):
    x,y,z=bloch
    if x*x+y*y+z*z>1+1e-9:
        raise ArithmeticError("Nonpositive 2x2 density state")
    # [[rho00,rho01],[rho10,rho11]] (complex).
    return ((complex((1+z)/2,0),complex(x/2,-y/2)),
            (complex(x/2,y/2),complex((1-z)/2,0)))


def historical_eight_bar_log_returns(closes,i):
    """32 strictly PAST nonoverlapping 2h blocks ending at or before bar i."""
    if i<SAMPLE_LOOKBACK:
        raise ValueError("Insufficient historical block window")
    return [math.log(closes[k+HORIZON_BARS]/closes[k])
            for k in range(i-SAMPLE_LOOKBACK,i,HORIZON_BARS)]


def minimax_expected_log(side, past_logs, *, atr_fraction):
    """Uncalibrated but explicit distributionally robust 2-hour surrogate.

    All three adversarial model distributions have only known (past) inputs:
    A: past nonoverlapping 2h moves with ordinary fee+slippage
    B: past moves after extra worst-case cost slippage
    C: contaminated measure (90% empirical, 10% shock AGAINST direction)
    D: 80% empirical + 20% worst realized fifth-quantile moves
    Return worst expected log increment; WAIT has score exactly zero.
    This is NOT CVaR of actual 15m TP/SL fills.
    """
    if side not in (-1,1) or len(past_logs)<16:
        raise ValueError("Invalid adversarial return sample")
    if not 0<atr_fraction<1:
        raise ValueError("Invalid volatility estimate")
    roundtrip=(2*TAKER_FEE+2*BASE_SLIPPAGE+
               FUNDING_PER_8H*HORIZON_BARS/32)
    stress=(2*STRESS_FEE+2*STRESS_SLIPPAGE+
            FUNDING_PER_8H*HORIZON_BARS/32+
            2*MAX_STRESS_ADDITIONAL_SLIPPAGE)
    rets=[side*math.expm1(log_move) for log_move in past_logs]
    if any(not math.isfinite(z) for z in rets):
        raise ValueError("Non-finite past shocks")
    def growth(x,cost):
        # Capital at risk is held at 1x notional/equity within this minimax
        # *decision* score, independently of the stop-sized paper sim.
        r=x-cost
        return math.log1p(max(-.95,r))
    normal=statistics.mean(growth(r,roundtrip) for r in rets)
    expensive=statistics.mean(growth(r,stress) for r in rets)
    severe_move=-max(3*atr_fraction,2*statistics.pstdev(past_logs),.009)
    contaminated=.9*normal+.1*growth(severe_move,stress)
    worst=sorted(rets)[:max(1,int(len(rets)*TAIL_FRACTION))]
    tilted=.8*normal+.2*statistics.mean(growth(x,stress) for x in worst)
    return min(normal,expensive,contaminated,tilted)


def make_survival_signals(bars):
    """Causal decisions at completed bar i; simulation trades at open(i+1)."""
    validate_frozen(bars)
    closes=[float(b["close"]) for b in bars]
    e20=ema_series(closes,20)
    e60=ema_series(closes,60)
    bloch=(0.0,0.0,0.0)
    unshielded,robust,classical=[],[],[]
    state_audit=[]
    # Simulate physical CPTP channel on historical events in chronological order.
    # Last candle excluded explicitly; no future bar is inspected.
    for i in range(64,len(bars)-1):
        prev_ret=math.log(closes[i]/closes[i-1])
        atr=atr_simple(bars,i,14)
        if atr<=0 or not math.isfinite(atr):
            raise ValueError("Missing ATR")
        af=atr/closes[i]
        trend=math.log(closes[i]/closes[i-16])
        theta=clamp(18*prev_ret,-.5,.5)
        dephasing=clamp(DEPHASING_BASE+2*abs(prev_ret)/max(af,1e-7),0,.92)
        target_bias=math.tanh(trend/max(af*4,1e-7))
        bloch=density_step(bloch,rotation=theta,dephasing=dephasing,
                           reset=RESET_RATE,bias=target_bias)
        if i%SIGNAL_STRIDE or i<WARMUP or not .0012<=af<=.045:
            continue
        # Observable is Tr(rho Z), i.e. z in [-1,1].
        z=bloch[2]
        if abs(z)>=MIN_STATE_CONFIDENCE:
            side=1 if z>0 else -1
            unshielded.append((i,side,atr))
        else:
            side=0
        classical_side=(1 if e20[i]>e60[i]+.4*atr else
                        -1 if e20[i]<e60[i]-.4*atr else 0)
        if not side and not classical_side:
            continue
        samples=historical_eight_bar_log_returns(closes,i)
        if side and minimax_expected_log(side,samples,atr_fraction=af)>0:
            robust.append((i,side,atr))
        if classical_side and minimax_expected_log(
                classical_side,samples,atr_fraction=af)>0:
            classical.append((i,classical_side,atr))
        if len(state_audit)<5:
            state_audit.append({"bar_ms":bars[i]["ts"],"z":round(z,6),
                                "rho_trace":1.0,
                                "state_l2":round(math.sqrt(sum(v*v for v in bloch)),6),
                                "no_future_data_in_decision":True})
    return {
        "open_quantum_density_unshielded":unshielded,
        "quantum_adversarial_survival":robust,
        "classical_adversarial_survival":classical,
        "ema_rsi":signals(bars,"ema_rsi"),
        "breakout":signals(bars,"breakout"),
    },state_audit


def metrics_only(obj):
    return {k:v for k,v in obj.items() if k!="trade_log"}


def evaluate(frozen,*, hashes=None,at_ms=None):
    if set(frozen)!=set(SYMBOLS):
        raise ValueError("Incomplete or modified real-market set")
    summary={}
    market={}
    for symbol in SYMBOLS:
        b=frozen[symbol]
        validate_frozen(b)
        if len(b)<MIN_CANDLES:
            raise ValueError("Insufficient completed historical bars for "+symbol)
        split=int(len(b)*TRAIN_FRAC)
        votes,audit=make_survival_signals(b)
        rec={"bars":len(b),
             "first_utc":datetime.fromtimestamp(b[0]["ts"]/1000,timezone.utc).isoformat(),
             "last_utc":datetime.fromtimestamp(b[-1]["ts"]/1000,timezone.utc).isoformat(),
             "holdout_start_utc":datetime.fromtimestamp(b[split]["ts"]/1000,timezone.utc).isoformat(),
             "open_system_density_sanity_samples":audit,
             "strategies":{}}
        for name in NAMES:
            rows=votes[name]
            train=trade_simulation(b,rows,start_index=WARMUP,end_index=split)
            h=trade_simulation(b,rows,start_index=split,end_index=len(b))
            stress=trade_simulation(b,rows,start_index=split,end_index=len(b),
                                   fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
            rec["strategies"][name]={
                "train_trades":train["trades"],
                "train_return_pct":train["return_pct"],
                "holdout_trades":h["trades"],
                "holdout_net_return_pct":h["return_pct"],
                "holdout_stress_return_pct":stress["return_pct"],
                "holdout_profit_factor":h["profit_factor"],
                "holdout_win_rate_pct":h["win_rate_pct"],
                "holdout_drawdown_pct":h["max_drawdown_pct"],
                "holdout_fees_model_usdt":h["fees_usd"],
                "raw_signals":len(rows),
                "holdout_trade_log":h["trade_log"][:35],
            }
        market[symbol]=rec
    for name in NAMES:
        arr=[market[s]["strategies"][name] for s in SYMBOLS]
        summary[name]={
            "train_trades":sum(v["train_trades"] for v in arr),
            "train_mean_net_pct":round(statistics.mean(v["train_return_pct"] for v in arr),4),
            "holdout_trades":sum(v["holdout_trades"] for v in arr),
            "holdout_mean_net_pct":round(statistics.mean(
                v["holdout_net_return_pct"] for v in arr),4),
            "holdout_mean_stress_net_pct":round(statistics.mean(
                v["holdout_stress_return_pct"] for v in arr),4),
            "positive_holdout_markets":sum(v["holdout_net_return_pct"]>0 for v in arr),
            "mean_holdout_max_drawdown_pct":round(statistics.mean(
                v["holdout_drawdown_pct"] for v in arr),4),
            "no_holdout_signals":sum(v["holdout_trades"] for v in arr)==0,
        }
    q=summary["quantum_adversarial_survival"]
    train_gate=(q["train_trades"]>=REQUIRED_TRAIN_TRADES
                and q["train_mean_net_pct"]>=MIN_TRAIN_NET_PCT
                and sum(market[s]["strategies"]["quantum_adversarial_survival"][
                    "train_return_pct"]>0 for s in SYMBOLS)>=REQUIRED_POSITIVE_TRAIN_MARKETS)
    research_gate=(train_gate and q["holdout_trades"]>=20 and
                   q["holdout_mean_net_pct"]>0 and
                   q["holdout_mean_stress_net_pct"]>MIN_TRAIN_STRESS_PCT and
                   q["positive_holdout_markets"]>=4)
    return {
        "mode":"REAL_HISTORICAL_OPEN_SYSTEM_CLASSICAL_EMULATOR_ADVERSARIAL_NO_ORDERS",
        "data_source":"OKX public /api/v5/market/history-candles",
        "market_set_predeclared_before_download":list(SYMBOLS),
        "data_sha256":hashes or {},
        "market_bars_total":sum(len(v) for v in frozen.values()),
        "market_snapshot_utc":datetime.fromtimestamp(at_ms/1000,timezone.utc).isoformat() if at_ms else None,
        "history_days_requested":DAYS,
        "train_fraction":TRAIN_FRAC,
        "holdout_fraction":1-TRAIN_FRAC,
        "policy":"NO_TRADE_UNLESS_EXPECTED_LOG_GROWTH_POSITIVE_UNDER_ALL_PRECOMMITTED_ADVERSARIES",
        "quantum_hardware_used":False,
        "physical_open_system_channel_modeled":True,
        "quantum_runtime_advantage_evidenced":False,
        "minimax_uses_past_8bar_returns_only":True,
        "execution_stop_first_ambiguous_intrabar":True,
        "starting_equity_usdt_per_symbol_not_real_account":START_EQUITY,
        "stressed_fees_and_slippage_assumed":True,
        "real_futures_lot_and_liquidation_omitted":True,
        "train_gate_met":train_gate,
        "research_gate_met":research_gate,
        "verified_decision":"NO_LIVE_PROMOTION" if not research_gate
                            else "RESEARCH_ONLY_POSITIVE_NOT_LIVE_APPROVED",
        "summary":summary,
        "zero_trade_reference":{
            "holdout_net_pct":0,
            "holdout_stress_pct":0,
            "trades":0
        },
        "per_market":market,
        "risk_caveats":[
            "Density-matrix dynamics are a classical computational simulation, not quantum hardware",
            "Historical candle OHLC lacks orderbook/depth, mark-price liquidations and actual funding",
            "Worst-tail and shock probabilities in the adversarial scenario set are hypotheses",
            "Per-market equity resets to 1000 USDT, not an executable 4.15 USDT futures account",
            "No historically tested winning strategy is authorization for an OKX live trade",
        ]
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",default="reports/titan_open_quantum_adversarial.json")
    parser.add_argument("--data-dir",default="reports/titan_open_quantum_raw")
    opt=parser.parse_args(argv)
    recorded_ms=int(time.time()*1000)
    out=Path(opt.output);raw=Path(opt.data_dir)
    out.parent.mkdir(exist_ok=True,parents=True)
    raw.mkdir(exist_ok=True,parents=True)
    found={};hashes={}
    for symbol in SYMBOLS:
        print("OPEN QUANTUM HISTORICAL OKX FETCH",symbol,flush=True)
        data=fetch_history(symbol,DAYS,now_ms=recorded_ms)
        validate_frozen(data)
        if len(data)<MIN_CANDLES:
            raise ValueError("Incomplete real-history series: "+symbol)
        found[symbol]=data
        snapshot=json.dumps(data,separators=(",",":")).encode()
        hashes[symbol]=hashlib.sha256(snapshot).hexdigest()
        with gzip.open(raw/(symbol+".json.gz"),"wb",compresslevel=6) as f:
            f.write(snapshot)
        print("OPEN QUANTUM REAL DATA",symbol,len(data),"sha256",hashes[symbol],flush=True)
    report=evaluate(found,hashes=hashes,at_ms=recorded_ms)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for name,stats in report["summary"].items():
        print("OPEN QUANTUM HOLDOUT",name,
              "trades",stats["holdout_trades"],
              "mean_net_pct",stats["holdout_mean_net_pct"],
              "mean_stress_pct",stats["holdout_mean_stress_net_pct"],
              "markets_positive",stats["positive_holdout_markets"],
              "of",len(SYMBOLS),flush=True)
    print("OPEN QUANTUM FINAL",report["verified_decision"],
          "train_gate",report["train_gate_met"],
          "NO ORDERS",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""TITAN blind six-market historical tournament — public OKX bars, NO ORDERS.

Six new swap markets never used in TITAN's earlier frozen six-market tests.
Locked signals and Ising selection logic are committed BEFORE the first real
data-fetch job. Training-only Ising exact ground state competes with classical
annealing and classically emulated six-qubit QAOA. Next-bar stop-first fill;
taker fee, slippage, funding and stress costs modeled. NOT a 4.15 USDT live
account simulation. Real execution, minimum lots and liquidation unmodeled.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from trading.edge_lab import (
    BAR_MS, START_EQUITY, TAKER_FEE, BASE_SLIPPAGE,
    STRESS_FEE, STRESS_SLIPPAGE, FUNDING_PER_8H,
    ema_series, atr_simple, rsi_simple, signals, trade_simulation, fetch_history,
)
from trading.titan_regime_research import validate_frozen, regime_signals
from trading.titan_quantum_ising_lab import (
    exact_ground_state, anneal_ising, votes_consensus, unbiased_null_control
)
from trading.titan_qaoa_emulator import audit_qaoa
from trading.titan_alpha_tribunal import (
    single_position_episodes, daily_blocks, block_bootstrap
)

# Frozen independent symbols: deliberately NOT the first BTC/ETH/SOL/XRP/DOGE/SUI test basket.
SYMBOLS = ("LTC-USDT-SWAP", "ADA-USDT-SWAP", "AVAX-USDT-SWAP",
           "LINK-USDT-SWAP", "DOT-USDT-SWAP", "APT-USDT-SWAP")
FAMILIES = ("ema_rsi", "breakout", "regime_breakout",
            "fractal_momentum", "variance_reversion", "entropy_breakout")
SAMPLE_DAYS = 45
TRAIN_FRACTION = 0.60
WARMUP = 192
MIN_BARS = 3500
MIN_TRAIN_TRADES = 40
SEED = 8300617


def variance_ratio(prices, i, *, width=64, scale=4):
    """Causal 4-lag variance / 4 times 1-lag variance on 64 completed bars."""
    if i < width+scale:
        raise ValueError("Not enough history for variance ratio")
    one=[math.log(prices[k]/prices[k-1]) for k in range(i-width+1,i+1)]
    many=[math.log(prices[k]/prices[k-scale]) for k in range(i-width+scale,i+1)]
    v1=statistics.pvariance(one)
    v4=statistics.pvariance(many)
    return v4/(scale*v1) if v1>1e-14 else 1.0


def binary_entropy(prices, i, width=24):
    """Shannon entropy of historical positive-v-negative return directions."""
    moves=[prices[k]>prices[k-1] for k in range(i-width+1,i+1)]
    p=sum(moves)/width
    return -sum(q*math.log(q,2) for q in (p,1-p) if q>0)


def advanced_signals(bars, strategy):
    """Three predeclared causal hypotheses. Future t+1 never read at time t."""
    if strategy not in FAMILIES[3:]:
        raise ValueError("Only new locked family names")
    validate_frozen(bars)
    cl=[b["close"] for b in bars]
    e13=ema_series(cl,13);e34=ema_series(cl,34);e89=ema_series(cl,89)
    output=[]
    for i in range(WARMUP,len(bars)-1):
        p=cl[i]
        atr=atr_simple(bars,i,14)
        if not (.0012<=atr/p<=.045):
            continue
        direction=0
        if strategy=="fractal_momentum":
            vr=variance_ratio(cl,i)
            rsi=rsi_simple(cl,i)
            if (vr>=1.08 and e13[i]>e34[i]>e89[i]
                and cl[i]>cl[i-4] and cl[i]>cl[i-16]
                and 52<=rsi<=78):
                direction=1
            elif (vr>=1.08 and e13[i]<e34[i]<e89[i]
                  and cl[i]<cl[i-4] and cl[i]<cl[i-16]
                  and 22<=rsi<=48):
                direction=-1
        elif strategy=="variance_reversion":
            vr=variance_ratio(cl,i)
            previous=cl[i-40:i]
            dev=statistics.pstdev(previous)
            z=(p-statistics.mean(previous))/dev if dev>0 else 0
            rsi=rsi_simple(cl,i)
            if vr<0.92 and abs(e34[i]-e34[i-16])<2*atr:
                if z<=-1.40 and rsi<42:
                    direction=1
                elif z>=1.40 and rsi>58:
                    direction=-1
        else:
            r=bars[i-24:i]
            old=bars[i-96:i-24]
            width_new=(max(x["high"] for x in r)-min(x["low"] for x in r))/p
            width_old=(max(x["high"] for x in old)-min(x["low"] for x in old))/p
            ent=binary_entropy(cl,i-1)
            if width_old>0 and width_new<.5*width_old and ent>=.75:
                if p>max(x["high"] for x in r) and e13[i]>e34[i]:
                    direction=1
                elif p<min(x["low"] for x in r) and e13[i]<e34[i]:
                    direction=-1
        if direction:
            output.append((i,direction,atr))
    return output


def all_signals(bars,name):
    if name in ("ema_rsi","breakout"):
        return signals(bars,name)
    if name=="regime_breakout":
        return regime_signals(bars,name)
    return advanced_signals(bars,name)


def training_ising(day_returns):
    """Training-only daily covariance of six strategy families."""
    if set(day_returns)!=set(FAMILIES):
        raise ValueError("Missing predeclared market families")
    all_days=sorted(set().union(*(set(x) for x in day_returns.values())))
    if len(all_days)<10:
        raise ValueError("Not enough historical training days")
    vec=[[day_returns[name].get(day,0.) for day in all_days] for name in FAMILIES]
    mu=[statistics.mean(v) for v in vec]
    cov=[[sum((x-mu[i])*(y-mu[j]) for x,y in zip(vec[i],vec[j]))
          /(len(all_days)-1) for j in range(6)] for i in range(6)]
    return mu,cov,len(all_days)


def evaluate(data, *, hashes=None, fetched_at_ms=None):
    if set(data)!=set(SYMBOLS):
        raise ValueError("Six new markets are fixed before the experiment")
    raw={};train_daily={name:{} for name in FAMILIES}
    per_market={}
    for symbol in SYMBOLS:
        bars=data[symbol];validate_frozen(bars)
        if len(bars)<MIN_BARS:
            raise ValueError("Insufficient true 45-day data for "+symbol)
        split=int(len(bars)*TRAIN_FRACTION)
        choices=[all_signals(bars,name) for name in FAMILIES]
        raw[symbol]=(bars,choices,split)
        metrics={}
        for name,choice in zip(FAMILIES,choices):
            tr=trade_simulation(bars,choice,start_index=WARMUP,end_index=split)
            ts=trade_simulation(bars,choice,start_index=WARMUP,end_index=split,
                                fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
            hold=trade_simulation(bars,choice,start_index=split,end_index=len(bars))
            stress=trade_simulation(bars,choice,start_index=split,end_index=len(bars),
                                    fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
            # Use historical TRAINING only for selection, never OOS.
            for x in tr["trade_log"]:
                day=int(x["entry_ts"])//86_400_000
                train_daily[name][day]=train_daily[name].get(day,0)+(
                    x["net_usd"]/START_EQUITY/len(SYMBOLS)*10000)
            metrics[name]={
                "train_trades":tr["trades"],"train_net_pct":tr["return_pct"],
                "train_stress_pct":ts["return_pct"],
                "holdout_trades":hold["trades"],
                "holdout_net_pct":hold["return_pct"],
                "holdout_stress_pct":stress["return_pct"],
                "holdout_profit_factor":hold["profit_factor"],
                "holdout_max_drawdown_pct":hold["max_drawdown_pct"]
            }
        per_market[symbol]={
            "bars":len(bars),
            "first_utc":datetime.fromtimestamp(bars[0]["ts"]/1000,timezone.utc).isoformat(),
            "last_utc":datetime.fromtimestamp(bars[-1]["ts"]/1000,timezone.utc).isoformat(),
            "holdout_start_utc":datetime.fromtimestamp(bars[split]["ts"]/1000,timezone.utc).isoformat(),
            "strategies":metrics
        }
    mu,cov,n_days=training_ising(train_daily)
    selected,ground=exact_ground_state(mu,cov)
    annealed,e_anneal=anneal_ising(mu,cov,seed=SEED)
    if e_anneal<ground-1e-9:
        raise AssertionError("Ising energy ground proof inconsistent")
    qaoa=audit_qaoa(mu,cov,ground)
    portfolio={}
    null_input={}
    for symbol,(bars,rows,split) in raw.items():
        combined=votes_consensus(rows,selected)
        tr=trade_simulation(bars,combined,start_index=WARMUP,end_index=split)
        te=trade_simulation(bars,combined,start_index=split,end_index=len(bars))
        st=trade_simulation(bars,combined,start_index=split,end_index=len(bars),
                             fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
        portfolio[symbol]=te.pop("trade_log")
        null_input[symbol]=(bars,rows)
        per_market[symbol]["strategies"]["ising_3_vote_train_only"]={
            "train_trades":tr["trades"],
            "train_net_pct":tr["return_pct"],
            "holdout_trades":te["trades"],
            "holdout_net_pct":te["return_pct"],
            "holdout_stress_pct":st["return_pct"],
            "holdout_profit_factor":te["profit_factor"],
            "holdout_max_drawdown_pct":te["max_drawdown_pct"],
        }
    summary={}
    for name in FAMILIES+("ising_3_vote_train_only",):
        metrics=[per_market[s]["strategies"][name] for s in SYMBOLS]
        summary[name]={
            "training_trades":sum(x["train_trades"] for x in metrics),
            "holdout_trades":sum(x["holdout_trades"] for x in metrics),
            "training_mean_net_pct":round(statistics.mean(x["train_net_pct"] for x in metrics),4),
            "holdout_mean_net_pct":round(statistics.mean(x["holdout_net_pct"] for x in metrics),4),
            "holdout_mean_stress_pct":round(statistics.mean(x["holdout_stress_pct"] for x in metrics),4),
            "positive_holdout_markets":sum(x["holdout_net_pct"]>0 for x in metrics),
            "holdout_mean_profit_factor":round(statistics.mean(
                x["holdout_profit_factor"] for x in metrics
                if x["holdout_profit_factor"] is not None),3)
                if any(x["holdout_profit_factor"] is not None for x in metrics) else None,
        }
    aggregate=summary["ising_3_vote_train_only"]
    null=unbiased_null_control(
        null_input,selected,{s:raw[s][2] for s in SYMBOLS},
        aggregate["holdout_mean_net_pct"],samples=64,seed=SEED)
    episodes=single_position_episodes(portfolio)
    blocks=daily_blocks(episodes)
    risk=(block_bootstrap(blocks,notional_to_equity=4.0,samples=400,seed=SEED,
                          cost_overlay_per_notional=0.005)
          if len(blocks)>=10 else None)
    # A paper "pass" is NOT a live approval, even if metrics turn positive.
    eligible=(aggregate["training_trades"]>=MIN_TRAIN_TRADES
              and aggregate["training_mean_net_pct"]>0
              and aggregate["holdout_mean_net_pct"]>0
              and aggregate["holdout_mean_stress_pct"]>0
              and aggregate["positive_holdout_markets"]>=4
              and null["empirical_exceedance_fraction_not_p_value"]<=.1)
    return {
        "experiment":"TITAN_BLIND_SIX_NEW_REAL_OKX_HISTORICAL_MARKETS_NO_ORDERS",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "historical_data_source":"https://www.okx.com/api/v5/market/history-candles",
        "days_requested":SAMPLE_DAYS,
        "market_symbols_predeclared":list(SYMBOLS),
        "market_bars_total":sum(len(x) for x in data.values()),
        "data_sha256":hashes or {},
        "fetched_at_utc":datetime.fromtimestamp(fetched_at_ms/1000,timezone.utc).isoformat()
                         if fetched_at_ms is not None else None,
        "test_not_previously_used_in_titan_studies":True,
        "chronological_train_fraction":TRAIN_FRACTION,
        "candidate_families_predeclared":list(FAMILIES),
        "selection_from_training_data_only":True,
        "train_only_exact_ising_combo":[FAMILIES[i] for i in selected],
        "classical_annealer_equal_to_ground":abs(e_anneal-ground)<1e-8,
        "classical_qaoa_emulator":qaoa,
        "random_sign_control":null,
        "goal_vs_severe_loss_hypothetical":risk,
        "holdout_nonoverlapping_events":len(episodes),
        "per_market":per_market,
        "summary":summary,
        "zero_trade_baseline_net_pct":0,
        "guarded_model_start_equity_per_market_usdt":START_EQUITY,
        "live_small_account_min_lot_not_checked":True,
        "real_liquidations_not_simulated":True,
        "real_balance_usdt_read":False,
        "real_orders":0,
        "live_trading_permitted":False,
        "research_paper_gate": "PASS_REQUIRES_INDEPENDENT_FORWARD" if eligible
                               else "REJECT_NO_POSITIVE_ROBUST_EDGE",
        "limitations":[
            "Six correlated USDT swaps are not six independent research trials",
            "Historical 15-minute OHLCV snapshot omits L2 orderbook, mark liquidation and actual funding",
            "Cost and slippage tier are illustrative, not verified user-specific OKX charges",
            "Per-symbol 1000 USDT accounts are NOT the user's 4.15 USDT portfolio",
            "QAOA statevector and Ising annealing execute on a classical computer",
            "Any eventual winner on these seen tests requires NEW untouched forward validation",
        ],
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",default="reports/titan_unseen_45d_result.json")
    p.add_argument("--data-dir",default="reports/titan_unseen_45d_data")
    a=p.parse_args(argv)
    snapshot_ts=int(time.time()*1000)
    output=Path(a.output);outdir=Path(a.data_dir)
    output.parent.mkdir(parents=True,exist_ok=True)
    outdir.mkdir(parents=True,exist_ok=True)
    frozen, hashes={},{}
    for symbol in SYMBOLS:
        print("REAL OKX 15m FETCH",symbol,flush=True)
        bars=fetch_history(symbol,SAMPLE_DAYS,now_ms=snapshot_ts)
        validate_frozen(bars)
        if len(bars)<MIN_BARS:
            raise ValueError("Data insufficient "+symbol)
        frozen[symbol]=bars
        raw=json.dumps(bars,separators=(",",":")).encode()
        hashes[symbol]=hashlib.sha256(raw).hexdigest()
        with gzip.open(outdir/(symbol+".json.gz"),"wb",compresslevel=6) as handle:
            handle.write(raw)
        print("REAL DATA",symbol,"bars",len(bars),
              "hash",hashes[symbol],flush=True)
    result=evaluate(frozen,hashes=hashes,fetched_at_ms=snapshot_ts)
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for name,s in result["summary"].items():
        print("REAL HISTORICAL OOS",name,
              "trades",s["holdout_trades"],
              "net_pct",s["holdout_mean_net_pct"],
              "stress_pct",s["holdout_mean_stress_pct"],
              "positive_markets",s["positive_holdout_markets"],
              "/6",flush=True)
    print("QUANTUM CLASSICAL ISING exact_combo",result["train_only_exact_ising_combo"],
          "QAOA_ground_mass",result["classical_qaoa_emulator"]["ground_state_probability_mass"],
          "DECISION",result["research_paper_gate"],"NO_ORDERS",flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())

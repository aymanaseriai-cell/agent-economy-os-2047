#!/usr/bin/env python3
"""Quantum-INSPIRED (classical) Ising challenge for TITAN Omega; NO ORDERS.

No quantum computer, entanglement, or claimed quantum advantage. A 6-bit
Ising/QUBO-style energy chooses exactly three signal families on TRAINING bars
ONLY; simulated annealing is audited against exact exhaustive enumeration.
Consensus then faces costs, frozen historical holdout, and decoy controls.
Previously published frozen data are NOT a pristine new out-of-sample set.
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
from datetime import datetime, timezone
from pathlib import Path

from trading.edge_lab import (
    DEFAULT_SYMBOLS, BAR_MS, START_EQUITY,
    TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE, STRESS_SLIPPAGE,
    TRAIN_FRACTION, ema_series, rsi_simple, atr_simple,
    signals, trade_simulation,
)
from trading.titan_regime_research import (
    BASELINES, CANDIDATES, WARMUP_BARS, regime_signals, validate_frozen,
)
from trading.titan_alpha_tribunal import (
    single_position_episodes, daily_blocks, block_bootstrap,
)

FAMILIES = BASELINES + CANDIDATES + ("squeeze_release", "shock_recovery")
COUNT_SELECTED = 3
DAY_MS = 86_400_000
RISK_COEFFICIENT = 0.12
COUNT_PENALTY = 100.0
ANNEAL_SEED = 60830
DECOY_SEED = 12047
DECOY_TRIALS = 64
MIN_POSITIVE_TRAIN_MARKETS = 4
MIN_TRAIN_TRADES = 40
TRAIN_FEE_STRESS_REQUIRED = True
MAX_TRAIN_DRAWDOWN_PCT = 12.0


def extra_signals(bars, strategy):
    """Causal squeeze or post-shock mean-reversion signals, fixed ex ante."""
    if strategy not in ("squeeze_release", "shock_recovery"):
        raise ValueError("Unknown experimental signal family")
    validate_frozen(bars)
    n = len(bars)
    closes = [b["close"] for b in bars]
    ema_21 = ema_series(closes, 21)
    out = []
    for i in range(WARMUP_BARS, n-1):
        close = closes[i]
        atr = atr_simple(bars, i, 14)
        if atr <= 0 or not (0.001 < atr/close < 0.055):
            continue
        side = 0
        if strategy == "squeeze_release":
            earlier = [bars[i-80:i-60], bars[i-60:i-40], bars[i-40:i-20]]
            old_ranges = [(max(b["high"] for b in a) - min(b["low"] for b in a))
                          / statistics.mean(b["close"] for b in a) for a in earlier]
            recent = bars[i-20:i]
            recent_range = ((max(b["high"] for b in recent)
                             - min(b["low"] for b in recent))
                            / statistics.mean(b["close"] for b in recent))
            if recent_range < 0.72*statistics.median(old_ranges):
                if close > max(b["high"] for b in recent) and ema_21[i] > ema_21[i-8]:
                    side = 1
                elif close < min(b["low"] for b in recent) and ema_21[i] < ema_21[i-8]:
                    side = -1
        else:
            # Past-band breach, then completed-bar reentry while EMA slope is
            # small enough to avoid fading a strongly trending selloff.
            past = closes[i-21:i-1]
            mean, sd = statistics.mean(past), statistics.pstdev(past)
            if sd > 0 and abs(ema_21[i]-ema_21[i-16]) < 2*atr:
                rsi = rsi_simple(closes, i)
                if closes[i-1] < mean-2*sd and close > mean-1.7*sd and rsi < 48:
                    side = 1
                elif closes[i-1] > mean+2*sd and close < mean+1.7*sd and rsi > 52:
                    side = -1
        if side:
            out.append((i, side, atr))
    return out


def candidate_signals(bars, family):
    if family in BASELINES:
        return signals(bars, family)
    if family in CANDIDATES:
        return regime_signals(bars, family)
    return extra_signals(bars, family)


def votes_consensus(rows, indices):
    """At least 2 aligned out of 3 votes; contradictory votes veto trading."""
    if len(indices) != COUNT_SELECTED or len(set(indices)) != COUNT_SELECTED:
        raise ValueError("Exactly three distinct features required")
    collective = {}
    for k in indices:
        if not 0 <= k < len(rows):
            raise ValueError("Bad Ising bit index")
        for t, side, atr in rows[k]:
            if side not in (-1, 1) or atr <= 0:
                raise ValueError("Invalid component signal")
            pos = collective.setdefault(t, [])
            pos.append((side, atr))
    confirmed = []
    for t in sorted(collective):
        votes = collective[t]
        buys = sum(side==1 for side, _ in votes)
        sells = sum(side==-1 for side, _ in votes)
        if buys >= 2 and sells == 0:
            confirmed.append((t,1,statistics.median(atr for _,atr in votes)))
        elif sells >= 2 and buys == 0:
            confirmed.append((t,-1,statistics.median(atr for _,atr in votes)))
    return confirmed


def training_matrix(train_day_returns):
    """Correlated DAILY risk measured only within chronological training data.

    Each market contributes one-sixth of the synthetic per-market account
    return. The covariance is only descriptive, not portfolio tail inference.
    """
    if set(train_day_returns) != set(FAMILIES):
        raise ValueError("Missing Ising features")
    all_days = sorted(set().union(*(set(v) for v in train_day_returns.values())))
    if len(all_days) < 10:
        raise ValueError("Insufficient aligned training days")
    vectors = [
        [float(train_day_returns[name].get(d, 0.0)) for d in all_days]
        for name in FAMILIES
    ]
    mu = [statistics.mean(v) for v in vectors]
    cov = []
    for i, v in enumerate(vectors):
        row = []
        for j, w in enumerate(vectors):
            row.append(sum((a-mu[i])*(b-mu[j]) for a,b in zip(v,w))
                       / (len(all_days)-1))
        cov.append(row)
    return mu, cov, len(all_days)


def ising_energy(bits, mu, cov):
    """Quadratic E(z)= -mu.z + lambda*z'Cov*z + P*(sum(z)-3)^2."""
    if (len(bits) != len(FAMILIES) or len(mu) != len(FAMILIES)
            or len(cov) != len(FAMILIES)
            or any(len(v) != len(FAMILIES) for v in cov)
            or any(v not in (0,1) for v in bits)):
        raise ValueError("Invalid binary QUBO state")
    total = sum(bits)
    return (-sum(a*b for a,b in zip(bits,mu))
            + RISK_COEFFICIENT*sum(
                bits[i]*cov[i][j]*bits[j]
                for i in range(len(bits)) for j in range(len(bits)))
            + COUNT_PENALTY*(total-COUNT_SELECTED)**2)


def exact_ground_state(mu,cov):
    best = None
    for combo in itertools.combinations(range(len(FAMILIES)),COUNT_SELECTED):
        bits = tuple(int(i in combo) for i in range(len(FAMILIES)))
        point = (ising_energy(bits,mu,cov),combo)
        if best is None or point < best:
            best=point
    return best[1], best[0]


def anneal_ising(mu,cov, *, seed=ANNEAL_SEED):
    """Classical simulated annealing with swap moves preserving bit count."""
    rng = random.Random(seed)
    global_best = None
    for restart in range(24):
        active = set(rng.sample(range(len(FAMILIES)),COUNT_SELECTED))
        bits = tuple(int(i in active) for i in range(len(FAMILIES)))
        current = ising_energy(bits,mu,cov)
        if global_best is None or current < global_best[0]:
            global_best = (current,tuple(sorted(active)))
        for k in range(240):
            old = rng.choice(tuple(sorted(active)))
            new = rng.choice(tuple(i for i in range(len(FAMILIES)) if i not in active))
            trial = (active - {old}) | {new}
            guess = tuple(int(i in trial) for i in range(len(FAMILIES)))
            candidate = ising_energy(guess,mu,cov)
            temp = 2.0*(0.008/2.0)**(k/239)
            if candidate < current or rng.random() < math.exp(
                    min(0.0,(current-candidate)/temp)):
                active, current = trial, candidate
                if global_best is None or current < global_best[0]:
                    global_best = (current,tuple(sorted(active)))
    return global_best[1],global_best[0]


def sample_day_returns(trade_log, symbol_count):
    outcome = {}
    for t in trade_log:
        day=int(t["entry_ts"])//DAY_MS
        outcome[day] = outcome.get(day,0.0)+ (
            float(t["net_usd"])/START_EQUITY/symbol_count*10000)
    return outcome


def unbiased_null_control(bars_and_votes, chosen, boundaries, actual_mean,
                          *, samples=DECOY_TRIALS, seed=DECOY_SEED):
    """Future-only decoys; reassign sides while preserving signal timing."""
    rng = random.Random(seed)
    null_means=[]
    for _ in range(samples):
        vals=[]
        for symbol, (bars, signal_rows) in bars_and_votes.items():
            rows=votes_consensus(signal_rows,chosen)
            flipped=[(t, side if rng.random()<.5 else -side,atr)
                     for t,side,atr in rows]
            m=trade_simulation(bars,flipped,start_index=boundaries[symbol],
                               end_index=len(bars))
            vals.append(m["return_pct"])
        null_means.append(statistics.mean(vals))
    return {
        "decoy_trials":samples,
        "actual_net_mean_pct":round(actual_mean,4),
        "decoy_median_net_pct":round(statistics.median(null_means),4),
        "decoy_best_net_pct":round(max(null_means),4),
        "empirical_exceedance_fraction_not_p_value":round(
            sum(v>=actual_mean for v in null_means)/samples,4),
        "controls_are_not_independent_or_proof_of_profit":True,
    }


def evaluate(frozen,*, fingerprints=None):
    if set(frozen)!=set(DEFAULT_SYMBOLS):
        raise ValueError("Require exact six predeclared frozen symbols")
    signals_by_symbol={}
    boundaries={}
    train_days={name:{} for name in FAMILIES}
    for symbol in DEFAULT_SYMBOLS:
        bars=frozen[symbol]
        validate_frozen(bars)
        boundary=int(len(bars)*TRAIN_FRACTION)
        boundaries[symbol]=boundary
        members=[candidate_signals(bars,name) for name in FAMILIES]
        signals_by_symbol[symbol]=(bars,members)
        for name,rows in zip(FAMILIES,members):
            trading=trade_simulation(bars,rows,start_index=WARMUP_BARS,
                                     end_index=boundary)
            for day,ret in sample_day_returns(
                    trading["trade_log"],len(DEFAULT_SYMBOLS)).items():
                train_days[name][day]=train_days[name].get(day,0.0)+ret
    mu,cov,days=training_matrix(train_days)
    selected, exact_E=exact_ground_state(mu,cov)
    annealed, anneal_E=anneal_ising(mu,cov)
    # Quantum-like amplitude calculation, emulated classically on six bits.
    # Optimize cost energy ONLY from training; never from historical holdout.
    from trading.titan_qaoa_emulator import audit_qaoa
    qaoa = audit_qaoa(mu,cov,exact_E)
    # Never let a stochastic approximation silently override exact optimum.
    if anneal_E + 1e-8 < exact_E:
        raise ArithmeticError("Annealer beat exhaustive global minimum")
    comps={}
    portfolio_holdout={}
    for symbol,(bars,members) in signals_by_symbol.items():
        row=votes_consensus(members, selected)
        train=trade_simulation(bars,row,start_index=WARMUP_BARS,
                               end_index=boundaries[symbol])
        stress_train=trade_simulation(bars,row,start_index=WARMUP_BARS,
                                      end_index=boundaries[symbol],
                                      fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
        holdout=trade_simulation(bars,row,start_index=boundaries[symbol],
                                end_index=len(bars))
        stress_holdout=trade_simulation(bars,row,start_index=boundaries[symbol],
                                       end_index=len(bars),
                                       fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
        extra_50bp=trade_simulation(bars,row,start_index=boundaries[symbol],
                                   end_index=len(bars),
                                   fee=STRESS_FEE+0.0025,slip=STRESS_SLIPPAGE)
        portfolio_holdout[symbol]=holdout.pop("trade_log")
        train.pop("trade_log")
        stress_train.pop("trade_log")
        stress_holdout.pop("trade_log")
        extra_50bp.pop("trade_log")
        comps[symbol]={
            "training_trades":train["trades"],
            "training_net_pct":train["return_pct"],
            "training_stress_pct":stress_train["return_pct"],
            "training_max_drawdown_pct":train["max_drawdown_pct"],
            "historical_holdout_trades":holdout["trades"],
            "historical_holdout_net_pct":holdout["return_pct"],
            "historical_holdout_stress_pct":stress_holdout["return_pct"],
            "historical_holdout_extra50bp_pct":extra_50bp["return_pct"],
        }
    ntrain=sum(x["training_trades"] for x in comps.values())
    mtrain=statistics.mean(x["training_net_pct"] for x in comps.values())
    mstress=statistics.mean(x["training_stress_pct"] for x in comps.values())
    mtest=statistics.mean(x["historical_holdout_net_pct"] for x in comps.values())
    teststress=statistics.mean(x["historical_holdout_stress_pct"] for x in comps.values())
    positive_train=sum(x["training_net_pct"]>0 for x in comps.values())
    pass_train=(ntrain>=MIN_TRAIN_TRADES and mtrain>0 and mstress>0
                and positive_train>=MIN_POSITIVE_TRAIN_MARKETS
                and max(x["training_max_drawdown_pct"] for x in comps.values())
                    <= MAX_TRAIN_DRAWDOWN_PCT)
    null = unbiased_null_control(signals_by_symbol,selected,boundaries,mtest)
    episodes = single_position_episodes(portfolio_holdout)
    blocks=daily_blocks(episodes)
    risk=None
    if len(blocks)>=10:
        risk=block_bootstrap(blocks,notional_to_equity=4.0,
                             samples=300,seed=ANNEAL_SEED,
                             cost_overlay_per_notional=0.005)
    return {
        "experiment":"CLASSICAL_QUANTUM_INSPIRED_ISING_CHALLENGE_NO_ORDERS",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "is_real_quantum_computer":False,
        "quantum_speedup_claimed":False,
        "goal_usdt":8.30,
        "starting_balance_usdt":4.15,
        "real_exchange_balance_read":False,
        "orders_placed":0,
        "can_trade_live":False,
        "sources_previously_inspected_not_pristine_holdout":True,
        "feature_families":list(FAMILIES),
        "selected_features_train_only":[FAMILIES[i] for i in selected],
        "selection_rule":"6 binary features; exact 3 selected; 2 compatible votes and no conflicting vote",
        "ising_objective":"-mean_daily_train_bp + 0.12*cov_daily_train_bp2 + 100*(count-3)^2",
        "training_day_count":days,
        "annealer_exact_agreement":abs(exact_E-anneal_E)<1e-8,
        "six_qubit_qaoa_classical_emulator":qaoa,
        "anneal_energy":round(anneal_E,8),
        "exhaustive_global_energy":round(exact_E,8),
        "training_trade_count":ntrain,
        "training_mean_per_symbol_pct":round(mtrain,4),
        "training_mean_stress_pct":round(mstress,4),
        "training_positive_markets":positive_train,
        "candidate_passes_training_gate":pass_train,
        "historical_holdout_mean_per_symbol_pct":round(mtest,4),
        "historical_holdout_mean_stress_pct":round(teststress,4),
        "historical_holdout_positive_markets":sum(
            x["historical_holdout_net_pct"]>0 for x in comps.values()),
        "negative_control_random_side_flip":null,
        "hypothetical_goal_vs_severe_loss_day_resampling":risk,
        "holdout_nonoverlapping_events":len(episodes),
        "per_symbol":comps,
        "data_sha256":fingerprints or {},
        "verdict":"FAIL_CANNOT_PROMOTE_TO_LIVE" if not pass_train else
                  "TRAIN_ONLY_CANDIDATE_NOT_YET_FORWARD_VALIDATED",
        "limitations":[
            "This is classical simulated annealing plus exact enumeration, NOT quantum hardware",
            "No measured quantum advantage, no new unique global trading algorithm",
            "The historical holdout has already been inspected in earlier studies",
            "Training performance and stochastic null checks cannot establish trading alpha",
            "Futures liquidation, fees by tier, minimum lots and real fills are not modeled",
            "Independent future forward evidence is required before live promotion",
        ],
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline-dir",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args(argv)
    folder=Path(a.offline_dir)
    frozen, hashes={},{}
    for symbol in DEFAULT_SYMBOLS:
        file=folder/(symbol+".candles.json.gz")
        with gzip.open(file,"rt",encoding="utf-8") as stream:
            bars=json.load(stream)
        frozen[symbol]=bars
        hashes[symbol]=hashlib.sha256(json.dumps(
            bars,separators=(",",":")).encode()).hexdigest()
    r=evaluate(frozen,fingerprints=hashes)
    output=Path(a.out)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("ISING LAB quantum_hardware=NO, annealer_exact_match=",
          r["annealer_exact_agreement"],flush=True)
    print("ISING LAB selected=",r["selected_features_train_only"],flush=True)
    print("ISING QAOA CLASSICAL emulation=",r["six_qubit_qaoa_classical_emulator"],
          flush=True)
    print("ISING LAB training n=",r["training_trade_count"],
          "mean_net_pct=",r["training_mean_per_symbol_pct"],
          "stress_pct=",r["training_mean_stress_pct"],flush=True)
    print("ISING LAB historical holdout mean_net_pct=",
          r["historical_holdout_mean_per_symbol_pct"],
          "stress_pct=",r["historical_holdout_mean_stress_pct"],flush=True)
    print("ISING LAB decoy comparison=",r["negative_control_random_side_flip"],
          flush=True)
    print("ISING LAB VERIFIED VERDICT=",r["verdict"],"NO ORDERS",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())

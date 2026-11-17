#!/usr/bin/env python3
"""TITAN Ω QSI +128% PAPER harvest experiment; absolutely NO live orders.

The target is 4.15 * 2.28 = 9.462 USDT on already-inspected OKX 15m
crypto perpetuals, using mathematically classically simulated 3-qubit QSI
signals LOCKED before this experiment. No new curve-fitted entries.
Hypothesis: reducing exposure AFTER realized +32% / +64% might
preserve gains while seeking +128%. Test fixed x3 and x10, x10->x5
after +32, x10->x3 after +64, x10->x5->x3 staged.
Use same exact public contract sizes, ordinary vs harsh fees/slippage,
pessimistic 15m OHLC liquidation proxy, single-position execution.

All source markets were seen previously. This is RETROSPECTIVE,
not a clean unseen test, an exchange fill record or verified earnings.
No private OKX credentials or real orders; research-only workflow.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from trading import titan_quantum_survival_interferometer as qsi
from trading.edge_lab import TAKER_FEE,BASE_SLIPPAGE,STRESS_FEE,STRESS_SLIPPAGE
from trading.titan_qsi_target32_lock_test import load_original, public_specs, TARGET32
from trading.titan_qsi_plus64_profitlock import (
    validate_original_replay, TARGET64
)

TARGET128=round(qsi.START*2.28,6)
FROZEN_FAMILIES=qsi.POLICIES
COSTS={"ordinary":(TAKER_FEE,BASE_SLIPPAGE),
       "stress":(STRESS_FEE,STRESS_SLIPPAGE)}
MODES=("fixed3","fixed10","reduce5_after32","reduce3_after64",
       "reduce5_after32_reduce3_after64")


def leverage_for_realized_equity(equity,mode):
    """Exposure selection is based only on ACTUAL CLOSED paper account PnL."""
    if mode not in MODES or not 0<=equity<1000000:
        raise ValueError("Invalid closed equity or unregistered strategy")
    if mode=="fixed3":return 3.
    if mode=="fixed10":return 10.
    if mode=="reduce5_after32":
        return 5. if equity>=TARGET32 else 10.
    if mode=="reduce3_after64":
        return 3. if equity>=TARGET64 else 10.
    return 3. if equity>=TARGET64 else 5. if equity>=TARGET32 else 10.


def paper_lock128(markets,specs,signals,*,policy,mode,start,end,
                  fee,slip,goal=TARGET128,trade_func=None):
    """Exact original QSI rank/entry/one-position chronology; 128% stop
    *after* entire trade closes with net profit, never at a favorable wick.
    """
    if goal!=TARGET128 or mode not in MODES:
        raise ValueError("Cannot tune target or leverage schedule post-hoc")
    if policy not in FROZEN_FAMILIES or set(markets)!=set(specs) or set(markets)!=set(signals):
        raise ValueError("Missing source instruments or frozen QSI family")
    one=qsi.sim_one if trade_func is None else trade_func
    choices={}
    for sym in markets:
        for sig in signals[sym][policy]:
            idx=sig[0]
            if start<=idx and idx+1<end:
                choices.setdefault(idx,[]).append((sig[3],sym,sig))
    equity=qsi.START
    available=start
    rows=[]
    crossing=None
    realized_peak=equity
    used_after32=0
    used_after64=0
    for i in sorted(choices):
        if i<available or equity<=qsi.RUIN or equity>=goal:
            continue
        for _,sym,signal in sorted(choices[i],key=lambda z:(-z[0],z[1])):
            leverage=leverage_for_realized_equity(equity,mode)
            t=one(markets[sym],signal,specs[sym],equity=equity,
                  leverage=leverage,fee=fee,slip=slip,end=end)
            if t is None:continue
            if equity>=TARGET32:used_after32+=1
            if equity>=TARGET64:used_after64+=1
            equity=t["equity_after"]
            realized_peak=max(realized_peak,equity)
            available=t["exit_i"]+1
            rows.append(t)
            if equity>=goal:
                crossing=t["exit_i"]
            break
        if crossing is not None:
            break
    # Must explicitly record whether an original 10x hypothesis breaches
    # paper 0.83 ruin at any point, rather than counting only end state.
    ruined=any(t["equity_after"]<=qsi.RUIN for t in rows)
    fees=sum(t["entry_fee_usdt"]+t["exit_fee_usdt"] for t in rows)
    return {
        "start_usdt":qsi.START,
        "goal_usdt":goal,
        "mode":mode,
        "trades":len(rows),
        "end_usdt":round(equity,8),
        "return_pct":round(100*(equity/qsi.START-1),5),
        "peak_realized_equity_usdt":round(realized_peak,8),
        "plus32_closed_equity_reached":any(t["equity_after"]>=TARGET32 for t in rows),
        "plus64_closed_equity_reached":any(t["equity_after"]>=TARGET64 for t in rows),
        "plus128_goal_closed_equity_reached":equity>=goal,
        "plus128_first_realized_exit_index":crossing,
        "trades_started_after_plus32":used_after32,
        "trades_started_after_plus64":used_after64,
        "proxy_ruin_happened":ruined,
        "proxy_liquidation_events":sum(t["status"]=="liquidation_proxy" for t in rows),
        "fee_total_usdt":round(fees,8),
    }


def run(archive):
    markets,original,n=load_original(archive)
    specs=public_specs()  # public OKX minSz/lotSz/ctVal now, never private
    votes={sym:qsi.candidate_stream(rows) for sym,rows in markets.items()}
    splits,replayed=validate_original_replay(markets,specs,votes,original,n)
    if replayed!=48:raise ValueError("All 48 original QSI original results must replay")
    tests={}
    for family in FROZEN_FAMILIES:
        for mode in MODES:
            k=family+"_"+mode
            periods={}
            for period,(start,end) in splits.items():
                periods[period]={
                    label:paper_lock128(markets,specs,votes,policy=family,
                                       mode=mode,start=start,end=end,
                                       fee=fee,slip=slip)
                    for label,(fee,slip) in COSTS.items()}
            tests[k]=periods
    # PREDECLARED promotion: a success must be present with BOTH assumed
    # cost models, FIRST in train, and independently in BOTH holdouts.
    qualified=[name for name,r in tests.items() if (
        all(r["train"][cost]["plus128_goal_closed_equity_reached"]
            and not r["train"][cost]["proxy_ruin_happened"]
            and r["train"][cost]["trades"]>=24 for cost in COSTS))]
    selected=max(qualified,
                 key=lambda name:tests[name]["train"]["stress"]["return_pct"]
                ) if qualified else None
    held=bool(selected) and all(
        tests[selected][p][cost]["plus128_goal_closed_equity_reached"]
        and not tests[selected][p][cost]["proxy_ruin_happened"]
        for p in ("holdout_1","holdout_2") for cost in COSTS)
    return {
        "study":"TITAN_QSI_FROZEN_PLUS128_GOAL_RESEARCH_PAPER_ONLY",
        "start_usdt":qsi.START,"goal_plus128_usdt":TARGET128,
        "milestone_plus32_usdt":TARGET32,"milestone_plus64_usdt":TARGET64,
        "frozen_original_qsi_replay_checks":replayed,
        "all_source_market_sha256":original["raw_market_hashes"],
        "market_symbols":sorted(markets),
        "real_public_15m_candles":n*len(markets),
        "chronology":"60% training, 20% holdout_1, 20% holdout_2; independent equity resets",
        "old_and_new_hypotheses_are_post_hoc":True,
        "locked_model_families":list(FROZEN_FAMILIES),
        "locked_risk_modes":list(MODES),
        "candidates_predeclared":len(tests),
        "train_only_selected":selected,
        "training_qualified":qualified,
        "qualified_in_both_future_assumed_cost_historical_windows":held,
        "wait_zero_trade_benchmark":{"ending_usdt":qsi.START,"net_return_pct":0},
        "verdict":("RETROSPECTIVE_ONLY_NEEDS_UNSEEN_PROSPECTIVE_FORWARD"
                   if held else "NO_TRADE_NO_REPEATED_PLUS128_EDGE"),
        "not_real_user_balance":True,"no_private_api":True,
        "no_real_orders":True,"no_automations_created":True,
        "disclaimers":[
            "Preselected target after seeing many positive and negative QSI historical results; no unseen independent validation.",
            "10x leveraged futures has an extreme small-account ruin risk.",
            "Public OKX current contract minimums may differ at dates of historical prices.",
            "OHLC-based execution is not real bid/ask spread, liquidity, mark price liquidation, account tier fees or actual funding.",
            "Classically simulated quantum-inspired algorithm is not quantum hardware or a proven quantum edge.",
            "A simulated hit at +128 cannot establish expected return or real user profitability."
        ],
        "results":tests,
    }


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--original",required=True)
    p.add_argument("--out",default="reports/titan_qsi_128_paper.json")
    a=p.parse_args(argv)
    report=run(a.original)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("QSI128 ORIGINAL REPLAY PASS",report["frozen_original_qsi_replay_checks"],flush=True)
    for name,v in report["results"].items():
        print("QSI128 RESULT",name,"TRAIN",v["train"]["ordinary"],
              "TRAIN_STRESS",v["train"]["stress"]["return_pct"],
              "H1",v["holdout_1"]["ordinary"],
              "H1_STRESS",v["holdout_1"]["stress"]["return_pct"],
              "H2",v["holdout_2"]["ordinary"],
              "H2_STRESS",v["holdout_2"]["stress"]["return_pct"],flush=True)
    print("QSI128 FINAL",report["verdict"],"train_choice",
          report["train_only_selected"],"NO ORDERS",flush=True)


if __name__=="__main__":
    main()

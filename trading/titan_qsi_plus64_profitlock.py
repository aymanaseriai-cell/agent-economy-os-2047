#!/usr/bin/env python3
"""TITAN QSI 4.15 to +64% (6.806 USDT) — one-off retrospective falsification.

A previous QSI 10x paper simulation reached 32% before failing to show a
repeatable stressed edge. Test whether a REALIZED-only 32% profit milestone,
followed by reduced exposure to 5x or 3x, can reach 64% before ruin.

All four original QSI trading policies remain COMPLETELY FROZEN. The
same six original public OKX crypto instruments and immutable public 15m
candles are SHA256-verified. The original QSI simulation must replay
within 1e-6 USDT for all 48 policy/period/cost combinations BEFORE target
or sizing experiments. Uses QSI current public lot-size verification,
conservative next-open/stop-first/approximate liquidation and stress fees.
No private credentials, real orders, real account reads or automation.

RESEARCH LIMITATION: user picked 64% AFTER previous holdout and 32% results;
ALL historical results here are RETROSPECTIVE AND MULTIPLY TESTED, never proof
of forward profitability, true executable fills, or quantum superiority.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path

from trading import titan_quantum_survival_interferometer as qsi
from trading.edge_lab import TAKER_FEE,BASE_SLIPPAGE,STRESS_FEE,STRESS_SLIPPAGE
from trading.titan_qsi_target32_lock_test import load_original,public_specs,target_book,TARGET32

TARGET64=round(qsi.START*1.64,6)
FAMILIES=qsi.POLICIES
LEVERAGES=(3.,10.)
WINDOWS=("train","holdout_1","holdout_2")
COSTS={"ordinary":(TAKER_FEE,BASE_SLIPPAGE),"stress":(STRESS_FEE,STRESS_SLIPPAGE)}
MODES=("fixed","after32_reduce5","after32_reduce3")
CANDIDATE_TESTS=len(FAMILIES)*(1+len(MODES))


def effective_leverage(equity,original,mode):
    """Only *already realized* equity can reduce subsequent exposure.

    No future price, intrabar high, target exit-price or oracle required.
    Do NOT raise leverage when account is below +32% of initial capital.
    """
    if mode not in MODES or original not in LEVERAGES:
        raise ValueError("Unexpected precommitted risk option")
    if mode=="fixed" or original==3 or equity<TARGET32:
        return original
    return 5. if mode=="after32_reduce5" else 3.


def book_with_gate(markets,specs,signals,*,policy,leverage,start,end,
                   fee,slip,mode="fixed",goal=TARGET64,
                   executor=None):
    """QSI target_book reuses the same exact single-position trade chronology.

    The only added variation: after an ALREADY CLOSED trade yields +32%,
    future positions use 5x or 3x instead of original 10x. Does not stop
    or assume an exchange exit while an existing trade remains open.
    """
    execution=qsi.sim_one if executor is None else executor
    applied=[]
    def trade(bars,signal,spec,*,equity,leverage,fee,slip,end):
        effective=effective_leverage(equity,leverage,mode)
        applied.append((float(equity),float(effective)))
        return execution(bars,signal,spec,equity=equity,leverage=effective,
                         fee=fee,slip=slip,end=end)
    result=target_book(markets,specs,signals,
                       policy=policy,leverage=leverage,start=start,end=end,
                       fee=fee,slip=slip,goal=goal,one_trade=trade)
    result.pop("trade_log")
    result["risk_mode"]=mode
    result["stage32_activated_on_new_entry"]=any(
        lev<leverage and equity>=TARGET32 for equity,lev in applied)
    result["max_paper_leverage_used"]=max((v for _,v in applied),default=0)
    result["paper_trades_after_32_stage"]=sum(
        equity>=TARGET32 for equity,_ in applied)
    return result


def validate_original_replay(markets,specs,votes,original,n):
    """Abort on changes to metadata, historical source, QSI decision logic."""
    cut=int(n*.6);mid=cut+(n-cut)//2
    ranges={"train":(qsi.WARMUP,cut),"holdout_1":(cut,mid),
            "holdout_2":(mid,n)}
    count=0
    for family in FAMILIES:
        for leverage in LEVERAGES:
            key=family+"_"+str(int(leverage))+"x"
            for period,(start,end) in ranges.items():
                for cost,(fee,slip) in COSTS.items():
                    original_value=original["all_results"][key][period][
                        "normal" if cost=="ordinary" else "stress"]["ending_usdt"]
                    reproduced=qsi.paper_portfolio(markets,specs,votes,
                        policy=family,leverage=leverage,start=start,end=end,
                        fee=fee,slip=slip)["ending_usdt"]
                    if abs(original_value-reproduced)>0.000001:
                        raise ValueError("Original QSI reference replay mismatch: "+
                                         key+" "+period+" "+cost)
                    count+=1
    return ranges,count


def research(archive_dir):
    markets,original,n=load_original(archive_dir)
    specs=public_specs()
    votes={s:qsi.candidate_stream(b) for s,b in markets.items()}
    ranges,checks=validate_original_replay(markets,specs,votes,original,n)
    models={}
    for family in FAMILIES:
        for lev in LEVERAGES:
            modes=MODES if lev==10 else ("fixed",)
            for mode in modes:
                key=family+"_"+str(int(lev))+"x_"+mode
                periods={}
                for period,(start,end) in ranges.items():
                    cost_rows={}
                    for label,(fee,slip) in COSTS.items():
                        cost_rows[label]=book_with_gate(
                            markets,specs,votes,policy=family,leverage=lev,
                            mode=mode,start=start,end=end,fee=fee,slip=slip)
                    periods[period]=cost_rows
                models[key]=periods

    # Holdout data NEVER used to choose preferred model. A candidate must
    # reach the target (realized, not high wick) on train normal AND stress,
    # with enough trading days and without simulated ruin first.
    training_eligible=[name for name,p in models.items() if
        p["train"]["ordinary"]["reached_and_locked_32_at_close"]
        and p["train"]["stress"]["reached_and_locked_32_at_close"]
        and not p["train"]["ordinary"]["paper_ruin"]
        and not p["train"]["stress"]["paper_ruin"]
        and p["train"]["ordinary"]["trades"]>=24
        and p["train"]["stress"]["trades"]>=24]
    chosen=(max(training_eligible,
        key=lambda name:models[name]["train"]["stress"]["return_pct"])
        if training_eligible else None)
    repeat=bool(chosen) and all(
        models[chosen][period][cost]["reached_and_locked_32_at_close"]
        and not models[chosen][period][cost]["paper_ruin"]
        for period in ("holdout_1","holdout_2") for cost in COSTS)
    return {
        "experiment":"TITAN_QSI_PLUS64_REALIZED_PROFIT_LOCK_PAPER_NO_ORDERS",
        "initial_paper_usdt":qsi.START,
        "milestone_plus32_usdt":TARGET32,
        "goal_plus64_usdt":TARGET64,
        "prior_plus100_goal_usdt":qsi.TARGET,
        "timeframes":"60% train, two 20% chronological historical holdout windows",
        "market_symbols":list(sorted(markets)),
        "completed_public_15m_ohlc_bars":n*len(markets),
        "source_market_sha256":original["raw_market_hashes"],
        "original_qsi_replay_passed":True,
        "original_qsi_replay_checks":checks,
        "public_contract_metadata":"current public OKX instruments, not historical exchange-user account fills",
        "candidate_models":len(models),
        "precommitted_variants":list(MODES),
        "all_models_train_eligible":training_eligible,
        "selected_using_training_only":chosen,
        "selected_repeats_plus64_normal_and_stress":repeat,
        "zero_trade_baseline":{"paper_end_usdt":qsi.START,"net_pct":0},
        "verdict":("HISTORICAL_ONLY_INDEPENDENT_PROOF_REQUIRED" if repeat
                   else "NO_TRADE_NO_REPEATABLE_PROVEN_PLUS64_EDGE"),
        "no_real_account_read":True,
        "no_private_api":True,
        "no_real_orders":True,
        "not_prospective":True,
        "warnings":[
            "Post-hoc goal 64% was selected after seeing 32% historical results; already inspected six assets are NOT independent",
            "All winning historical positive results count only as retrospective path existence, NOT future-profit evidence",
            "10x not recommended; baseline history shows severe train losses and 0.83 ruin breaches",
            "OHLC bars do not reconstruct actual stop execution, real funding, spread/orderbook or mark-price liquidation",
            "Public contract minSz/lotSz/ctVal are current public info; user account permissions and real fills unverified",
            "Realized-profit gate stops NEW paper entries only after previously OPEN position fully closes"
        ],
        "results":models
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True)
    p.add_argument("--out",default="reports/titan_qsi_plus64_paper.json")
    args=p.parse_args(argv)
    report=research(args.input)
    output=Path(args.out)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("PLUS64 ORIGINAL QSI REPLAY CHECKS",report["original_qsi_replay_checks"],
          "PASS",report["original_qsi_replay_passed"],flush=True)
    for name,parts in report["results"].items():
        print("PLUS64 MODEL",name,
              "TRAIN",parts["train"]["ordinary"]["return_pct"],
              "TRAIN_STRESS",parts["train"]["stress"]["return_pct"],
              "H1",parts["holdout_1"]["ordinary"],
              "H1_STRESS",parts["holdout_1"]["stress"]["return_pct"],
              "H2",parts["holdout_2"]["ordinary"],
              "H2_STRESS",parts["holdout_2"]["stress"]["return_pct"],
              flush=True)
    print("PLUS64 VERDICT",report["verdict"],
          "SELECTED",report["selected_using_training_only"],"NO ORDERS",flush=True)

if __name__=="__main__":
    main()

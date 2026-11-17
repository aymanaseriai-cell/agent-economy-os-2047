#!/usr/bin/env python3
"""QSI 32% realized-profit lock: repeat original real-micro-contract paper trial.

Goal: verify if pre-frozen 3-qubit QSI strategy that *historically* ended at
+42.34% in ONE ordinary-cost holdout would actually have hit and locked +32%
when all NEW paper entries STOP upon realizing >=5.478 USDT from 4.15.
Runs all four QSI policies ×3x/10x ×60/20/20 train and heldout half periods
and both ordinary/STRESS execution frictions. Uses the actual archived
completed 15-minute OKX candles and FRESH public contract details; verifies
every SHA-256 against the original real dataset manifest, and replays the
original untouched policy before applying the 32% exit rule.

Post-hoc target suggested after viewing old positive holdout, so this is
NOT independent OOS, not evidence of repeatable profitability and not a
permitted live trade. No orders/private endpoints are used.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,statistics
from datetime import datetime,timezone
from pathlib import Path

from trading import titan_quantum_survival_interferometer as qsi
from trading.edge_lab import TAKER_FEE,BASE_SLIPPAGE,STRESS_FEE,STRESS_SLIPPAGE
from trading.titan_regime_research import validate_frozen

TARGET32=round(qsi.START*1.32,6)
EXPECTED_SYMBOLS=(
    "1INCH-USDT-SWAP","BLUR-USDT-SWAP","CFX-USDT-SWAP",
    "LPT-USDT-SWAP","XTZ-USDT-SWAP","ZK-USDT-SWAP")
POLICIES=qsi.POLICIES
LEVERAGES=(3.,10.)
PERIODS=("train","holdout_1","holdout_2")
COSTS={"ordinary":(TAKER_FEE,BASE_SLIPPAGE),
       "stress":(STRESS_FEE,STRESS_SLIPPAGE)}


def load_original(indir):
    root=Path(indir)
    manifest=json.loads((root/"titan_qsi_4_15_usdt.json").read_text())
    assert set(manifest["chosen_public_markets"])==set(EXPECTED_SYMBOLS)
    assert len(manifest["raw_market_hashes"])==6
    markets={}
    for symbol in EXPECTED_SYMBOLS:
        gz=root/"titan_qsi_raw_candles"/(symbol+".json.gz")
        raw=gzip.decompress(gz.read_bytes())
        checksum=hashlib.sha256(raw).hexdigest()
        if checksum!=manifest["raw_market_hashes"][symbol]:
            raise ValueError("Original OKX historical data integrity mismatch")
        bars=json.loads(raw)
        validate_frozen(bars)
        if len(bars)<5600:
            raise ValueError("Incomplete archived 15-minute market")
        markets[symbol]=bars
    n=min(len(m) for m in markets.values())
    reference=[b["ts"] for b in markets[EXPECTED_SYMBOLS[0]][:n]]
    if any([b["ts"] for b in v[:n]]!=reference for v in markets.values()):
        raise ValueError("Original public OHLC candle clock mismatches")
    return markets,manifest,n


def public_specs():
    # The exact same public, non-private QSI instrument catalogue as the
    # original historical study; fails if the deterministic six changed.
    specs,count=qsi.public_instruments()
    data={x["instId"]:x for x in specs}
    if set(data)!=set(EXPECTED_SYMBOLS):
        raise ValueError("Public contract universe changed; cannot silently replay")
    for symbol,meta in data.items():
        if not all(meta.get(k) is not None for k in
                   ("minSz","lotSz","ctVal","ctType","state")):
            raise ValueError("Incomplete public contract meta: "+symbol)
    return data


def target_book(markets,specs,votes,*,policy,leverage,start,end,fee,slip,
                goal=TARGET32,one_trade=qsi.sim_one):
    """Original QSI single-position selection, with post-CLOSE target lock.

    This is strictly *realized* equity. It never pretends to close an
    in-progress trade at a favorable OHLC intra-candle high.
    """
    if goal<=qsi.START or goal>qsi.TARGET:
        raise ValueError("Target must be between start and original goal")
    equity=qsi.START
    positions={}
    for symbol in markets:
        for signal in votes[symbol][policy]:
            i=signal[0]
            if start<=i and i+1<end:
                positions.setdefault(i,[]).append((signal[3],symbol,signal))
    all_trades=[]
    available=start
    first_hit=None
    for i in sorted(positions):
        if i<available or equity<=qsi.RUIN or equity>=goal:
            continue
        for _,symbol,signal in sorted(positions[i],key=lambda x:(-x[0],x[1])):
            result=one_trade(markets[symbol],signal,specs[symbol],
                             equity=equity,leverage=leverage,fee=fee,slip=slip,end=end)
            if result is None:continue
            equity=result["equity_after"]
            available=result["exit_i"]+1
            result["symbol"]=symbol
            all_trades.append(result)
            if equity>=goal and first_hit is None:
                first_hit=result["exit_i"]
            break
        if first_hit is not None:
            break
    high=max([qsi.START]+[x["equity_after"] for x in all_trades])
    costs=sum(t["entry_fee_usdt"]+t["exit_fee_usdt"] for t in all_trades)
    return {
        "target_usdt":goal,
        "trades":len(all_trades),
        "ending_usdt":round(equity,8),
        "return_pct":round(100*(equity/qsi.START-1),5),
        "reached_and_locked_32_at_close":equity>=goal,
        "first_target_hit_exit_index":first_hit,
        "peak_realized_usdt":round(high,8),
        "fee_total_usdt":round(costs,8),
        "paper_ruin":equity<=qsi.RUIN,
        "trade_log":all_trades,
    }


def research(indir):
    markets,original,n=load_original(indir)
    specs=public_specs()
    votes={s:qsi.candidate_stream(b) for s,b in markets.items()}
    split=int(n*.60);middle=split+(n-split)//2
    ranges={"train":(qsi.WARMUP,split),
            "holdout_1":(split,middle),
            "holdout_2":(middle,n)}
    report={}
    baseline_verified={}
    for policy in POLICIES:
        for leverage in LEVERAGES:
            key=policy+"_"+str(int(leverage))+"x"
            out={}
            for phase,(a,b) in ranges.items():
                series={}
                for frictions,(fee,slip) in COSTS.items():
                    original_b=qsi.paper_portfolio(
                        markets,specs,votes,policy=policy,leverage=leverage,
                        start=a,end=b,fee=fee,slip=slip)
                    # Before altering profit exit rule reproduce exact logged
                    # original historical results; otherwise fail closed.
                    expected=original["all_results"][key][phase][
                        "normal" if frictions=="ordinary" else "stress"]["ending_usdt"]
                    if abs(original_b["ending_usdt"]-expected)>0.000001:
                        raise ValueError("QSI original replay mismatch: "+key+" "+phase+
                                         " "+frictions+" current "+str(original_b["ending_usdt"])+
                                         " archived "+str(expected))
                    variant=target_book(
                        markets,specs,votes,policy=policy,leverage=leverage,
                        start=a,end=b,fee=fee,slip=slip)
                    series[frictions]={
                        "original_qsi_end_usdt":original_b["ending_usdt"],
                        "original_qsi_trades":original_b["trades"],
                        "target_locked":{k:v for k,v in variant.items()
                                         if k!="trade_log"}}
                    baseline_verified[key+":"+phase+":"+frictions]=True
                out[phase]=series
            report[key]=out

    eligible=[]
    for key,d in report.items():
        t=d["train"]
        a=t["ordinary"]["target_locked"]
        b=t["stress"]["target_locked"]
        if (a["trades"]>=24 and a["return_pct"]>0
            and b["return_pct"]>0 and a["reached_and_locked_32_at_close"]
            and b["reached_and_locked_32_at_close"]
            and not a["paper_ruin"] and not b["paper_ruin"]):
            eligible.append(key)
    chosen=max(eligible,key=lambda x:report[x]["train"][
        "stress"]["target_locked"]["return_pct"]) if eligible else None
    holdout_persist=bool(chosen) and all(
        report[chosen][part][cost]["target_locked"][
            "reached_and_locked_32_at_close"] for part in ("holdout_1","holdout_2")
        for cost in COSTS)
    result={
        "experiment":"TITAN_QSI_RETROSPECTIVE_REALIZED_32_LOCK_AUDIT_NO_ORDERS",
        "exploratory_not_independent":True,
        "explanation":"User requested +32 after original QSI +42.34 holdout already observed; using same prices is retrospective and subject to data snooping.",
        "target32_usdt":TARGET32,
        "start_usdt":qsi.START,
        "initial_value_of_target32_pct":32,
        "public_symbols":list(EXPECTED_SYMBOLS),
        "original_completed_15m_bars":n*len(markets),
        "original_hashes_verified":original["raw_market_hashes"],
        "original_reference_run":"https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/runs/44030465243",
        "original_six_market_paper_replay_passed":all(baseline_verified.values()),
        "original_replay_checks":len(baseline_verified),
        "separate_60_20_20_periods":True,
        "train_only_qualified":eligible,
        "train_only_choice":chosen,
        "all_cost_and_holdout_crossing_proven":holdout_persist,
        "verdict":"HISTORICAL_ONLY_CANNOT_VERIFY_FUTURE" if holdout_persist
                else "NO_TRADE_NO_REPEATED_32_PERCENT_EDGE",
        "no_private_api":True,"no_orders":True,"not_real_user_balance":True,
        "results":report,
        "limitations":[
            "Prior study had already inspected all six asset returns and the +42.34% holdout result",
            "Targeting 32% after seeing that outcome is NOT prospective, independent, or proof of future edge",
            "PAPER min lots use a current PUBLIC instrument descriptor; spec could differ historically",
            "Historical OHLC is not a true mark-liquidation/orderbook/latency/funding ledger",
            "10x high leverage can easily deplete a 4.15 USDT account",
            "If stress outcomes or training do not clear the target, do NOT promote to real trades"
        ]
    }
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--out",default="reports/titan_qsi_32_profitlock_paper.json")
    args=p.parse_args(argv)
    result=research(args.input)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("QSI ORIGINAL REPLAY CHECKS",result["original_replay_checks"],
          "ALL",result["original_six_market_paper_replay_passed"],flush=True)
    for name,p in result["results"].items():
        print("QSI TARGET32",name,
              "TRAIN",p["train"]["ordinary"]["target_locked"],
              "H1",p["holdout_1"]["ordinary"]["target_locked"],
              "H1_STRESS",p["holdout_1"]["stress"]["target_locked"],
              "H2",p["holdout_2"]["ordinary"]["target_locked"],
              "H2_STRESS",p["holdout_2"]["stress"]["target_locked"],flush=True)
    print("QSI FINAL",result["verdict"],
          "TRAIN_ELIGIBLE",result["train_only_qualified"],
          "NO ORDERS",flush=True)


if __name__=="__main__":
    main()

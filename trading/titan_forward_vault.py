#!/usr/bin/env python3
"""TITAN sealed forward-paper audit: record NOW, score LATER, NO ORDERS.

All input market data are public completed OKX 15m candles. Prediction records
are sealed BEFORE their future entry candle. The later scorer NEVER recomputes
the original signal. This is NOT exchange execution or a claim of profitable
trading. No private credentials, account balances, orders, leverage or TP/SL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from trading.edge_lab import (
    BAR_MS, DEFAULT_SYMBOLS, TAKER_FEE, BASE_SLIPPAGE,
    STRESS_FEE, STRESS_SLIPPAGE, FUNDING_PER_8H, fetch_history,
)
from trading.titan_quantum_ising_lab import (
    FAMILIES, candidate_signals, votes_consensus,
)
from trading.titan_regime_research import validate_frozen

ENSEMBLE_MEMBERS = ("regime_pullback", "squeeze_release", "shock_recovery")
STRATEGIES = FAMILIES + ("locked_ising_consensus",)
SEAL_MODE = "PRE_REGISTERED_FUTURE_15M_OHLC_SHADOW_NO_ORDERS"
BAR_HORIZON = 4
TARGET_830 = 8.30
START_415 = 4.15
HISTORY_DAYS = 5
MAX_LATEST_BAR_STALENESS_MS = 2 * BAR_MS


def _canonical(obj):
    return json.dumps(obj, ensure_ascii=True,sort_keys=True,
                      separators=(",",":"),allow_nan=False).encode("utf-8")


def _hash(obj):
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _utc(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()


def _lookback_signal(bars):
    """Artificial future candle is NEVER read in a historical signal decision.

    Existing signal functions intentionally exclude their last candle, so
    append a placeholder at t+1 and read ONLY the last REAL completed candle.
    The placeholder OHLC is set to the last completed close (not future data).
    """
    validate_frozen(bars)
    anchor=len(bars)-1
    close=float(bars[-1]["close"])
    placeholder={"ts":bars[-1]["ts"]+BAR_MS,"open":close,
                 "high":close,"low":close,"close":close}
    with_placeholder=bars+[placeholder]
    family_rows=[candidate_signals(with_placeholder,name) for name in FAMILIES]
    selected=tuple(FAMILIES.index(name) for name in ENSEMBLE_MEMBERS)
    ensemble=votes_consensus(family_rows,selected)
    side_by_name={}
    for family,rows in zip(FAMILIES, family_rows):
        side_by_name[family] = rows[-1][1] if rows and rows[-1][0]==anchor else 0
    side_by_name["locked_ising_consensus"] = (
        ensemble[-1][1] if ensemble and ensemble[-1][0]==anchor else 0)
    return side_by_name


def capture(*, sealed_ms=None, get_bars=fetch_history, git_sha="unknown", run_id="unknown"):
    """Pre-register decisions with next entry strictly after start timestamp."""
    sealed_ms=int(time.time()*1000) if sealed_ms is None else int(sealed_ms)
    if sealed_ms <= 0:
        raise ValueError("Invalid creation timestamp")
    # ENTRY intentionally starts at least 15m in the future, never at current
    # partially formed candle; allows for GitHub public fetch latency.
    entry=(sealed_ms//BAR_MS + 2)*BAR_MS
    final_bar_start=entry+(BAR_HORIZON-1)*BAR_MS
    mature_at=entry+BAR_HORIZON*BAR_MS
    rows=[]
    for symbol in DEFAULT_SYMBOLS:
        bars=get_bars(symbol,HISTORY_DAYS,now_ms=sealed_ms)
        validate_frozen(bars)
        last=bars[-1]["ts"]
        if (last+BAR_MS>sealed_ms or
                sealed_ms-(last+BAR_MS)>MAX_LATEST_BAR_STALENESS_MS):
            raise ValueError("No recent completed public history for " +symbol)
        current=_lookback_signal(bars)
        rows.append({
            "symbol":symbol,
            "last_completed_bar_start_ms":last,
            "latest_completed_candle_sha256":_hash(bars[-1]),
            "signals":{name:current[name] for name in STRATEGIES},
        })
    result={
        "mode":SEAL_MODE,
        "created_at_ms":sealed_ms,
        "created_at_utc":_utc(sealed_ms),
        "source_git_sha":str(git_sha),
        "source_github_run_id":str(run_id),
        "start_balance_usdt_not_account_verified":START_415,
        "target_balance_usdt":TARGET_830,
        "symbol_count":len(DEFAULT_SYMBOLS),
        "strategy_names":list(STRATEGIES),
        "ensemble_members_locked_from_prior_experiment":list(ENSEMBLE_MEMBERS),
        "entry_open_future_ms":entry,
        "exit_bar_start_ms":final_bar_start,
        "score_not_before_ms":mature_at,
        "horizon_candles":BAR_HORIZON,
        "costs": {"fee":TAKER_FEE, "slippage":BASE_SLIPPAGE,
                  "stress_fee":STRESS_FEE,"stress_slippage":STRESS_SLIPPAGE,
                  "funding_8h_assumption":FUNDING_PER_8H},
        "signals_from_public_completed_bars_only":True,
        "no_live_orders":True,
        "snapshot_rows":rows,
    }
    result["seal_sha256"]=_hash(result)
    return result


def _validate_seal(seal):
    if not isinstance(seal,dict):
        raise ValueError("Missing sealed evidence")
    original={k:v for k,v in seal.items() if k!="seal_sha256"}
    if seal.get("seal_sha256")!=_hash(original):
        raise ValueError("Seal hash mismatch: historical record was changed")
    if (seal.get("mode")!=SEAL_MODE or seal.get("strategy_names")!=list(STRATEGIES)
            or seal.get("symbol_count")!=len(DEFAULT_SYMBOLS)
            or seal.get("ensemble_members_locked_from_prior_experiment")
                  !=list(ENSEMBLE_MEMBERS)
            or seal.get("horizon_candles")!=BAR_HORIZON
            or seal.get("start_balance_usdt_not_account_verified")!=START_415
            or seal.get("target_balance_usdt")!=TARGET_830
            or seal.get("signals_from_public_completed_bars_only") is not True
            or seal.get("no_live_orders") is not True):
        raise ValueError("Unexpected untrusted capture schema")
    start,end,mature,created=(seal["entry_open_future_ms"],
                             seal["exit_bar_start_ms"],
                             seal["score_not_before_ms"],
                             seal["created_at_ms"])
    if (not all(type(v)==int and v>0 for v in (start,end,mature,created))
            or start<=created or start % BAR_MS
            or end != start+(BAR_HORIZON-1)*BAR_MS
            or mature != start+BAR_HORIZON*BAR_MS):
        raise ValueError("Capture horizon or chronology invalid")
    if not isinstance(seal.get("snapshot_rows"),list):
        raise ValueError("Missing sealed rows")
    names=[]
    for row in seal["snapshot_rows"]:
        symbol=row.get("symbol")
        if symbol not in DEFAULT_SYMBOLS or row.get("last_completed_bar_start_ms",0)+BAR_MS>created:
            raise ValueError("Forbidden or post-seal input candle")
        if (not isinstance(row.get("signals"),dict)
                or set(row["signals"])!=set(STRATEGIES)
                or any(type(v)!=int or v not in (-1,0,1)
                       for v in row["signals"].values())):
            raise ValueError("Unexpected signal vocabulary")
        names.append(symbol)
    if sorted(names)!=sorted(DEFAULT_SYMBOLS):
        raise ValueError("Duplicate or missing frozen symbols")
    if seal.get("costs")!={"fee":TAKER_FEE,"slippage":BASE_SLIPPAGE,
         "stress_fee":STRESS_FEE,"stress_slippage":STRESS_SLIPPAGE,
         "funding_8h_assumption":FUNDING_PER_8H}:
        raise ValueError("Attempt to change precommitted costs")
    return True


def _net_return(side, entry, exit_price, *, fee,slip):
    if side not in (-1,1) or min(entry,exit_price)<=0:
        raise ValueError("Invalid scored trade")
    adjusted_entry=entry*(1+side*slip)
    adjusted_exit=exit_price*(1-side*slip)
    gross=side*(adjusted_exit/adjusted_entry-1)
    cost=fee*(1+adjusted_exit/adjusted_entry)
    funding=FUNDING_PER_8H*BAR_HORIZON/32
    return (gross-cost-funding)*100


def score(seal, *, now_ms=None, get_bars=fetch_history):
    """Score only mature future OHLC. Never recompute or retro-fit signals."""
    _validate_seal(seal)
    now_ms=int(time.time()*1000) if now_ms is None else int(now_ms)
    if now_ms < seal["score_not_before_ms"]:
        raise ValueError("Future label is not yet matured; never score early")
    scores=[]
    for frozen in seal["snapshot_rows"]:
        symbol=frozen["symbol"]
        bars=get_bars(symbol,HISTORY_DAYS,now_ms=now_ms)
        validate_frozen(bars)
        by_ts={b["ts"]:b for b in bars}
        starts=[seal["entry_open_future_ms"]+i*BAR_MS for i in range(BAR_HORIZON)]
        if any(t not in by_ts or t+BAR_MS>now_ms for t in starts):
            raise ValueError("Future completed candles missing: "+symbol)
        entry=float(by_ts[starts[0]]["open"])
        exit_price=float(by_ts[starts[-1]]["close"])
        for family,side in frozen["signals"].items():
            rec={"symbol":symbol,"family":family,
                 "predicted_side_precommitted":side,
                 "signal_entered_after_seal":starts[0]>seal["created_at_ms"],
                 "status":"NO_SIGNAL" if side==0 else "MATURED_SHADOW",
                 "entry_open_ms":starts[0],"horizon_mature_ms":seal["score_not_before_ms"]}
            if side:
                rec["model_net_pct"]=round(_net_return(
                    side,entry,exit_price,fee=TAKER_FEE,slip=BASE_SLIPPAGE),6)
                rec["stress_net_pct"]=round(_net_return(
                    side,entry,exit_price,fee=STRESS_FEE,
                    slip=STRESS_SLIPPAGE),6)
            scores.append(rec)
    summary={}
    for family in STRATEGIES:
        rows=[x for x in scores if x["family"]==family and
              x["status"]=="MATURED_SHADOW"]
        summary[family]={
            "matured_signal_count":len(rows),
            "positive_signals_after_costs":sum(x["model_net_pct"]>0 for x in rows),
            "net_mean_pct":round(sum(x["model_net_pct"] for x in rows)/len(rows),6)
                           if rows else None,
            "stress_net_mean_pct":round(sum(x["stress_net_pct"] for x in rows)/len(rows),6)
                                  if rows else None,
            "validated_profitable_edge":False,
        }
    return {
        "mode":"MATURED_UNTOUCHED_FORWARD_OHLC_SHADOW_NO_ORDERS",
        "seal_sha256":seal["seal_sha256"],
        "original_capture_run_id":seal["source_github_run_id"],
        "original_capture_commit":seal["source_git_sha"],
        "capture_created_utc":seal["created_at_utc"],
        "entry_open_future_utc":_utc(seal["entry_open_future_ms"]),
        "scored_at_utc":_utc(now_ms),
        "required_market_horizon_minutes":BAR_HORIZON*15,
        "strategy_results":summary,
        "records":scores,
        "account_double_probability":None,
        "account_liquidation_probability":None,
        "live_orders":0,
        "forward_market_quotes_not_order_fills":True,
        "caveat":"One 60m observation on six correlated markets; no live fills, SL or TP. Repeated future samples needed.",
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="phase",required=True)
    c=sub.add_parser("capture")
    c.add_argument("--out",required=True)
    s=sub.add_parser("score")
    s.add_argument("--sealed",required=True)
    s.add_argument("--out",required=True)
    opts=p.parse_args(argv)
    if opts.phase=="capture":
        report=capture(git_sha=os.environ.get("GITHUB_SHA","unknown"),
                       run_id=os.environ.get("GITHUB_RUN_ID","unknown"))
        if int(time.time()*1000)>=report["entry_open_future_ms"]:
            raise ValueError("Capture took too long; future entry is no longer future")
        out=Path(opts.out)
        print("FORWARD SEALED",report["seal_sha256"],
              "github_run_id",report["source_github_run_id"],
              "entry_utc",_utc(report["entry_open_future_ms"]),
              "mature_utc",_utc(report["score_not_before_ms"]),
              "directional_signals",sum(v!=0 for row in report["snapshot_rows"]
                                        for v in row["signals"].values()),
              "NO_ORDERS",flush=True)
    else:
        seal=json.loads(Path(opts.sealed).read_text(encoding="utf-8"))
        report=score(seal)
        out=Path(opts.out)
        print("FORWARD SCORED",report["seal_sha256"],
              "capture_run_id",report["original_capture_run_id"],
              "summary",report["strategy_results"],
              "NO_ORDERS",flush=True)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return 0


if __name__=="__main__":
    raise SystemExit(main())

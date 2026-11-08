#!/usr/bin/env python3
"""Falsification/robustness diagnostics on *actual archived* 6+7 council signals.

No private credentials, no order placement, no network calls, no strategy
optimization. Repeats are correlated, and reversal/placebo are diagnostics,
NOT independently sourced alternative trading strategies.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from .council_forward_audit import (
    BAR_MS, audit_signal, utc_ms, validate_bars
)

HORIZON = 4
LOOKBACK_MS = 18 * 3600 * 1000
STRESS_TAKER_FEE = .0008
STRESS_SLIPPAGE = .001
STRESS_FUNDING_8H = .0002

def geometric_flip(signal: dict, bars: list[dict]) -> dict:
    """Opposite-side counterfactual, exactly matched % stop/target geometry.

    Uses original *next-open* for calculating percentage distances; does not
    borrow future price levels to choose the counterfactual direction.
    """
    start=((utc_ms(signal["published_utc"])+BAR_MS-1)//BAR_MS)*BAR_MS
    row=next((b for b in bars if b["ts"]==start),None)
    if row is None:
        raise ValueError("Missing original next-open")
    price=row["open"]
    stop_frac=abs(price-signal["stop"])/price
    target_frac=abs(price-signal["target"])/price
    if not 0<stop_frac<1 or not 0<target_frac<1:
        raise ValueError("Invalid stop/target geometry")
    side="SHORT" if signal["side"]=="LONG" else "LONG"
    d=1 if side=="LONG" else -1
    return {**signal,"side":side,
            "stop":price-d*stop_frac*price,
            "target":price+d*target_frac*price}

def placebo_outcomes(signal: dict, bars: list[dict], *, lookback_ms=LOOKBACK_MS):
    """Only earlier 1h windows ending BEFORE the report was published.

    Each synthetic sample keeps original side and same proportional stop/target
    distances, rescales them to that sample's *entry* open, and enters at that
    past open; unlike a post-event simulation, this cannot leak future prices
    into the historical placebo's reference window.
    """
    posted=utc_ms(signal["published_utc"])
    observed_start=((posted+BAR_MS-1)//BAR_MS)*BAR_MS
    by_ts={x["ts"]:x for x in bars}
    observed=by_ts.get(observed_start)
    if observed is None:
        raise ValueError("Frozen history misses actual signal entry")
    base_price=observed["open"]
    stop_frac=abs(signal["stop"]-base_price)/base_price
    target_frac=abs(signal["target"]-base_price)/base_price
    if not 0<stop_frac<1 or not 0<target_frac<1:
        raise ValueError("Invalid source protection geometry")
    d=1 if signal["side"]=="LONG" else -1
    out=[]
    for b in bars:
        ts=b["ts"]
        # No historical placebo uses an outcome candle that was incomplete
        # at the time the actual report was emitted.
        if not(posted-lookback_ms<=ts and ts+HORIZON*BAR_MS<=posted):
            continue
        sample={**signal,
                "published_utc":datetime.fromtimestamp((ts-1)/1000,timezone.utc).isoformat(),
                "stop":b["open"]-d*stop_frac*b["open"],
                "target":b["open"]+d*target_frac*b["open"]}
        row=audit_signal(sample,bars,HORIZON)
        if row["status"]=="matured":
            out.append(row["net_unlevered_notional_pct"])
    return out

def summarize_groups(rows):
    groups=defaultdict(list)
    for row in rows:
        groups[row["symbol"]].append(row["net_base_pct"])
    return {name:{"candidate_count":len(vals),"mean_net_pct":round(statistics.mean(vals),5),
                  "all_negative":all(v<0 for v in vals)}
            for name,vals in sorted(groups.items())}

def evaluate(provenance, histories):
    rows=[]
    for source in provenance["signals"]:
        candles=histories[source["symbol"]]
        validate_bars(candles)
        baseline=audit_signal(source,candles,HORIZON)
        if baseline["status"]!="matured":
            raise ValueError("Actual 1h observation must be complete")
        no_cost=audit_signal(source,candles,HORIZON,fee=0,slip=0,funding=0)
        stressed=audit_signal(source,candles,HORIZON,fee=STRESS_TAKER_FEE,
                              slip=STRESS_SLIPPAGE,funding=STRESS_FUNDING_8H)
        reversed_side=audit_signal(geometric_flip(source,candles),
                                   candles,HORIZON)
        historical=placebo_outcomes(source,candles)
        base_return=baseline["net_unlevered_notional_pct"]
        rows.append({
            "symbol":source["symbol"],"side":source["side"],
            "run_id":source["run_id"],"published_utc":source["published_utc"],
            "original_source_url":source["source_url"],
            "net_base_pct":base_return,
            "frictionless_pct":no_cost["net_unlevered_notional_pct"],
            "net_stress_pct":stressed["net_unlevered_notional_pct"],
            "cost_drag_pct":round(no_cost["net_unlevered_notional_pct"]-base_return,5),
            "reverse_direction_symmetric_R_net_pct":reversed_side.get("net_unlevered_notional_pct"),
            "reverse_direction_status":reversed_side["status"],
            "past_same_side_placebo_windows":len(historical),
            "past_placebo_mean_pct":round(statistics.mean(historical),5) if historical else None,
            "event_rank_pct_vs_past_placebo":round(100*sum(x<=base_return for x in historical)/len(historical),2) if historical else None,
            "comparison_limitations":"Overlapping earlier windows, same-asset regimes; no independent p-value",
        })
    for row in rows:
        if row["past_same_side_placebo_windows"]<10:
            raise ValueError("Insufficient earlier chronological matched windows")
    groups=summarize_groups(rows)
    report={
       "mode":"READ_ONLY_ARCHIVED_FULL_QUANT_COUNCIL_FALSIFICATION",
       "scope":"Original ex-ante 6-agent + 7-quant research labels; NVIDIA votes NOT observed",
       "limitations":[
         "Six overlapping signals on only three assets: correlated, not six independent trials.",
         "Counterfactual reverse side is hypothetical matched geometry, not AI-approved trades.",
         "Placebo is fixed same-side, same-symbol historical window, not a causal randomized control.",
         "18-hour lookback windows overlap and do not yield a statistically valid p-value.",
         "Fees/slippage/funding are explicit assumptions; real fills and NVIDIA gate absent.",
         "All original signal times were saved before the evaluated outcomes.",
         "A negative sample cannot prove a system will always lose."
       ],
       "assumptions":{
         "outcome_minutes":60,"placebo_past_lookback_hours":18,
         "base_taker_fee_each_side":.0005,"base_slippage_each_side":.0003,
         "base_funding_8h":.0001,
         "stress_taker_fee_each_side":STRESS_TAKER_FEE,
         "stress_slippage_each_side":STRESS_SLIPPAGE,
         "stress_funding_8h":STRESS_FUNDING_8H
       },
       "summary":{
         "signals":len(rows),"underlying_instruments":len(groups),
         "negative_baseline_count":sum(x["net_base_pct"]<0 for x in rows),
         "positive_baseline_count":sum(x["net_base_pct"]>0 for x in rows),
         "baseline_mean_pct":round(statistics.mean(x["net_base_pct"] for x in rows),5),
         "frictionless_mean_pct":round(statistics.mean(x["frictionless_pct"] for x in rows),5),
         "stressed_mean_pct":round(statistics.mean(x["net_stress_pct"] for x in rows),5),
         "reverse_direction_mean_pct":round(statistics.mean(x["reverse_direction_symmetric_R_net_pct"] for x in rows),5),
         "original_better_than_opposite_count":sum(x["net_base_pct"]>x["reverse_direction_symmetric_R_net_pct"] for x in rows),
         "placebo_median_event_percentile":round(statistics.median(x["event_rank_pct_vs_past_placebo"] for x in rows),2),
         "asset_cluster_results":groups,
         "no_verified_nvidia_approvals":True
       },
       "rows":rows
    }
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base",default="reports")
    ap.add_argument("--out",default="reports/council_adversarial_20261108.json")
    a=ap.parse_args()
    base=Path(a.base)
    prov=json.loads((base/"actual_council_signals_20261108.json").read_text())
    symbols=sorted({x["symbol"] for x in prov["signals"]})
    histories={s:json.loads((base/(s+".outcome_candles_20261108.json")).read_text()) for s in symbols}
    r=evaluate(prov,histories)
    r["source_sha256"]={f.name:hashlib.sha256(f.read_bytes()).hexdigest()
        for f in [base/"actual_council_signals_20261108.json"]+
        [base/(s+".outcome_candles_20261108.json") for s in symbols]}
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(r,indent=2,ensure_ascii=False)+"\n")
    for row in r["rows"]:
        print(row["symbol"],row["side"],"base",row["net_base_pct"],
              "no-cost",row["frictionless_pct"],"stress",row["net_stress_pct"],
              "reverse",row["reverse_direction_symmetric_R_net_pct"],
              "placebo_pct_rank",row["event_rank_pct_vs_past_placebo"],
              "placebo_count",row["past_same_side_placebo_windows"])
    print("SUMMARY",json.dumps(r["summary"]))
    print("REPORT",out)
    return 0
if __name__=="__main__":
    raise SystemExit(main())

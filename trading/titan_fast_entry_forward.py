#!/usr/bin/env python3
"""Fast Entry Forward Auditor: evaluate archived pre-committed public hypotheses.

Read-only. Forward OHLC outcome starts at NEXT full candle; no signal tuning,
trading API, private account endpoint, or automated promotion to live.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import statistics
import time

from trading.shadow_observatory import (
    BAR_MS, MAX_DAYS, TAKER_FEE, SLIPPAGE, FUNDING_PER_8H,
    fetch_public_candles, outcome, utc_ms, verify_snapshot,
)

FOUR_HOURS_MS = 4*3600*1000
DAY_MS = 24*3600*1000
MIN_EVIDENCE = 100
MIN_UTC_DAYS = 14
ALLOWED_STRATEGIES = frozenset((
    "20_bar_breakout","ema20_pullback","10_bar_liquidity_sweep",
))


def bootstrap_lower5(xs, repetitions=1000):
    """Fixed exploratory 5th percentile of bootstrap mean, not significance."""
    if len(xs) < 30:
        return None
    rng = random.Random(2047)
    size = len(xs)
    means=sorted(sum(xs[rng.randrange(size)] for _ in range(size))/size
                 for _ in range(repetitions))
    return round(means[int(.05*repetitions)],6)


def evaluate(snapshots, histories):
    if not isinstance(snapshots,list) or not isinstance(histories,dict):
        raise ValueError("Bad input collection")
    if len(snapshots)>200:
        raise ValueError("Audit capacity limit")
    unique={}
    for snap in snapshots:
        verify_snapshot(snap)
        unique[snap["snapshot_sha256"]]=snap
    ordered=sorted(unique.values(),key=lambda x:(utc_ms(x["timestamp_utc"]),x["snapshot_sha256"]))
    policy=ordered[-1]["decision_policy_sha256"] if ordered else None
    n=Counter()
    episodes=[]
    clustered=set()
    for snapshot in ordered:
        if snapshot["decision_policy_sha256"] != policy:
            n["old_policy_excluded"]+=len(snapshot["decisions"])
            continue
        posted=utc_ms(snapshot["timestamp_utc"])
        for decision in snapshot["decisions"]:
            n["public_market_rows"]+=1
            entry=decision.get("fast_entry_research")
            if entry is None:
                n["legacy_without_fast_entry_evidence"]+=1
                continue
            if entry.get("direction") not in ("LONG","SHORT"):
                n["fast_research_wait"]+=1
                continue
            if entry.get("research_only_no_orders") is not True:
                raise ValueError("Fast entry not research-only")
            strategy=entry.get("strategy")
            if strategy not in ALLOWED_STRATEGIES:
                raise ValueError("Unknown strategy")
            key=(decision["symbol"],posted//FOUR_HOURS_MS)
            if key in clustered:
                n["same_asset_four_hour_repeat_excluded"]+=1
                continue
            clustered.add(key)
            if decision["symbol"] not in histories:
                raise ValueError("Actual future candles missing for market "+decision["symbol"])
            speculative={"decision":entry["direction"],
                         "stop":entry["stop"],"target":entry["target"]}
            base=outcome(speculative,snapshot["timestamp_utc"],
                         histories[decision["symbol"]],4,
                         fee=TAKER_FEE,slippage=SLIPPAGE,
                         funding=FUNDING_PER_8H)
            stressed=outcome(speculative,snapshot["timestamp_utc"],
                             histories[decision["symbol"]],4,
                             fee=TAKER_FEE*2,slippage=SLIPPAGE*3,
                             funding=FUNDING_PER_8H*2)
            if base["status"]!="matured" or stressed["status"]!="matured":
                n["unmatured_or_invalid_original_protection"]+=1
                continue
            episodes.append({
                "symbol":decision["symbol"],"posted_ms":posted,
                "strategy":strategy, "side":entry["direction"],
                "normal_net_unlevered_pct":base["net_unlevered_pct"],
                "stressed_net_unlevered_pct":stressed["net_unlevered_pct"],
                "stressed_outcome":stressed["outcome"],
            })
    episodes.sort(key=lambda e:(e["posted_ms"],e["symbol"]))
    length=len(episodes)
    cutoff=max(1,int(.7*length)) if length>1 else length
    test=episodes[cutoff:]
    first_test=test[0]["posted_ms"] if test else None
    train=[e for e in episodes[:cutoff]
           if first_test is not None and e["posted_ms"]+FOUR_HOURS_MS<=first_test]
    days=len({x["posted_ms"]//DAY_MS for x in episodes})
    by_strategy=defaultdict(list)
    for row in test:
        by_strategy[row["strategy"]].append(row["stressed_net_unlevered_pct"])
    breakdown={}
    for key,values in sorted(by_strategy.items()):
        breakdown[key]={
            "holdout_episodes":len(values),
            "stressed_holdout_mean_unlevered_pct":round(statistics.mean(values),6) if len(values)>=30 else None,
            "stressed_bootstrap_lower5_mean_pct":bootstrap_lower5(values),
        }
    holdout=[e["stressed_net_unlevered_pct"] for e in test]
    lower=bootstrap_lower5(holdout)
    evidence=(length>=MIN_EVIDENCE and days>=MIN_UTC_DAYS and
              len(train)>=30 and len(test)>=30 and lower is not None)
    if not evidence:
        governance="INSUFFICIENT_FORWARD_EVIDENCE"
    elif lower>0:
        governance="RESEARCH_REVIEW_ELIGIBLE_NOT_LIVE_APPROVED"
    else:
        governance="NONPOSITIVE_STRESSED_EDGE_REJECT"
    return {
        "mode":"FAST_ENTRY_PROSPECTIVE_PUBLIC_ONLY",
        "current_policy_fingerprint":policy,
        "archived_snapshot_count":len(ordered),
        "candidate_episodes_matured":length,
        "independent_utc_days":days,
        "purged_training_count":len(train),
        "chronological_holdout_count":len(test),
        "holdout_stressed_mean_unlevered_pct":round(statistics.mean(holdout),6) if len(holdout)>=30 else None,
        "holdout_stressed_bootstrap_lower5_mean_pct":lower,
        "strategy_holdout":breakdown,
        "exclusions":dict(sorted(n.items())),
        "governance":governance,
        "live_trading_approved":False,
        "live_order_count":0,
        "strategy_promoted_automatically":False,
        "assumptions":{
            "entry":"next fully completed 15m bar opening after snapshot publication",
            "stop_first_on_intrabar_ambiguous_ohlc":True,
            "one_hour_forward_horizon":True,
            "taker_fees_multiplier":2,"slippage_multiplier":3,
            "funding_multiplier":2,
            "same_market_four_hour_bucket_dedup":True,
            "cross_asset_correlation_not_adjusted":True,
            "exchange_actual_fill_not_observed":True,
        }
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-dir",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--now-ms",type=int)
    args=p.parse_args()
    now=args.now_ms if args.now_ms is not None else int(time.time()*1000)
    snaps=[json.loads(p.read_text(encoding="utf-8"))
           for p in sorted(Path(args.archive_dir).glob("**/quant2037_snapshot.json"))]
    # Download only markets with a prospective directional fast-entry hypothesis.
    symbols=sorted({r["symbol"] for snap in snaps for r in snap.get("decisions",[])
                    if r.get("fast_entry_research",{}).get("direction") in ("LONG","SHORT")})
    earliest=max(min((utc_ms(s["timestamp_utc"]) for s in snaps),default=now)-BAR_MS,
                 now-MAX_DAYS*DAY_MS)
    histories={symbol:fetch_public_candles(symbol,earliest,now_ms=now)
               for symbol in symbols}
    report=evaluate(snaps,histories)
    target=Path(args.out)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("FAST ENTRY FORWARD",report["governance"],
          "matured=",report["candidate_episodes_matured"],"orders=0")

if __name__=="__main__":
    main()

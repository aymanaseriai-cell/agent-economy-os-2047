#!/usr/bin/env python3
"""TITAN 2037 Counterfactual Veto Laboratory.

Read-only evaluation of declined *directional* signals from immutable-by-value
public research snapshots. Never sends orders, changes live controls or loosens
existing hard risk gates. Counterfactual returns are NOT real exchange fills.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import statistics
import time

from trading.shadow_observatory import (
    BAR_MS, TAKER_FEE, SLIPPAGE, FUNDING_PER_8H, MAX_DAYS,
    fetch_public_candles, outcome, utc_ms, verify_snapshot,
)

DAY_MS = 86400000
CLUSTER_MS = 4 * 3600000
MIN_COUNT = 100
MIN_DAYS = 14
COST_MULTIPLIERS = (2.0, 3.0, 2.0)
AGENTS = (
    "candidate_resurrection", "hard_veto_isolation", "chronology_firewall",
    "cost_stress_twin", "independent_episode_filter", "holdout_auditor",
    "uncertainty_tail_judge", "deployment_guardian",
)


def _lower_bound(values, repeats=1000):
    """Deterministic exploratory bootstrap fifth percentile; not causal evidence."""
    if len(values) < 30:
        return None
    rng = random.Random(2037)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(repeats))
    return round(means[int(.05 * repeats)], 6)


def inspect(snapshots, histories, *, horizon=4):
    if horizon != 4:
        raise ValueError("Predeclared one-hour horizon only")
    if not isinstance(snapshots, list) or not isinstance(histories, dict):
        raise ValueError("Malformed audit data")
    if len(snapshots) > 200:
        raise ValueError("Too many snapshots")
    unique = {}
    for snapshot in snapshots:
        verify_snapshot(snapshot)
        unique[snapshot["snapshot_sha256"]] = snapshot
    ordered = sorted(unique.values(), key=lambda s: (utc_ms(s["timestamp_utc"]), s["snapshot_sha256"]))
    latest_policy = ordered[-1].get("decision_policy_sha256") if ordered else None
    if latest_policy is None and ordered:
        raise ValueError("Missing strategy fingerprint")
    episodes = []
    stats = Counter()
    seen = set()
    start_ms = None
    end_ms = None
    for snap in ordered:
        if snap.get("decision_policy_sha256") != latest_policy:
            stats["prior_policy_excluded"] += len(snap.get("decisions", []))
            continue
        posted = utc_ms(snap["timestamp_utc"])
        start_ms = min(posted, start_ms) if start_ms is not None else posted
        end_ms = max(posted, end_ms) if end_ms is not None else posted
        for r in snap.get("decisions", []):
            stats["archived_decisions_checked"] += 1
            if r.get("decision") != "WAIT":
                stats["original_nonwait_excluded"] += 1
                continue
            side = r.get("core_before_filters")
            if side not in ("LONG", "SHORT"):
                stats["core_without_direction_excluded"] += 1
                continue
            # A prospective decision may be studied only if NO hard veto,
            # NO missing derivatives data, and an original protective stop exists.
            if r.get("derivatives_data_warnings"):
                stats["missing_derivatives_excluded"] += 1
                continue
            if any(v.get("veto") for v in r.get("role_votes", [])):
                stats["hard_agent_veto_excluded"] += 1
                continue
            reasons = r.get("advanced_veto_reasons", [])
            if not isinstance(reasons, list) or not reasons:
                stats["no_named_soft_veto_excluded"] += 1
                continue
            if any(not isinstance(v, str) or not v or len(v)>100 for v in reasons):
                raise ValueError("Malformed veto reasons")
            symbol = r.get("symbol")
            if not isinstance(symbol, str) or not symbol.endswith("-USDT-SWAP"):
                raise ValueError("Bad symbol")
            # Same market within 4h is an observational repeat, not an
            # independent chance to inflate apparent sample size.
            cluster = (symbol, posted // CLUSTER_MS)
            if cluster in seen:
                stats["correlated_repeats_excluded"] += 1
                continue
            seen.add(cluster)
            if symbol not in histories:
                raise ValueError("Missing actual public candle history for "+symbol)
            virtual = dict(r, decision=side)
            normal = outcome(virtual, snap["timestamp_utc"], histories[symbol], horizon,
                             fee=TAKER_FEE, slippage=SLIPPAGE,
                             funding=FUNDING_PER_8H)
            stress = outcome(virtual, snap["timestamp_utc"], histories[symbol], horizon,
                             fee=TAKER_FEE*COST_MULTIPLIERS[0],
                             slippage=SLIPPAGE*COST_MULTIPLIERS[1],
                             funding=FUNDING_PER_8H*COST_MULTIPLIERS[2])
            if normal["status"] != "matured" or stress["status"] != "matured":
                stats["missing_or_invalid_horizon_excluded"] += 1
                continue
            episodes.append({
                "symbol": symbol, "published_ms": posted,
                "vetoes": tuple(sorted(set(reasons))), "side": side,
                "net_unlevered_pct": normal["net_unlevered_pct"],
                "stressed_net_unlevered_pct": stress["net_unlevered_pct"],
                "outcome": stress["outcome"],
            })
    episodes.sort(key=lambda e: (e["published_ms"], e["symbol"]))
    n = len(episodes)
    distinct_days = len({e["published_ms"] // DAY_MS for e in episodes})
    span = round((end_ms-start_ms)/DAY_MS, 5) if start_ms is not None else 0
    cutoff = max(1, int(n * .7)) if n > 1 else n
    holdout_start = episodes[cutoff]["published_ms"] if cutoff < n else None
    purged_train = [e for e in episodes[:cutoff]
                    if holdout_start is not None and e["published_ms"] + CLUSTER_MS <= holdout_start]
    test = episodes[cutoff:]
    by_veto = defaultdict(list)
    for e in test:
        for reason in e["vetoes"]:
            by_veto[reason].append(e["stressed_net_unlevered_pct"])
    veto_report = {}
    for name, values in sorted(by_veto.items()):
        lb = _lower_bound(values)
        veto_report[name] = {
            "holdout_episodes": len(values),
            "stressed_mean_hypothetical_pct": round(statistics.mean(values),6) if len(values)>=30 else None,
            "stressed_bootstrap_lower5_mean_pct": lb,
            "status": "DESCRIPTIVE_NOT_VALIDATION" if lb is not None else "INSUFFICIENT_HOLDOUT",
        }
    obs = [e["stressed_net_unlevered_pct"] for e in test]
    lower = _lower_bound(obs)
    enough = n >= MIN_COUNT and distinct_days >= MIN_DAYS and len(test)>=30 and len(purged_train)>=30
    governance = "INSUFFICIENT_PROSPECTIVE_EVIDENCE"
    if enough:
        governance = "HUMAN_REVIEW_ELIGIBLE_NOT_AUTOMATIC_APPROVAL" if lower is not None and lower > 0 else "NEGATIVE_OR_UNCERTAIN_EDGE_NO_APPROVAL"
    return {
        "mode": "COUNTERFACTUAL_VETO_LAB_READ_ONLY",
        "agents": {
            "candidate_resurrection": {"potential_extra_directional_episodes": n,
                                        "not_real_trades": True},
            "hard_veto_isolation": {"exclusions": dict(sorted(stats.items())),
                                    "hard_safety_vetoes_never_overridden": True},
            "chronology_firewall": {"current_policy_fingerprint": latest_policy,
                                    "all_outcomes_from_completed_future_bars": True},
            "cost_stress_twin": {"modeled_taker_fee_multiplier":2,
                                 "modeled_slippage_multiplier":3,
                                 "modeled_funding_multiplier":2},
            "independent_episode_filter": {"primary_episodes":n,
                                            "distinct_utc_days":distinct_days,
                                            "evidence_span_days":span},
            "holdout_auditor": {"purged_training_episodes":len(purged_train),
                                "holdout_episodes":len(test),
                                "fixed_horizon_minutes":60},
            "uncertainty_tail_judge": {"holdout_stressed_lower5_mean_pct":lower,
                                       "not_confidence_of_actual_profit":True},
            "deployment_guardian": {"status":governance, "live_trading_allowed":False,
                                     "force_entry_allowed":False},
        },
        "by_veto": veto_report,
        "potential_extra_trades_hypothetical_only":n,
        "actual_orders_placed":0,
        "live_configuration_modified":False,
        "not_a_quantum_computer":True,
        "limitations": [
            "OHLCV stop-first approximations; no real order fills or queue modeling",
            "No causal claim about removing any veto; correlated cross-asset risks remain",
            "Observational selection bias and chosen policy make this exploratory",
            "GitHub snapshot digests are not independent tamper-proof timestamps",
            "The actual 30-second cooldown requires exchange-confirmed close; not tested by 15-minute candles",
        ],
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir",required=True)
    parser.add_argument("--out",required=True)
    parser.add_argument("--now-ms",type=int)
    args=parser.parse_args()
    archive=Path(args.archive_dir)
    snaps=[]
    for p in sorted(archive.glob("**/quant2037_snapshot.json")):
        snaps.append(json.loads(p.read_text(encoding="utf-8")))
    now=args.now_ms if args.now_ms is not None else int(time.time()*1000)
    if not snaps:
        report=inspect([], {})
    else:
        newest = sorted(snaps,key=lambda s:utc_ms(s["timestamp_utc"]))
        earliest = max(utc_ms(newest[0]["timestamp_utc"])-BAR_MS,now-MAX_DAYS*DAY_MS)
        symbols=sorted({r["symbol"] for s in snaps for r in s.get("decisions",[])
                        if r.get("decision")=="WAIT" and r.get("core_before_filters") in ("LONG","SHORT")})
        # All data is public, read-only and downloaded with bounded page limits.
        histories={sym:fetch_public_candles(sym,earliest,now_ms=now) for sym in symbols}
        report=inspect(snaps,histories)
    dest=Path(args.out)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("VETO LAB",report["agents"]["deployment_guardian"]["status"],"orders=0")

if __name__=="__main__":
    main()

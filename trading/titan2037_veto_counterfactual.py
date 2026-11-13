#!/usr/bin/env python3
"""TITAN 2037 veto counterfactual: genuine archived PUBLIC WAIT decisions.

Investigates whether rejected *directional* hypotheses would have worked in
subsequent CLOSED public candles with original stops/targets. Never trades.
This is descriptive retrospective evidence, NOT causal edge or profit proof.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import statistics
import time

from .shadow_observatory import (
    BAR_MS, HORIZONS, MAX_DAYS, diagnostic, fetch_public_candles,
    outcome, sha, utc_ms, verify_snapshot,
)

AGENTS = ("immutable_evidence", "directional_veto_replay", "cost_stress_triad",
          "counterfactual_stop_first", "four_hour_independence",
          "policy_firewall", "blocked_day_bootstrap", "human_only_governance")
FOUR_HOURS_MS = 4 * 60 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000
MAX_SNAPSHOTS = 180
MAX_SYMBOLS = 100


def read_snapshots(root):
    root = Path(root)
    if not root.is_dir():
        raise ValueError("Missing research archive")
    paths = sorted(root.glob("**/quant2037_snapshot.json"))
    if len(paths) > MAX_SNAPSHOTS:
        raise ValueError("Archive exceeds declared cap")
    snapshots = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        verify_snapshot(payload)
        snapshots.append(payload)
    return snapshots


def _block_lower(events, samples=400):
    """Exploratory UTC-day-block bootstrap, not proof of positive alpha."""
    by_day = defaultdict(list)
    for e in events:
        by_day[e["decision_ms"] // DAY_MS].append(e["stress_net_bp"])
    keys = sorted(by_day)
    if len(keys) < 14:
        return None
    values = [statistics.mean(by_day[k]) for k in keys]
    rng = random.Random(2037)
    res = sorted(statistics.mean(values[rng.randrange(len(values))]
                                 for _ in values) for _ in range(samples))
    return round(res[int(.05 * samples)], 5)


def evaluate(snapshots, bars_by_symbol, now_ms):
    if type(now_ms) is not int or now_ms < 1:
        raise ValueError("Invalid as-of clock")
    if not isinstance(snapshots, list) or len(snapshots) > MAX_SNAPSHOTS:
        raise ValueError("Unbounded snapshots")
    if not isinstance(bars_by_symbol, dict) or len(bars_by_symbol) > MAX_SYMBOLS:
        raise ValueError("Unbounded price universe")
    unique = {}
    for snap in snapshots:
        verify_snapshot(snap)
        stamp = utc_ms(snap["timestamp_utc"])
        if stamp > now_ms:
            raise ValueError("Future-dated archival snapshot")
        digest = snap["snapshot_sha256"]
        if digest in unique:
            continue
        unique[digest] = snap
    snapshots = sorted(unique.values(), key=lambda s: (utc_ms(s["timestamp_utc"]), s["snapshot_sha256"]))
    latest_policy = snapshots[-1]["decision_policy_sha256"] if snapshots else None
    last_seen = {}
    records = []
    coverage = Counter()
    for snap in snapshots:
        stamp = utc_ms(snap["timestamp_utc"])
        for decision in snap["decisions"]:
            if decision.get("decision") != "WAIT":
                continue
            direction = decision.get("core_before_filters")
            if direction not in ("LONG", "SHORT"):
                continue
            coverage["directional_rejected"] += 1
            symbol = decision["symbol"]
            if symbol not in bars_by_symbol:
                coverage["missing_public_prices"] += 1
                continue
            closed_at = decision.get("last_complete_15m_candle_ms")
            if closed_at is not None and (
                type(closed_at) is not int or closed_at + BAR_MS > stamp
            ):
                raise ValueError("Unconfirmed/future source candle in snapshot")
            if snap["decision_policy_sha256"] != latest_policy:
                coverage["other_policy_version"] += 1
                continue
            if symbol in last_seen and stamp - last_seen[symbol] < FOUR_HOURS_MS:
                coverage["correlated_repeated_wait"] += 1
                continue
            last_seen[symbol] = stamp
            # Price timestamps beyond 'now' are never used for a matured result.
            bars = bars_by_symbol[symbol]
            if not isinstance(bars, list):
                raise ValueError("Invalid OHLC history")
            observed = [b for b in bars
                        if type(b.get("ts")) is int and b["ts"] + BAR_MS <= now_ms]
            if any(type(b.get("ts")) is not int or b["ts"] < 0 for b in bars):
                raise ValueError("Invalid public candle timestamp")
            model = {**decision, "decision": direction}
            base_1h = outcome(model, snap["timestamp_utc"], observed, HORIZONS[0])
            base_4h = outcome(model, snap["timestamp_utc"], observed, HORIZONS[1])
            if base_1h["status"] != "matured" or base_4h["status"] != "matured":
                coverage["immature_missing_or_invalid_protection"] += 1
                continue
            # Stress fee, slippage and funding; no new entry timing assumptions.
            adverse_2x = outcome(model, snap["timestamp_utc"], observed,
                                 HORIZONS[0], fee=.0010, slippage=.0006,
                                 funding=.0002)
            adverse_3x = outcome(model, snap["timestamp_utc"], observed,
                                 HORIZONS[0], fee=.0015, slippage=.0009,
                                 funding=.0003)
            if adverse_2x["status"] != "matured" or adverse_3x["status"] != "matured":
                coverage["stress_invalidated_entry"] += 1
                continue
            values = (base_1h["net_unlevered_pct"], base_4h["net_unlevered_pct"],
                      adverse_2x["net_unlevered_pct"], adverse_3x["net_unlevered_pct"])
            row = {
                "episode_hash": sha({"snapshot": snap["snapshot_sha256"],
                                     "symbol": symbol, "published": stamp}),
                "symbol": symbol, "decision_ms": stamp, "original_action": "WAIT",
                "hypothetical_side": direction, "original_vetoes": diagnostic(decision),
                "decision_policy_sha256": latest_policy,
                "one_hour_net_bp": round(values[0]*100, 5),
                "four_hour_net_bp": round(values[1]*100, 5),
                "double_cost_net_bp": round(values[2]*100, 5),
                "stress_net_bp": round(values[3]*100, 5),
                "one_hour_exit": base_1h["outcome"],
                "four_hour_exit": base_4h["outcome"],
                "hypothetical_only": True,
            }
            records.append(row)
    records.sort(key=lambda x: (x["decision_ms"], x["episode_hash"]))
    cutoff = int(.7*len(records))
    if records and cutoff == 0:
        cutoff = 1
    holdout = records[cutoff:]
    first_holdout = holdout[0]["decision_ms"] if holdout else None
    # Purge the 4h label horizon and add another 4h embargo.
    train = [r for r in records[:cutoff] if first_holdout is not None
             and r["decision_ms"] + 8*60*60*1000 <= first_holdout]
    span = (records[-1]["decision_ms"] - records[0]["decision_ms"]) / DAY_MS if records else 0
    day_count = len({r["decision_ms"] // DAY_MS for r in records})
    sufficient = len(records) >= 100 and span >= 14 and len(holdout) >= 30
    positive_under_3x = sum(r["stress_net_bp"] > 0 for r in holdout)
    lower = _block_lower(holdout)
    reasons = Counter(reason for r in records for reason in r["original_vetoes"])
    verdict = "INSUFFICIENT_PROSPECTIVE_OUTCOMES" if not sufficient else "HUMAN_REVIEW_ONLY_NOT_PROFIT_PROOF"
    return {
        "mode": "TITAN2037_VETO_COUNTERFACTUAL_PUBLIC_ONLY",
        "trading_allowed": False, "orders_placed": 0,
        "latest_decision_policy_sha256": latest_policy,
        "agents": {
            "immutable_evidence": "SNAPSHOT_DIGEST_VERIFIED_NOT_PUBLIC_NOTARIZATION",
            "directional_veto_replay": "ONLY_PRE_RECORDED_DIRECTION_WITH_ORIGINAL_STOP_TARGET",
            "cost_stress_triad": "MODELED_1X_2X_3X_COSTS_NOT_LIVE_FILLS",
            "counterfactual_stop_first": "CONSERVATIVE_CANDLE_PATH_AND_GAPS",
            "four_hour_independence": "SAME_SYMBOL_4H_DEDUP_NOT_FULL_CROSS_ASSET_INDEPENDENCE",
            "policy_firewall": "LATEST_SOURCE_FINGERPRINT_ONLY",
            "blocked_day_bootstrap": "EXPLORATORY_DAY_BLOCK_5TH_PERCENTILE_NOT_SIGNIFICANCE",
            "human_only_governance": verdict
        },
        "summary": {
            "archived_snapshots": len(snapshots), "directional_rejected_checked": coverage["directional_rejected"],
            "primary_matured_counterfactuals": len(records),
            "correlated_repeats_excluded": coverage["correlated_repeated_wait"],
            "other_policy_versions_excluded": coverage["other_policy_version"],
            "missing_prices": coverage["missing_public_prices"],
            "immature_or_protection_invalid": coverage["immature_missing_or_invalid_protection"],
            "stress_invalidated": coverage["stress_invalidated_entry"],
            "observed_span_days": round(span,3), "distinct_days": day_count,
            "purged_training_count": len(train), "untouched_holdout_count": len(holdout),
            "holdout_positive_after_3x_cost": positive_under_3x,
            "holdout_mean_3x_net_bp": round(statistics.mean(r["stress_net_bp"] for r in holdout),5) if holdout else None,
            "holdout_day_block_bootstrap_lower_bp": lower,
            "original_veto_counts": dict(sorted(reasons.items())),
            "status": verdict,
        },
        "episodes": records,
        "warning": "Rejected WAIT is not a lost trade. These are hypothetical future price paths, "
                   "not causal veto quality, fills or verified profits. No automatic relaxation."
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--now-ms", type=int)
    args = p.parse_args()
    now_ms = args.now_ms if args.now_ms is not None else int(time.time()*1000)
    snapshots = read_snapshots(args.archive_dir)
    # Keep a bounded, chronological 15-day sampling window.
    snapshots = [s for s in snapshots if utc_ms(s["timestamp_utc"]) >= now_ms - MAX_DAYS*DAY_MS]
    symbols = sorted({d["symbol"] for s in snapshots for d in s["decisions"]
                      if d.get("decision")=="WAIT" and d.get("core_before_filters") in ("LONG","SHORT")})
    if len(symbols)>MAX_SYMBOLS:
        raise ValueError("Public market universe over cap")
    bars = {}
    if snapshots:
        first = min(utc_ms(s["timestamp_utc"]) for s in snapshots)
        for symbol in symbols:
            bars[symbol] = fetch_public_candles(symbol, max(first-BAR_MS,
                            now_ms-MAX_DAYS*DAY_MS), now_ms=now_ms)
    report = evaluate(snapshots, bars, now_ms)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n",encoding="utf-8")
    print("TITAN VETO RED TEAM:", report["summary"]["status"],
          "matured=", report["summary"]["primary_matured_counterfactuals"],
          "orders_placed=0")


if __name__=="__main__":
    main()

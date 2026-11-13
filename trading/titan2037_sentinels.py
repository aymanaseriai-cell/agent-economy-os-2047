#!/usr/bin/env python3
"""TITAN 2037 Sentinels: independent, offline research on rejected signals.

No exchange connections, credentials, order routes, or automatic trading approval.
All outcomes are imported hypothetical forward observations, not verified fills.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
CLUSTER_MS = 4 * HOUR_MS
AGENTS = (
    "chronology_sentinel", "independence_graph", "veto_regret_auditor",
    "cost_reality", "regime_drift_radar", "tail_shield",
    "uncertainty_guard", "governance_council",
)


def number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"Invalid {name}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if not result.is_finite():
        raise ValueError(f"Nonfinite {name}")
    return result


def _timestamp(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {name}")
    return value


def _episode(raw, as_of_ms):
    if not isinstance(raw, dict):
        raise ValueError("Episode must be an object")
    key = raw.get("decision_id")
    symbol = raw.get("symbol")
    side = raw.get("side")
    vetoes = raw.get("vetoes")
    if not isinstance(key, str) or not key.strip() or len(key) > 128:
        raise ValueError("Missing decision ID")
    if not isinstance(symbol, str) or not symbol.strip() or len(symbol) > 80:
        raise ValueError("Invalid symbol")
    if side not in ("LONG", "SHORT"):
        raise ValueError("Invalid side")
    if not isinstance(vetoes, list) or not vetoes or len(vetoes) > 20 or any(
        not isinstance(v, str) or not v.strip() or len(v) > 100 for v in vetoes
    ):
        raise ValueError("Rejected episode requires explicit veto reasons")
    decision = _timestamp(raw.get("decision_ms"), "decision_ms")
    outcome = _timestamp(raw.get("outcome_ms"), "outcome_ms")
    if not (0 < decision < outcome <= as_of_ms):
        raise ValueError("Missing, future, or pre-decision outcome")
    if outcome - decision > 7 * DAY_MS:
        raise ValueError("Unbounded outcome horizon")
    entry = number(raw.get("entry"), "entry")
    exit_price = number(raw.get("forward_exit"), "forward_exit")
    if entry <= 0 or exit_price <= 0:
        raise ValueError("Nonpositive price")
    fee, slip, funding = (number(raw.get(k), k) for k in
                          ("fee_bp", "slippage_bp", "funding_bp"))
    if not (0 <= fee <= 500 and 0 <= slip <= 500 and -500 <= funding <= 500):
        raise ValueError("Invalid cost assumptions")
    regime = raw.get("regime")
    if not isinstance(regime, str) or not regime or len(regime) > 80:
        raise ValueError("Missing regime tag")
    feature = number(raw.get("regime_feature"), "regime_feature")
    feature_float = float(feature)
    if not math.isfinite(feature_float):
        raise ValueError("Nonfinite regime feature")
    direction = Decimal(1) if side == "LONG" else Decimal(-1)
    gross = direction * (exit_price / entry - 1) * 10000
    cost = fee + slip + funding
    return {"decision_id": key, "symbol": symbol, "side": side,
            "decision_ms": decision, "outcome_ms": outcome,
            "vetoes": tuple(sorted(set(vetoes))), "regime": regime,
            "feature": feature_float, "gross_bp": float(gross),
            "cost_bp": float(cost), "net_bp": float(gross - cost)}


def _independent(events):
    """Collapse repeated same-symbol signals inside 4h UTC buckets.

    Proxy for independence, not proof that different symbols are uncorrelated.
    """
    seen = set()
    selected = []
    for event in events:
        cluster = (event["symbol"], event["decision_ms"] // CLUSTER_MS)
        if cluster in seen:
            continue
        seen.add(cluster)
        selected.append(event)
    return selected


def _psi(train, holdout):
    """Population stability index using training-only quantile boundaries."""
    if len(train) < 30 or len(holdout) < 15:
        return None
    ordered = sorted(train)
    edges = sorted(set(ordered[min(len(ordered) - 1, int(p * len(ordered)))]
                       for p in (0.2, 0.4, 0.6, 0.8)))
    if not edges:
        return 0.0

    def bins(values):
        buckets = [0] * (len(edges) + 1)
        for value in values:
            if not math.isfinite(value):
                raise ValueError("Nonfinite regime feature")
            index = sum(value > edge for edge in edges)
            buckets[index] += 1
        # Jeffreys prior avoids infinite PSI in empty buckets.
        return [(n + .5) / (len(values) + .5 * len(buckets)) for n in buckets]

    p, q = bins(train), bins(holdout)
    return sum((b - a) * math.log(b / a) for a, b in zip(p, q))


def _bootstrap_lower(net_values, iterations=800):
    """Deterministic exploratory 5th percentile, NOT confidence/profit proof."""
    if len(net_values) < 30:
        return None
    rng = random.Random(2037)
    n = len(net_values)
    means = sorted(sum(net_values[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(iterations))
    return means[int(.05 * iterations)]


def _digest(raw_episodes):
    canonical = json.dumps(sorted(raw_episodes, key=lambda e: e["decision_id"]),
                           sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def audit(evidence):
    if not isinstance(evidence, dict):
        raise ValueError("Expected JSON object")
    as_of_ms = _timestamp(evidence.get("as_of_ms"), "as_of_ms")
    raw = evidence.get("episodes")
    if not isinstance(raw, list) or len(raw) > 100000:
        raise ValueError("Missing or excessive evidence episodes")
    if raw and as_of_ms == 0:
        raise ValueError("as_of_ms must be positive when episodes exist")
    parsed = [_episode(e, as_of_ms) for e in raw]
    ids = [e["decision_id"] for e in parsed]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate decision ID; cannot inflate sample")
    ordered = sorted(parsed, key=lambda e: (e["decision_ms"], e["decision_id"]))
    independent = _independent(ordered)
    total = len(independent)
    distinct_days = len({e["decision_ms"] // DAY_MS for e in independent})
    veto_stats = defaultdict(list)
    for e in independent:
        for veto in e["vetoes"]:
            veto_stats[veto].append(e["net_bp"])
    veto_report = {
        k: {"independent_episodes": len(values),
            "hypothetical_mean_net_bp": round(sum(values) / len(values), 5)
            if len(values) >= 10 else None,
            "status": "DESCRIPTIVE_ONLY" if len(values) >= 10
            else "INSUFFICIENT_EPISODES"}
        for k, values in sorted(veto_stats.items())
    }
    costs = [e["cost_bp"] for e in independent]
    nets = [e["net_bp"] for e in independent]
    tail_size = max(1, math.ceil(total * .1)) if total else 0
    worst_tail = round(sum(sorted(nets)[:tail_size]) / tail_size, 5) if total >= 20 else None
    # Chronological holdout: predeclared last 30% of deduplicated episodes.
    cut = max(1, int(.7 * total)) if total > 1 else total
    split = independent[cut]["decision_ms"] if cut < total else None
    holdout = independent[cut:]
    # Data used for training must resolve before holdout with four-hour embargo.
    train = [e for e in independent[:cut]
             if split is not None and e["outcome_ms"] + CLUSTER_MS <= split]
    psi = _psi([e["feature"] for e in train],
               [e["feature"] for e in holdout])
    drift = "INSUFFICIENT_CHRONOLOGICAL_HOLDOUT" if psi is None else (
        "REVIEW_DRIFT" if psi > .25 else "NO_LARGE_PSI_SHIFT_OBSERVED")
    bootstrap = _bootstrap_lower([e["net_bp"] for e in holdout])
    enough = total >= 100 and distinct_days >= 14 and len(holdout) >= 30
    if drift == "REVIEW_DRIFT":
        governance = "REVIEW_DRIFT_NO_AUTOMATIC_APPROVAL"
    elif not enough:
        governance = "INSUFFICIENT_PROSPECTIVE_EVIDENCE"
    else:
        governance = "HUMAN_REVIEW_REQUIRED_NOT_PROFIT_PROOF"
    return {
        "agents": {
            "chronology_sentinel": {"status": "CHECKED", "matured_episode_count": len(parsed),
                                    "as_of_ms": as_of_ms},
            "independence_graph": {"status": "PROXY_ONLY", "distinct_symbol_4h_clusters": total,
                                   "repeated_signals_excluded": len(parsed) - total,
                                   "distinct_utc_days": distinct_days},
            "veto_regret_auditor": {"status": "HYPOTHETICAL_NOT_CAUSAL",
                                   "by_veto": veto_report},
            "cost_reality": {"status": "IMPORTED_ASSUMPTIONS",
                             "mean_assumed_cost_bp": round(sum(costs) / total, 5) if total else None,
                             "mean_hypothetical_net_bp": round(sum(nets) / total, 5) if total else None},
            "regime_drift_radar": {"status": drift, "psi": round(psi, 6) if psi is not None else None,
                                   "purged_train": len(train), "holdout": len(holdout)},
            "tail_shield": {"status": "HYPOTHETICAL_10PCT_WORST_TAIL",
                            "worst_tail_mean_net_bp": worst_tail},
            "uncertainty_guard": {"status": "EXPLORATORY_NO_SIGNIFICANCE_CLAIM",
                                  "holdout_bootstrap_5pct_mean_bp": round(bootstrap, 5)
                                  if bootstrap is not None else None},
            "governance_council": {"status": governance, "automatic_live_approval": False},
        },
        "evidence_sha256": _digest(raw), "orders": 0,
        "live_trading_reenabled": False, "verified_against_private_exchange": False,
        "warning": "Imported hypothetical forward outcomes; no causal/profit claim. "
                   "Research only; cannot authorize or submit trades.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = audit(json.loads(Path(args.evidence).read_text(encoding="utf-8")))
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TITAN SENTINELS:", result["agents"]["governance_council"]["status"],
          "orders=0", "live_trading_reenabled=False")


if __name__ == "__main__":
    main()

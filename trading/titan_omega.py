#!/usr/bin/env python3
"""TITAN Omega: ten auditable, quantum-inspired PUBLIC research diagnostics.

These are deterministic numerical research roles, not quantum hardware, autonomous
LLM agents, guaranteed predictions, or permission to trade. Never uses secrets.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from datetime import datetime, timezone

SYSTEMS = (
    "01_multiverse_bootstrap",
    "02_adversarial_red_team",
    "03_quantum_inspired_qubo",
    "04_exchange_digital_twin",
    "05_regime_mutation_detector",
    "06_observational_causal_diagnostics",
    "07_extreme_tail_risk",
    "08_walk_forward_research_laboratory",
    "09_meta_cognitive_calibration",
    "10_proof_of_trade_evidence",
)
HORIZON_BARS = 12  # 12 * 15m = 3 hours
SCENARIOS = 384
TAKER_FEE_BP_ASSUMED = 5.0  # conservative illustrative model; check actual OKX tier
MAX_ROUND_TRIP_COST_BP = 70.0


def _finite(value, fallback=0.0):
    try:
        x = float(value)
        return x if math.isfinite(x) else fallback
    except (TypeError, ValueError, OverflowError):
        return fallback


def _record(name, status, evidence, veto=False):
    return {"name": name, "status": status, "veto": bool(veto), "evidence": evidence}


def _close_returns(bars):
    closes = [_finite(b.get("close")) for b in bars]
    if len(closes) < 110 or any(not math.isfinite(x) or x <= 0 for x in closes):
        raise ValueError("Omega requires at least 110 completed finite-price candles")
    return [math.log(b / a) for a, b in zip(closes[:-1], closes[1:])]


def _percentile(values, q):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int((len(s) - 1) * q)))]


def _bootstrap(returns, price, stop, target, direction, seed):
    # Empirical i.i.d. resampling is a deliberately crude null-model, not a
    # validated predictive distribution. Inject a two-sided stress shock.
    generator = random.Random(seed)
    hits = []
    stopped = 0
    for i in range(SCENARIOS):
        p = price
        event = None
        for j in range(1, HORIZON_BARS + 1):
            ret = generator.choice(returns[-96:])
            if i % 40 == 0 and j == 1:
                ret += (0.05 if i % 80 else -0.05)
            p *= math.exp(max(-0.15, min(0.15, ret)))
            if direction == "LONG":
                if p <= stop:
                    event = "STOP"
                elif p >= target:
                    event = "TARGET"
            else:
                if p >= stop:
                    event = "STOP"
                elif p <= target:
                    event = "TARGET"
            if event:
                if event == "TARGET":
                    hits.append(j * 15)
                else:
                    stopped += 1
                break
    return {"target_hit_fraction": round(len(hits) / SCENARIOS, 5),
            "stop_hit_fraction": round(stopped / SCENARIOS, 5),
            "target_time_p75_minutes": _percentile(hits, 0.75),
            "unresolved_fraction": round((SCENARIOS - stopped - len(hits)) / SCENARIOS, 5),
            "paths": SCENARIOS, "horizon_minutes": HORIZON_BARS * 15,
            "assumption": "historical bootstrap null-model + shocks, not calibrated forecast"}


def qubo_pick(records):
    """Exact solve one-of-N-or-WAIT QUBO, maximizing vetted utility.

    Energy = -sum(u_i*x_i) + 1000*sum_{i<j}(x_i*x_j), with x_i in {0,1}.
    Since each candidate is independently scored, optimal choice is the single
    positive maximum; WAIT (all zeros) is preferred if no positive utility.
    """
    choices = [(float(x.get("omega_rank_score", 0)), x.get("symbol"))
               for x in records
               if x.get("signal") in ("LONG", "SHORT")
               and x.get("omega_system_count") == len(SYSTEMS)
               and not x.get("omega_veto_reasons")
               and math.isfinite(_finite(x.get("omega_rank_score")))]
    if not choices:
        return None
    value, symbol = max(choices, key=lambda pair: pair[0])
    return symbol if value > 0 else None


def evaluate_omega(bars, hourly, four_hourly, book, trades, ticker, funding, interest, mark, record):
    """Evaluate 10 independent role outputs. Unknown/invalid evidence vetoes entry.

    Uses completed public candles and observable quotes; no market order is placed.
    """
    r = _close_returns(bars)
    direction = record.get("signal")
    price = _finite(record.get("quote_price"))
    risk = (record.get("agents") or [{}])[-1].get("evidence", {})
    stop = _finite(risk.get("indicative_stop_not_an_order"))
    target = _finite(risk.get("indicative_target_not_an_order"))
    side = 1 if direction == "LONG" else -1
    spread_bp = _finite(ticker.get("spread_bp"), 10000)
    round_trip_bp = 2 * TAKER_FEE_BP_ASSUMED + spread_bp + 6.0  # two-way impact reserve
    vtos = []
    systems = []
    valid = (direction in ("LONG", "SHORT") and
             0 < min(price, stop, target) and
             (stop < price < target if side > 0 else target < price < stop))
    seed = int(hashlib.sha256(
        ("%s:%s" % (record.get("symbol"), bars[-1].get("ts"))).encode()).hexdigest()[:16], 16)
    if valid:
        sim = _bootstrap(r, price, stop, target, direction, seed)
        edge_bp = abs(target - price) / price * 10000
        stop_bp = abs(stop - price) / price * 10000
        # Unknown exit in horizon is not assumed to be a profit.
        expected_bp = (sim["target_hit_fraction"] * edge_bp -
                       sim["stop_hit_fraction"] * stop_bp -
                       sim["unresolved_fraction"] * stop_bp -
                       round_trip_bp)
        fast = sim["target_time_p75_minutes"]
        # Owner-selected policy: null-model target-hit rate, estimated net
        # expectation and target arrival-time remain evidence, NOT entry vetoes.
        # Exchange, market-quality and portfolio protection gates still apply.
    else:
        sim = {"target_hit_fraction": 0.0, "stop_hit_fraction": 0.0,
               "target_time_p75_minutes": None, "paths": 0,
               "assumption": "no trade hypothesis"}
        edge_bp = stop_bp = expected_bp = 0.0
        fast = None
    systems.append(_record(SYSTEMS[0], "DIAGNOSTIC",
                           {**sim, "net_expectation_bp_null_model": round(expected_bp, 2),
                            "null_model_entry_veto": False}, False))
    buy = sum(_finite(t.get("sz")) for t in trades if t.get("side") == "buy")
    sell = sum(_finite(t.get("sz")) for t in trades if t.get("side") == "sell")
    flow = (buy - sell) / max(buy + sell, 1e-9)
    funding_rate = _finite(funding.get("fundingRate"))
    # Data ambiguity remains a hard veto in existing seven-system scanner.
    conflict = (valid and ((side > 0 and flow < -0.75) or
                           (side < 0 and flow > 0.75) or
                           (side > 0 and funding_rate > 0.002) or
                           (side < 0 and funding_rate < -0.002)))
    if conflict:
        vtos.append("adversarial_flow_or_funding_conflict")
    systems.append(_record(SYSTEMS[1], "REJECT" if conflict else "PASS",
                           {"signed_trade_flow_proxy": round(flow, 4),
                            "funding_rate": funding_rate}, conflict))
    # The QUBO optimizer gets final utility from all ten diagnostic roles.
    systems.append(_record(SYSTEMS[2], "DIAGNOSTIC",
                           {"method": "exact_one_of_n_or_wait_qubo",
                            "guaranteed_quantum_advantage": False}))
    costly = valid and (round_trip_bp >= edge_bp / 2 or
                        round_trip_bp > MAX_ROUND_TRIP_COST_BP)
    if costly:
        vtos.append("digital_twin_expected_cost_excessive")
    systems.append(_record(SYSTEMS[3], "REJECT" if costly else "PASS",
                           {"estimated_round_trip_cost_bp": round(round_trip_bp, 2),
                            "actual_depth_impact_known": False,
                            "fees_assumed_bp_per_side": TAKER_FEE_BP_ASSUMED}, costly))
    recent_vol = statistics.pstdev(r[-24:])
    previous_vol = max(statistics.pstdev(r[-72:-24]), 1e-8)
    mutation = (recent_vol > previous_vol * 3 or
                max(abs(x) for x in r[-8:]) > max(0.07, 6 * previous_vol))
    if mutation and valid:
        vtos.append("regime_mutation_or_jump")
    systems.append(_record(SYSTEMS[4], "REJECT" if mutation and valid else "PASS",
                           {"volatility_ratio": round(recent_vol / previous_vol, 3),
                            "regime": "MUTATION" if mutation else "STABLE_UNVERIFIED"},
                           mutation and valid))
    systems.append(_record(SYSTEMS[5], "OBSERVATION_ONLY",
                           {"open_interest_usd": _finite(interest.get("oiUsd")),
                            "mark_price": _finite(mark.get("markPx")),
                            "flow_proxy": round(flow, 4),
                            "causal_inference_performed": False}))
    lower_tail = statistics.mean(sorted(r)[0:max(2, int(len(r) * 0.05))])
    upper_tail = statistics.mean(sorted(r)[-max(2, int(len(r) * 0.05)):])
    danger = valid and max(-lower_tail, upper_tail) * 10000 > max(stop_bp * 3, 500)
    if danger:
        vtos.append("extreme_15m_tail_exceeds_stop_budget")
    systems.append(_record(SYSTEMS[6], "REJECT" if danger else "PASS",
                           {"historical_lower_tail_mean_bp": round(lower_tail * 10000, 2),
                            "historical_upper_tail_mean_bp": round(upper_tail * 10000, 2)},
                           danger))
    # Offline / research-only: candidate strategies do not self-deploy to live.
    systems.append(_record(SYSTEMS[7], "RESEARCH_ONLY",
                           {"walk_forward_passed": False,
                            "automated_strategy_promotion": False,
                            "research_required": "time-split out-of-sample + fees + leakage tests"}))
    systems.append(_record(SYSTEMS[8], "UNCALIBRATED",
                           {"live_probability_calibration_samples": 0,
                            "historical_reliability_not_established": True,
                            "agent_weights_auto_changed": False}))
    digest = hashlib.sha256(json.dumps({
        "symbol": record.get("symbol"), "bar": bars[-1]["ts"],
        "signal": direction, "price": price, "stop": stop, "target": target,
        "model": "TITAN_OMEGA_1"}, sort_keys=True).encode()).hexdigest()
    systems.append(_record(SYSTEMS[9], "PUBLIC_PROOF_ONLY",
                           {"sha256_public_evidence": digest,
                            "persistent_private_trade_ledger": False,
                            "order_submitted": False}))
    # Diagnostic estimates no longer veto or rank live candidates.
    # Rank by target payoff relative to initial-stop distance, net of
    # assumed execution cost; still an uncalibrated heuristic, NOT an edge claim.
    # Independent exchange, volatility, funding and portfolio vetoes remain.
    rank = ((edge_bp - round_trip_bp) / max(stop_bp, 1e-9)
            if valid and not vtos and edge_bp > round_trip_bp else 0.0)
    return {"omega_system_count": len(SYSTEMS), "omega_systems": systems,
            "omega_veto_reasons": vtos,
            "omega_rank_score": round(rank, 8),
            "omega_estimated_time_to_target_minutes": fast,
            "omega_target_hit_fraction_null_model": sim["target_hit_fraction"],
            "omega_model_warning": "Research-only bootstrap. No proven edge, quantum hardware, or guaranteed return."}

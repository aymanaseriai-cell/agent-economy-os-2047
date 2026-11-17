#!/usr/bin/env python3
"""TITAN Quantum Research Gate: classical simulation of three qubits, NO ORDERS.

Reusable causal feature / quantum interference / classical ablation protocol.
A successful CI check confirms math and evidence consistency, NOT profitability,
quantum hardware access, real exchange fills or an attainable +128% return.
Standard library only; never reads credentials, never imports order executors.
"""
from __future__ import annotations

import argparse
import cmath
import json
import math
from pathlib import Path

START_USDT = 4.15
TARGET_MULTIPLIER = 2.28
TARGET_USDT = round(START_USDT * TARGET_MULTIPLIER, 6)
RUIN_USDT = 0.83
HOLDOUTS = ("holdout_1", "holdout_2")
PERIODS = ("train",) + HOLDOUTS
COSTS = ("ordinary", "stress")
MODELS = ("quantum", "classical")
PHASES = (0.0, 0.7, 1.0, 1.3)
CUTOFF = 0.66
EPSILON = 1e-9


def _finite(values):
    if len(values) != 3 or any(not math.isfinite(float(v)) for v in values):
        raise ValueError("Three finite, observed features required")
    return tuple(float(v) for v in values)


def _ry(state, bit, angle):
    out = list(state)
    mask = 1 << bit
    c, s = math.cos(angle / 2), math.sin(angle / 2)
    for i in range(8):
        if i & mask:
            continue
        a, b = state[i], state[i | mask]
        out[i] = c * a - s * b
        out[i | mask] = s * a + c * b
    return out


def _hadamard(state, bit):
    out = list(state)
    mask = 1 << bit
    scale = 1 / math.sqrt(2)
    for i in range(8):
        if i & mask:
            continue
        a, b = state[i], state[i | mask]
        out[i] = (a + b) * scale
        out[i | mask] = (a - b) * scale
    return out


def quantum_probability(features, phase=1.0):
    """3-qubit 8-amplitude statevector, unitary ZZ-phase interference.

    This is a CLASSICAL COMPUTER simulation of quantum circuits, not hardware.
    """
    f = _finite(features)
    if not math.isfinite(phase) or not 0.0 <= phase <= 2.0:
        raise ValueError("Invalid, non-precommitted phase")
    state = [0j] * 8
    state[0] = 1 + 0j
    for bit, value in enumerate(f):
        state = _ry(state, bit, 1.4 * math.tanh(value))
    for i in range(8):
        z = tuple(1 if i & (1 << bit) else -1 for bit in range(3))
        coupling = z[0] * z[1] + z[1] * z[2] - z[0] * z[2]
        feature_phase = sum(z[j] * math.tanh(f[j]) for j in range(3))
        state[i] *= cmath.exp(1j * phase * (.54 * coupling + .21 * feature_phase))
    for bit in range(3):
        state = _hadamard(state, bit)
    for bit, value in enumerate(f):
        state = _ry(state, bit, .65 * math.tanh(value))
    state = _hadamard(state, 1)
    norm = sum(abs(a) ** 2 for a in state)
    if abs(norm - 1) > EPSILON:
        raise ArithmeticError("Non-unitary quantum simulation")
    probability = sum(abs(a) ** 2 for i, a in enumerate(state) if i.bit_count() >= 2)
    if not -EPSILON <= probability <= 1 + EPSILON:
        raise ArithmeticError("Invalid Born probability")
    return min(1., max(0., probability))


def classical_probability(features):
    """Same three observed features, without quantum interference."""
    f = _finite(features)
    p = [.5 + .43 * math.tanh(x) for x in f]
    return (p[0] * p[1] * (1 - p[2])
            + p[0] * (1 - p[1]) * p[2]
            + (1 - p[0]) * p[1] * p[2] + p[0] * p[1] * p[2])


def quantum_and_control(features):
    """Identical inputs: phase-sweep robustness, zero-phase and classical."""
    f = _finite(features)
    versions = {str(p): quantum_probability(f, p) for p in PHASES}
    active = (versions["0.7"], versions["1.0"], versions["1.3"])
    return {
        "quantum": versions["1.0"],
        "quantum_zero_phase": versions["0.0"],
        "quantum_robust": min(active),
        "classical": classical_probability(f),
        "quantum_signal": (1 if min(active) >= CUTOFF else
                           -1 if max(active) <= 1 - CUTOFF else 0),
        "classical_signal": (1 if classical_probability(f) >= CUTOFF else
                             -1 if classical_probability(f) <= 1 - CUTOFF else 0),
        "unitary_state_dimension": 8,
        "quantum_hardware_used": False,
    }


def completed_causal_features(bars, index):
    """Only OHLC data at or before index; signal must trade at index+1 or later."""
    if index < 96 or index >= len(bars):
        raise ValueError("Required completed history unavailable")
    window = bars[index - 96:index + 1]
    closes = []
    for bar in window:
        op, hi, lo, cl = (float(bar[k]) for k in ("open", "high", "low", "close"))
        if not all(math.isfinite(x) for x in (op, hi, lo, cl)):
            raise ValueError("Nonfinite OHLC")
        if not 0 < lo <= op <= hi or not lo <= cl <= hi:
            raise ValueError("Inconsistent OHLC")
        closes.append(cl)
    tr = []
    for offset in range(83, 97):  # most recent 14 completed true ranges
        current, previous = window[offset], closes[offset - 1]
        tr.append(max(float(current["high"]) - float(current["low"]),
                      abs(float(current["high"]) - previous),
                      abs(float(current["low"]) - previous)))
    atr_fraction = sum(tr) / len(tr) / closes[-1]
    if atr_fraction <= 0:
        raise ValueError("Undefined ATR")
    out = []
    for lag in (8, 32, 96):
        raw = math.log(closes[-1] / closes[-1 - lag])
        scale = max(atr_fraction * math.sqrt(lag), 1e-8)
        out.append(max(-3., min(3., raw / scale)))
    return tuple(out)


def audit_closed_paper_report(report):
    """Check evidence schema, not prove profitability; fail closed on missing data.

    Reports with exceptional performance remain only *paper candidates*:
    verification of live fills and prospective independent validation is separate.
    """
    if not isinstance(report, dict):
        raise ValueError("Paper report must be an object")
    if (report.get("start_usdt") != START_USDT or
        report.get("goal_usdt") != TARGET_USDT or
        report.get("real_orders") != 0 or
        report.get("quantum_hardware_used") is not False):
        raise ValueError("Wrong goal or potentially misleading provenance")
    data = report.get("data")
    if (not isinstance(data, dict) or
        data.get("precommitted") is not True or
        not isinstance(data.get("public_market_sha256"), dict) or
        not data["public_market_sha256"]):
        raise ValueError("Missing predeclared public data evidence")
    models = report.get("models")
    if not isinstance(models, dict) or any(k not in models for k in MODELS):
        raise ValueError("Identical-input classical control is mandatory")
    summaries = {}
    for model in MODELS:
        group = models[model]
        if not isinstance(group, dict) or any(p not in group for p in PERIODS):
            raise ValueError("Missing train or untouched chronological holdout")
        summaries[model] = {}
        for period in PERIODS:
            frames = group[period]
            if not isinstance(frames, dict) or any(c not in frames for c in COSTS):
                raise ValueError("Both ordinary and stress-cost tests are mandatory")
            summaries[model][period] = {}
            for cost in COSTS:
                row = frames[cost]
                if not isinstance(row, dict):
                    raise ValueError("Missing period cost results")
                end = row.get("closed_equity_usdt")
                trades = row.get("closed_trades")
                drawdown = row.get("max_drawdown_pct")
                ruined = row.get("ruin_happened")
                if (type(end) not in (int, float) or
                    type(trades) is not int or
                    type(drawdown) not in (int, float) or
                    type(ruined) is not bool or
                    not math.isfinite(end) or not math.isfinite(drawdown) or
                    end < 0 or trades < 0 or not 0 <= drawdown <= 100):
                    raise ValueError("Invalid closed-trade accounting")
                if trades == 0 and abs(end - START_USDT) > 1e-7:
                    raise ValueError("Unfilled strategy cannot claim realized earnings")
                if row.get("hit_128") is not None and row["hit_128"] != (end >= TARGET_USDT):
                    raise ValueError("Floating profit falsely counted as closed +128%")
                summaries[model][period][cost] = {
                    "net_return_pct": round((end / START_USDT - 1) * 100, 5),
                    "closed_target_hit": end >= TARGET_USDT,
                    "closed_trades": trades,
                    "max_drawdown_pct": drawdown,
                    "ruin": ruined,
                }
    quantum_holdouts = [summaries["quantum"][p][c] for p in HOLDOUTS for c in COSTS]
    classical_holdouts = [summaries["classical"][p][c] for p in HOLDOUTS for c in COSTS]
    controlled_pass = (all(r["closed_target_hit"] and not r["ruin"] and
                           r["closed_trades"] >= 20 and r["max_drawdown_pct"] <= 30
                           for r in quantum_holdouts) and
                       all(q["net_return_pct"] > c["net_return_pct"]
                           for q, c in zip(quantum_holdouts, classical_holdouts)))
    return {
        "candidate_for_prospective_only": bool(controlled_pass),
        "verified_live_plus128": False,
        "real_orders": 0,
        "models": summaries,
        "verdict": ("PAPER_CANDIDATE_NOT_REAL_PROFIT" if controlled_pass
                    else "NO_REPLICATED_128_EDGE_DO_NOT_DEPLOY"),
    }


def run_selfcheck():
    """Synthetic features only. CI success NEVER means +128% was achieved."""
    sample = (.3, -.1, .5)
    scores = quantum_and_control(sample)
    if not all(0 <= scores[k] <= 1 for k in
               ("quantum", "quantum_zero_phase", "quantum_robust", "classical")):
        raise ArithmeticError("Probability out of range")
    if scores["quantum_hardware_used"] is not False:
        raise AssertionError("Hardware claim prohibited")
    return {
        "goal_usdt": TARGET_USDT,
        "goal_return_pct": 128,
        "quantum_method": "classical 3-qubit unitary + ZZ interaction + Born projection",
        "checks": ["unitarity", "phase_ablation", "same_input_classical_control",
                   "causal_ohlc_contract", "closed_equity_only", "two_holdouts",
                   "ordinary_and_stress_costs"],
        "sample_diagnostic": scores,
        "historical_profit_proven": False,
        "live_profit_proven": False,
        "trade_orders_submitted": 0,
        "verdict": "MATH_AND_PROTOCOL_ONLY_NOT_A_PROFIT_BACKTEST",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--out", default="reports/titan_quantum_ci_gate.json")
    args = parser.parse_args()
    report = run_selfcheck()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("TITAN QUANTUM CI", report["verdict"], "NO ORDERS", flush=True)
    print("QUANTUM CORE", report["quantum_method"], "classical baseline included")
    if args.ci and report["historical_profit_proven"]:
        raise RuntimeError("CI invariant: fake profitable research verdict")


if __name__ == "__main__":
    main()

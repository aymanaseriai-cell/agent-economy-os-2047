"""QUANT2037: seven transparent, deterministic research filters over six OKX agents.

Public-market analysis only. This is not quantum computing, six autonomous LLMs,
a validated alpha model, position management, or an order executor.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter


def _emit(name, direction=0, risk="PASS", **metrics):
    if direction not in (-1, 0, 1) or risk not in ("PASS", "CAUTION", "VETO"):
        raise ValueError("Invalid system verdict")
    return {
        "system": name,
        "vote": direction,
        "direction": {1: "LONG", -1: "SHORT", 0: "NEUTRAL"}[direction],
        "risk": risk,
        "metrics": metrics,
    }


def _returns(bars):
    values = [float(x["close"]) for x in bars]
    if len(values) < 12 or any(p <= 0 or not math.isfinite(p) for p in values):
        raise ValueError("Not enough finite positive closed prices")
    return [math.log(b / a) for a, b in zip(values, values[1:])]


# SYSTEM 1: Robust jump detection, not a prediction of the next candle.
def jump_sentinel(bars):
    values = _returns(bars)
    history = values[-65:-1]
    if len(history) < 24:
        raise ValueError("Insufficient non-overlapping history for jump baseline")
    center = statistics.median(history)
    mad = statistics.median(abs(x - center) for x in history)
    # MAD floor prevents constant-price data from generating infinite z-scores.
    scale = max(1.4826 * mad, 0.0002)
    score = abs(values[-1] - center) / scale
    risk = "VETO" if score >= 8.0 else "CAUTION" if score >= 4.5 else "PASS"
    return _emit("01_jump_sentinel", risk=risk, robust_jump_z=round(score, 3),
                 last_log_return=round(values[-1], 6), baseline_points=len(history))


# SYSTEM 2: Ordinal-pattern entropy: indicates order/disorder, not win rate.
def permutation_entropy(bars):
    xs = _returns(bars)[-110:]
    if len(xs) < 40:
        raise ValueError("Not enough returns for permutation entropy")
    # Ordinal patterns of 3 consecutive log returns, stable tie-breaking.
    counts = Counter(tuple(sorted(range(3), key=lambda k: (xs[i + k], k)))
                     for i in range(len(xs) - 2))
    total = sum(counts.values())
    h = -sum((n / total) * math.log(n / total) for n in counts.values()) / math.log(6)
    # High entropy means we decline to infer direction from this measurement.
    trend = math.log(float(bars[-1]["close"]) / float(bars[-17]["close"]))
    vote = (1 if trend > 0 else -1) if h < .80 and abs(trend) >= .007 else 0
    return _emit("02_permutation_entropy", direction=vote,
                 risk="CAUTION" if h > .98 else "PASS",
                 normalized_entropy=round(h, 4), move_16_bars_pct=round(100 * (math.exp(trend) - 1), 3),
                 observed_patterns=len(counts))


# SYSTEM 3: Overlapping variance ratio (diagnostic, not a hypothesis-test p-value).
def variance_ratio(bars):
    r = _returns(bars)[-140:]
    if len(r) < 50:
        raise ValueError("Not enough returns for variance ratio")
    q = 4
    one = statistics.pvariance(r)
    multi = [sum(r[i:i + q]) for i in range(len(r) - q + 1)]
    ratio = statistics.pvariance(multi) / (q * one) if one > 1e-15 else 1.0
    recent = sum(r[-16:])
    vote = (1 if recent > 0 else -1) if ratio >= 1.2 and abs(recent) >= .006 else 0
    return _emit("03_variance_ratio", direction=vote,
                 variance_ratio_4=round(ratio, 4), last_16_log_return=round(recent, 6),
                 note="Not a formal Lo-MacKinlay significance test")


# SYSTEM 4: 24h-to-24h volume-profile migration (approximate OHLCV only).
def value_migration(bars):
    if len(bars) < 192:
        raise ValueError("Need at least 192 completed 15m candles (48 hours)")
    frame = bars[-192:]
    low = min(float(x["low"]) for x in frame)
    high = max(float(x["high"]) for x in frame)
    if not 0 < low < high:
        raise ValueError("Invalid 48h price range")
    bins = 40
    step = (high - low) / bins

    def profile(part):
        amounts = [0.0] * bins
        for bar in part:
            left = max(0, min(bins - 1, int((float(bar["low"]) - low) / step)))
            right = max(0, min(bins - 1, int((float(bar["high"]) - low) / step)))
            if right < left:
                raise ValueError("Invalid candle high/low")
            quote = float(bar["quote_vol"])
            if quote < 0 or not math.isfinite(quote):
                raise ValueError("Invalid quote volume")
            per_bin = quote / (right - left + 1)
            for idx in range(left, right + 1):
                amounts[idx] += per_bin
        if not sum(amounts):
            raise ValueError("No volume for 24h value migration")
        idx = max(range(bins), key=lambda i: amounts[i])
        return low + (idx + .5) * step

    old_poc, new_poc = profile(frame[:96]), profile(frame[96:])
    shift_bp = 10000 * (new_poc / old_poc - 1)
    vote = 1 if shift_bp >= 25 else -1 if shift_bp <= -25 else 0
    return _emit("04_value_area_migration", direction=vote,
                 prior_24h_poc_approx=round(old_poc, 9),
                 latest_24h_poc_approx=round(new_poc, 9), poc_shift_bp=round(shift_bp, 2),
                 method="OHLCV candle-volume histogram; not tick-level fixed volume profile")


# SYSTEM 5: L2 book concentration and imbalance; not spoofing detection.
def depth_fragility(book):
    bids, asks = book.get("bids", []), book.get("asks", [])
    if len(bids) < 10 or len(asks) < 10:
        return _emit("05_depth_fragility", risk="VETO", reason="orderbook_too_shallow_or_missing")

    def sizes(levels):
        vals = [float(level[1]) for level in levels[:20]]
        if not vals or any(v < 0 or not math.isfinite(v) for v in vals):
            raise ValueError("Invalid orderbook size")
        return vals

    bid, ask = sizes(bids), sizes(asks)
    b, a = sum(bid), sum(ask)
    if not min(b, a) > 0:
        return _emit("05_depth_fragility", risk="VETO", reason="no_both_sides_depth")
    imbalance = (b - a) / (b + a)
    concentration = max(sum(bid[:5]) / b, sum(ask[:5]) / a)
    risk = "CAUTION" if concentration > .93 or abs(imbalance) > .65 else "PASS"
    return _emit("05_depth_fragility", risk=risk,
                 depth_imbalance=round(imbalance, 4),
                 max_top5_share=round(concentration, 4), observed_levels=min(len(bids), len(asks)),
                 note="One orderbook snapshot; cannot identify spoofing")


# SYSTEM 6: Two-phase aggressor flow change, not historical cumulative volume delta.
def flow_acceleration(trades):
    valid = []
    for row in trades:
        if row.get("side") not in ("buy", "sell"):
            continue
        try:
            ts, qty = int(row["ts"]), float(row["sz"])
        except (KeyError, TypeError, ValueError):
            continue
        if qty > 0 and math.isfinite(qty):
            valid.append((ts, 1 if row["side"] == "buy" else -1, qty))
    if len(valid) < 40:
        return _emit("06_flow_acceleration", risk="CAUTION", reason="insufficient_timestamped_trade_sample",
                     valid_trades=len(valid))
    valid.sort(key=lambda v: v[0])
    split = len(valid) // 2

    def pressure(part):
        total = sum(row[2] for row in part)
        return sum(row[1] * row[2] for row in part) / total if total else 0.0

    earlier, recent = pressure(valid[:split]), pressure(valid[split:])
    change = recent - earlier
    vote = 1 if recent >= .2 and change >= .12 else -1 if recent <= -.2 and change <= -.12 else 0
    return _emit("06_flow_acceleration", direction=vote,
                 older_sample_delta=round(earlier, 4), recent_sample_delta=round(recent, 4),
                 pressure_change=round(change, 4), sample_size=len(valid),
                 caveat="Recent public trades sample; no full-history CVD or whale attribution")


# SYSTEM 7: Counterfactual stability under removal of each core directional agent.
def counterfactual_stability(core):
    direction = {"LONG": 1, "SHORT": -1, "WAIT": 0}[core["signal"]]
    voters = [x for x in core["agents"] if x["agent"] in (
        "02_auction_cartographer", "03_tape_detective", "04_derivatives_intelligence",
        "05_structure_navigator")]
    if len(voters) != 4:
        return _emit("07_counterfactual_stability", risk="VETO", reason="missing_core_directional_agents")
    survival = 0
    if direction:
        for skip in range(len(voters)):
            others = voters[:skip] + voters[skip + 1:]
            own = [a for a in others if a["vote"] == direction]
            opposite = [a for a in others if a["vote"] == -direction]
            strength = sum(a["strength"] for a in own)
            opposition = sum(a["strength"] for a in opposite)
            if len(own) >= 2 and strength >= 3 and strength - opposition >= 2:
                survival += 1
    fraction = survival / 4 if direction else 0
    return _emit("07_counterfactual_stability", direction=direction if survival >= 2 else 0,
                 risk="CAUTION" if direction and survival < 2 else "PASS",
                 leave_one_out_survivals=survival, total_knockouts=4,
                 directional_consensus_survival_ratio=round(fraction, 2),
                 caveat="Stress diagnostic, not an independently trained predictive model")


def evaluate_advanced(bars, book, trades, core):
    """Run exactly seven systems and apply explicit, risk-first secondary gating.

    Never converts the original WAIT into a trade label.
    A data-quality exception fails closed at the upstream per-market boundary.
    """
    systems = [
        jump_sentinel(bars),
        permutation_entropy(bars),
        variance_ratio(bars),
        value_migration(bars),
        depth_fragility(book),
        flow_acceleration(trades),
        counterfactual_stability(core),
    ]
    original = core["signal"]
    direction = 1 if original == "LONG" else -1 if original == "SHORT" else 0
    directional_models = systems[1:4] + systems[5:6]
    confirming = sum(s["vote"] == direction for s in directional_models) if direction else 0
    opposing = sum(s["vote"] == -direction for s in directional_models) if direction else 0
    reasons = [x["system"] + ":veto" for x in systems if x["risk"] == "VETO"]
    if direction and confirming < 1:
        reasons.append("no_independent_quant_confirmation")
    if direction and opposing >= 2:
        reasons.append("two_or_more_quant_contradictions")
    decision = original if not reasons else "WAIT"
    return {
        "advanced_systems": systems,
        "advanced_system_count": len(systems),
        "core_signal_before_advanced": original,
        "advanced_confirmations": confirming,
        "advanced_contradictions": opposing,
        "advanced_veto_reasons": reasons,
        "signal": decision,
        "execution": "DISABLED",
        "order_count": 0,
        "warning": "No live trading. These quantitative rules are uncalibrated and not a validated edge.",
    }

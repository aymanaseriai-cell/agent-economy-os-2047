"""TITAN COSMOS: ten deterministic, physics/quantum-inspired mathematical diagnostics.

READ ONLY. Uses historical PUBLIC candles and order-book snapshots only.
No divine/supernatural capability, genuine quantum processor, proven predictive edge,
live authorization, order placement or leverage control. Never overrides an executor veto.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter

SYSTEMS = (
    "01_quantum_amplitude_interference_proxy",
    "02_ising_spin_alignment",
    "03_shannon_market_entropy",
    "04_fourier_spectral_resonance",
    "05_hurst_diffusion_exponent",
    "06_ornstein_uhlenbeck_reversion",
    "07_extreme_tail_event_horizon",
    "08_escape_velocity_momentum",
    "09_gravitational_orderbook_pressure",
    "10_multiscale_phase_coherence",
)


def _prices(bars, minimum=48):
    if not isinstance(bars, list) or len(bars) < minimum:
        raise ValueError("Insufficient completed candle history")
    result = []
    for item in bars:
        if not isinstance(item, dict):
            raise ValueError("Malformed candle row")
        value = float(item["close"])
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Invalid nonpositive candle price")
        result.append(value)
    return result


def _safe(value, digits=6):
    if value is None:
        return None
    v = float(value)
    return round(v, digits) if math.isfinite(v) else None


def _point(name, **metrics):
    return {"name": name, "status": "DIAGNOSTIC_ONLY",
            "metrics": {key: _safe(value) for key, value in metrics.items()}}


def _variance(values):
    return statistics.pvariance(values) if len(values) >= 2 else 0.0


def _entropy_of_signs(returns):
    # Three states reduce falsely significant tiny-move directional votes.
    states = [1 if x > 0.0001 else -1 if x < -0.0001 else 0 for x in returns]
    counts = Counter(states)
    n = len(states)
    return -sum((v / n) * math.log(v / n) for v in counts.values()) / math.log(3)


def _fourier_concentration(returns):
    # Normalized concentration of top three nonzero Fourier bins. O(48^2).
    values = list(returns[-48:])
    mean = statistics.fmean(values)
    values = [x - mean for x in values]
    n = len(values)
    powers = []
    for k in range(1, n // 2 + 1):
        real = sum(v * math.cos(2 * math.pi * k * j / n) for j, v in enumerate(values))
        imag = sum(v * math.sin(2 * math.pi * k * j / n) for j, v in enumerate(values))
        powers.append(real * real + imag * imag)
    total = sum(powers)
    return sum(sorted(powers, reverse=True)[:3]) / total if total > 1e-18 else 0.0


def _hurst_proxy(prices):
    x = [math.log(v) for v in prices[-96:]]
    increments_1 = [x[j] - x[j - 1] for j in range(1, len(x))]
    increments_4 = [x[j] - x[j - 4] for j in range(4, len(x))]
    v1, v4 = _variance(increments_1), _variance(increments_4)
    if v1 <= 1e-18 or v4 <= 1e-18:
        return None
    # Variance growth proxy, not a long-memory proof or calibrated Hurst estimate.
    return min(1.0, max(0.0, math.log(v4 / v1) / (2 * math.log(4))))


def _ou_proxy(prices):
    x = [math.log(v) for v in prices[-48:]]
    mean = statistics.fmean(x)
    vol = statistics.pstdev(x)
    zscore = (x[-1] - mean) / vol if vol > 1e-12 else 0.0
    prev, nxt = x[:-1], x[1:]
    mprev, mnxt = statistics.fmean(prev), statistics.fmean(nxt)
    denom = sum((v - mprev) ** 2 for v in prev)
    phi = (sum((a - mprev) * (b - mnxt) for a, b in zip(prev, nxt)) / denom
           if denom > 1e-18 else 0.0)
    halflife = -math.log(2) / math.log(phi) if 0 < phi < 1 else None
    return zscore, halflife


def _orderbook_pressure(book):
    if not isinstance(book, dict):
        return None
    try:
        bid = sum(float(level[1]) for level in book.get("bids", [])[:20])
        ask = sum(float(level[1]) for level in book.get("asks", [])[:20])
    except (ValueError, TypeError, IndexError):
        return None
    if not all(math.isfinite(v) and v >= 0 for v in (bid, ask)) or bid + ask <= 0:
        return None
    return (bid - ask) / (bid + ask)


def evaluate_cosmos(bars15, bars1h, bars4h, book):
    """Produce ten reproducible diagnostics without changing LONG/SHORT/WAIT."""
    try:
        price = _prices(bars15, minimum=96)
        h1 = _prices(bars1h, minimum=30)
        h4 = _prices(bars4h, minimum=15)
        ret = [math.log(price[j] / price[j - 1]) for j in range(1, len(price))]
        window = ret[-48:]
        sigma = statistics.pstdev(window)
        absolute = sorted(abs(x) for x in ret[-96:])
        signs = [1 if x > 0 else -1 if x < 0 else 0 for x in window]
        magnitude = sum(abs(x) for x in window)
        weighted_amp = sum(window) / magnitude if magnitude > 1e-12 else 0.0
        magnetization = statistics.fmean(signs)
        coupling = statistics.fmean(a * b for a, b in zip(signs[:-1], signs[1:]))
        # Empirical 95th percentile / median; not a forecast of maximum loss.
        median_abs = statistics.median(absolute)
        empirical_p95 = absolute[min(len(absolute)-1, int(len(absolute)*0.95))]
        shock_ratio = empirical_p95 / median_abs if median_abs > 1e-12 else 0.0
        recent_12 = sum(window[-12:])
        escape = recent_12 / (sigma * math.sqrt(12)) if sigma > 1e-12 else 0.0
        ou_z, ou_half = _ou_proxy(price)
        # Coherence compares log returns in native timeframe bars, not clock-speed equality.
        trend15 = math.log(price[-1] / price[-6])
        trend1h = math.log(h1[-1] / h1[-4])
        trend4h = math.log(h4[-1] / h4[-3])
        trend_signs = [1 if v > 0 else -1 if v < 0 else 0
                       for v in (trend15, trend1h, trend4h)]
        coherent = abs(sum(trend_signs)) / 3.0
        systems = [
            _point(SYSTEMS[0], normalized_amplitude_proxy=weighted_amp),
            _point(SYSTEMS[1], magnetization=magnetization, nearest_neighbor_coupling=coupling),
            _point(SYSTEMS[2], normalized_sign_entropy=_entropy_of_signs(window)),
            _point(SYSTEMS[3], top_three_frequency_energy_share=_fourier_concentration(window)),
            _point(SYSTEMS[4], diffusion_exponent_proxy=_hurst_proxy(price)),
            _point(SYSTEMS[5], latest_logprice_zscore=ou_z, ar1_half_life_bars=ou_half),
            _point(SYSTEMS[6], empirical_p95_to_median_shock_ratio=shock_ratio),
            _point(SYSTEMS[7], momentum_to_realized_volatility=escape),
            _point(SYSTEMS[8], top20_depth_imbalance=_orderbook_pressure(book)),
            _point(SYSTEMS[9], direction_coherence=coherent,
                   trend_15m=trend15, trend_1h=trend1h, trend_4h=trend4h),
        ]
        return {"cosmos_system_count": len(systems), "cosmos_systems": systems,
                "cosmos_research_only": True, "cosmos_data_valid": True,
                "cosmos_errors": [], "orders_placed": 0,
                "warning": "Physics/quantum metaphors; no quantum computer, supernatural edge or live-order authority."}
    except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as exc:
        # Noncritical research must not convert bad observations into fabricated signals.
        return {"cosmos_system_count": len(SYSTEMS), "cosmos_systems": [],
                "cosmos_research_only": True, "cosmos_data_valid": False,
                "cosmos_errors": [type(exc).__name__], "orders_placed": 0,
                "warning": "Research data unavailable. No trade decision may be derived from COSMOS."}

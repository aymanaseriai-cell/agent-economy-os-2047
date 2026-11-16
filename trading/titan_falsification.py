"""TITAN FALSIFICATION LAB: deliberately attempt to disprove apparent alpha.

No keys, private API calls, exchange trading, position sizing or live approval.
Expanding chronological training; three disjoint unseen test windows; signal at
close(t), next-bar open(t+1) to close(t+1) fills, and explicit round-trip costs.
Circular-shift null is heuristic and NOT a calibrated statistical p-value for
dependent/nonstationary financial data. No strategy can be promoted by this lab.
"""
from __future__ import annotations

import math
import random

from trading.titan_edge_lab import signal_at_close, validate_bars

STRATEGIES = ("ema_trend", "donchian_breakout", "bollinger_reversion")


def _trade_series(bars, strategy, start, end):
    """One entry per signal; no overlapping trades; returns on FOLLOWING bar."""
    out = []
    for t in range(start, end):
        side = signal_at_close(bars, t, strategy)
        nxt = bars[t + 1]
        raw_return = float(nxt["close"]) / float(nxt["open"]) - 1.0
        # Preserve the REALIZED return even for NO-TRADE candles so the
        # circular-shift null has a complete, unbiased return sequence.
        out.append((side, raw_return))
    return out


def _costed(series, roundtrip_cost):
    trades = [side * raw - roundtrip_cost for side, raw in series if side]
    wealth = peak = 1.0
    worst_drawdown = 0.0
    for net in trades:
        wealth *= max(1e-9, 1 + net)
        peak = max(peak, wealth)
        worst_drawdown = max(worst_drawdown, 1 - wealth / peak)
    return {"trades": len(trades),
            "net_sum_pct": round(sum(trades) * 100, 5),
            "compounded_pct": round((wealth - 1) * 100, 5),
            "max_drawdown_pct": round(worst_drawdown * 100, 5),
            "wins": sum(x > 0 for x in trades),
            "fragile_without_best_trade_pct": (
                round((sum(trades) - max(trades)) * 100, 5) if trades else None)}


def _regime_divergence(bars, train_end, test_start, test_end):
    """Jensen-Shannon divergence in nats for 3 return bins. Observational only."""
    def counts(lo, hi):
        x = [0.5, 0.5, 0.5]
        for t in range(lo, hi):
            prev = float(bars[t - 1]["close"])
            r = float(bars[t]["close"]) / prev - 1.0
            x[0 if r < -0.0008 else 2 if r > 0.0008 else 1] += 1
        n = sum(x)
        return [v / n for v in x]
    train = counts(max(1, train_end - 48), train_end)
    test = counts(test_start, test_end)
    mixture = [(a + b) / 2 for a, b in zip(train, test)]
    return 0.5 * sum(a * math.log(a / m) + b * math.log(b / m)
                     for a, b, m in zip(train, test, mixture))


def _null_shift_pvalue(fold_vectors, cost, seed=2047, simulations=96):
    """Circularly shift signal timing against next-bar returns INSIDE each fold.

    Preserve within-fold signal autocorrelation and realized gross return order.
    Not a statistically calibrated independence test under all market regimes.
    """
    observed = sum(side * raw - cost for vec in fold_vectors
                   for side, raw in vec if side)
    rng = random.Random(seed)
    exceed = 0
    for _ in range(simulations):
        score = 0.0
        for vec in fold_vectors:
            n = len(vec)
            if n < 3:
                continue
            shift = rng.randrange(1, n)
            # The recorded raw return must include non-entry candles.
            # Otherwise the null would systematically attenuate the
            # randomly shifted strategy and overstate apparent significance.
            raw = [realized for _, realized in vec]
            for i in range(n):
                moved_side = vec[(i + shift) % n][0]
                if moved_side:
                    score += moved_side * raw[i] - cost
        if score >= observed - 1e-12:
            exceed += 1
    return (exceed + 1) / (simulations + 1)


def falsify_edge(bars, *, fee_bp_per_side=5, slippage_bp_per_side=5):
    """Bias-aware, fail-closed SHADOW audit on >=200 complete 15m OHLCV rows.

    This does not establish a profitable strategy. Never returns an allow-trade
    boolean; only diagnostics whose integrity can be independently tested.
    """
    try:
        validate_bars(bars, minimum=200)
        fee, slip = float(fee_bp_per_side), float(slippage_bp_per_side)
        if not all(math.isfinite(v) and 0 <= v <= 100 for v in (fee, slip)):
            raise ValueError("Invalid modeled execution cost")
        cost = 2 * (fee + slip) / 10000
        n = len(bars)
        boundaries = [int(n * 0.48), int(n * 0.65), int(n * 0.82), n - 1]
        folds = []
        test_vectors = []
        for k in range(3):
            start, end = boundaries[k], boundaries[k+1]
            # Last training fill occurs at start-1. First test signal is at start.
            # Thus no training label can contain any test-period outcome.
            history_end = start - 2
            train_results = {
                strategy: _costed(_trade_series(bars, strategy, 50, history_end), cost)
                for strategy in STRATEGIES}
            eligible = [s for s in STRATEGIES if train_results[s]["trades"] >= 8]
            if not eligible:
                folds.append({"fold": k+1, "train_end_exclusive": history_end,
                              "test_start_signal": start, "test_end_exclusive": end,
                              "selected": None, "training": train_results,
                              "holdout": None, "regime_js_divergence": None})
                continue
            # Training-only optimization; never inspect the holdout to pick a strategy.
            best = max(eligible, key=lambda s: (
                train_results[s]["net_sum_pct"], -STRATEGIES.index(s)))
            test = _trade_series(bars, best, start, end)
            test_vectors.append(test)
            folds.append({
                "fold": k+1, "train_end_exclusive": history_end,
                "test_start_signal": start, "test_end_exclusive": end,
                "selected": best, "training": train_results,
                "holdout": _costed(test, cost),
                "regime_js_divergence": round(
                    _regime_divergence(bars, history_end, start, end), 6)})
        total_trades = sum(sum(1 for side, _ in v if side) for v in test_vectors)
        stress = {
            str(multiplier) + "x": round(sum(
                _costed(v, cost * multiplier)["net_sum_pct"] for v in test_vectors), 5)
            for multiplier in (1, 2, 4)}
        pvalue = (_null_shift_pvalue(test_vectors, cost)
                  if total_trades >= 20 and len(test_vectors) == 3 else None)
        test_fold_positive = sum(f["holdout"]["net_sum_pct"] > 0 for f in folds
                                 if f["holdout"] is not None)
        unstable = sum((f["regime_js_divergence"] or 0) > 0.10 for f in folds)
        # Research verdict, never an entry gate. This is deliberately stringent.
        status = ("INSUFFICIENT_EVIDENCE" if total_trades < 20 or len(test_vectors) < 3
                  else "FRAGILE_OR_UNPROVEN" if (
                      stress["4x"] <= 0 or test_fold_positive < 2
                      or pvalue is None or pvalue > 0.05 or unstable > 0)
                  else "SURVIVED_SHADOW_HEURISTICS_NOT_VALIDATED")
        return {"data_valid": True, "status": status, "research_only": True,
                "can_trade_live": False, "orders_placed": 0,
                "folds": folds, "out_of_sample_trades": total_trades,
                "out_of_sample_positive_folds": test_fold_positive,
                "regime_shift_folds": unstable,
                "cost_bp_per_side": fee + slip,
                "stress_net_sum_pct": stress,
                "circular_shift_null_tail_fraction": (
                    round(pvalue, 6) if pvalue is not None else None),
                "caveat": "Not calibrated alpha, not a futures simulator, no live promotion."}
    except (ValueError, TypeError, KeyError, IndexError, OverflowError,
            ZeroDivisionError):
        return {"data_valid": False, "status": "INVALID_DATA_OR_COSTS",
                "research_only": True, "can_trade_live": False,
                "orders_placed": 0, "folds": [], "out_of_sample_trades": 0}

#!/usr/bin/env python3
"""TITAN ADVERSARIAL TRIBUNAL — frozen-market, NO-ORDER falsification.

Research-only, not a strategy, API client, liquidation simulator, or permission
to trade. Separates training-only selection from untouched holdout, preserves
same-day market clustering, and compares goal-first versus severe-loss-first
frequencies under explicitly hypothetical bankroll multipliers.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path

from trading.edge_lab import (
    DEFAULT_SYMBOLS, TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE, STRESS_SLIPPAGE,
    FUNDING_PER_8H, TRAIN_FRACTION, signals, trade_simulation,
)
from trading.titan_regime_research import (
    CANDIDATES, BASELINES, WARMUP_BARS, regime_signals, validate_frozen,
)

STRATEGIES = BASELINES + CANDIDATES
INITIAL_EQUITY = 4.15
TARGET_EQUITY = 8.30
# A severe-loss barrier, not an exchange liquidation threshold.
SEVERE_LOSS_EQUITY = 0.83
SECONDS_PER_DAY_MS = 86_400_000
MAX_PATHS = 1200
BOOTSTRAP_SEED = 2047
# A decision rule frozen before touching holdout.
MIN_TRAIN_TRADES = 50
MIN_POSITIVE_TRAIN_MARKETS = 4
MIN_MEAN_TRAIN_RETURN_PCT = 0.5
MIN_MEAN_TRAIN_STRESS_PCT = 0.0
# These are synthetic notional/equity ratios, NOT instructions for real orders.
EXPOSURES = (
    ("guarded_0_2x_notional", 0.2),
    ("aggressive_4x_notional", 4.0),
    ("extreme_49_5x_notional", 49.5),
)


def safe_number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a return")
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("Nonfinite return")
    return x


def single_position_episodes(trades_by_symbol):
    """One hypothetical slot, earliest entry wins; never stack overlapping swaps.

    Fully deterministic across dict order; uses simulated entry and exit times.
    A different live concurrency policy would require its own dedicated proof.
    """
    pool = []
    for symbol, trades in sorted(trades_by_symbol.items()):
        for row in trades:
            entry, exit_ts = int(row["entry_ts"]), int(row["exit_ts"])
            notional = safe_number(row["notional"])
            net = safe_number(row["net_usd"])
            if entry > exit_ts or notional <= 0 or not symbol.endswith("-USDT-SWAP"):
                raise ValueError("Invalid hypothetical trade event")
            pool.append({"symbol": symbol, "entry_ts": entry, "exit_ts": exit_ts,
                         "net_per_notional": net / notional})
    pool.sort(key=lambda x: (x["entry_ts"], x["symbol"], x["exit_ts"]))
    accepted, latest_exit = [], -1
    for row in pool:
        if row["entry_ts"] <= latest_exit:
            continue
        accepted.append(row)
        latest_exit = row["exit_ts"]
    return accepted


def daily_blocks(events):
    """Preserve chronological within-day clusters, including no-trade days."""
    if not events:
        return []
    buckets = {}
    for row in events:
        day = int(row["entry_ts"]) // SECONDS_PER_DAY_MS
        buckets.setdefault(day, []).append(safe_number(row["net_per_notional"]))
    return [buckets.get(d, []) for d in range(min(buckets), max(buckets)+1)]


def run_path(blocks, *, notional_to_equity, start=INITIAL_EQUITY,
             goal=TARGET_EQUITY, severe=SEVERE_LOSS_EQUITY,
             cost_overlay_per_notional=0.0):
    """Absorbing goal/severe-loss barriers; no invented take-profit fills.

    A move crossing the goal only means hypothetical end-of-trade equity
    crossed it. Liquidation before the exit and exchange minimums are unknown.
    """
    if (not math.isfinite(notional_to_equity) or notional_to_equity > 100
            or notional_to_equity <= 0 or not 0 <= cost_overlay_per_notional <= .2
            or not 0 < severe < start < goal):
        raise ValueError("Invalid counterfactual capital scenario")
    equity, highwater, worst_dd, steps = start, start, 0.0, 0
    for block in blocks:
        for value in block:
            r = safe_number(value) - cost_overlay_per_notional
            # This model treats the gap to zero as complete loss, not a margin
            # liquidation execution, negative cash balance or insurance fund.
            equity = max(0.0, equity * (1 + notional_to_equity * r))
            steps += 1
            highwater = max(highwater, equity)
            worst_dd = max(worst_dd, (highwater-equity)/highwater)
            # Severe loss is checked first so an ambiguous account state
            # cannot be counted as a successful target event.
            if equity <= severe:
                return {"state": "SEVERE_LOSS_FIRST", "equity": round(equity, 6),
                        "trades": steps, "max_drawdown_pct": round(worst_dd*100, 3)}
            if equity >= goal:
                return {"state": "GOAL_FIRST", "equity": round(equity, 6),
                        "trades": steps, "max_drawdown_pct": round(worst_dd*100, 3)}
    return {"state": "NEITHER", "equity": round(equity, 6), "trades": steps,
            "max_drawdown_pct": round(worst_dd*100, 3)}


def block_bootstrap(blocks, *, notional_to_equity, samples=MAX_PATHS, seed=BOOTSTRAP_SEED,
                    cost_overlay_per_notional=0.0):
    """Illustrative conditional replay of day blocks, NOT predictive odds."""
    if not blocks or not 1 <= len(blocks) <= 366 or not 1 <= samples <= 5000:
        raise ValueError("Insufficient bootstrap sample")
    rng = random.Random(seed)
    counts = {"GOAL_FIRST": 0, "SEVERE_LOSS_FIRST": 0, "NEITHER": 0}
    observed = run_path(blocks, notional_to_equity=notional_to_equity,
                        cost_overlay_per_notional=cost_overlay_per_notional)
    for _ in range(samples):
        # Same-day observations remain together. All symbols in the
        # original day share their market regime. No random trade shuffling.
        drawn = [blocks[rng.randrange(len(blocks))] for _ in range(len(blocks))]
        status = run_path(drawn, notional_to_equity=notional_to_equity,
                          cost_overlay_per_notional=cost_overlay_per_notional)["state"]
        counts[status] += 1
    return {
        "paths": samples,
        "observed_chronological": observed,
        "bootstrap_frequencies_not_probabilities": {
            k: round(counts[k] / samples, 4) for k in counts},
        "no_validated_prediction": True,
        "liquidation_not_modelled": True,
        "real_minimum_contract_size_not_modelled": True,
    }


def train_only_choice(metrics):
    """The held-out data is NOT an argument. Return NO_TRADE if no evidence."""
    eligible = []
    for name in STRATEGIES:
        rows = [m[name] for m in metrics.values()]
        if not rows:
            continue
        if (sum(x["train"]["trades"] for x in rows) < MIN_TRAIN_TRADES
                or sum(x["train"]["return_pct"] > 0 for x in rows)
                    < min(MIN_POSITIVE_TRAIN_MARKETS, len(rows))
                or statistics.mean(x["train"]["return_pct"] for x in rows)
                    < MIN_MEAN_TRAIN_RETURN_PCT
                or statistics.mean(x["train_stress"]["return_pct"] for x in rows)
                    < MIN_MEAN_TRAIN_STRESS_PCT):
            continue
        eligible.append((statistics.mean(x["train_stress"]["return_pct"] for x in rows), name))
    return max(eligible)[1] if eligible else "NO_TRADE"


def evaluate(frozen, *, hashes=None, bootstrap_paths=MAX_PATHS):
    if set(frozen) != set(DEFAULT_SYMBOLS):
        raise ValueError("Exactly six predeclared historical markets required")
    if not 100 <= bootstrap_paths <= 5000:
        raise ValueError("Invalid path count")
    # Entire signal family and all eligibility rules fixed before holdout.
    data, logs = {}, {name: {} for name in STRATEGIES}
    for symbol in DEFAULT_SYMBOLS:
        bars = frozen[symbol]
        validate_frozen(bars)
        split = int(len(bars) * TRAIN_FRACTION)
        row = {}
        for name in STRATEGIES:
            sig = signals(bars, name) if name in BASELINES else regime_signals(bars, name)
            train = trade_simulation(bars, sig, start_index=WARMUP_BARS,
                                     end_index=split)
            train_stress = trade_simulation(
                bars, sig, start_index=WARMUP_BARS, end_index=split,
                fee=STRESS_FEE, slip=STRESS_SLIPPAGE)
            holdout = trade_simulation(bars, sig, start_index=split,
                                       end_index=len(bars))
            stress = trade_simulation(
                bars, sig, start_index=split, end_index=len(bars),
                fee=STRESS_FEE, slip=STRESS_SLIPPAGE)
            logs[name][symbol] = holdout.pop("trade_log")
            train.pop("trade_log")
            train_stress.pop("trade_log")
            stress.pop("trade_log")
            row[name] = {"train": train, "train_stress": train_stress,
                         "holdout": holdout, "holdout_stress": stress}
        data[symbol] = row

    choice = train_only_choice(data)
    outcome = {
        "mode": "OFFLINE_ADVERSARIAL_ALPHA_TRIBUNAL_NO_ORDERS",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "goal_usdt": TARGET_EQUITY, "initial_usdt": INITIAL_EQUITY,
        "severe_loss_barrier_usdt": SEVERE_LOSS_EQUITY,
        "train_selected_candidate": choice,
        "promotion_to_real_trading": False,
        "real_orders": 0,
        "holdout_used_for_selection": False,
        "actual_okx_account_checked": False,
        "real_contract_lot_checked": False,
        "estimated_probability_of_doubling": None,
        "estimated_probability_of_ruin": None,
        "notional_equity_ratio_hypothetical": dict(EXPOSURES),
        "data_hashes_sha256": hashes or {},
        "methodology": {
            "source": "six frozen 15-minute OKX USDT swap OHLC series",
            "train_fraction": TRAIN_FRACTION,
            "predeclared_strategies": list(STRATEGIES),
            "holdout_policy": "strict chronological, no tuning on holdout",
            "fees_each_side_assumed": TAKER_FEE,
            "slippage_each_side_assumed": BASE_SLIPPAGE,
            "funding_per_8h_assumed": FUNDING_PER_8H,
            "max_one_position": True,
            "bootstrap": "resample daily blocks with replacement",
            "bootstrap_seed": BOOTSTRAP_SEED,
            "liquidation_and_tiny_lot": "NOT MODELED — optimistic risk estimate",
            "purpose": "try to falsify claimed alpha, not certify profit",
        },
        "holdout_diagnostics": {},
    }
    for name in STRATEGIES:
        rows = [data[s][name] for s in DEFAULT_SYMBOLS]
        episodes = single_position_episodes(logs[name])
        blocks = daily_blocks(episodes)
        diagnostics = {
            "train_mean_symbol_return_pct": round(statistics.mean(
                x["train"]["return_pct"] for x in rows), 4),
            "train_stress_mean_symbol_return_pct": round(statistics.mean(
                x["train_stress"]["return_pct"] for x in rows), 4),
            "holdout_mean_symbol_return_pct": round(statistics.mean(
                x["holdout"]["return_pct"] for x in rows), 4),
            "holdout_stress_mean_symbol_return_pct": round(statistics.mean(
                x["holdout_stress"]["return_pct"] for x in rows), 4),
            "holdout_trade_events_raw": sum(len(logs[name][s]) for s in DEFAULT_SYMBOLS),
            "holdout_nonoverlapping_portfolio_events": len(episodes),
            "resampled_day_blocks": len(blocks),
            "positive_holdout_markets": sum(x["holdout"]["return_pct"] > 0 for x in rows),
            "portfolio_scenario": {},
            "can_trade_live": False,
        }
        if blocks:
            for label, exposure in EXPOSURES:
                diagnostics["portfolio_scenario"][label] = {
                    "normal_costs": block_bootstrap(blocks, notional_to_equity=exposure,
                                                    samples=bootstrap_paths),
                    # Extra 50 bp/trade of unobserved adverse costs/tail loss,
                    # above the baseline modeled fees/slippage.
                    "adversarial_extra_50bp": block_bootstrap(
                        blocks, notional_to_equity=exposure, samples=bootstrap_paths,
                        cost_overlay_per_notional=0.005),
                }
        outcome["holdout_diagnostics"][name] = diagnostics
    outcome["decision"] = ("STOP_NO_TRAIN_POSITIVE_EDGE" if choice == "NO_TRADE"
                           else "RESEARCH_ONLY_SELECTED_ON_TRAIN_NEEDS_NEW_FORWARD_PROOF")
    outcome["limitations"] = [
        "Frozen 60-day candles do not reconstruct 6-agent live orderbook signals",
        "Bootstrapping historical blocks is not an unbiased probability forecast",
        "Finite sample and same-day market correlation limit inference",
        "Futures liquidation, slippage tails, lot minimums, and API failures are not modeled",
        "A 49.5x notional/equity ratio risks total loss on very small adverse moves",
        "The holdout is now seen; any further development needs untouched forward data",
    ]
    return outcome


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    root=Path(args.offline_dir)
    frozen, hashes = {}, {}
    for symbol in DEFAULT_SYMBOLS:
        path = root / (symbol + ".candles.json.gz")
        if not path.is_file():
            parser.error("Missing frozen evidence " + symbol)
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            bars=json.load(stream)
        frozen[symbol]=bars
        hashes[symbol]=hashlib.sha256(
            json.dumps(bars, separators=(",", ":")).encode()).hexdigest()
    result=evaluate(frozen, hashes=hashes)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("TRIBUNAL TRAIN-ONLY VERDICT:",result["decision"],
          "candidate=",result["train_selected_candidate"],flush=True)
    for name, row in result["holdout_diagnostics"].items():
        print("TRIBUNAL",name,"train_net_pct=",row["train_mean_symbol_return_pct"],
              "holdout_net_pct=",row["holdout_mean_symbol_return_pct"],
              "holdout_events=",row["holdout_nonoverlapping_portfolio_events"],
              "live=NEVER",flush=True)
        if "aggressive_4x_notional" in row["portfolio_scenario"]:
            e=row["portfolio_scenario"]["aggressive_4x_notional"]["adversarial_extra_50bp"]
            print("TRIBUNAL ILLUSTRATIVE 4x STRESS", name,
                  e["bootstrap_frequencies_not_probabilities"],flush=True)
    print("TRIBUNAL goal 4.15 -> 8.30: no demonstrated probability; NO ORDERS",flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())

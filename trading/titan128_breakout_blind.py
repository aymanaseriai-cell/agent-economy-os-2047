#!/usr/bin/env python3
"""TITAN Ω: precommitted trend-breakout challenger for the +128% PAPER goal.

This is an alternative to QFRV, not a post-hoc retune of its losing trades.
The six-symbol basket is selected by immutable SHA256 ordering among a stated
universe BEFORE downloading candles. Prices are public OKX completed 15m bars.
All entries occur next bar; fills are simulated, including min lot, fees,
slippage, funding and adverse liquidation proxy via existing QSI sim_one.
NO private API, NO orders, NO live execution or claim of quantum hardware.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, math, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading import titan_quantum_survival_interferometer as qsi
from trading import titan_quantum_gate as quantum_gate
from trading.edge_lab import (
    BAR_MS, TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE, STRESS_SLIPPAGE,
    ema_series, atr_simple, fetch_history,
)
from trading.titan_regime_research import validate_frozen

STUDY = "TITAN128-QUANTUM-BREAKOUT-COMPARISON-20261117-V2"
QUANTUM_POLICIES = ("quantum_phase_robust", "quantum_interference",
                    "quantum_zero_phase", "classical_same_features")
UNIVERSE = set(("AAVE ADA ALGO APT ARB ATOM AVAX BCH COMP CRV DOT ETC FIL "
                "ICP INJ JUP LINK LTC NEAR OP SEI SUI TON TRX UNI XLM XMR "
                "WAVES ZRX KAVA JASMY").split())
FORBIDDEN = {"BTC", "ETH", "SOL", "XRP", "DOGE", "HYPE", "ZEC", "BNB"}
MARKETS = 6
DAYS = 60
MIN_BARS = 5600
START = 4.15
GOAL = 9.462
RUIN = 0.83
LEVERAGES = (3., 10.)
SCAN_STRIDE = 4
LOOKBACK = 48
MIN_ATR_FRACTION = .003
MAX_ATR_FRACTION = .050
MIN_TRAIN_TRADES = 12

def eligible_market_catalogue():
    url = "https://www.okx.com/api/v5/public/instruments?" + urlencode({"instType": "SWAP"})
    with urlopen(Request(url, headers={"User-Agent": "TITAN-128-PAPER-NO-ORDERS"}), timeout=35) as h:
        data = json.load(h)
    if data.get("code") != "0":
        raise ValueError("OKX public instrument catalogue unavailable")
    eligible = []
    cutoff = int(time.time() * 1000) - 90 * 86400000
    for spec in data.get("data", []):
        sym = spec.get("instId", "")
        if not sym.endswith("-USDT-SWAP"):
            continue
        coin = sym[:-10]
        if (coin not in UNIVERSE or coin in FORBIDDEN or
            spec.get("ctValCcy") != coin or spec.get("state") != "live" or
            spec.get("ctType") != "linear"):
            continue
        try:
            if int(spec["listTime"]) > cutoff:
                continue
            vals = [float(spec[k]) for k in ("ctVal", "lotSz", "minSz")]
            if not all(math.isfinite(v) and v > 0 for v in vals):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        eligible.append(spec)
    eligible.sort(key=lambda z: hashlib.sha256(
        (STUDY + "|" + z["instId"]).encode()).hexdigest())
    if len(eligible) < MARKETS:
        raise ValueError("Not enough precommitted live crypto markets")
    return eligible[:MARKETS], len(eligible)

def breakout_signals(bars):
    """No future price: prior 48 highs/lows exclude candidate bar i."""
    validate_frozen(bars)
    cl = [float(z["close"]) for z in bars]
    fast, slow = ema_series(cl, 24), ema_series(cl, 96)
    result = []
    for i in range(max(qsi.WARMUP, LOOKBACK + 97), len(bars) - 1, SCAN_STRIDE):
        atr = atr_simple(bars, i, 14)
        if not math.isfinite(atr) or cl[i] <= 0:
            continue
        fraction = atr / cl[i]
        if not MIN_ATR_FRACTION <= fraction <= MAX_ATR_FRACTION:
            continue
        high = max(z["high"] for z in bars[i - LOOKBACK:i])
        low = min(z["low"] for z in bars[i - LOOKBACK:i])
        rising = fast[i] > slow[i] and fast[i] > fast[i - 16] and cl[i] > cl[i - 16]
        falling = fast[i] < slow[i] and fast[i] < fast[i - 16] and cl[i] < cl[i - 16]
        if cl[i] > high and rising:
            side, distance = 1, (cl[i] - high) / atr
        elif cl[i] < low and falling:
            side, distance = -1, (low - cl[i]) / atr
        else:
            continue
        # Predeclared deterministic tie-break strength; never look at holdout returns.
        result.append((i, side, atr, min(1., max(0., distance))))
    return result

def paper(markets, specs, votes, *, leverage, start, end, fee, slip):
    if (leverage not in LEVERAGES or
        set(markets) != set(specs) or set(markets) != set(votes)):
        raise ValueError("Invalid frozen public-only paper setup")
    entries = {}
    for sym, signals in votes.items():
        for sig in signals:
            if start <= sig[0] and sig[0] + 1 < end:
                entries.setdefault(sig[0], []).append((sig[3], sym, sig))
    equity, available, peak = START, start, START
    drawdown = 0.
    trades = []
    first_goal_exit = None
    for idx in sorted(entries):
        if idx < available or equity <= RUIN or equity >= GOAL:
            continue
        for _, sym, signal in sorted(entries[idx], key=lambda x: (-x[0], x[1])):
            t = qsi.sim_one(markets[sym], signal, specs[sym], equity=equity,
                            leverage=leverage, fee=fee, slip=slip, end=end)
            if t is None:
                continue
            equity = t["equity_after"]
            available = t["exit_i"] + 1
            peak = max(peak, equity)
            drawdown = max(drawdown, 100 * (peak - equity) / peak)
            trades.append(t)
            if equity >= GOAL:
                first_goal_exit = t["exit_i"]
            break
        if first_goal_exit is not None:
            break
    return {
        "trades": len(trades),
        "end_usdt": round(equity, 8),
        "return_pct": round(100 * (equity / START - 1), 5),
        "max_drawdown_pct": round(drawdown, 5),
        "reached128_on_closed_paper_trade": first_goal_exit is not None,
        "first_goal_closed_exit_i": first_goal_exit,
        "ruin_at_closed_equity": any(t["equity_after"] <= RUIN for t in trades),
        "liquidation_proxy_count": sum(t["status"] == "liquidation_proxy" for t in trades),
        "fee_total_usdt": round(sum(
            t["entry_fee_usdt"] + t["exit_fee_usdt"] for t in trades), 8),
    }

def evaluate(markets, specs, sha, timestamp):
    if len(markets) != MARKETS or set(markets) != set(specs) or set(markets) != set(sha):
        raise ValueError("Exactly six frozen-symbol datasets and manifests required")
    n = min(len(rows) for rows in markets.values())
    if n < MIN_BARS:
        raise ValueError("Incomplete 60-day history")
    time_grid = [z["ts"] for z in next(iter(markets.values()))[:n]]
    for sym, rows in markets.items():
        if sym[:-10] not in UNIVERSE or sym[:-10] in FORBIDDEN:
            raise ValueError("Wrong fixed market universe")
        validate_frozen(rows)
        if [z["ts"] for z in rows[:n]] != time_grid:
            raise ValueError("Misaligned OHLC; fail closed")
    cut = int(n * .60)
    middle = cut + (n - cut) // 2
    splits = {"train": (qsi.WARMUP, cut),
              "holdout_1": (cut, middle), "holdout_2": (middle, n)}
    votes = {sym: breakout_signals(rows[:n]) for sym, rows in markets.items()}
    results = {}
    for lev in LEVERAGES:
        results[str(int(lev)) + "x"] = {
            phase: {
                label: paper(markets, specs, votes, leverage=lev, start=a, end=b,
                             fee=fee, slip=slip)
                for label, (fee, slip) in {
                    "ordinary": (TAKER_FEE, BASE_SLIPPAGE),
                    "stress": (STRESS_FEE, STRESS_SLIPPAGE),
                }.items()
            }
            for phase, (a, b) in splits.items()
        }
    # FROZEN quantum ablations on identical markets, candles, costs and sizing.
    # 3-qubit Born amplitudes and phase sweeps are computed on a CLASSICAL CPU.
    # Classical comparison uses precisely QSI's same three causal features.
    qsi_all = {sym: qsi.candidate_stream(rows[:n])
               for sym, rows in markets.items()}
    quantum_comparators = {}
    for family in QUANTUM_POLICIES:
        quantum_votes = {sym: pols[family] for sym, pols in qsi_all.items()}
        quantum_comparators[family] = {
            str(int(lev)) + "x": {
                p: {
                    cost: paper(markets, specs, quantum_votes, leverage=lev,
                                start=a, end=b, fee=fee, slip=slip)
                    for cost, (fee, slip) in {
                        "ordinary": (TAKER_FEE, BASE_SLIPPAGE),
                        "stress": (STRESS_FEE, STRESS_SLIPPAGE),
                    }.items()
                }
                for p, (a, b) in splits.items()
            }
            for lev in LEVERAGES
        }
    def as_closed(row):
        return {
            "closed_equity_usdt": row["end_usdt"],
            "closed_trades": row["trades"],
            "max_drawdown_pct": row["max_drawdown_pct"],
            "ruin_happened": row["ruin_at_closed_equity"],
            "hit_128": row["reached128_on_closed_paper_trade"],
        }

    quantum_evidence = quantum_gate.audit_closed_paper_report({
        "start_usdt": START, "goal_usdt": GOAL,
        "real_orders": 0, "quantum_hardware_used": False,
        "data": {"precommitted": True, "public_market_sha256": sha},
        "models": {
            "quantum": {
                p: {cost: as_closed(quantum_comparators[
                    "quantum_phase_robust"]["3x"][p][cost])
                    for cost in ("ordinary", "stress")}
                for p in splits
            },
            "classical": {
                p: {cost: as_closed(quantum_comparators[
                    "classical_same_features"]["3x"][p][cost])
                    for cost in ("ordinary", "stress")}
                for p in splits
            },
        },
    })
    # The primary model is FIXED 3x. Never promote the better of 3x/10x post hoc.
    main = results["3x"]
    train_ok = (main["train"]["stress"]["trades"] >= MIN_TRAIN_TRADES
                and main["train"]["stress"]["return_pct"] > 0
                and main["train"]["stress"]["max_drawdown_pct"] <= 25
                and not main["train"]["stress"]["ruin_at_closed_equity"])
    holdouts_ok = train_ok and all(
        main[p][cost]["return_pct"] > 0
        and not main[p][cost]["ruin_at_closed_equity"]
        for p in ("holdout_1", "holdout_2")
        for cost in ("ordinary", "stress"))
    repeated128 = holdouts_ok and all(
        main[p][cost]["reached128_on_closed_paper_trade"]
        for p in ("holdout_1", "holdout_2")
        for cost in ("ordinary", "stress"))
    return {
        "study": STUDY,
        "method": "48-bar EMA-confirmed breakout, 14-bar ATR; no tuned parameters",
        "data": "public OKX 15m completed candles only",
        "markets": sorted(markets),
        "sha256_per_market": sha,
        "market_bars": n * MARKETS,
        "captured_at_utc": datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat(),
        "start_usdt": START, "goal_usdt": GOAL, "ruin_usdt": RUIN,
        "primary_model": "3x (fixed before market data)",
        "train_pass": train_ok, "both_holdouts_pass": holdouts_ok,
        "strict_repeated_128_pass": repeated128,
        "verdict": "NEEDS_FUTURE_PROSPECTIVE_TEST" if repeated128
                   else "NO_VALIDATED_REPEATED_128_EDGE_DO_NOT_DEPLOY",
        "results": results, "real_orders": 0,
        "quantum_models": quantum_comparators,
        "quantum_evidence": quantum_evidence,
        "quantum_hardware_used": False,
        "quantum_research_only": True,
        "warnings": [
            "These are retrospective public-bar simulations, not user account PnL",
            "Crypto OHLC cannot model full orderbook execution, mark-price liquidation or real funding",
            "Historical source basket may overlap other earlier unrelated research projects",
            "No quantum hardware; 3x/10x paper leverage are not live trading recommendations",
        ],
    }

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="reports/titan128_breakout_blind.json")
    p.add_argument("--raw-dir", default="reports/titan128_breakout_raw")
    args = p.parse_args(argv)
    timestamp = int(time.time() * 1000)
    basket, pool_size = eligible_market_catalogue()
    print("BLIND128 FROZEN PUBLIC MARKETS", pool_size,
          [spec["instId"] for spec in basket], flush=True)
    markets, specs, digests = {}, {}, {}
    raw = Path(args.raw_dir)
    raw.mkdir(parents=True, exist_ok=True)
    for spec in basket:
        sym = spec["instId"]
        bars = fetch_history(sym, DAYS, now_ms=timestamp)
        if len(bars) < MIN_BARS:
            raise ValueError("Not enough fully completed 15m bars " + sym)
        payload = json.dumps(bars, separators=(",", ":")).encode()
        digests[sym] = hashlib.sha256(payload).hexdigest()
        with gzip.open(raw / (sym + ".json.gz"), "wb") as out:
            out.write(payload)
        markets[sym], specs[sym] = bars, spec
        print("BLIND128 PUBLIC SHA", sym, len(bars), digests[sym], flush=True)
    report = evaluate(markets, specs, digests, timestamp)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for lev, phases in report["results"].items():
        print("BLIND128 RESULTS", lev,
              "TRAIN", phases["train"]["ordinary"]["return_pct"],
              "TRAIN_STRESS", phases["train"]["stress"]["return_pct"],
              "H1", phases["holdout_1"]["ordinary"]["return_pct"],
              "H1_STRESS", phases["holdout_1"]["stress"]["return_pct"],
              "H2", phases["holdout_2"]["ordinary"]["return_pct"],
              "H2_STRESS", phases["holdout_2"]["stress"]["return_pct"], flush=True)
    for family, phase_data in report["quantum_models"].items():
        phases = phase_data["3x"]
        print("BLIND128 QUANTUM ABLATION", family,
              "TRAIN_STRESS", phases["train"]["stress"]["return_pct"],
              "H1_STRESS", phases["holdout_1"]["stress"]["return_pct"],
              "H2_STRESS", phases["holdout_2"]["stress"]["return_pct"],
              "NO ORDERS", flush=True)
    print("BLIND128 QUANTUM AUDIT", report["quantum_evidence"]["verdict"],
          "QUANTUM_HARDWARE", False, flush=True)
    print("BLIND128 FINAL", report["verdict"],
          "STRICT_REPEATED_128", report["strict_repeated_128_pass"],
          "NO ORDERS", flush=True)

if __name__ == "__main__":
    main()

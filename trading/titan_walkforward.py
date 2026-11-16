"""Offline, single-candle, fee-and-slippage-aware walk-forward SHADOW audit.

Strategy selected only from historical training samples. The signal uses close(t),
fills at open(t+1), and exits at close(t+1). The test slice is never used to
choose the strategy. No lookahead, broker integration, leverage, or live orders.
One-bar holding is a simplified research convention, not a futures fill model.
"""
from __future__ import annotations

import math
from trading.titan_edge_lab import validate_bars, signal_at_close

STRATEGIES = ("ema_trend", "donchian_breakout", "bollinger_reversion")


def _simulate(bars, strat, start_signal, stop_signal, cost_fraction):
    curve = 1.0
    highwater = 1.0
    max_drawdown = 0.0
    n = wins = 0
    net_sum = 0.0
    # The decision at signal index t is filled on NEXT candle t+1 only.
    for t in range(start_signal,stop_signal):
        side = signal_at_close(bars,t,strat)
        if side == 0:
            continue
        nxt = bars[t+1]
        entry, exit_price = float(nxt["open"]),float(nxt["close"])
        if entry <= 0:
            raise ValueError("Invalid open")
        net = side*(exit_price/entry - 1.0) - cost_fraction
        n += 1
        wins += net > 0
        net_sum += net
        curve *= max(0.000001,1+net)
        highwater = max(highwater,curve)
        max_drawdown = max(max_drawdown,1 - curve/highwater)
    return {"trades":n,"win_rate":round(wins/n,6) if n else None,
            "total_return_pct":round((curve-1)*100,4),
            "mean_trade_net_pct":round(100*net_sum/n,5) if n else None,
            "max_drawdown_pct":round(max_drawdown*100,4)}


def walk_forward_audit(bars, *, fee_bp_per_side=5, slippage_bp_per_side=5,
                       train_fraction=0.65):
    """No strategy promotion. Evaluate one held-out segment with modeled costs."""
    try:
        validate_bars(bars,minimum=400)
        if not 0.5 <= train_fraction <= 0.8:
            raise ValueError("Invalid chronological split")
        fee,slip = float(fee_bp_per_side),float(slippage_bp_per_side)
        if not all(math.isfinite(x) and 0<=x<=100 for x in (fee,slip)):
            raise ValueError("Invalid fee or slippage reserve")
        cost=(fee+slip)*2/10000
        split=int(len(bars)*train_fraction)
        train={s:_simulate(bars,s,50,split-1,cost) for s in STRATEGIES}
        eligible=[s for s in STRATEGIES if train[s]["trades"]>=20]
        if not eligible:
            return {"status":"INSUFFICIENT_TRAIN_TRADES","research_only":True,
                    "train":train,"selected":None,"test":None,"can_trade_live":False}
        # Strictly TRAINING-only selection; no hindsight on test results.
        best=max(eligible,key=lambda s:(train[s]["total_return_pct"],-STRATEGIES.index(s)))
        test=_simulate(bars,best,split-1,len(bars)-1,cost)
        return {"status":"SHADOW_TESTED_NOT_VALIDATED" if test["trades"]>=20 else "INSUFFICIENT_TEST_TRADES",
                "research_only":True,"can_trade_live":False,"selected":best,
                "train_bars":split,"test_bars":len(bars)-split,
                "fee_bp_per_side":fee,"slippage_bp_per_side":slip,
                "train":train,"test":test,
                "caveat":"One held-out sample and simplified one-bar fills cannot establish edge or guarantee a 2x balance."}
    except (KeyError,ValueError,TypeError,IndexError,OverflowError,ZeroDivisionError):
        return {"status":"INVALID_OR_INSUFFICIENT_INPUT","research_only":True,
                "can_trade_live":False,"selected":None,"test":None}

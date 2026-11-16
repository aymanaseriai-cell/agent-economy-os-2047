# TITAN FALSIFICATION LAB — trying to disprove apparent edge

This is the anti-overfitting, physics-inspired **research-only** component of TITAN.
It cannot and must not send an OKX order, set leverage, authorize LIVE, or change
existing LONG/SHORT/WAIT decisions, Omega, COSMOS or EDGE LAB vetoes.

## Mechanics

- Three chronological, expanding-training, **disjoint** unseen test windows.
- At each fold, select among EMA trend, Donchian 20-bar breakout and Bollinger
  mean reversion using **only training labels**. Train labels end before test.
- Generate each signal from completed bar t; simulate entry at next bar t+1 open
  and exit at that bar's close. This simplifies execution; no TP/SL, funding,
  latency, liquidation, contract size or mark prices are simulated.
- Baseline fees and slippage are explicitly subtracted both ways, with a 2x and
  4x adversarial cost budget. Holding selections fixed across stress tests
  avoids accidentally cherry-picking a different winner at each price.
- Circular-shift 96-times heuristic null: rotate directions within each holdout
  window while leaving realized next-bar price moves in chronological order;
  report only a **heuristic tail fraction**, *not* a calibrated scientific p value.
- Jensen-Shannon three-state return-distribution divergence checks regime shift.
- Remove the largest trade to indicate concentration of any apparent gain.
- Always return `can_trade_live=false` and `orders_placed=0`; even the
  best research verdict is NOT proof of alpha or permission to trade.

## Non-obvious limitations

Historical backtesting can strongly overstate expected profit due to selection
bias and lookahead leakage. The 2017 PBO/CSCV literature is related but this
module does **not** implement the full CSCV estimator or White Reality Check;
its null is only a simple exploratory falsification heuristic. Results need
many non-overlapping periods, different market regimes, exchange-specific costs,
historical contract rules, tick/lot min, and independent forward paper trading.

With a 4.53 USDT account, reaching 9 requires +98.68% before fees. Increasing
leverage is not evidence of a profitable opportunity and can liquidate the
account. Do not infer OKX balance or position state from this research report.

Research references:
- David H Bailey et al., Probability of Backtest Overfitting (2017):
  https://escholarship.org/uc/item/4w1110bb
- Freqtrade lookahead-analysis:
  https://github.com/freqtrade/freqtrade/blob/develop/docs/lookahead-analysis.md

The new `falsification_lab` field is appended to public scanner output and
never read as an authorization condition in the private trade executor.

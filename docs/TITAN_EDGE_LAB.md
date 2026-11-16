# TITAN EDGE LAB — Public research layer (shadow only)

**State:** The real-money Futures workflow has been stopped independently of this commit. This module never places or authorizes OKX orders. Production reports expose `edge_lab` and `edge_lab_system_count`, without changing existing LONG/SHORT/WAIT, omega vetoes, leverage, full-margin allocation, or stop-loss rules.

Eight original indicators:
- Kaufman efficiency ratio (20 completed bars), trend signal-to-noise
- EMA12/EMA26 trend alignment across 15m, 1h, 4h
- Prior-20-candle Donchian confirmed breakout (the current candle is excluded from thresholds)
- ATR14 relative to ATR50 for a volatility regime proxy
- DX14 directional movement strength (not smoothed ADX)
- Choppiness Index 14 (normalised range-vs-path proxy)
- Bollinger bandwidth percentile over 80 observations
- Volume-to-prior-median + top-20-level orderbook pressure

The separate `trading.titan_walkforward.walk_forward_audit` checks three **one-bar, shadow-only** strategies: EMA trend, prior-high breakout, and Bollinger mean reversion. Selection uses the chronological training prefix only; fills are modeled at next-bar open and closes at next-bar close. Training/test results deduct *both sides* of configurable trading fees and slippage. It requires at least 400 completed bars, 20 training trades, and reports fewer than 20 test trades as insufficient. There is no optimization on the test slice, no live strategy promotion, no margin/leverage simulation, and no guarantee that assumed execution prices will be achievable.

This is **not** a sufficient backtest or proof of profitable signals. Further work would require verified exchange historical data, exchange-specific contract fees/funding, mark-price liquidation rules, tick size, proper TP/SL stop execution, latency, multi-market time-based out-of-sample tests and forward paper trading.

Relevant independent open-source research references:
- Freqtrade lookahead analysis: https://github.com/freqtrade/freqtrade/blob/develop/docs/lookahead-analysis.md
- Freqtrade recursive analysis: https://github.com/freqtrade/freqtrade/blob/develop/docs/recursive-analysis.md
- Freqtrade protections: https://github.com/freqtrade/freqtrade/blob/develop/docs/includes/protections.md
- VectorBT research and portfolio simulation: https://github.com/polakowo/vectorbt

We did **not** copy their code or add heavy dependencies. Scientific vocabulary does not imply a quantum computer or supernatural capability.

Account-growth goal 4.53 -> 9 USDT requires around 98.7% gain. No known strategy offers such a return reliably in a short fixed period. Full-margin 20x–100x leverage can wipe out a small account; user-reported equity is not verified through the repo.

# TITAN OMEGA V4 ABSOLUTE FRONTIER - 2023/2024/2025 PRECOMMITTED PROTOCOL

Research-only objective: hypothetical +25,000,000% from 4.15 USDT to 1,037,504.15 USDT. Zero live orders. Reject success unless completed, affordable paper trades reach target on preselected independent 2025 final with both base and stress costs.

## V1/V2/V3 FAILURE AUTOPSY (ORIGINAL FROZEN GITHUB EVIDENCE)
OMEGA V1 -51.76302% selected final, 34 paper trades, 9 winners, gross -2.0442 USDT before transaction costs, 30 stopped, 0 historical-liquidation proxies. Frontier V2 diagnostic -57.92167%, 20 paper trades, 7 winners and 3 liquidation proxies, gross -2.0049 USDT. V3 rejected all 8 economic families and all 27 leverage variations on development; smallest Holm adjusted p was 0.703125. The preselected V3 final policy always-flat net 0%, compared with fixed V3 2x momentum +2.014211% ordinary and -18.680974% extreme costs. The 2026 calendar is consumed as a research holdout and is not claimed blind again.

## V4 MATERIAL CHANGE
Five hypotheses use genuine exchange MARK price and INDEX price alongside executed-trade OHLC. Earlier V1-V3 did not archive matched historical three-source price bars.
1. Mark-index premium mean reversion: x=-log(MarkClose/IndexClose).
2. Trade-mark execution dislocation reversion: x=-log(TradeClose/MarkClose).
3. Mark-index premium impulse exhaustion: x=-(premium_t-premium_t-3bar).
4. Signed premium duration: x=-premium_t log(1+min(40,consecutive same-sign bars)).
5. Mark-index downside wick asymmetry: x=-(MarkLow/IndexLow-MarkHigh/IndexHigh).
Each hypothesis predicts the sign of next FULL 4h-trade-bar open-to-close log return; it must prove after-cost predictive direction and survive blocked chronological tests before conversion to paper orders.
Additional data-gated hypotheses NOT simulated: 2023-2025 genuine settlement-level funding shocks (public recent endpoint insufficient), point-in-time order-book imbalance, timestamped news response. No manufactured funding history, implied-volatility surface or synthetic spreads.

## FROZEN COHORT AND YEARS
Predefined ten CURRENTLY LIVE and listed before 2023-01-01 if verified: BTC ETH SOL XRP DOGE ADA DOT LINK LTC ETC USDT-SWAP. No replacements based on success/failure; currently-live selection remains SURVIVORSHIP BIASED.
Sources per symbol: OKX /api/v5/market/history-candles, /api/v5/market/history-mark-price-candles, and /api/v5/market/history-index-candles. Source timestamps from 2023-01-01 through 2025-12-31 UTC, confirmed FOUR-HOUR bars, exactly 6,576 rows per feed; store raw exchange strings gzip and SHA256. Incomplete feed gives explicit missing state; no interpolation. Require >=6 complete market triples. Target up to 197,280 independent original 4h candle records (10 markets x 3 feeds x 6576 bars), depending on historical availability.
Train year 2023, development year 2024, fixed blind final year 2025. Freeze train-only ridge beta and top-decile magnitude threshold before development. Subsample one event per coin/day in development, charge -0.4% ex-ante transaction friction, exact month-block sign-flip and familywise Holm correction of all five hypotheses.
Eligibility requires at least 30 triggered development events, eight distinct months, p_Holm<=0.05, total positive net event proxy AND positive separately 2024 H1 / H2. After that a selected hypothesis must clear >=8 affordable, positive paper trades under BOTH base and stressed costs and development max closed drawdown <=30% before ANY final 2025 trading strategy test. If none eligible, a flat strategy is the only accepted final policy.
One fully predeclared 12h momentum (3 completed 4h bars, absolute log move >=2.5%) is run as a classical 2025 comparator even when no alpha; its final outcome cannot change selection.

## EXECUTION IS A RANGE, NOT FALSE EXCHANGE FILL PRECISION
Single position across markets. Signal from fully completed 4h data; fill at NEXT true 4h open and close at end of that bar. Actual base/stress taker fee 0.05%/0.15% each way are ASSUMED tiers, not account historical fee records. Adverse spread+slip 0.04% or 0.30% each side, plus volume participation impact.
2x leverage only; current contract minSz/lotSz/ctVal quantized; at most 15% of CLOSED equity as initial margin, 2.5% planned risk estimate from PRIOR completed bar range only, at most 0.1% of true preceding 4h quote turnover. Reinvest only after closing PnL. Accrued funding charged using scenario assumptions of 0.01% vs 0.05% per 8h; these are NOT observed funding in 2023-25. The genuine mark HIGH/LOW is used to flag approximate 2x liquidation boundaries only; no historical point-in-time maintenance tiers or liquidation engine are available.
Without historical L2, maker fills, spread or matching-engine latency, the model cannot claim exact actual executability. A trade affordable at 4.15 need not be scalable to a million-dollar portfolio at the same impact and 0.1% turnover cap.

## STATISTICAL FALSIFICATION AND LIMITS
Month-block signflips may not adequately handle dependence between assets or months; Holm controls only five V4 comparisons, not all hundreds of previous exploratory models. 2025 is historically held out relative to V4 development and outside prior 2026 tests, but it is not prospective future time. Actual point-in-time listings, delisted instruments and historical contract tier changes are missing. Fully calibrated DSR/PBO, interventions for causal learning, neural controlled differential equations and offline RL are NOT implemented or claimed. Quantum-computing speedup NOT claimed.
No tests on 2025 may be used for selecting or changing model thresholds, costs, assets, sizing or policy; failed final remains failed. All performed trials and data availability failures must be preserved in the GitHub Actions artifact. No real orders, no use of secrets, no financial spending.

## REPRODUCE
python -m unittest discover -s tests -p 'test_titan_v4_basis.py' -v
python -m trading.titan_v4_research --raw-dir reports/v4_original_2023_2025 --out reports/v4_empirical_results.json --curve reports/v4_frozen_2025_equity.svg
python -m trading.titan_v4_research --offline --compare reports/v4_empirical_results.json --raw-dir reports/v4_original_2023_2025 --out reports/v4_offline_reproduced.json --curve reports/v4_offline_equity.svg
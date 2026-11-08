# Original TITAN QUANT2037 council: archived signal forward audit

## Verdict — no demonstrated positive edge in this small sample

**Six archived research labels, six negative 1-hour hypothetical outcomes**
(mean **-0.62312% of notional**;
6/6 negative, only 3 symbols, with overlapping PEPE and ZEC episodes).
This is evidence AGAINST claiming demonstrated short-term profitability,
not proof the system can never profit. With overlapping episodes, do not
treat the six candidates as six independent Bernoulli trials.

## What was actually measured

- Reviewed 11 original, completed, read-only GitHub council workflow reports
  under the modern 6-core-agent + 7-quant-filter configuration;
  66 repeated market reviews yielded 5 research signals.
- Added one separately archived 12-market 6+7 public-research scan
  that occurred before any account/private-execution call; 1 more signal.
- Excluded one earlier legacy run lacking the seven quant filters.
- Thus 6 candidate LONG/SHORT research labels in total, 0 confirmed
  historical NVIDIA gate approvals and 0 proved exchange executions.
- Captured exact publication timestamps, symbols, directions, reported
  indicative stops and targets, original GitHub workflow run references.
- Fetched and froze completed post-publication 15-minute OKX candles
  for ZEC, PEPE and UNI from the public exchange history endpoint.

## Immutable replay methodology

- Enter only at first 15-minute OPEN at or after the archived report's
  timestamp (never before the label was published).
- Use original indicated stop/target, or exit on last close of a
  60-minute (4-candle) or 240-minute (16-candle) holding horizon.
- If target and stop are both inside one OHLC candle, stop first.
- Stop gaps fill at actual candle open, not the less adverse stop price.
- Apply assumed 0.05% taker fee each side, 0.03% adverse slippage each side,
  and modeled 0.01% debit per eight hours. Funding history is NOT measured.
- Result is theoretical unlevered return on trade notional, not account PnL;
  no leverage multiplier, position sizing, actual fill, or real order.
- A horizon is only scored when all required post-publication complete
  candles are present. No future OHLC is used in selecting prior signals.

## All original qualifying research signals

| Report UTC | Symbol | Label | 1h net | 1h exit | 4h net | Provenance |
|---|---|---|---:|---|---:|---|
| 2026-11-07 21:25 | ZEC-USDT-SWAP | SHORT | -0.98596% | horizon_close | -0.96314% | [run 42415801779](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/runs/42415801779) |
| 2026-11-07 21:25 | PEPE-USDT-SWAP | SHORT | -0.55655% | horizon_close | -0.58111% | [run 42415801779](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/runs/42415801779) |
| 2026-11-07 22:08 | PEPE-USDT-SWAP | SHORT | -1.04161% | horizon_close | not matured | [run 42419200803](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/runs/42419200803) |
| 2026-11-07 22:47 | PEPE-USDT-SWAP | SHORT | -0.56025% | stop | not matured | [run 42422261628](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/runs/42422261628) |
| 2026-11-08 00:04 | ZEC-USDT-SWAP | SHORT | -0.11350% | horizon_close | not matured | [run 42428089304](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/runs/42428089304) |
| 2026-11-08 00:13 | UNI-USDT-SWAP | LONG | -0.48087% | horizon_close | not matured | [run 42428551777](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/runs/42428551777) |

At 4h, 2 of 6 outcomes had matured at data freeze,
and both were negative (mean -0.77212%).
The other 4 MUST NOT be scored as wins/losses.

## Falsifiability and strict limitations

**NOT a complete system validation.** Historical NVIDIA approval
votes were not captured. 6-agent+7-system reports provide valid research
labels only; unknown account, spreads, re-entry cooldowns, exchange-native
protection, NVIDIA veto or changing price could block any actual trade.

- This is short, correlated, nonrandom observational sample, not an
  out-of-sample randomized clinical-style test or validated trading edge.
- Only 3 unique symbols and 6 signals; repeated positions overlap.
- Taker fees, funding and slippage are explicit modeled assumptions.
- The OHLC order of intrabar prints is unknown; stops get priority.
- Snapshots cover approximately 25 recent hours, not long-term regimes.
- No strategy thresholds were optimized against these future outcomes.
- To establish predictive strength, preserve thousands of raw pre-trade
  decisions (including WAITs), model vetoes, actual quote and spread,
  and score at fixed horizons against matched benchmarks out of sample.
- Keep live order execution disabled until positive edge is established
  after fees, slippage, and risk limits.

## Artifacts and reproduction

- Original GitHub run IDs and artifact IDs: reports/actual_council_signals_20261108.json
- Frozen completed historical candle snapshots: reports/*.outcome_candles_20261108.json
- Machine-readable outcomes and source SHA256: reports/actual_council_forward_20261108.json
- Flat scored table: reports/actual_council_forward_20261108.csv

Run with Python 3.12, no private exchange credentials or network:

    python -m unittest discover -s tests -p test_council_forward_audit.py -v
    python -m trading.council_forward_audit --base reports --out reports/replay_actual_council.json

Offline GitHub Actions workflow verifies deterministic replay,
including complete report row equality and frozen data checksums.

The user's OKX automated-trading workflow remains DISABLED,
OKX_ENABLE_REAL_TRADING=NO and OKX_EXECUTION_MODE=dry_run.

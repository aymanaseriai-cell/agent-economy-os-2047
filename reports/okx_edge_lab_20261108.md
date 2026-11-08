# OKX edge lab — frozen 60-day historical assessment

## Decision: remain stopped; no demonstrated tradable edge

Two simple, fixed, candle-only hypotheses were replayed on 34,554 actual
complete public OKX 15-minute bars across six liquid USDT-SWAP markets.
Neither earned positive net average returns in the held-out 40% of the data.
This is NOT a backtest of the full six-agent/NVIDIA trading strategy:
historical order-book, funding, and model snapshots needed to reproduce
the live signals are not available in these OHLCV datasets.

## Predeclared financial model

- Fixed six symbols: BTC, ETH, SOL, XRP, DOGE, SUI perpetual swaps.
- Approximately 60 days, 5,759 complete consecutive bars per symbol.
- Chronological 60/40 earlier/later split. No tuning on holdout.
- Models: EMA(9)/EMA(21) with RSI(14), and 48-bar price breakout with EMA trend.
- Signal uses a completed candle; entry begins at NEXT 15-minute candle open.
- Planned stop: 1.5x ATR(14); target: 2.5x ATR(14); maximum duration six hours.
- If both stop and target touch in a candle, the stop fills first (conservative).
- Gap through stop fills at the gap open plus unfavorable slippage.
- $1,000 synthetic starting equity allocated independently to each symbol and strategy.
- Notional cap 20% of equity, 0.25% modeled stop-risk budget, no live leverage/execution.
- Baseline: 0.05% taker fee per side, 0.03% adverse execution slippage per side,
  assumed funding debit 0.01% every eight hours (not exchange-verified history).
- Stress: 0.08% taker fee per side, 0.10% adverse slippage per side.
- Frictionless is diagnostic only: 0 fees, 0 slippage, 0 funding.

## Held-out test results (base and stress net of model costs)

| Symbol | Prototype | Trades | Frictionless | Net | Stress net | Profit factor |
|---|---|---:|---:|---:|---:|---:|
| BTC-USDT-SWAP | ema_rsi | 193 | +0.740% | -5.777% | -15.254% | 0.4613 |
| BTC-USDT-SWAP | breakout | 66 | -0.197% | -2.217% | -5.662% | 0.4952 |
| ETH-USDT-SWAP | ema_rsi | 185 | +0.440% | -5.364% | -12.850% | 0.6019 |
| ETH-USDT-SWAP | breakout | 64 | +1.478% | -0.311% | -3.033% | 0.9398 |
| SOL-USDT-SWAP | ema_rsi | 186 | +0.289% | -5.138% | -13.125% | 0.675 |
| SOL-USDT-SWAP | breakout | 67 | -1.410% | -3.173% | -5.558% | 0.5138 |
| XRP-USDT-SWAP | ema_rsi | 181 | +2.433% | -3.171% | -12.626% | 0.7617 |
| XRP-USDT-SWAP | breakout | 68 | +1.003% | -1.994% | -5.521% | 0.6706 |
| DOGE-USDT-SWAP | ema_rsi | 183 | +0.150% | -5.921% | -13.621% | 0.6208 |
| DOGE-USDT-SWAP | breakout | 71 | -1.106% | -3.744% | -5.774% | 0.4797 |
| SUI-USDT-SWAP | ema_rsi | 196 | -3.769% | -10.090% | -16.309% | 0.5554 |
| SUI-USDT-SWAP | breakout | 71 | -1.053% | -3.133% | -5.337% | 0.6434 |

## Instrument-level equal-weight averages (not a portfolio simulation)

- **ema_rsi** — 1124 separately modeled holdout trades; mean frictionless +0.0470%; mean net -5.9103%; mean stress net -13.9642%.
- **breakout** — 407 separately modeled holdout trades; mean frictionless -0.2142%; mean net -2.4287%; mean stress net -5.1475%.

## Auditability and limitations

- Six frozen gzip candle datasets plus SHA256 manifest are included.
- Inspect data integrity in reports/okx_edge_lab_20261108_manifest.json.
- Inspect all per-strategy metrics in reports/okx_edge_lab_20261108.json
  and reports/okx_edge_lab_20261108.csv.
- Real intrabar transaction order, microstructure, orderbook depth, partial fills,
  funding timestamps, exchange downtime, mark-price liquidations, and trading
  latency were not observed. The OHLC engine uses conservative conventions.
- The 10-minute live-bot re-entry cooldown, NVIDIA veto, and all six-agent
  criteria are NOT represented. Do not generalize these outcomes to that bot.
- Multiple assets share market regimes; 1,531 total modeled trades are not
  1,531 independent statistical samples.
- No capital was deployed, no order was submitted, and no profitability is claimed.
- The user's real-money OKX workflow remains disabled.

## Exact offline replay (Python 3.12 standard library only)

Run from repository root, no credentials and no internet:

    python -m unittest discover -s tests -p test_edge_lab.py -v
    python -m trading.edge_lab --days 60 --symbols BTC-USDT-SWAP ETH-USDT-SWAP SOL-USDT-SWAP XRP-USDT-SWAP DOGE-USDT-SWAP SUI-USDT-SWAP --offline-dir reports --out reports/replay.json

The generated timestamp may differ; symbol-level metrics and dataset SHA256
must match the frozen reports. The separate manually triggered GitHub Actions
workflow verifies this without touching any exchange-private endpoint.

External API documentation: https://www.okx.com/docs-v5/en/

# OKX Futures Public Market Scanner — Research Lab

**Automated, real GitHub Actions execution. No trading orders. No credentials. No profit guarantees.**

This lab is isolated from the Agent Economy OS commercial product.

- Every ~15 minutes (subject to GitHub scheduling delays), Actions retrieves OKX public USDT perpetual swaps and the last 100 candles of the top eight pairs with estimated 24-hour quote turnover ≥ $20 million and bid/ask spread ≤ 0.25%.
- Calculates EMA(9), EMA(21), RSI(14) and ATR(14) on *completed* 15-minute candles.
- Returns `LONG`, `SHORT`, or `WAIT` research labels. Illustrative targets and stops are volatility-derived, not actual order requests.
- Writes a JSON report and uploads it as a GitHub Actions artifact with 7-day retention.
- Never loads API keys, reads positions, opens or closes orders, sets leverage, or manages capital.

## Run manually

Open **Actions → OKX Futures public-data 15m scanner (NO TRADES) → Run workflow**.

Or use Python 3.11+:

```bash
python3 trading/okx_signal_lab.py --top 8 --out reports/okx_15m_signals.json
```

No dependency installations required.

## Limits

GitHub Actions scheduled workflows can start late or be skipped. Jobs do **not** run continuously, and state is ephemeral. GitHub Actions is **not suitable for a sub-minute execution-sensitive live trading engine**. This is not a historical backtest or a demonstrated profitable strategy. Exchange data may be temporarily unavailable due to API or regional restrictions. `volCcy24h * last` is an estimate, not a precise USDT 24h matched turnover. A signal does not mean a fill or a profit.

A future production bot should require independent backtesting (fees, funding, spread, slippage), paper trading with persistent PnL, hard drawdown limits and emergency stop controls, and an always-on host with a stable allowlisted IP. API secrets must never be committed to public GitHub.

Official sources: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows and https://www.okx.com/docs-v5/

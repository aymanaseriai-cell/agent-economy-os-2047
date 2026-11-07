# SIX-AGENT EVIDENCE COUNCIL + QUANT2037 — OKX perpetual futures

**New:** Seven additional quantitative systems actively filter the six-agent consensus, including robust jumps, entropy, variance ratios, 24h/24h value migration, depth fragility, order-flow acceleration and counterfactual voting robustness. See [QUANT2037.md](QUANT2037.md).

The six components are **independent, deterministic quantitative agents**, not six independent LLMs. Their names convey roles, not supernatural powers. This public-data research workflow does **not** make trades, handle APIs keys, set margin or leverage, or guarantee profits.

1. **Liquidity Sentinel (hard veto)** — USD estimated 24h turnover, best-spread, depth and orderbook freshness. Invalid conditions veto a signal.
2. **Auction Cartographer** — reconstructs *approximate* VAL/POC/VAH from 48h of 15-minute candles by distributing each candle's quote volume over 40 price bins. Detects VAL sweeps/reclaims, VAH rejections and accepted breakouts. This **is not** an exact tick-data Fixed Range Volume Profile like on TradingView.
3. **Tape Detective** — investigates relative 20-level orderbook imbalance and aggressor-side trade sizes from the latest public trade sample. A single snapshot cannot identify whale wallets or compute true historical CVD.
4. **Derivatives Intelligence** — compares perpetual funding, mark-last basis and public open-interest snapshot; does not invent open-interest changes from one snapshot.
5. **Structure Navigator** — cross-checks completed 1-hour and 4-hour bars and detects higher-timeframe displacement/breaks (without EMA/RSI).
6. **Risk Marshal (hard veto)** — checks spread/volatility/stop distance, gives *illustrative, non-executable* structural stop and target, and vetoes insufficient multi-agent consensus.

The coordinator emits `LONG`, `SHORT` or `WAIT` research labels only if at least two independent directional agents agree, reach 3 ordinal points, avoid a strong contradictory majority, and pass all vetoes. **Ordinal points are not win probabilities.** No signal is forced. Errors are surfaced in the evidence artifact, not silently replaced with predictions.

## GitHub execution

Navigate to **Actions → OKX six-agent evidence council (public-data, NO TRADES) → Run workflow**. The schedule requests each 15 minutes but GitHub Actions may delay or drop runs; it is not a continuously executing futures bot. Outputs live in **Actions → Workflow run → Artifacts → six-agent-evidence-report** (JSON, 7-day retention). HTTP public OKX feeds and estimated turnover may vary by region or exchange changes.

Run locally with Python >=3.10 and no third-party dependencies:

```shell
python3 -m trading.six_agent_council --top 6 --out reports/okx_six_agents.json
python3 -m unittest discover -s tests -v
```

## Production gates (not implemented)

Before anyone connects trading permissions: separately verified historical trades/orderbook/funding datasets, out-of-sample and walk-forward backtests with real maker/taker fees and funding, realistic slippage, paper trading with persisted state, exchange-native protective stops, per-order ≤0.5% account risk, maximum daily drawdown, bounded gross leverage, deployment to stable always-on host with IP-bound credentials, emergency kill switch and manual approval for first live order. Never upload OKX or NVIDIA secrets to public GitHub or logs.

References: [OKX API v5](https://www.okx.com/docs-v5/en/) | [GitHub schedule timing](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Live execution adapter (disabled by default)

The market scanner's minimum **estimated** 24h USDT turnover is now **15,000,000**. A separately armed execution adapter exists at [okx_live_executor.py](okx_live_executor.py) with full security controls in [LIVE_TRADING.md](LIVE_TRADING.md). Six specialist agents and seven numerical systems still generate research-only evidence; **they do not themselves place orders**. No profitable edge, full protection against loss, or stable 24/7 production monitoring is established.

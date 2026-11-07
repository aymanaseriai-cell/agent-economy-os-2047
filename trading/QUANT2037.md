# QUANT2037 | Six Specialist Agents + Seven Quantitative Systems

**Status:** Real scheduled analysis of OKX public-market data. **NO LIVE TRADING.** No API keys, balance access, margin changes, orders, or leverage. The term "2037" is a project name, not a claim of supernatural or future technology.

Existing six specialists remain: liquidity, approximate fixed-volume auction, order-flow snapshot, derivatives, multi-timeframe structure, and veto-capable risk marshal. Their original direction is now examined by **seven additional independent calculations**:

| Quant system | What it actually computes | How it influences decisions |
|---|---|---|
| **01 Jump Sentinel** | Last 15m log return's robust deviation from median/MAD of recent closed returns | Hard veto for extreme jumps (8+ robust standard units); caution above 4.5 |
| **02 Permutation Entropy** | Normalized entropy of 3-return ordinal patterns | Directional confirmation only in lower-entropy regimes and with sufficient realized move |
| **03 Variance Ratio** | Overlapping four-step / one-step realized return variance ratio | Measures persistence vs mean-reversion; confirmation in strong trending regimes |
| **04 Value Migration** | Approximate 24h versus 24h POC shift over 192 completed 15m candles | Directional confirmation for significant volume-value migration; **not tick-level Fixed Volume Profile** |
| **05 Depth Fragility** | Top-five liquidity concentration and top-twenty orderbook imbalance | Hard veto when depth is missing; caution for unusually concentrated or imbalanced snapshots; not spoofing detection |
| **06 Flow Acceleration** | Signed aggressive-volume imbalance comparing early and late halves of recent timestamped OKX trades | Confirms acceleration of short-term order flow; **not historical CVD or whale attribution** |
| **07 Counterfactual Robustness** | Re-runs four-agent quorum after removing one directional agent at a time | Exposes signal fragility and labels unreliable consensus as caution |

## Decision logic

The original six-agent quorum still must pass first. Seven systems then add evidence. They cannot turn `WAIT` into a new trading signal. Extreme jump or missing orderbook depth produces a veto. At least one separate directional quant system must confirm any `LONG`/`SHORT`; two or more opposite quant votes cause abstention. Numerical scores **are not win probabilities**. No individual system promises profit.

Every market output includes `agents` (6), `advanced_systems` (7), `core_signal_before_advanced`, `advanced_confirmations`, `advanced_contradictions`, `advanced_veto_reasons`, `signal`, and `order_count:0`.

## Operational details

Scheduled every 15 minutes by GitHub Actions (runs can be late or dropped). View report under **Actions → OKX six agents + QUANT2037 (NO TRADES) → latest run → Artifacts → six-agent-evidence-report**. `trading/six_agent_council.py` fetches live public OKX SWAP market data, and all computations use completed 15m, 1h and 4h candles and current public orderbook/trades/derivatives feeds. Incomplete 48-hour 15m history causes abstention instead of an invented profile. No historical PnL/backtest or verified predictive edge exists yet.

### Run with no credentials

```sh
python3 -m trading.six_agent_council --top 6 --out reports/okx_six_agents.json
python3 -m unittest discover -s tests -v
```

## Before any actual trading

Validate the strategy out-of-sample with complete fee/funding/spread and slippage assumptions; use real paper fills and persistent accounting; limit risk, open positions and daily drawdown; provide exchange-native protective orders and an emergency kill switch; host on an always-on paid worker rather than scheduled GitHub Actions; provision brand-new scoped, IP-allowlisted OKX credentials securely (never in public repository or issue). Current implementation does **none** of the execution-side tasks and is deliberately read-only.

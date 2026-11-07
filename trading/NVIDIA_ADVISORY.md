# NVIDIA NIM advisory council

This is a separate, **read-only advisory layer**. It does not connect to OKX, read exchange credentials, place orders, modify positions, or authorize execution.

## Configuration
- Add `NVIDIA_API_KEY` in GitHub Actions repository secrets (never commit the value).
- Optional repository variable: `NVIDIA_MODEL`. Default: `nvidia/llama-3.3-nemotron-super-49b-v1.5`.
- NVIDIA NIM uses the OpenAI-compatible `https://integrate.api.nvidia.com/v1/chat/completions` endpoint.

## Run a validation
Open Actions → NVIDIA Advisory Council Validation → Run workflow. Supply a sanitized JSON snapshot, for example:
```json
{
  "symbol": "BTC-USDT-SWAP",
  "timeframe": "1h",
  "last_price": 67000,
  "change_24h_pct": 1.2,
  "turnover_24h_usd": 250000000,
  "spread_bps": 2.1,
  "orderbook_imbalance": 0.14,
  "funding_rate": 0.0001,
  "open_interest_change_pct": 3.2,
  "technical_context": "Describe only signals already calculated by the quantitative scanner",
  "news_context": "Optional timestamped headlines; omit if none"
}
```

The six specialist perspectives are trend, liquidity, tape/order-flow, derivatives, supplied news context, and adversarial risk review. The council returns WAIT if any agent fails, or if fewer than four valid votes align, or if aligned mean confidence is below 0.70. Even a directional result is labelled `ADVISORY_ONLY` and `execution_authorized: false`.

## Safety and limitations
- The model output is untrusted; confidence is not a calibrated probability or proof of edge.
- Never paste exchange keys, balances, account identifiers, or private information into the snapshot.
- This workflow is manual and does not run on a schedule.
- No live OKX workflow consumes these votes. Any future integration must be separately reviewed, backtested, paper-tested, and explicitly approved.
- API errors and malformed model responses fail closed to WAIT.

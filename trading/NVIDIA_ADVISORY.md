# NVIDIA NIM advisory council

Read-only research layer: no OKX client, exchange credentials, order placement, position changes, or execution authorization.

## Configuration
Add `NVIDIA_API_KEY` to GitHub Actions secrets. Optional GitHub Actions variable `NVIDIA_MODEL` can pin a model ID; otherwise the module reads the authenticated NVIDIA `/v1/models` catalog and selects an available Nemotron model. Never commit the key.

API base: `https://integrate.api.nvidia.com/v1`; model catalog: `GET /models`; inference: `POST /chat/completions`.

## Run
GitHub → Actions → NVIDIA Advisory Council Validation → Run workflow. Supply only sanitized market facts. Do not paste API keys, balances, exchange account IDs, or personal data.

Six independent role prompts: trend, liquidity, tape/order-flow, derivatives, supplied news context, and adversarial risk critic. All six must respond, at least four must align, and aligned mean confidence must reach 0.70 for a directional advisory. Otherwise the result is WAIT. Even BUY/SELL remains `ADVISORY_ONLY`, with `execution_authorized: false`.

Model output and confidence are not proof of a trading edge. This workflow is manual and is not consumed by any live OKX execution workflow. Any later live integration requires separate review, backtesting, paper trading, and explicit approval. API/model errors fail closed.

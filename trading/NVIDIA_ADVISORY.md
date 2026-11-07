# NVIDIA NIM advisory council

Read-only research layer: no OKX client, exchange credentials, order placement, position changes, or execution authorization.

## Configuration
Add `NVIDIA_API_KEY` to GitHub Actions secrets. Optional GitHub Actions variable `NVIDIA_MODEL` can pin a model ID; otherwise the module reads the authenticated NVIDIA `/v1/models` catalog and selects an available Nemotron model. Never commit the key.

API base: `https://integrate.api.nvidia.com/v1`; model catalog: `GET /models`; inference: `POST /chat/completions`.

## Run
GitHub → Actions → NVIDIA Advisory Council Validation → Run workflow. Supply only sanitized market facts. Do not paste API keys, balances, exchange account IDs, or personal data.

Six independent role prompts: trend, liquidity, tape/order-flow, derivatives, supplied news context, and adversarial risk critic. All six must respond, at least four must align, and aligned mean confidence must reach 0.70 for a directional advisory. Otherwise the result is WAIT. Even BUY/SELL remains `ADVISORY_ONLY`, with `execution_authorized: false`.

Model output and confidence are not proof of a trading edge. The OKX executor now calls the NVIDIA council as a **veto only** before any demo/live order. The AI cannot create signals, size positions, alter stops or targets, or place orders. All six specialist roles must respond, four or more high-confidence aligned votes must support the quantitative signal, the risk critic must affirm it, and no role may explicitly oppose it. Missing keys, model failures, errors, stale market data, or disagreement block the entry.

Run the separate manual OKX + NVIDIA gate validation workflow to check the public feed and AI gate without any OKX trading credentials.

Real orders are deliberately disarmed at GitHub variables (OKX_ENABLE_REAL_TRADING=NO, OKX_EXECUTION_MODE=dry_run, OKX_CAPITAL_MODE=guarded) pending demo validation. The scheduler may still scan, but cannot place real orders in this state. An existing OKX position, if present, is **not** modified by these changes; monitor the exchange-side native TP/SL. No trading edge or profit is guaranteed.

# TITAN 9 USDT target guard

Current GitHub Actions Futures workflow is DISABLED and left DISABLED by this code change.

User-specified target is **9.00 USDT of currency equity**. Read `GET /api/v5/account/balance?ccy=USDT` and `details[].eq`; never use totalEq (USD all assets) as proof of USDT goal. A threshold crossing can include unrealized P&L and does NOT guarantee 9 USDT realized at the moment of closure.

On explicitly armed LIVE manual run, a target gate checks before EACH scan, and again before an order could be created. At or above threshold, it refuses new entries and (if a valid net-mode isolated USDT-SWAP portfolio has no pending normal SWAP orders) sends one OKX market `POST /api/v5/trade/close-position` request per active supported swap with `autoCxl=true`, verifies no residual SWAP exposure and emits `TITAN TARGET9 LATCH: SUCCESS`. Any unknown close result, unsupported hedge/cross/non-USDT position, or pending order halts without automated retries, requiring manual exchange review.

On verified flat, the GitHub job exits nonzero (78), which prevents its chaining step from running. A finalizer also requests `actions/workflows/okx-guarded-execution.yml/disable` through the GitHub workflow token. The latter requires working GitHub permissions and can fail; if it fails the workflow must be disabled manually.

The speed ranking combines the *existing Omega positive rank score* and an estimated time-to-target from historical bootstrap diagnostics. Candidates must pass ALL existing signal, risk, cost, freshness and exchange conditions. Speed estimates are UNCALIBRATED and not promises of price moves or profits.

Scope: **only isolated USDT perpetual SWAPs in net mode**, not Spot, margin or other accounts. Exchange fees, slippage, gaps and liquidation can result in less than the indicated 9 USDT, or total capital loss.

With a reported 4.53 USDT, reaching 9 requires +98.6755%; no instrument can be proven to reach this goal in the shortest possible period.

References: https://www.okx.com/docs-v5/en/ ; https://github.com/freqtrade/freqtrade/blob/develop/docs/lookahead-analysis.md

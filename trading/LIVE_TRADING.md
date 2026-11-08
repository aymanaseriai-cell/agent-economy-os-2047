# OKX 6 agents + 7 systems — guarded real execution adapter

**FULL-MARGIN OPTION:** A separately armed `full_margin` mode can target **up to 100% of available USDT isolated margin**, with 10x leverage. This bypasses the guarded mode's 0.25% per-stop sizing and 20% notional cap. Full-margin trading can liquidate the account and is NOT a proven profitable strategy. It refuses trades with an estimated initial-stop risk greater than 10% of equity; actual losses can be larger due to gaps, fees, liquidations and execution failure. It does not automatically enable trading.\n\n**Real trading execution is implemented in `trading/okx_live_executor.py` but DISARMED until you explicitly configure it. No guarantee of profit.**

## Live-capable architecture

- Public-data 6-agent / QUANT2037 signal engine scans **up to 12** USDT perpetual instruments, with estimated 24h base-coin turnover **≥ US$15 million**. This is turnover, **not order-book liquidity**, and is not a guarantee of executable depth.
- Fresh `LONG` or `SHORT` must pass the six-agent scoring, seven independent quantitative veto filters and all exchange-side checks. No forced trades. Stale report, ambiguous signal, data errors or mismatched account mode result in **no trade**. NVIDIA recommendations are never an execution gate.
- Separate private execution engine authenticates using OKX REST API v5, checks account `net_mode`, positive free USDT equity, no outstanding perpetual position or order, 24h bot order count, current contract specification, spread, instrument turnover and current price.
- **Default guarded sizing** caps intended risk at **0.25% equity per order**, **20% equity gross notional**, **5% initial margin**, **10x leverage**. These are planned entry sizes in guarded mode, **not maximum realized loss**: gaps, slippage, funding and liquidation can cause larger loss.
- Only USDT-margined **linear isolated** perpetuals with `ctValCcy` equal to base asset are supported. Position quantity is quantized down to `lotSz`, never rounded up to `minSz`.
- Sets isolated leverage to 10x after preflight, then sends a single market order with **exchange-native attached stop-loss and take-profit**. Verifies fills and attempts verification of attached protective orders; unprotected fills trigger an emergency reduce-only market close attempt. **Neither stop orders nor emergency close are guaranteed to execute during outages.**
- **At least 10 minutes between any fully closed SWAP position and the earliest possible subsequent entry**, measured using the OKX server's authenticated `GET /api/v5/account/positions-history` `uTime`. A liquidation or fully closed ADL event also starts the cooldown. The bot checks this twice per entry and refuses trades if exit history is unavailable or ambiguous. This is a minimum wait, not a promise of a new signal/order at exactly 10 minutes.\n- **No fixed numerical maximum of bot orders per day.** This does **not** mean continuous trading: a fresh vetted 6-agent+7-system signal, no existing position/pending order, correct exchange-side protective orders and the **10-minute re-entry cooldown** are still mandatory. A full 24-hour order-history scan remains required to detect replayed client IDs. This is a high-loss-risk configuration, especially with full-margin allocation. An automated daily realized-loss limit is **not** implemented, so live activation is unsuitable without separate persistent drawdown protection.
- No key or balance logging, no withdrawals, transfers, or balance sweeping. Execution never calls NVIDIA; a **separate optional** NVIDIA advisory workflow sends only public market evidence to the NVIDIA inference API, and never receives account credentials or position details.

## Enter OKX credentials **securely** (public repository)

1. Revoke every old OKX API key ever posted in chat or code. In OKX create a **new** `Read` + `Trade` key (never `Withdraw`). Ideally use a dedicated sub-account and enforce a source IP allowlist on a stable-IP server.
2. In the repository's **Settings → Secrets and variables → Actions → Repository secrets**, create:
   - `OKX_API_KEY` = your new API key;
   - `OKX_SECRET_KEY` = your new API secret;
   - `OKX_PASSPHRASE` = your new OKX API passphrase.
   **Do not put these in source code, issues, commit messages, chat, Actions variables or shell commands.**
3. Under **Settings → Secrets and variables → Actions → Repository variables** set `OKX_EXECUTION_MODE=dry_run` initially, and if needed `OKX_API_DOMAIN=https://www.okx.com` (or region-appropriate `https://eea.okx.com` / `https://us.okx.com`).
4. Open **Actions → OKX guarded execution → Run workflow**, choose `validate`. This performs an authenticated **read-only** request, prints whether the account is in `net_mode`, and **never places an order**.
5. To test demo, use **OKX demo credentials** and set variable `OKX_EXECUTION_MODE=demo` plus secret `OKX_EXECUTION_ARM=CONFIRM_DEMO_ORDER`.
6. Optional **full available margin** sizing (particularly hazardous): configure repository variable `OKX_CAPITAL_MODE=full_margin` AND repository secret `OKX_FULL_MARGIN_ARM=I_ACCEPT_FULL_MARGIN_LIQUIDATION_RISK`. Until **both** are configured, full-margin trading is BLOCKED; the default remains `guarded`. A 10% estimated equity-at-stop cap may reject the trade instead of reducing its size. The exchange's `max-size` quote, lot rounding and fees may prevent exact 100% utilization; **never promise all available equity will be deployed**.\n7. **Real-money arming is a separate opt-in:** only after evaluating the demo and independently verifying account setup, set variable `OKX_EXECUTION_MODE=live`, set variable `OKX_ENABLE_REAL_TRADING=YES`, and set secret `OKX_EXECUTION_ARM=I_ACCEPT_REAL_MONEY_LOSS`. At that point scheduled runs *can submit real orders* without another prompt when a valid signal exists. Set either variable back to `dry_run` or `NO` immediately to stop new entries.

**Do not enable live mode with a key you have already disclosed elsewhere.** The workflow deliberately defaults to `dry_run` even when a valid trading key exists. The workflow does not switch account mode: OKX must already be `net_mode` and able to use USDT isolated perpetual margin.

## Scan cadence and the 10-minute re-entry rule\n\nGitHub Actions requests scans **every five minutes**; the previous schedule was every fifteen minutes. If a position is fully closed at 12:03, the next eligible run could be 12:17 or later depending on scheduling and signals. No trade is forced. There is no fixed bot order-count cap, although the scanner may return WAIT and the ten-minute post-exit wait still applies. The six-agent and seven-quant-system confirmations, position exclusivity and capital-mode opt-ins remain mandatory.\n\n## GitHub-hosted runner risks\n
GitHub Actions schedules **may delay or skip runs**, executions are ephemeral and cannot continuously monitor positions, and hosted runner IPs are not stable for reliable OKX API IP allowlisting. The system relies on exchange-native TP/SL after entry, **but GitHub Actions is not a safe substitute for a 24/7 execution/risk daemon**. An always-on private server with static IP, durable state, persistent PnL/drawdown limit, real-time health checks and kill switch is strongly preferred for production live trading.

There is **no backtested or live-verified positive expected return**. The six agents are deterministic analysis components, not six autonomous LLM instances. Seven advanced numerical systems are veto filters; "2037" is branding, not a claim to quantum computation.

## Emergency stop

Switch repository variable `OKX_ENABLE_REAL_TRADING` to `NO` and/or `OKX_EXECUTION_MODE` to `dry_run`, **then inspect existing positions and protective orders directly in OKX**. Disarming prevents new bot entries but does not close existing positions or stop working exchange-native protection orders. Revoke the API key if needed.

## More safety gates needed before treating this as production-grade

Current v1 does **not** have a fully independently reconciled realized-PnL daily drawdown monitor, transaction-proof persistence across crashes, guaranteed protection-order reconciliation across all OKX account modes, stable-IP secret allowlisting, or historical profitable performance. It deliberately caps bot order count and size and fails closed on unfamiliar conditions, but this does not cap all possible monetary losses. Test with isolated demo credentials before using live.

API references: https://www.okx.com/docs-v5/en/ | https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions


## Opt-in chained GitHub sessions (20-second handoff)

The `okx-guarded-execution.yml` workflow supports an **optional** chained session mode. In **Actions → OKX guarded execution → Run workflow**, choose `purpose=run`, check `confirm_live`, `continuous` and `confirm_continuous_live`. The new controls are off by default, so a previous **one-off** manual confirmation cannot silently become unlimited live trading. Set `OKX_EXECUTION_MODE=dry_run` first to validate the mechanism without placing orders. Real trading requires the separate account and secret arm checks described above.

Each worker session has a **245-second** bounded runtime. Only when the worker exits **successfully due to the normal time limit**, the workflow sleeps **20 seconds** and requests a fresh `workflow_dispatch` using the repository-scoped `GITHUB_TOKEN`. A repository-level concurrency group prevents overlapping execution jobs. GitHub queue time, runner startup, and service availability mean **20 seconds is the delay before requesting the next run, not a guaranteed time to execution**. GitHub Actions is not an always-on host and the chain can be interrupted.

**Fail-closed:** No automatic re-dispatch on market scanner / NVIDIA / executor errors, ambiguous order state, a placed order, protective-order concerns, or an early risk-veto stop. These cases need manual investigation rather than blind retries. A valid trade signal and 10-minute exchange-side re-entry cooldown are still required. The 20-second job handoff is **not** a 20-second trading cooldown.

**Stop:** In `Settings → Secrets and variables → Actions → Variables`, set `OKX_STOP_CONTINUOUS=YES` to prevent a clean worker from scheduling its next run. Also set `OKX_ENABLE_REAL_TRADING=NO` or `OKX_EXECUTION_MODE=dry_run` to block all new live orders; then review any open OKX positions and exchange-native TP/SL manually. To resume the chain, remove the stop flag or set it to `NO` and manually initiate a new, explicitly confirmed workflow run.

Continuous hosted sessions can exhaust usage quotas and accumulate losses. Production trading requires an always-on risk service, circuit breakers, reconciliation, stable IP and monitored loss limits; none is supplied by GitHub Actions chaining.

## NVIDIA research only — detached from real trade decisions

The live executor (`trading/okx_live_executor.py`) does **not** import or invoke NVIDIA and does **not** use model advice to approve/reject entries. A separate [read-only NVIDIA advisory workflow](../.github/workflows/okx-nvidia-advisory.yml) performs its own public-market scan (12 instruments maximum), selects a fresh qualifying quant signal, and optionally asks NVIDIA's six research roles to report a directional opinion and uncertainty/risk notes. The resulting JSON artifact contains public research only — not account details, balances, API keys or order information. It reports `NO_SIGNAL` if the quant scanner finds no eligible trade.

Advisory output can be `BUY`, `SELL`, `WAIT` or `UNAVAILABLE`, but it is **never passed to the OKX executor**. An AI timeout, missing key, opposing opinion or partial response does not suppress a quant-approved candidate. Neither NVIDIA nor the quant system guarantees profitability; independent checks on position state, cooldown, exchange availability, leverage, size, stop/target validity, freshness and protection remain mandatory.

This intentionally removes an advisory risk-veto layer. **It increases potential trading exposure, especially when live mode and `full_margin` are armed.** Users should prefer `dry_run`/demo, rotate any previously disclosed keys and install persistent realized-loss cutoffs before real-money automation.

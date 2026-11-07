# OKX 6 agents + 7 systems — guarded real execution adapter

**Real trading execution is implemented in `trading/okx_live_executor.py` but DISARMED until you explicitly configure it. No guarantee of profit.**

## Live-capable architecture

- Public-data 6-agent / QUANT2037 signal engine scans **up to 12** USDT perpetual instruments, with estimated 24h base-coin turnover **≥ US$15 million**. This is turnover, **not order-book liquidity**, and is not a guarantee of executable depth.
- Fresh `LONG` or `SHORT` must pass all six-agent votes, seven-system filters and risk vetoes. No forced trades. Stale report, ambiguous signal, data errors or mismatched account mode result in **no trade**.
- Separate private execution engine authenticates using OKX REST API v5, checks account `net_mode`, positive free USDT equity, no outstanding perpetual position or order, 24h bot order count, current contract specification, spread, instrument turnover and current price.
- Caps intended risk at **0.25% equity per order**, **20% equity gross notional**, **5% initial margin**, **10x leverage**. These are planned entry sizes, **not maximum realized loss**: gaps, slippage, funding and liquidation can cause larger loss.
- Only USDT-margined **linear isolated** perpetuals with `ctValCcy` equal to base asset are supported. Position quantity is quantized down to `lotSz`, never rounded up to `minSz`.
- Sets isolated leverage to 10x after preflight, then sends a single market order with **exchange-native attached stop-loss and take-profit**. Verifies fills and attempts verification of attached protective orders; unprotected fills trigger an emergency reduce-only market close attempt. **Neither stop orders nor emergency close are guaranteed to execute during outages.**
- Maximum **2 bot orders per rolling 24h**, derived from the exchange's order history. Blocks if it cannot verify a complete history window. Refuses if an existing swap position, pending order or pending algo stop is present.
- No key or balance logging, no third-party services, and no withdrawals, transfers, or balance sweeping.

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
6. **Real-money arming is a separate opt-in:** only after evaluating the demo and independently verifying account setup, set variable `OKX_EXECUTION_MODE=live`, set variable `OKX_ENABLE_REAL_TRADING=YES`, and set secret `OKX_EXECUTION_ARM=I_ACCEPT_REAL_MONEY_LOSS`. At that point scheduled runs *can submit real orders* without another prompt when a valid signal exists. Set either variable back to `dry_run` or `NO` immediately to stop new entries.

**Do not enable live mode with a key you have already disclosed elsewhere.** The workflow deliberately defaults to `dry_run` even when a valid trading key exists. The workflow does not switch account mode: OKX must already be `net_mode` and able to use USDT isolated perpetual margin.

## GitHub-hosted runner risks

GitHub Actions schedules **may delay or skip runs**, executions are ephemeral and cannot continuously monitor positions, and hosted runner IPs are not stable for reliable OKX API IP allowlisting. The system relies on exchange-native TP/SL after entry, **but GitHub Actions is not a safe substitute for a 24/7 execution/risk daemon**. An always-on private server with static IP, durable state, persistent PnL/drawdown limit, real-time health checks and kill switch is strongly preferred for production live trading.

There is **no backtested or live-verified positive expected return**. The six agents are deterministic analysis components, not six autonomous LLM instances. Seven advanced numerical systems are veto filters; "2037" is branding, not a claim to quantum computation.

## Emergency stop

Switch repository variable `OKX_ENABLE_REAL_TRADING` to `NO` and/or `OKX_EXECUTION_MODE` to `dry_run`, **then inspect existing positions and protective orders directly in OKX**. Disarming prevents new bot entries but does not close existing positions or stop working exchange-native protection orders. Revoke the API key if needed.

## More safety gates needed before treating this as production-grade

Current v1 does **not** have a fully independently reconciled realized-PnL daily drawdown monitor, transaction-proof persistence across crashes, guaranteed protection-order reconciliation across all OKX account modes, stable-IP secret allowlisting, or historical profitable performance. It deliberately caps bot order count and size and fails closed on unfamiliar conditions, but this does not cap all possible monetary losses. Test with isolated demo credentials before using live.

API references: https://www.okx.com/docs-v5/en/ | https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions

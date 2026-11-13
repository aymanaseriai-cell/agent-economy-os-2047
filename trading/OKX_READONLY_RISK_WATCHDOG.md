# OKX independent read-only safety watchdog

The trading worker stopped after two `FILLED_PROTECTED` results because
`okx_portfolio_guard.snapshot` reported **existing aggregate risk above permitted
limits**. This condition can arise from real mark-to-market movement or changing
account equity. It is **not a reason to bypass the caps or auto-resubmit orders**.

## Watchdog

`.github/workflows/okx-readonly-risk-watchdog.yml` checks the actual OKX
account, isolated USDT perpetual positions, and protective orders every five
minutes (GitHub Actions minimum). It is independent of the trading workflow:
a failed trading run will not disable scheduled future checks.

The watchdog enforces GET-only authenticated requests with an endpoint
allowlist and sends **no trading POST requests**. It needs the existing OKX API
credentials stored as GitHub Secrets. It does **not** require either live
execution arm or the `OKX_ENABLE_REAL_TRADING` flag to inspect the account.

Possible public status codes:

- `NO_OPEN_SWAP_POSITIONS`: no swap position found (exit 0)
- `PORTFOLIO_PROTECTED_WITHIN_POLICY`: all reported swap positions have
  verifiable SL/TP and aggregate initial-margin / planned-stop exposure is
  within configured ceilings (exit 0)
- `RISK_LIMIT_EXCEEDED`: aggregate planned-stop or margin threshold exceeded;
  **no new entries** and nonzero exit 2
- `ACCOUNT_OR_PROTECTION_UNVERIFIABLE`: missing stop, inconsistent state,
  unverified real leverage, open orders or unavailable data (exit 3)
- `READ_ONLY_CONNECTION_FAILED`: no verified API read (exit 3)

Account amounts, positions, keys, order IDs, and symbols are not printed.

## Limitations

A read-only watchdog **cannot fix an already unsafe position**, guarantee a
stop fills, or guarantee uptime; GitHub scheduled jobs can be delayed or missed.
A nonzero risk result must **not** be converted into permission to keep opening
positions. The live trading workflow stays fail-closed until independently
resolved. This is monitoring continuity, NOT automatic live-trading resumption.

Useful next steps: review actual open positions, reduce exposure manually if
necessary, confirm exchange-side TP/SL, and check margin, fee and funding risk.

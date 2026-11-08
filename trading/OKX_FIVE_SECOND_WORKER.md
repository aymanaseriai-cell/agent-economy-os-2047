# TITAN QUANT2037: five-second continuation after every FULL scan

Implementation: trading/okx_five_second_worker.py, with nine offline
regression tests in tests/test_okx_five_second_worker.py.

The worker executes the ORIGINAL public trading.six_agent_council scanner,
then invokes the ORIGINAL trading.okx_live_executor guarded decision path.
After a completed NO_CONSENSUS or DRY_RUN_SIGNAL_ONLY outcome it waits
exactly five seconds and starts the next full analysis cycle.

Important distinctions:
- A full scan takes longer than five seconds on a slow market/API.
  Therefore five seconds is the delay BETWEEN completed cycles,
  not a guarantee of a new complete 6+7 signal exactly every five seconds.
- GitHub Actions cron supports intervals >=five MINUTES and jobs can be
  delayed. A repository cannot itself host an uninterrupted five-second
  execution daemon. The existing disabled okx-guarded-execution.yml
  uses this new worker with --max-runtime-seconds 245 for each
  five-minute scheduled window only if the workflow is later enabled.
  This is NOT a continuously running 5-second cloud bot.
- For genuine uninterrupted operation, a separately hosted, persistent
  worker/VPS or private computer is necessary. Railway is NOT required.
  Its operating system must keep Python running and preserve secret
  environment variables outside Git.
- No private account query, order submission or new exchange endpoint
  was added. The existing executor's NVIDIA veto, 10x leverage cap,
  available balance checks, stop/target protection, 10-minute
  post-close cooldown and other safety gates are unchanged.
- Any actual/uncertain submitted order outcome, missing status,
  rejected exchange request, API error or slow/failed scan STOPS the
  worker. It does NOT blindly resubmit orders every five seconds.
  The process is not a replacement for an exchange-side stop order
  or a monitored trading operations service.
- Trading remains OFF: OKX_EXECUTION_MODE=dry_run,
  OKX_ENABLE_REAL_TRADING=NO, and the GitHub Actions live
  workflow remains disabled_manually.
- Neither the 5-second cadence nor faster scanning establishes
  profitability. Trading repeatedly against the same 15m candles
  may be redundant and incur exchange rate limits.

Local read-only research loop on a continuously powered machine:

    OKX_EXECUTION_MODE=dry_run OKX_ENABLE_REAL_TRADING=NO python -m trading.okx_five_second_worker --interval-seconds 5 --top 6

Manual public-only GitHub Actions smoke test (bounded to 3 cycles):

    .github/workflows/okx-five-second-proof.yml

No capital-mode, API-key secret, real-trading variable or arm was
changed by this feature. No approval is inferred from AI output.

# 15-minute closed-candle age forensic review — 2026-11-08

## Evidence
The OKX public research report from GitHub Actions run 42428551777,
2026-11-08 at 00:13:41 UTC, contained a quantitative research label:

- UNI-USDT-SWAP LONG, quote price 7.218.
- Research indicative stop 7.092, target 7.47, 2 advanced confirmations,
  zero advanced vetoes and no derivative-data warnings.
- Last completed 15-minute candle timestamp: 1794095100000,
  corresponding to 2026-11-07 at 23:45 UTC. This is the candle OPEN.
- The candle closed at 00:00 UTC. At the 00:13:41 UTC execution check,
  approximately 13m41s had elapsed after it CLOSED.

The old executor compared the report timestamp to the candle's opening
timestamp and rejected any record older than 25 minutes. Thus a candle
that had legitimately finished ~13m41s earlier was discarded, and the
executor reported NO_CONSENSUS. This is a false-negative signal-selection
bug, not evidence of profitable trade performance.

## Correction
For exactly 15-minute OHLCV bars, calculate
close_ms = last_complete_15m_candle_ms + 15 * 60 * 1000.
Allow an otherwise eligible report if its candle has closed and no
more than 15 minutes have elapsed since candle completion.

Future/unclosed candles and bars whose close was over 15 minutes ago
remain excluded. Report freshness (180 seconds) and every other NVIDIA
veto, account, margin, position, funding, spread and market gate remain
unchanged. The fix does NOT guarantee a trade would have been approved:
NVIDIA, account and exchange preflight were not reached in the old run.

The bot's Actions workflow is intentionally disabled and live-trading
variable remains NO / dry_run. This is only a code and test fix.

# TITAN Phoenix public-data recovery

When *all* of the following are true:
- The live recurring entry mode is separately, explicitly confirmed.
- The market scanner returns reserved code 75 with the **exact** marker
  TITAN PUBLIC GET TRANSIENT_NO_ORDERS.
- The current market data scan is INCOMPLETE, hence no execution is attempted.

The worker retries the original public GET path with delays 5, 10, 20
seconds. On the fourth such failure it waits 30 seconds and starts a fresh
sequence. On the eighth consecutive failure it waits 60 seconds and retries.
On the twelfth consecutive failure it STOPs, requiring diagnosis.

A successful complete scan clears both the short streak and extended
recovery streak. If a bounded GitHub session has insufficient time to wait,
it safely hands off without attempting any new scan or order.

Do not generalize this routine to an unknown-order state:
- Private OKX executor failure or post-submit uncertainty => STOP.
- Invalid exchange position state, unprotected open positions => STOP.
- Any HTTP public failure lacking the exact no-order marker => STOP.
- Owner STOP switches, enabled status and separate order confirmations
  remain authoritative.
- No private API credentials used in Phoenix code; no thresholds or
  risk controls changed.

Important: Phoenix only recovers verified temporary public market-data
faults. It is NOT autonomous source-code repair, not a guarantee that a
GitHub Actions runner remains alive 24/7, and never guarantees a trade
on startup. Tests intercept all APIs.

# OKX public market-data transient resilience

## Incident

The continuous live worker run #1183 stopped after `XPL-USDT-SWAP` returned
OKX code `50026` ("System error. Try again later") during an otherwise
healthy full-universe scan. This was a **public GET data error**, not an order
failure. The original fail-closed executor rejected any report containing
per-market errors, which is still the correct trading policy.

## Implemented

1. The public council retries only unauthenticated GET requests on temporary
   OKX error codes `50011` (rate limit), `50013` (busy), `50026` (system
   error) and HTTP 429/500/502/503/504 or network errors, with four attempts
   and bounded backoff of 1, 2 and 4 seconds. Permanent codes and malformed
   data are **never** treated as valid observations.
2. A fully accounted scan with only temporary public errors emits
   `TITAN PUBLIC GET TRANSIENT_NO_ORDERS` and exits 75. The continuous
   worker skips the private executor **entirely** for that scan and retries
   fresh analysis after 5, 10, then 20 seconds, subject to the GitHub job
   deadline. No cached signals or partially analyzed candidate are used.
3. A fourth consecutive failed scan halts live execution and leaves the
   independent read-only safety watchdog scheduled. Unknown failures, ambiguous
   states, protective-order problems and POST uncertainties still fail closed.
4. Only a completely successful fresh market scan reaches the unchanged
   executor and its margin, TP/SL, account and risk protections.

This reduces unnecessary halts on occasional exchange faults without
promising uninterrupted live trading. No new orders are sent by this change,
and a successful test is not proof of live profitability. Running in a hosted
GitHub job is bounded and cannot provide 100% guaranteed uptime.

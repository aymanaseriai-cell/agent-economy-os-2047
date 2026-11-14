# TITAN Omega: no-trade risk veto vs. system failure

Scope: the owner requested a bot which survives recoverable problems. The
14 November 2026 run #1283 stopped at a last-moment aggregate stop-risk
check. That is a **candidate rejection**, not evidence of an exchange outage.

The final exchange-state preflight is now split into two distinct operations:

- If the **fresh portfolio snapshot** is missing, malformed, ambiguous, or
  disagrees with the prior position set: STOP, no new order, manual review.
- If a **fully verified portfolio** makes the candidate exceed the existing
  5% aggregate stop risk or 50% allocated-margin cap: in separately authorized
  recurring mode only, return RISK_REJECTED_NO_ORDER to the worker, skip the
  candidate, and start a fresh market scan. Never submit this order.
- Unknown exceptions still fail closed. On non-recurring runs an over-limit
  pre-submit risk check still stops with ExecutionBlocked.
- No risk thresholds, order parameters, trader arming, or workflow startup
  settings have changed. The owner stop remains in effect.

Tests intercept all private requests. Zero actual orders.
This corrects one specific stop cause; it is *not* general autonomous
software repair or a guarantee of non-stop trading.

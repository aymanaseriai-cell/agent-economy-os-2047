# TITAN Phoenix — bounded restart authority

This is a **watchdog for a previously successful, explicitly authorized
continuous LIVE session**. It is not an order replay engine and not an AI
which modifies live code on its own.

There are four separate owner controls:

- OKX_STOP_CONTINUOUS=YES always stops the watchdog and live worker.
- OKX_ENABLE_REAL_TRADING=NO always disables real trading.
- OKX_EXECUTION_MODE=live must be confirmed.
- **OKX_PHOENIX_RESUME_ARM=YES** must be separately configured by the owner
  to permit a future recovery attempt. Absent by default, treated as NO.

Only after a completed, successful, manually dispatched `main`
continuous LIVE worker which ran the three actual signed live/chain
steps, followed by 9–60 minutes without an active session, may the
watchdog request a NEW workflow run. This covers lost *clean*
GitHub-session chaining, not failed or unknown orders.

The watchdog will NOT restart:
- any manually disabled or owner-stopped workflow;
- a failed, cancelled, queued, running, stale or otherwise uncertain job;
- a research/validate session without a completed live worker and
  chain step;
- unknown order/position states or jobs with incomplete proof;
- a session older than one hour without human reauthorization.

All old exchange-side checks, anti-replay order identifiers, 30-second
post-close cooldown, SL/TP and risk caps remain unmodified and mandatory.
The watchdog itself NEVER contacts OKX or submits exchange orders.

GitHub Actions scheduled workflows may be delayed or skipped. This is
**best effort** liveness, not guaranteed uninterrupted operation. Use a
persistent host with a correctly configured service supervisor if
availability is critical.

The owner currently requested an explicit STOP: all owner switches remain
off and the live workflow remains manually disabled. **Do not change the
stop flags automatically**.

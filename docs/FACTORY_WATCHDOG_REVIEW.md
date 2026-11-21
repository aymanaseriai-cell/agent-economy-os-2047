# Factory Scheduler Watchdog — bounded internal self-replay

Source-controlled private Supabase function snapshot for Agent Economy OS 2047, 21 November 2026. **No GitHub branch or production product release.**

The existing four executive ChatGPT automations and 12 registered limited worker identities are unchanged. The separate private SQL factory router (job 26, minutes 4/19/34/49) and source failover selector (job 27, minute 16 hourly) run without per-turn chat instructions. The new SQL watchdog (job 28, minute 24 hourly) checks *both* exactly named, active schedules.

- A completed scheduled job `succeeded` after the expected timestamp is recorded as `HEALTHY`.
- If a job is human-paused or its command/schedule is modified, record `PAUSED_NO_OVERRIDE` or `CONFIG_DRIFT_BLOCKED`; do not override or execute.
- During initial installation, the job's first due time before registration is `WARMUP_NOT_DUE`, preventing a false alarm.
- A missed or failed scheduled run is eligible for **one and only one** replay of the already allowlisted safe private DB function per hour/job. It does not repair the pg_cron infrastructure or switch cron configuration.
- Each replay has `READONLY_REPLAY_SUCCEEDED` or `READONLY_REPLAY_FAILED` evidence; a successful function return is *not proof* the original scheduler healed.
- Invocation provenance is `USER_REQUEST` for the initial manual check; later rows default to `UNVERIFIED` until the exact cron.job_run_details can be independently checked. Do not count them as unattended episodes merely because they exist.

**Manual checks completed on 21 November 2026:** 7/7 decision cases passed (healthy, paused, drift, warmup, grace, missed, failed). Invoking the live function twice in the same hour yielded job26 HEALTHY and job27 WARMUP_NOT_DUE, with zero retries; the second invocation reused the same two records. Never inject a fake source incident into live production to force a recovery demonstration.

**Constraints:** private schema with RLS and no anon access; no outbound HTTP, payments, crypto, live trading, customer replies, code deployment, or production release. GitHub issue #98 remains open. Jobs 27/28 require independently observed first unattended execution before making an autonomy claim.

## Pending watchdog safety correction (review-only, 21 Nov 2026)

The deployed function is *not* updated by this review-branch document. Two
defects were independently identified:

1. A read-only SQL invocation of the currently deployed `factory_watchdog_verdict`
   returned `REPLAY_ELIGIBLE` for a cron job marked `running` after its due
   time. Replaying then can overlap with the still-running job. The proposed
   verdict `RUN_STATUS_UNCERTAIN_NO_REPLAY` fails closed for unknown and
   nonterminal statuses when a cron run has started.
2. The deployed watchdog uses `ON CONFLICT(slot,jobid) DO NOTHING`.
   A preliminary `WAIT_EXPECTED_RUN` record created earlier in the hour can
   prevent the watchdog's later scheduled due-time check. The review patch
   permits exactly one in-hour refresh *only* from unattempted preliminary
   states; terminal results and previous replay attempts never reset.

The changed SQL snapshot is **not deployed**. The existing private job #28
remains scheduled, but its first unattended success must be verified by
`cron.job_run_details`. A human release reviewer should compare exact
Supabase source, inspect any overlapping jobs, verify the schema constraint
migration, and test retry idempotency/rollback before applying the change.
Neither successful unit tests nor a manual test constitutes auto-recovery.

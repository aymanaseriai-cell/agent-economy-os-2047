# Independent Cron Evidence Reconciliation — REVIEW ONLY

This proposal eliminates the need for a founder/chat turn to classify whether
our private factory watchdog and market failover observations were generated
by actual scheduled pg_cron runs.

Observed provider evidence, 21 November 2026:
- Watchdog job 28 run 21622 completed at 21:24 UTC; two health checks fell
  inside the provider-reported run interval and were marked
  INDEPENDENT_SCHEDULED_VERIFIED through an explicit, user-requested audit.
- Market-selector job 27 run 21613 completed at 21:16 UTC; its failover check
  fell inside the run interval, and two independently timed BasedAgents
  HTTP 200 receipts support the read-only provider selection. Classified as
  exactly one COO/CFO scheduled routine episode, not two.
- The above provider-backed rows were already reconciled manually by the
  user-requested execution. This file is NOT deployed.

The new SQL routine requires exact pg_cron job id, name, active schedule,
command, successful completed run, and in-window check timestamps. It only
updates previously UNVERIFIED provenance of health checks and source-selection
observations, with defensive no-money/no-outreach constraints. It never
inserts autonomy episodes or revenue records, so repeated runs do not inflate
the company automation percentage.

Before any deployment, independent reviewers must validate source parity,
schema privileges, backup/rollback, plan timing, and the P0 issue #98 release
gate. A commented sample cadence of 25 past the hour is not a live schedule.

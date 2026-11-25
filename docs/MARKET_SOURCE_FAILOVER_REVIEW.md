# Automated fallback for agent opportunity discovery (review-only)

Project: Agent Economy OS 2047 · verified private control-plane update, 21 November 2026.

## Problem and measured evidence

AgentSouk's last two captured public HTTP probes returned DNS error ("Couldn't resolve host name"), without any HTTP 200 or funded candidate evidence. BasedAgents probes at 19:11 and 20:11 UTC returned HTTP 200 and parsed JSON array responses; both report 0 screened relevant funded opportunities. **Zero matching records is not evidence of zero market demand or company revenue.**

## Executed outcome

The private Supabase `executive_nexus.run_market_failover_check()` reuses two separately timed, parsed, independently captured HTTP observations per market and requires freshness, valid status, no network parser error and a parsed opportunity array. It never sends a network request itself. Initial live decision was `DEGRADED_HEALTHY_FALLBACK`: allowed `basedagents`, blocked `agentsouk`. Repeating the cycle with unchanged receipts recorded no new transition. The readonly view `executive_nexus.active_market_discovery_signal` currently returns BasedAgents only, with 0 screened candidate records and no buyer/payment claims.

The existing private 4-manager roster and 12 worker identities are unchanged. CEO, CRO, COO/CFO scheduled executive instructions now consult this private routing state. Provider probing continues on existing market cron jobs; the selector does not disable polling, repair external DNS or alter product API traffic.

## Running and verification

- Private pg_cron job 27: `aeos2047-autonomous-market-source-failover-hourly`, schedule minute 16 of every hour (after existing hourly probes are collected at minute 14).
- Verify `cron.job_run_details` for the exact job 27 and inspect `executive_nexus.market_failover_state` and `executive_nexus.market_failover_checks`.
- Confirm two distinct recent HTTP 200 responses per allowed source from `public.agent_economy_bounty_monitor`, not a self-declared application status.
- With no two fresh valid proofs, the source is excluded. If neither provider qualifies, decision becomes `HALTED_NO_TRUSTED_SOURCE`. A previously blocked source can only be reinstated after two distinct new valid observations.
- This snapshot of DDL and active function is for independent code/security review; it is **not** an automatic deploy pipeline. Release gate [#98](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/98) stays OPEN.

## Strict limits

The technical operation proves provider observation and internal source selection, not 100% company autonomy, a working independent language-model agent, vendor repair, qualified inbound consent, paid deal, independently secured contract, or lawful settlement. No cash, client outreach, trading or production deployment is performed.

## Provenance correction

The first source failover check at 20:24 UTC on 2026-11-21 was **USER_REQUEST/manual**, not an unattended scheduled achievement. The private audit row was corrected to `USER_REQUEST_READONLY_MARKET_SOURCE_CHECK`, and future transition rows are labeled `SYSTEM_INTERNAL_READONLY_MARKET_SOURCE_SELECTION` until their actual scheduler provenance is independently verified. The new hourly job 27 was enabled but had not yet executed unattended at the time of this review.

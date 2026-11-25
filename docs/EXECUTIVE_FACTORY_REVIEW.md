# Executive Factory — Review-only management and worker dispatch

Agent Economy OS 2047 has four scheduled ChatGPT executive automations and exactly 12 registered role-specific worker capabilities (not 12 separately instantiated LLM agents). This module implements a testable CEO -> executives -> validated worker decision path with no money, customer contact, production deployment or new OAuth permissions.

## Scope

- The private Supabase executive_nexus.work_dispatch table remains the authenticated source of persistent work orders. Never publish credentials, private customer data, service-role keys or raw work snapshots.
- An authorized executive may export only the non-sensitive subset of up to 12 work orders (work_key, owner_role, action_code, work_status, priority, proof_ref) to a local private JSON file.
- automation.factory_operator.plan_dispatch checks exact worker identity, manager ownership, action allowlist, status/proof consistency and duplicate suppression; each of four executives receives a priority selection.
- Only QUEUED `REVIEW_ONLY_ACTION_ELIGIBLE` probes or interrupted `IN_PROGRESS` probes selected as `VERIFY_IN_PROGRESS_FIRST` may pass to `execute_reviewonly`. Both use the existing strictly read-only `run_fleet` dispatcher. The latter is a bounded verification replay, **not** permission to retry a customer contact, money movement, production deployment, or other side effect. Missing/foreign live jobs fail closed. Blocked or approval-gated work is NOT executed.
- An input VERIFIED field reflects an observed database record, NOT independent proof that the business outcome happened. Provider logs, external buyers, accepted delivery and lawful payment still require separate verification.
- Passing execute_reviewonly does NOT instantiate an AI worker model. This review branch has no code-write, payment, mass messaging or deployment grants.

## Local review-only operation

Command: python3 -m unittest discover -s tests -p 'test_factory_operator.py' -v

Command: python3 -m automation.factory_operator --orders /private/role-owned-work-orders.json --out /tmp/factory-decision.json

If an authorized operator separately provides current allowlisted read-only worker jobs in a private file, the --jobs /private/live-jobs.json --root . options run eligible worker probes through the existing restricted dispatcher. No new GitHub Actions or Supabase database credentials are required for offline decisions.

## What is NOT deployed

The operator is PR code, not a new default-branch scheduler, independent human reviewer, autonomous production patcher, financial decision-maker or full company operating system. The existing Supabase read-only schedulers continue unchanged. GitHub release gate #98 requires independent source, security and rollback review before merger or any production change. Do not mark queued decisions as executed or business impact.

## Acceptance criteria for a later release

1. Independently review exact-source role/authorization boundaries and provider-backed evidence.
2. Verify all test cases and branch-specific GitHub CI against the current PR head.
3. Determine how genuinely authorized executive sessions will retrieve private, non-sensitive work orders and submit actions with isolated role-scoped credentials, audit logs, retries and revocation.
4. Add approval-gated release controls and rollback tests; close #98 only after all P0 prerequisites.
5. Track actual unattended end-to-end work separately from successful read-only checks; never claim 100% autonomy from test volume.

## Source-bound read-only execution (2026-11-22 review update)

The executor now **requires the same limited, operator-exported source order rows** that generated the manager plan. It independently recalculates the entire plan, checks an auditable SHA-256 of the source snapshot and rejects any altered role, priority, status, or extra private fields before dispatch. This is a consistency check, **not proof of independent Supabase authentication or signed orders**. Keep source orders private and do not treat the digest as a signature.

For a local private export, use `--auto-live-jobs` instead of manually curating an allowlisted GitHub worker-job file. Only if an eligible order exists does the tool read current public GitHub evidence and construct bounded read-only jobs. With all orders blocked, verified or awaiting approval, no provider execution occurs; the outcome reports zero rather than creating synthetic work.

Do not enable this as a production scheduler before #98 and independently reviewed real work-order authentication, replay-resistant state transition control and rollback are complete.

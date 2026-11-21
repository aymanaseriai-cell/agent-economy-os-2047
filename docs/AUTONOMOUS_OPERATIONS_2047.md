# Agent Economy OS 2047 — bounded autonomous operations

This document describes a **review-first, zero-extra-budget** path to repeatable CTO/CRO operations. Configuration or a scheduled job is not proof of independent management or sales.

## Engineering / CTO: event to reviewable fix

- GitHub's Test and verify CI runs on main. A separate workflow-run handler checks that the reported SHA is the *latest main* SHA.
- When that current SHA fails, the handler creates one bot-owned, deduplicated CTO incident issue with the exact run link, SHA, and an acceptance test.
- The scheduled CTO automation may examine the issue, reproduce the defect in isolation, generate a minimal fix, run focused/full tests, create a review branch and Draft PR through the already connected authorized GitHub tool, and attach evidence.
- No GitHub Action may autonomously merge, deploy, modify payments, trade, leak secrets, or bypass release gate #98.
- When a later current-main run succeeds, the handler closes only its own marked bot incidents. Human-authored issues are never silently closed.
- No arbitrary code generation or model calls are launched by this deterministic workflow; intelligent repair depends on the separate hourly CTO agent and its actual tool access and run outcome.

## Commercial / CRO: consent-first public reply

- GitHub's service-request issue form explicitly asks for consent to **bounded public follow-up**. No private email, customer data, or payment is requested.
- Existing issue-router performs the initial public response to inbound service inquiries. The new issue-comment workflow responds only to comments by the original service-request author on an **open, opted-in public** issue.
- Only specific questions about scope, pricing, demo/integration, or confidential data get a templated answer. It never echoes untrusted comment text, fetches buyer code, or invents a contract.
- At most two automated follow-ups per issue, at least 24 hours apart. Repeat event deliveries are deduplicated by comment ID. When the first page of comments cannot provide complete evidence, fail closed.
- Neither submitted inquiries nor automated answers establish buyer identity, qualification, adoption, contracts, payments, or verified revenue. Close the issue to stop automated follow-ups.
- GitHub event-based customer replies become active **only after** a reviewed PR is merged into main, with Actions and issue-write permissions permitted by the repository owner.

## How to measure true autonomy

Count **eligible, permitted, bounded operational episodes**, not the number of scheduled scripts. Record the original externally observed trigger, responsible executive, authorized actions, start/end, any human intervention, and independently reproducible outcome/ref. A success must be independently verifiable and cannot be a queued task, a synthetic probe, or a draft without completed tests.

Suggested acceptance threshold for a statement like **90% routine operational autonomy**:

1. At least 30 eligible episodes across CTO, CRO, CEO and COO/CFO over a rolling 14-day window; no role can be absent from the sample.
2. At least 90% completed end-to-end without intervention after the original external trigger, with source and evidence links.
3. All required safety, confidentiality, consent, finance and production controls honored; zero unapproved transactions or production changes.
4. Report denominator, failures, unknown outcomes, time-to-recover and reviewer sample. A percentage is not meaningful if it excludes real blockers or if evidence is absent.

Business strategy, contracts, payments, protected production releases and other material consequences retain human approvals. A technical 90% target is a measurable aspiration, not a currently achieved or guaranteed rate.

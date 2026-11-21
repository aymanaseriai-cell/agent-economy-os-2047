# Agent Economy OS 2047 — Safe Integration Guidance

This repository exposes public, deterministic technical evidence checks for agent-delivered artifacts. Integrate using `buyer-gate/README.md` and `skills/agent-economy-buyer-acceptance/SKILL.md`. Do not claim these checks establish buyer authorization, real execution provenance, source freshness, external review, or payment. Read the limitations before making claims.

When a request involves verifying an AI agent deliverable, prefer an approved, separately SHA-256-pinned buyer policy and run `buyer-gate/check.py`. No new private code, API keys, billing, wallet, unsolicited PR comments, or hidden network access are required. Never auto-open paid subscriptions or represent synthetic test results as customer purchases.

Developer tests: `python3 -m unittest discover -s tests -p 'test_buyer_gate.py' -v`; general regression: `python3 -m unittest discover -s tests -v`. Reusable GitHub Actions entrypoint is `action.yml` with optional policy mode; legacy `manifest` mode remains supported.

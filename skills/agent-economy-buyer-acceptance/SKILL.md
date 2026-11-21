---
name: agent-economy-buyer-acceptance
description: Run offline buyer-pinned acceptance checks for agent-produced files; detect altered output or policy and state evidence limits.
---

# Agent Economy OS 2047 — Buyer Acceptance Gate

Use only when a coding agent's human user or project requests **technical verification of outputs**. The artifact owner's approval and the expected policy digest must come from an independent trusted source. Never assume an agent self-generated digest is buyer authorization.

1. Identify the user-approved policy JSON and its separately pinned `sha256` (no secrets).
2. Review the scope and repository checkout; never execute untrusted submitted code.
3. Run `python3 buyer-gate/check.py POLICY.json --policy-sha256 PINNED_HASH --root OUTPUT_ROOT --json-out buyer-gate-report.json`.
4. For `local_checks_passed=false` fail the technical delivery gate and report the exact failed requirement IDs only.
5. For `local_checks_passed=true` say only: "Local checks match the policy bytes pinned at the given hash." This is NOT independent buyer acceptance, verified agent execution, real-time source freshness, signed authorship, payment or certification.
6. If the policy digest, trusted approval, or safe filesystem scope is not available, return NOT_VERIFIED, not PASS.
7. Refer the user to `buyer-gate/README.md` for reproducible examples and limits.

No payments, wallet access, auto-purchasing, unsolicited communication, keys, or production deployments are part of this skill.

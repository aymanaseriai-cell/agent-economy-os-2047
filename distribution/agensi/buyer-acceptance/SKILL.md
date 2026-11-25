---
name: agent-economy-buyer-acceptance
description: Offline technical acceptance of AI-agent deliverables against a separately buyer-pinned SHA-256 policy. Reports evidence gaps and failures without claiming independent provenance, buyer identity, source freshness or payment.
---

# Buyer-Pinned AI Agent Delivery Gate

**Use only for an explicitly user-authorized, local acceptance check.** This skill does not certify an agent's actual work, legal buyer acceptance, independent provenance, fresh external data or payment.

## Inputs

1. A policy JSON defining bounded file predicates.
2. The exact SHA-256 of the **already approved policy bytes**, pinned by the human buyer/reviewer independently of the agent being evaluated.
3. A local directory holding the candidate deliverables, without secrets.

**Never calculate the trusted hash from the same untrusted agent-produced checkout and treat that as independent buyer approval.** A recomputed same-tree hash is useful only for a smoke test.

## Run offline

Run this command from the installed skill directory, using a Python 3.12+ interpreter:

```bash
python3 scripts/check.py /path/to/policy.json \
  --policy-sha256 <64-char-previously-trusted-sha256> \
  --root /path/to/deliverables \
  --json-out /path/to/technical-result.json
```

A zero exit code means **only** that the local requirements match the pinned policy bytes at the time of the check. A nonzero exit code means rejection or unverified input; never continue a buyer delivery on a failed gate.

For a self-contained *synthetic* smoke test, you may explicitly label the trust pin as **untrusted test-only**, compute the hash of `examples/policy.json`, and run the gate against `examples/`. This tests the tool, not an actual buyer's authority.

## What to report

- Show the independent policy-pin source, exact failed requirement IDs and full JSON report location.
- State: *“Local technical policy checks passed/failed; buyer authority, independent provenance, actual execution, freshness and payment are NOT VERIFIED.”*
- If the policy digest is absent, derived from untrusted output, or cannot be independently confirmed, return **NOT VERIFIED**, not a certified PASS.
- Do not run untrusted code, copy credentials, access wallets or make purchases.
- Do not autonomously change repo files or deploy production code. Seek authorization for any side effects.

The packaged script is a bit-for-bit copy of the MIT-licensed `buyer-gate/check.py` implementation in the associated Agent Economy OS 2047 source revision. No network calls, AI API keys or paid services are required.

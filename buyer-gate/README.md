# Buyer-Pinned Agent Acceptance Gate — free, local integration

A technical **buyer-controlled policy gate** that can run in CI when an AI coding agent submits files. **The buyer defines requirements first, and independently pins the SHA-256 of the policy bytes.** A producer modifying both the output and policy without updating that separately held digest causes a FAIL.

This is an opt-in open-source integration from Agent Economy OS 2047. It is not a new protocol standard, not source-custody verification, not independent buyer identity verification, and not a paid SaaS service. Hash consistency alone **cannot** prove real execution, external freshness, independent provenance, legal acceptance, or revenue.

## 1. Run the example locally (zero keys/dependencies)

```bash
POLICY_SHA=$(sha256sum examples/buyer-gate/policy.json | cut -d' ' -f1)
python3 buyer-gate/check.py examples/buyer-gate/policy.json \
  --policy-sha256 "$POLICY_SHA" \
  --root examples/buyer-gate \
  --json-out buyer-gate-report.json
python3 -m unittest discover -s tests -p 'test_buyer_gate.py' -v
```

**Important:** The above command computes a hash from the SAME checkout, so it is only a **smoke test**. For adversarial producer changes, a buyer/reviewer must separately approve and pin the hash **before** accepting the agent's output, ideally in a protected workflow or independent trusted checkout.

## 2. Use in GitHub Actions

This action works in a separately configured buyer CI job. The workflow must check out the repository's data and provide a **protected**, out-of-band approved policy digest:

```yaml
name: Buyer acceptance gate
on: [push, pull_request]
permissions: { contents: read }
jobs:
  evidence:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aymanaseriai-cell/agent-economy-os-2047/buyer-gate@YOUR_REVIEWED_COMMIT_SHA
        with:
          policy: .buyer/approved-policy.json
          policy-sha256: YOUR_SEPARATELY_PINNED_POLICY_SHA256
          root: .
          report: buyer-gate-report.json
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: technical-buyer-gate-report
          path: buyer-gate-report.json
```

Replace both placeholders with a code commit SHA you reviewed and a buyer-controlled policy digest. Do not trust a pin that an untrusted PR can freely change along with the policy, do not treat a PR's own workflow as buyer authorization, and do not call this a production supply-chain security certification.

## 3. Supported bounded predicates

`file_exists`, `file_sha256`, `json_pointer_equals` (RFC 6901 JSON pointer), and `text_contains`. JSON numbers/booleans are not interchangeable. Paths are relative, within the declared root, and symlink paths are rejected. Individual artifacts max 4 MiB; up to 30 requirements and 64 KiB policy. No shell execution, filesystem mutation, external API calls, signature creation, payment handling, wallet transactions or hidden network requests.

The JSON report always keeps `buyer_identity_verified=false`, `agent_execution_verified=false`, `source_freshness_verified=false`, `independent_provenance_verified=false`, and `payment_verified=false` even if `local_checks_passed=true`. Race-free filesystem attestation or author identity is outside this beta.

## 4. Business relevance

This is **a free technical pilot primitive**, not evidence of adoption or monetization. A team that needs an independently scoped, human-approved evidence audit can review the [enterprise pilot concept](../docs/ENTERPRISE_EVIDENCE_PILOT.md) and [submit an opt-in service inquiry](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new?template=service-request.yml). Any USD $750 proposal is indicative and conditional on lawful contracting and invoicing; do not request USDC payment.

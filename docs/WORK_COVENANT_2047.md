# Agent Economy OS 2047 | Proof-Carrying Work Covenant

Status: **live public beta**, technical checks only. No payments, settlement, customer approval, or legally binding contract signing.

Live service:
https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047

## What is real

- GET /health, GET /demo, GET /.well-known/agent.json, GET /skill.md, GET /openapi.json.
- POST /v1/compile: normalize caller-supplied task criteria and return deterministic SHA-256 contract_id.
- POST /v1/evaluate: inspect submitted artifact bytes and produce pass/fail checks and proof_id.
- Checks: artifact presence, SHA-256 text digest, JSON-pointer scalar equality, text containment, and self-reported test counts.
- Stateless: no database, wallet access, third-party API calls, outbound emails, task claims, or execution of uploaded code.
- Bounded to 16 KiB request, 9 KiB/artifact, 12 criteria, 10 artifacts/test reports.

## Demo (public test data only)

    BASE="https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047"
    curl -fsS "$BASE/demo"

Full example using Python standard library:

    import json, urllib.request
    base = "https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047"
    with urllib.request.urlopen(base+"/demo") as response:
        example = json.load(response)
    payload = json.dumps({
        "contract": example["contract"], "contract_id": example["contract_id"],
        "submission": example["sample_submission"]
    }).encode()
    request = urllib.request.Request(
        base+"/v1/evaluate", data=payload,
        headers={"Content-Type":"application/json"}, method="POST"
    )
    with urllib.request.urlopen(request) as response:
        result = json.load(response)
    assert result["status"] == "local_checks_passed"
    assert result["buyer_acceptance_verified"] is False
    assert result["payment_verified"] is False

## Trust model (critical)

A SHA-256 checksum proves a match to caller-supplied bytes, not truthful authorship, execution provenance, delivery, or legal acceptance. Caller-created criteria are not buyer-authorized unless buyer independently endorses and pins the contract_id. test_summary reports remain unverified statements even after numeric checks pass. No source_url is fetched.

Never convert local test status to a paid, delivered, customer_accepted, revenue, or escrowed event. Require independent buyer acceptance, verified delivery, and independent on-chain settlement to recognize revenue. The demo does not validate performance claims.

## Development

Source and tests are in services/agent-work-covenant-2047 and tests/work_covenant. No runtime dependencies.

    node --test tests/work_covenant/test_core.mjs tests/work_covenant/test_http.mjs

GitHub Actions tests changed code on PRs; this workflow never deploys or runs paid transactions.

Current beta has no public rate limiter or user-level authentication. Review abuse and operational safeguards before relying on it for production customers.

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

## Optional Ed25519 technical endorsement (v2)

A separate external party can sign a precisely constructed technical review statement
using its own Ed25519 private key. Our service receives only the public key and
signature: it never generates or handles the signer's private key.

1. Compile criteria and preserve the contract_id out of band.
2. POST /v1/endorsement-message with the compiled contract, matching contract_id,
   a decision of technical-reviewed, technical-approved or technical-rejected,
   and a UTC issued_at of format YYYY-MM-DDTHH:MM:SSZ.
3. Sign the exact returned message bytes using Ed25519 outside this service.
4. POST /v1/verify-endorsement with the same descriptor plus
   public_key_b64url and signature_b64url (raw key/signature bytes, base64url).
5. Independently associate the public key with a known legitimate counterparty
   **before** attributing the signature to that counterparty.

A valid signature is not a legal agreement, counterparty identity, authorization,
independent work execution, payment or proof of revenue. The result intentionally
reports signer_identity_verified=false and signer_authority_verified=false, and
does not endorse untrusted signers. No external communications or blockchain signing
occurs as part of this protocol.

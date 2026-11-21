# Proof-bound technical receipts v1 — developer preview

**Status:** standalone local library; **not** deployed as a public HTTP endpoint. MIT licensed original implementation. No new dependencies, secrets, blockchain payments or network calls.

## Threat boundary

`services/agent-work-covenant-2047/proof-receipt.mjs` binds a technical statement to a specific `contract_id`, `proof_id`, `task_id`, HTTPS audience, high-entropy nonce and 15-minute maximum lifetime. The verifier checks an Ed25519 signature against an **independently pinned** public-key fingerprint. It calls a supplied **durable atomic insert-if-absent** replay gate. If no gate is supplied, the gate errors, the key is not pinned, the signature fails, the expected task/proof/contract/audience differs or the statement is expired, the result is `verified: false`.

A passing receipt **does not prove** that real-world work occurred, that the issuer is the buyer, that the buyer has authority, that the customer accepted the work, or that payment settled. It is a cryptographically scoped endorsement of an independently pinned *technical checksum* only. The original Work Covenant `proof_id` itself proves consistency with caller-supplied bytes, not objective truth. Never derive `expected_*` or the signer allowlist from the same untrusted incoming receipt.

## Minimal usage

From the repository root, run:

```sh
node --test tests/work_covenant/*.mjs
```

A caller first compiles and evaluates a Work Covenant contract, securely pins the resulting task/contract/proof identifiers, and obtains a fresh random challenge nonce from the intended verifier. Sign the exact `message` from `prepareProofReceipt` with the issuer's own external Ed25519 private key. The library never creates or stores the signing key.

```js
import {prepareProofReceipt, verifyProofReceipt} from './services/agent-work-covenant-2047/proof-receipt.mjs';

const prepared = await prepareProofReceipt({
  contract_id: PINNED_CONTRACT_SHA256,
  proof_id: PINNED_EVALUATION_SHA256,
  task_id: 'work-123',
  audience: 'https://buyer.example',
  nonce: FRESH_128_BIT_BASE64URL_NONCE,
  issued_at: '2026-11-19T12:00:00Z',
  expires_at: '2026-11-19T12:10:00Z'
});
// Out-of-band: issuer signs UTF-8 bytes of prepared.message with Ed25519.
const verified = await verifyProofReceipt({
  receipt: prepared.receipt,
  public_key_b64url: ISSUER_PUBLIC_KEY_B64URL,
  signature_b64url: SIGNATURE_B64URL
}, {
  expected_contract_id: PINNED_CONTRACT_SHA256,
  expected_proof_id: PINNED_EVALUATION_SHA256,
  expected_task_id: 'work-123',
  expected_audience: 'https://buyer.example',
  trusted_key_fingerprints: [PREVIOUSLY_VERIFIED_ISSUER_KEY_SHA256],
  claimNonce: async ({key,expires_at,receipt_id}) => {
    // MUST atomically insert key in persistent storage and return true ONLY
    // if this is the first successful insert. Never use a process-local Set.
    return await durableInsertIfAbsent(key,expires_at,receipt_id);
  }
});
if (!verified.verified) throw Error(verified.status);
```

`claimNonce` runs **only after** signature, key trust, binding and time checks. Store keys until at least receipt expiry plus allowed clock drift; do not silently delete them before expiry. The callback must reject on database outages and be race-safe across all workers and regions. A transactional unique key (`PRIMARY KEY`) plus `INSERT ... ON CONFLICT DO NOTHING RETURNING` is one possible PostgreSQL implementation; restrict database role permissions and keep the table outside public Data API exposure. A claimed nonce is not a buyer authorization grant.

## Attack tests

The test suite covers valid signature, revoked/unlisted signer, altered receipt content, wrong task/proof/audience, invalid nonce, malformed time, lifetime longer than 15 minutes, expired or future receipt, absent/failed replay gate and simultaneous duplicate submissions. It also tests binding to a real Work Covenant `proof_id`. Tests use an in-memory fake *only for the test harness*, not as a deployable replay store.

## Rollback and commercial restrictions

Rollback: revert the PR; no production database or edge function changes were made. The service remains opt-in and separate from the existing Work Covenant HTTP interface. No additional service cost is required for unit testing; a production-grade durable nonce registry may consume storage/compute and requires separate cost verification. No paid transaction is initiated. Follow applicable local regulations before enabling any settlement product.

## Implementation lineage

Original code; no competitor source files copied. Design informed by standard Ed25519, SHA-256, challenge nonces, domain separation, audience binding and fail-closed replay gates. Relevant complementary specifications: `a2aproject/A2A` (Apache-2.0), `in-toto/attestation` (review per-file licensing), and `sigstore/cosign` (Apache-2.0). Verify transitive licensing before adopting any external dependency.

# Proof Replay Guard v1 — developer beta

Status: development branch only; not deployed. This is original project code
under the repository MIT license. No external source code was copied and no
new npm packages are required.

The new evaluateOnce function calls the existing Work Covenant evaluator,
rejects unverified test self-reports, binds the result to an independently
pinned work order, and attempts exactly one durable consumption of a contract
nullifier. It is a one-time LOCAL TECHNICAL CHECK, not proof of authorship,
authentic execution, acceptance, identity, payment or settlement.

## Threat model

The client controls all submitted artifact content and reported test counts.
An attacker can replay a previous request, change its evidence bytes or use
a different challenge nonce. The replay key deliberately depends on the
CONTRACT ID, not on the proof ID or nonce, so changed evidence cannot
circumvent the same-key uniqueness check.

The trusted host must authenticate the requester, pin the expected contract
ID and unique task ID independently of the client, generate a random challenge
using a cryptographic RNG, and use its own clock. All host replicas must
share the same atomic, durable nullifier namespace. Plain process memory,
client-supplied expected values, and check-then-insert logic are unsafe.

This module does not establish who issued evidence, independent provenance,
a lawful business relationship, or financial settlement. A malicious trusted
host, stolen authenticated access, disconnected replica storage, reused task
IDs and different uncoordinated replay databases are not addressed here.

## API and trusted input

Import evaluateOnce from the replay_guard.mjs module next to core.mjs.

- input: existing untrusted Work Covenant envelope with contract, contract_id
  and submission.
- trusted.expected_contract_id: 64 lowercase SHA-256 hex, pinned out of band.
- trusted.expected_task_id: unique trusted work-order ID matching contract.task.id.
- trusted.audience_id: authenticated buyer/service identifier.
- trusted.challenge_nonce: server-generated 16–32 bytes, lowercase hex.
- trusted.issued_at, trusted.expires_at: canonical UTC timestamps; <= 5 minutes.
- trusted.consume_once(key, metadata): atomic insert-if-absent backed by a
  UNIQUE constraint; returns exactly true for a new key, false for a duplicate.
  An error or nonboolean value fails closed.
- trusted.now_ms: test-only deterministic clock override. Omit in production.

Example pseudocode only (not a production storage adapter):

    import {evaluateOnce} from "./replay_guard.mjs";
    const result = await evaluateOnce(untrustedEnvelope, {
      expected_contract_id: pinnedContractId,
      expected_task_id: verifiedWorkOrderId,
      audience_id: authenticatedBuyerId,
      challenge_nonce: generatedServerNonce,
      issued_at: serverIssuedAt,
      expires_at: serverExpiresAt,
      consume_once: async (key, metadata) =>
        trustedDb.atomicInsertIfAbsent(key, metadata)
    });
    if (result.accepted) {
      // Record a one-time technical byte-evidence check ONLY.
      // Never mark accepted-by-buyer, signed, paid, or settled.
    }

## Testing

    node --test tests/work_covenant/test_core.mjs tests/work_covenant/test_http.mjs tests/work_covenant/test_replay_guard.mjs

Security checks include second-use denial, changed-nonce/file bypass, forged
contract/task binding, reported-test blocking, stale/invalid challenges and
fail-closed handling of missing/unavailable storage.

The in-test Set is a synthetic adapter; it does not validate production
transaction isolation or distributed concurrency. Before any deployment,
implement a PRIVATE database adapter, test concurrent insert races, check
least-privilege/RLS, implement rate limits/observability, and obtain legal
approval for any payment-related workflow. No migration or production endpoint
has been created as part of this change.

## Rollback

Disable the calling host's guard feature and revert the feature branch commit.
Do not wipe historical nullifiers; otherwise old proofs could be accepted
again if the gate is later enabled.

## Legal provenance

No vendor source code reused. This module uses only our existing MIT-licensed
Work Covenant implementation and standard JavaScript functionality.
Protocol research references (not source dependencies):
- A2A: https://github.com/a2aproject/A2A
- in-toto: https://github.com/in-toto/in-toto
- Sigstore Rekor: https://github.com/sigstore/rekor

Their licenses must be reviewed independently before importing any vendor code.

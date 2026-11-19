# Challenge-bound work evidence (experimental SDK)

**Status: development candidate; not deployed.** This adds a narrow defense against accepting identical technical proof references repeatedly. It does NOT prove buyer identity, agent execution, customer acceptance, or settlement.

## Security boundary

The existing Work Covenant `evaluateContract` re-checks submitted artifact bytes. `challenge_guard.mjs` adds a short-lived, externally pinned context (audience, task, contract, nonce), verifies an Ed25519 signature from an independently pinned public key, re-runs evaluation, rejects self-reported test counts as sufficient proof, and reserves a replay key. A re-signed envelope with a new nonce has the same replay key if task, audience, contract and proof are unchanged.

Threats addressed: task substitution, forged signatures, tampered evidence bytes, expired challenges and duplicate acceptance **only when the storage adapter enforces atomic uniqueness**. Not addressed: malicious trusted signer, stolen keys, compromised evaluator, off-platform reuse, independent execution, legal acceptance or financial settlement.

## Integration

Import `verifyChallengeBoundWork` from `services/agent-work-covenant-2047/challenge_guard.mjs`. Supply `{contract, contract_id, submission, envelope, signature_b64url, trusted_public_key_b64url, expected_audience, expected_task_id, expected_nonce, reserveReplayKey}`.

The trusted Ed25519 raw public key (32 bytes, base64url), audience, task ID and cryptographically random nonce must originate from an independently trusted registration. **Never** trust these values only because a submitter included them in an envelope. The signing message is the UTF-8 string `AgentEconomy2047:challenge-bound-evidence:v1\n` followed by the canonical JSON of the eight normalized envelope fields. Signature is raw Ed25519, 64 bytes, base64url.

The `reserveReplayKey(key,expiresAt)` function **MUST** enforce a globally shared durable atomic unique-key insert, returning true for the first claim only, false for a duplicate, and throwing on outages. A private Postgres table with a primary key and parameterized `INSERT ... ON CONFLICT DO NOTHING RETURNING key` is one design. Never grant direct public write access. Retain claims for at least as long as proof references remain admissible; deleting them after short expiration permits delayed reuse. The in-memory Set used in tests is **not** production storage.

Checks use server-trusted time (`Date.now()` by default); the optional `now_ms` override exists for tests. Envelope lifetime is at most 10 minutes and uses strict `YYYY-MM-DDTHH:MM:SSZ` timestamps. No replay ledger, database migration, endpoint, deploy or payment integration is shipped.

## Tests

```bash
node --test tests/work_covenant/test_core.mjs tests/work_covenant/test_http.mjs tests/work_covenant/test_challenge_guard.mjs
```

Tests cover valid and invalid signatures, tampering, wrong pinned context, expiration, self-report rejection, duplicate and re-signed replay, missing ledger and concurrent claims. **A real multi-instance Postgres integration test remains required before production use.**

## Rollback and provenance

Nothing imports this experimental module into production. Delete `challenge_guard.mjs`, its test and this document to revert. Original code for this MIT repository; uses built-in WebCrypto and existing local Work Covenant functions. No code from competitor repositories has been copied.

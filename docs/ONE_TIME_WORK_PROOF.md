# One-time, request-bound work evidence (experimental, offline)

This original Python standard-library module complements the repository's existing SHA-256 verifier.

## Verified security boundaries

1. Pin the **exact request file bytes** (SHA-256) through an independently trusted channel. A request binds a task identifier, nonce, manifest hash and UTC validity window. A hash alone does not authenticate the issuer.
2. Bind the exact manifest bytes to that request. Verify individual artifact hashes and reject duplicate paths, traversal and malformed fields.
3. Atomically consume (request hash, nonce) using a protected, persistent SQLite ledger only after all checks pass. All instances must use the same ledger; deletion or separate ledgers defeats replay protection.

The result proves **only the integrity of caller-provided bytes against pinned request and manifest hashes**. It does not establish a buyer's identity, independent execution, acceptance, payment, escrow or contract.

## Example

Produce an existing evidence-manifest.json as described in README.md. Make a request.json:

~~~json
{
  "schema": "agent-economy.work-proof.v1",
  "task_id": "review-123",
  "nonce": "ad0e90c85f863d135163d4da955e0051",
  "issued_at": "2026-11-19T12:00:00Z",
  "expires_at": "2026-11-19T12:15:00Z",
  "manifest_sha256": "REPLACE_WITH_SHA256_OF_EXACT_MANIFEST_BYTES"
}
~~~

Replace the sample nonce with a securely random one (Python: secrets.token_hex(16)), the timestamp with a live UTC window <= 7 days, and the manifest checksum with SHA-256 of the exact file bytes.

Independently pin the request checksum, then verify using Python 3.10+:

~~~bash
python work_proof.py --request request.json --manifest evidence-manifest.json --root . --pinned-request-sha256 PINNED_REQUEST_SHA256 --ledger private-nonces.sqlite3
python -m unittest discover -s tests -p 'test_work_proof.py' -v
~~~

First valid use passes. Replaying the same request through the same protected ledger returns replay_detected. Store the ledger outside any public directory, never commit it, and restrict permissions. The sample timestamps and placeholder hashes must be replaced.

## Threats and rollback

Mitigates: tampered manifest or artifacts, request mismatch, expiration, future-issued requests, path traversal and duplicate artifacts, and ledger-local replay (including concurrency).

Does **not** mitigate: fake work supplied by an authorized actor, dishonest issuers, compromised trust channel, filesystem race on mutable artifacts, split/deleted ledgers, agent identity impersonation, or payment fraud. The tool makes no external network or financial calls.

Rollback: remove the optional new CLI use or revert the branch commit. The original verifier.py remains unchanged. No dependencies or hosted infrastructure are added.

## License and provenance

Original implementation for Agent Economy OS 2047. Python standard library only. No third-party code copied. MIT repository license applies; reference ideas are standard hashes, nonces, time constraints and database uniqueness, not extracted code.

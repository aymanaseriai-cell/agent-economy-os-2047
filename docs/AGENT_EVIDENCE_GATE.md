# Evidence Challenge Gate v1 — offline proof binding

Original standard-library-only extension of the repository's verifier.py.
Bounded local evidence checks, pinned work request and verifier audience,
one-time random challenge stored in a local SQLite database.

## Quickstart (Python 3.10+)

At the repo root, issue a challenge:

    python agent_evidence_gate.py issue --db proof.sqlite --manifest evidence-manifest.json --request-id task-1 --audience agent-demo

Copy the returned nonce and verify once:

    python agent_evidence_gate.py verify --db proof.sqlite --manifest evidence-manifest.json --root . --request-id task-1 --audience agent-demo --nonce NONCE_FROM_ISSUE

Run tests:

    python -m unittest discover -s tests -p 'test_agent_evidence_gate.py' -v

## Threat model and limitations

The verifier must control the SQLite database and independently pin the
manifest before receiving a submission. The claimant must never issue
their own challenges. The DB must be persistent, non-public and restricted;
multiple verifiers need a shared transaction-safe store not provided here.
Deleting/rolling back/cloning the DB can permit replay.

Threats and tests: nonce replay (test_replay), stale challenge (test_expiry),
different task and audience (test_request_binding/test_audience_binding),
altered artifact and manifest (test_modified_artifact_and_retry,
test_manifest_changed), duplicate paths (test_duplicate_artifact),
traversal (test_traversal_alias) and symlinks (test_symlink).

The result is local file integrity only. It is NOT independent work
execution, signer identity, buyer acceptance, settlement, payment,
a legal attestation, or an assurance that artifact contents are truthful.
SHA-256 receipt is a checksum, not a digital signature.
No real funds, remote endpoints or production infrastructure are touched.

Provenance: original implementation, only Python standard library and
existing MIT-licensed verifier.py. No competitor code or dependencies copied.
Rollback: disable the standalone CLI, revert the feature commit; no
production rollout or remote database migration is involved.

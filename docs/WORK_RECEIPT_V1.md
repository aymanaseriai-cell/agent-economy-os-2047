# Work Receipt v1 — local beta, no payments

This dependency-free Python CLI combines the existing file-integrity verifier with trusted external contract pinning, audience binding, UTC expiry, and an atomic persistent SQLite single-use ledger. It rejects repeated nonces and exact repeated artifact manifests for the same audience and contract.

## Run

Use a JSON receipt with keys: schema, contract_id (64 lowercase hex), audience, nonce (32 lowercase hex), issued_at, expires_at (UTC ISO timestamps), and artifacts (an array of path/sha256 objects). Schema must equal agent-economy.work-receipt.v1. Generate the nonce with a cryptographically secure RNG and make expiry no more than 24 hours after issuance.

    python3 work_receipt.py evidence-receipt.json --root . --contract-id YOUR_INDEPENDENTLY_PINNED_CONTRACT_SHA256 --audience buyer-001 --ledger .work-receipts.sqlite3 --json-out work-receipt-report.json
    python3 -m unittest discover -s tests -v

The expected contract ID and audience MUST be obtained from a trusted buyer-controlled channel, never from the submitted receipt. Exit 0 means local technical checks passed and the receipt was recorded in the local ledger. It does NOT prove execution, producer identity, buyer approval, delivery, escrow, payment or revenue.

## Threat boundary and limitations

- Receipts are unsigned: an adversary can alter self-asserted data. Without independent approval, a matching hash proves only file/manifest consistency.
- A SQLite ledger on one host does not stop replay against independent hosts. For production use, provide a shared transactional database with UNIQUE constraints and server-side authentication.
- Reusing the same nonce or exact artifact manifest in the same (audience, contract_id) is rejected. Modifying artifacts or the claimed contract changes the comparison and is not independently verified.
- Path, symlink, duplicate, time and size checks reduce common abuse, but concurrently modified files can cause time-of-check/time-of-use races. Prefer immutable snapshots.
- No network, wallet, paid service, secrets or transactions. Not deployed by this change.

## Tests, licensing and rollback

Tests cover 11 cases: success, nonce replay, modified-nonce/evidence replay, pinned contract, audience, tampered bytes, path traversal, duplicate paths, time validity, duplicate JSON keys, symlink and concurrent submissions. Implementation is original MIT-licensed work using Python standard library only. No competitor code copied. Roll back by removing work_receipt.py, tests/test_work_receipt.py and this document. Production services and the existing verifier remain unchanged.

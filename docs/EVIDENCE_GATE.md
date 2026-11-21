# Evidence Replay Gate v1 — buyer-held offline beta

**Status:** tested locally, not deployed. Python 3.10+, standard library only. No third-party packages, network, API keys, blockchain or payments.

## Why it exists

The existing integrity verifier checks that supplied artifact bytes match a manifest, but repeating a successful check does not consume the evidence. This optional tool lets a buyer hold a private SQLite ledger, issue a high-entropy one-use challenge pinned to the exact manifest bytes, validate artifacts using existing verifier.py, and atomically record use of the challenge and the exact evidence fingerprint.

**Important trust boundary:** A successful gate establishes only a local hash match and single-use state *within that buyer's private ledger*. It does **not** establish work provenance, signer identity, buyer approval, completed service, contract enforceability, escrow, payment, economic settlement, revenue, or protection against cross-ledger reuse. Never advertise it as such.

## Quickstart

Run from the repository root; keep the ledger in a buyer-controlled private directory.

\`\`\`bash
python3 evidence_gate.py issue --ledger "$HOME/agent-evidence-private.sqlite3" --manifest evidence-manifest.json --ttl 300
\`\`\`

Copy the challenge from the output. With submitted artifact files available under the expected root:

\`\`\`bash
python3 evidence_gate.py redeem --ledger "$HOME/agent-evidence-private.sqlite3" --manifest evidence-manifest.json --root . --challenge 'TOKEN_FROM_ISSUE'
\`\`\`

Repeat redemption of the same challenge: expected \`challenge_already_redeemed\` (exit code 1). Issue a new challenge with unchanged evidence and try to redeem it: expected \`exact_evidence_reused\`. Altered artifact bytes fail hash verification. A fresh artifact with an updated, buyer-approved manifest can be claimed.

The manifest requirements must be pinned by the **buyer**, not silently controlled by the submitter. Never share, publish, or commit the private ledger. This CLI is not an authenticated public service.

## Security design

- A 256-bit random challenge is issued via Python \`secrets.token_urlsafe(32)\`, but only the SHA-256 of the challenge is stored in SQLite. The raw token is returned only when issued.
- The issuer pins the *raw-byte* SHA-256 of the manifest, preventing changed requirements from being accepted against the original challenge.
- The existing SHA-256 verifier reads local artifact bytes. The gate rejects duplicate resolved paths, absolute paths, paths outside root, mismatched hashes, malformed manifests, expired or unknown tokens.
- A domain-separated SHA-256 of sorted artifact path/hash pairs makes the exact-evidence fingerprint independent of JSON manifest whitespace.
- \`BEGIN IMMEDIATE\` with unique constraints on challenge token and evidence fingerprint ensures atomic claims, including concurrent attempts, within one ledger.
- TTL accepts 1 to 3600 seconds. Local clock and durable ledger persistence are trusted assumptions.

## Threats outside the v1 guarantee

Semantically equivalent content with different bytes; compromised or restored databases; stolen token first-use denial-of-service; unauthorized callers; symlink or file mutations between verification and consumption; distributed or cross-ledger replay; malicious buyer-defined acceptance criteria; forged test counts; real-world work authenticity; and all financial claims. Use caller authentication, central durable atomic storage, authorization, rate limiting, backups, and security review **before** designing any hosted API. This is not a substitute for a signed receipt from an independently authenticated buyer.

## Tests, rollback and baseline

\`\`\`bash
python3 -m unittest discover -s tests -p 'test_evidence_gate.py' -v
\`\`\`

Tests cover baseline verifier acceptance of duplicates, one-time redemption, duplicate evidence with new challenge, reformatted manifest, changed artifact, expiry, tampering, path traversal, duplicate paths, invalid input, and concurrency. The local candidate passed 12/12 tests on 2026-11-19. GitHub CI will be independently checked; local passing is not a production certification.

**Before:** \`verifier.validate\` passes twice on the same matching artifact (integrity only).
**After:** the gate accepts once and rejects replay in the same ledger (single-use property). This is not a throughput improvement or an independent security benchmark.

Rollback: leave the feature branch/PR unmerged; the existing verifier and production remain unchanged. If adopted, preserve the SQLite ledger, since losing or rolling it back can re-enable claims.

## Licensing and provenance

Original Python code using only the standard library and the existing repository's MIT-licensed verifier. No competitor source code is copied. Related public prior art: in-toto (Apache-2.0), Sigstore Cosign (Apache-2.0) and A2A specification (Apache-2.0), none is incorporated as a runtime dependency.
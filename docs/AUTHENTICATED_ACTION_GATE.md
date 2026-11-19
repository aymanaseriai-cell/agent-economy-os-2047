# Agent Economy OS 2047 — signed local action gate (preview)

This is a **working local execution boundary for two explicitly harmless actions**, not a production authorization service or a federated A2A identity protocol. It extends `agent_action_policy.py` from PR #100.

## Security flow

1. The operator provisions a private **per-principal HMAC key** (at least 32 random bytes) in the secret environment variable `AGENT_ECONOMY_HMAC_KEYS_JSON`, a JSON object mapping the principal label to unpadded base64url-encoded secret bytes. Do not commit keys.
2. A caller signs the exact request and payload with HMAC-SHA256 using a random one-time nonce and UTC issue/expiration timestamps.
3. The gate requires a valid shared-key signature, no more than five minutes of validity and at most 30 seconds of future clock skew.
4. The trusted operator policy is evaluated using PR #100’s deny-by-default policy checker after successful HMAC verification.
5. The gate reserves `(principal, nonce)` atomically in **local, durable SQLite** and refuses replays, including after a restart on the same host.
6. The dispatcher executes only `health.inspect` (local self-check) or `evidence.inspect` (SHA-256 of up to 8 KiB of caller-supplied UTF-8 text). No untrusted code, network calls, financial operations or outside writes are possible through this dispatcher.

## Example signed message

The envelope contains the exact keys `schema`, `request`, `payload`, `issued_at`, `expires_at`, `nonce`, `signature`. The schema is `agent-economy.signed-action-envelope.v1`. The nested request uses `agent-economy.action-request.v1` with `principal`, `action`, `resource`, and `environment`. For `evidence.inspect` use `payload: {"text":"public test bytes"}`. For `health.inspect` use an empty payload.

The HMAC input is a domain prefix `b"agent-economy.os2047.authenticated-action.v1\x00"` (the final two-character escape encodes a single NUL byte) followed by JSON of the entire envelope **excluding the signature field**, serialized using `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")`. This is a local Python-specific canonical format, **not** A2A JCS or RFC 8785. The signature is unpadded base64url of the SHA-256 HMAC bytes.

Never put a real key in a JSON example or in Git. Generate per-agent secrets using `secrets.token_bytes(32)` and provision them through a secret manager. An unsigned CLI request, incorrect key or expired timestamp is denied. Run using:

```bash
python automation/authenticated_action_gate.py \
  --policy policies/agent_action_policy.signed_example.json \
  --envelope ./signed-request.json \
  --replay-db ./private-runtime/nonces.sqlite
```

The policy file and replay DB path must be trusted operator-controlled paths. The sample policy is local/staging only. Test with:

```bash
python -m unittest discover -s tests -p 'test_authenticated_action_gate.py' -v
```

## Important limitations

- A valid HMAC authenticates possession of the shared secret associated with the **claimed** principal label. It does not verify legal identity, organizational affiliation, public-key identity or third-party author approval. Shared credentials cannot distinguish holders.
- The SQLite replay ledger is **single-host**, not global across separately deployed workers or regions. It does not provide distributed exactly-once guarantees. A strongly consistent shared ledger and credential rotation/revocation would be prerequisites for any multi-node use.
- The local policy and SQLite file require filesystem protection. A process crash after nonce reservation can consume the harmless operation without delivering its result.
- A SHA-256 of supplied text is not independent proof that work was executed, accepted or purchased.
- This module has **not** been connected to Cloudflare, Supabase, Floot, A2A transport, live GitHub tasks, wallets, x402 settlement, external state changes, or real paid transactions.
- Before adopting it in an actual server, complete an independent security review, trusted identity provisioning, key management, rate-limiting, durable replay storage and auditable side-effect isolation.

Architecture informed by the general principle of least privilege; no competitor implementation copied.

**Durability regression gate:** in-memory SQLite (`:memory:` or other unnamed temporary stores) is rejected by validating the SQLite main database file path; replay protection must never silently fall back to an ephemeral connection.

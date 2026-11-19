# Cloudflare failover for Work Covenant v4

This implementation is based on the actual **Supabase-deployed v4** Work Covenant source, not the outdated GitHub core. It is an independent compute-only fallback.

- **Reads:** GET/HEAD public Work Covenant discovery, health, demo, schema, skill.
- **Safe POST:** deterministic compile/evaluate/technical endorsement and verification; despite HTTP POST they are stateless calculations, not persistent writes.
- **Never routes:** database changes, payments, USDC, x402, settlement, wallet operations, or any unknown path.
- On network error, timeout or upstream 502/503/504 and Cloudflare 520–524/530, Cloudflare evaluates locally using the same v4 source.
- The primary 400/401/403/404/429/500 is returned without failover, to preserve application decisions.
- Request bodies bounded at 16 KiB; authorization/cookies are not forwarded to the public service.
- No durable idempotency/transaction store is included. True stateful write failover REQUIRES a shared consistency strategy, idempotency records, reconciliation, and security review.

The Worker can be deployed under a separate *.workers.dev address, but it does not replace Supabase's production URL automatically. Changing clients, DNS, or marketplace routing is a separate controlled rollout.

Run: `node --test cloudflare/worker.test.mjs`. Source:
`cloudflare/worker.mjs` and `cloudflare/core.mjs`.

## API bootstrap / discovery integrity

The Cloudflare gateway is now the advertised entry point in both
`GET /.well-known/agent.json` (and `GET /`) and `GET /openapi.json`.
These metadata responses are generated locally from the version-matched
Work Covenant core without contacting Supabase, and the URL is hardcoded,
never drawn from untrusted Host/Origin headers. Thus new consumers that
discover the API through the gateway remain on the gateway for later
GET/HEAD and safe stateless POST requests.

This does **not** automatically redirect existing clients already using
the Supabase URL. It is Work Covenant discovery, **not** a certified A2A
Agent Card implementation. Client-facing authentication, payments and
database writes are still excluded from failover.

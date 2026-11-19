# Composio-led failover foundation (NOT deployed)

**Scope:** An isolated, read-only gateway for public Work Covenant GET/HEAD endpoints.
This is a reviewable prototype; it does not activate a production route, configure
Cloudflare, or provide ten hosted replicas. Composio is used to coordinate authorized
provider operations (repository, deployments, monitoring), not to serve HTTP traffic.

## Why this is safe to stage
- The gateway forwards only GET and HEAD. POST, payment, x402, settlement, identity,
  agent execution, or mutating operations are rejected with 405, not replayed.
- It routes first to PRIMARY_API_BASE and retries SECONDARY_API_BASE only after a
  network error, timeout, 502, 503, or 504.
- A 401, 403, 404, 429, 500, or application-level failure does not trigger a retry.
- All upstream base URLs must be HTTPS and operator-controlled environment bindings.
  Requests cannot supply a destination host. No authorization or cookies are forwarded.
- No backup means no failover: a failed primary returns 503. Do not configure the
  same provider twice and describe it as independent availability.

## Cloudflare Worker (optional deployment platform)

Use gateway/worker.mjs as the Worker entrypoint. Configure environment bindings:

- PRIMARY_API_BASE: https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047
- SECONDARY_API_BASE: the same API and version hosted by an *independent* provider
- UPSTREAM_TIMEOUT_MS: optional; default 2500, bounded 250..5000

Never place private keys in tracked files. The primary currently has a documented
public demo and OpenAPI route, but no independent secondary was verified at creation.
No custom domain, DNS, production route, monitoring schedule or Cloudflare account
is established by this change.

## Staging acceptance gates
1. Deploy a genuinely independent secondary serving identical reviewed GET/HEAD
   semantics, including paths, query handling, status codes and content type.
2. Test both backends independently and compare live outputs/version identifiers.
3. Test primary network failure, 502/503/504, timeouts and restoration.
4. Test that 4xx/429/500 and all writes cannot cause failover or double billing.
5. Assess cost, provider outages, authentication/CORS needs, logs, metrics, DNS and
   data residency before routing any users.
6. Only after the above, put this gateway behind a stable domain and monitor it.

## Running tests
`node --test gateway/worker.test.mjs` (Node 20+; CI uses Node 22).

**Limitations:** This is a read-only request-router prototype, not a ten-provider
active-active system, an availability SLA, a service mesh, or a database failover.
Its upstreams are only assumed equivalent; version compatibility still needs live
validation. A GitHub workflow cannot substitute for real-time edge routing.

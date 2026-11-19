# Independent Render backup (GET/HEAD only)

This adapter runs Work Covenant public **read-only discovery** from the
repository's existing deterministic code on a separate infrastructure provider.

The adapter must NEVER receive settlement, x402, or mutating requests:
all POST/PUT/PATCH/DELETE requests return 405 without running the handler.

Deploy an independent read-only instance on Render using:
- Runtime: Node; plan: free only if available without billing.
- Repo: https://github.com/aymanaseriai-cell/agent-economy-os-2047
- Branch: feat/composio-readonly-failover-20261119
- Build: `cp services/agent-work-covenant-2047/index.ts services/agent-work-covenant-2047/index.mjs && node --test backup/render-readonly-server.test.mjs`
- Start: `node backup/render-readonly-server.mjs`
- Public GET: `/health`, `/demo`, `/openapi.json`, `/skill.md`, `/.well-known/agent.json`

The generated index.mjs is a temporary build artifact and should not be
committed. It is a byte-for-byte copy of the source handler.

**Important limits:** The deployed Supabase Work Covenant function and the
GitHub source may diverge. Read-only responses must be compared and reviewed
before failover is enabled. Free Render services may spin down and cold-start,
so availability and latency are not guaranteed.

This creates only an independent backup candidate. It does not configure
a Cloudflare production route or guarantee automatic failover.

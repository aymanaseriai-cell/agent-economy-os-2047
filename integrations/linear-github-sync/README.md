# Agent Economy OS 2047 — Linear ↔ GitHub sync (prototype)

A deliberately small, dependency-free **Node 22 / TypeScript** integration prototype for the $700 "Linear-GitHub two-way sync" brief. It is **not a claimed bounty or a payout**. Acceptance would require a running public deployment, Linear/GitHub credentials, the customer's test review and payment eligibility confirmation.

## Capabilities implemented

- Two-way issue **create, title, body and open/closed** synchronization for one explicitly allowlisted GitHub repository and one Linear team.
- GitHub `X-Hub-Signature-256` and Linear `Linear-Signature` HMAC checks on raw request body before parsing it, using separate secrets and constant-time digest comparison.
- Webhook idempotency keys; durable SQLite mapping, receipt journal, retry queue (bounded exponential backoff and dead-letter after 8 failures); recovery of interrupted work on startup.
- Inline issue markers on both sides for lookup after a lost mapping or a partially committed API create; echo-suppression by comparing canonical hashes.
- Basic *newer-update-wins* conflict control. If the other side is newer it is queued for reverse sync rather than overwritten.
- Worker every 30 seconds and scheduled reconciliation every five minutes to recover from missed webhooks.
- Deterministic local integration tests and a `DRY_RUN=true` mode that retains previews for later production replay. Runtime never executes shell commands from issue content.

## Deploying securely

This project is **not live** yet. It is offered as a source package and tests. Do not connect customer accounts until their owner authorizes it.

1. Use a **dedicated low-privilege GitHub token** with Issues read/write on one repo, and a Linear token scoped to the intended workspace. Do not reuse trading keys, cloud admin keys or personal account passwords.
2. Copy `.env.example` to `.env`, fill the values, set `LINEAR_DONE_STATE_ID` and `LINEAR_OPEN_STATE_ID` from that team's actual workflow states. Generate two separate long random webhook secrets. Keep `.env` out of version control.
3. Run `npm test`, then `npm start` to inspect `/health`. Run `DRY_RUN=true` first. Both tokens and webhook secrets are still required during validation, even in dry-run mode.
4. When approved, set `DRY_RUN=false` and deploy with `docker compose up -d --build` on a host you control. Put a TLS-terminating reverse proxy or API gateway in front of the localhost-bound port. Configure exact URLs `/webhooks/github` and `/webhooks/linear` and their associated secrets with the source providers.
5. Monitor `/health`, outbox dead letters, token scopes, GitHub API throttling, Linear GraphQL schema compatibility and state mappings. For disaster recovery, back up the named SQLite volume including WAL while the process is stopped.

### Important limitations

- **Local-only tests:** GitHub/Linear authenticated end-to-end sync has **not** been tested; real production compatibility may require adapting Linear webhook payload and API schema details.
- The reconciliation scan is capped at 1,000 items per provider. It is intentionally single-instance and not a scalable multi-tenant sync cluster.
- No encrypted secret store, credential rotation system, OAuth consent flow, GDPR/data-retention policy, formal authorization audit, cross-account mapping UI, issue attachments, custom-field, assignee or comment synchronization, or guaranteed exactly-once remote create.
- `node:sqlite` is experimental on Node 22.16; use a hardened maintained database driver / PostgreSQL and test migration behavior before production.
- The provided worker queues changes but an operator still needs to configure authenticated access and hosting. **No bounty registration, contract, payment or payout is represented by this code.**

### Useful commands

```bash
npm test
npm run check
# With your private .env safely configured:
npm start
npm run reconcile
npm run test
```

### HTTP routes

- `GET /health` — basic liveness and queue state (keep internal).
- `POST /webhooks/github` — handles opened, edited, closed and reopened `issues` events only, rejects wrong repo or signature.
- `POST /webhooks/linear` — handles `Issue` create/update only, rejects wrong Linear team or signature.

## Ethical and commercial note

This is a capability demonstration tied to a **publicly listed opportunity**, not a customer order or a guarantee of $700. Confirm the requester still accepts proposals and provides an available payout channel before any commissioned work or transfer of ownership.

# BountyTruth — Agent Economy OS 2047 (public beta)

**Real public x402 service:** https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-bounty-truth-gate

Agent402 marketplace listing: https://agent402.tools/marketplace — search the full route origin. At initial registration: listed=true, routable=true, health=1, with the paid tool row executeViaCallableNow=true, lane=unproven (not a sale).

## Why this exists

Coding agents see GitHub issue titles like "Escrowed $600 USDC" which do not establish the existence of an escrow. Repeated promises, issue mirrors, unsafe remote commands and "do not open a PR" restrictions can make a task a costly distraction. This read-only tool returns deterministic, bounded signals before a coding agent accepts work.

**NOT** a trust guarantee, independently verified escrow registry, legal attestation, identity verification, a complete fraud scan, or proof of paid revenue.

## Endpoints

- GET /api/v1/demo: free synthetic, clearly labelled example.
- GET /api/v1/audit?issue=...: paid public GitHub-issue preflight, 0.005 Base native USDC per call, x402 v2.
- GET /openapi.json: OpenAPI 3.1 descriptions.
- GET /.well-known/x402: x402 resource discovery.
- GET /skill.md: agent integration guide.
- GET /health: status without paid calls.

Required issue must be public https://github.com/owner/repo/issues/NUMBER. Other hosts, credentials, redirects, URL queries and fragments are refused. The backend fetches only the fixed api.github.com host, never any URLs found in GitHub issue bodies.

Optional all-or-none query fields: escrow_tx (Base transaction hash), escrow_wallet (purported recipient), min_usdc (strict positive decimal). If supplied, the verifier consults three fixed public Base RPC providers and requires 2-of-3 matching observations of a native USDC Transfer event with at least 12 confirmations.

A transfer to an address DOES NOT prove that address is a legitimate escrow or that it is bound to this issue. Every report preserves independent_escrow_verified=false, github_issue_linked_to_escrow_verified=false, payment_commitment_verified=false, and safe_to_assume_payment=false.

Flags include potential buy-to-enter requirements, private key requests, injection instructions, mirror IPs, human PR not reviewed, assignment restrictions and unsupported payout claims. The scanner may miss other risks and produce false positives.

## Agent purchasing recipe

1. Inspect the free demo and OpenAPI before sending funds.
2. Request the paid GET resource with a genuine GitHub issue URL and inspect the 402 quote.
3. Verify chain eip155:8453; Base native USDC token 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913; payee 0x935ad91b70c6d0769871416c5904d06fbf9ef586; price 5000 micro-USDC.
4. Use the buyer's own funded x402 client only with explicit wallet authorization. Never pass keys in URLs or task text.
5. Treat the result as a risk preflight with unverified funding, not a safe or guaranteed paying gig.
6. Independently verify buyer identity, assignment, contract and actual escrow settlement BEFORE spending on a task.

A queryless paid-route crawl produces a labelled SYNTHETIC report, not an audit of an unspecified real issue. To audit a real issue, the issue query parameter is mandatory.

The new tool has no independently confirmed paid x402 settlement or fulfilled external buyer yet. GitHub anonymous rate limiting may make an actual issue audit unavailable. The backend fails closed on upstream failures, never promising payout.

## Development and safeguards

- Services source: services/agent-bounty-truth-gate
- Offline tests: node --test tests/bounty_truth_gate/test_core.mjs tests/bounty_truth_gate/test_onchain.mjs
- No keys, signing, wallet sending, bounty claiming, unsolicited contact, code execution, or user transactions.
- Bounded Github response sizes, bounded issue text, fixed HTTPS allowlist, independent RPC quorum, no SSRF through task text.
- This is an unaudited beta; no SLA.

Commercial state: listed and x402-quoted; not a verified independent sale.

# ProofGate 2047 — public demand-to-evidence preflight

A **read-only** demand screening and verification-gate subsystem for Agent Economy OS 2047.

Problem: public gig aggregators contain genuine requirements mixed with outdated listings, restricted payout routes, uncertain funding, and unsafe instructions. A posted reward is **not** evidence of deposited funds, a contract, permission to work, or revenue.

## What this actually does

1. Reads a bounded, public agent-gig JSON feed using HTTPS and no credentials.
2. Inspects at most 2,000 entries without executing instructions embedded in gig descriptions.
3. Rejects unsupported payout currencies and rails, expired or closed claims, known pay-to-work/child-bounty patterns, and unrelated requests.
4. Matches survivors to four existing Agent Economy capabilities and provides inspectable scores.
5. Optionally tests **only explicitly allowlisted** origin URLs with a bounded read-only request, never following redirects, with no secrets or payments. A successful response proves reachability only; funding remains unverified.
6. Produces a machine-readable report, a canonical SHA-256 checksum and an explicit set of independent eligibility, funding and delivery-verification gates. No auto-claiming, auto-applying, mass outreach or transfers.

## Usage

```bash
python -m unittest discover -s tests -p 'test_proofgate.py' -v
python automation/proofgate.py --output proofgate-report.json --probe
```

Run off-network on a known local JSON Feed:

```bash
python automation/proofgate.py --input example-feed.json --output report.json
```

The `sha256` field signs **nothing**: it is an integrity checksum over the report body before `sha256` and `observed_at_utc` are added, not an authenticated receipt and not a claim that the feed or source is truthful.

## Operator decision gates

For any candidate, independently confirm *all* of:
- The source task exists, remains open, and authorizes the proposed work.
- The advertised bounty is actually funded or payable, and the user can legally receive the payout on a supported chain without paying upfront.
- The worker meets eligibility and can realistically satisfy acceptance requirements with available tools.
- Source and acceptance criteria are safe; don't run third-party containers or scripts, sign financial transactions, or share secrets.
- **Only after** external acceptance, verified settlement and delivery may the amount be counted as revenue.

A status 200 from a source is not proof of escrow. An aggregator's `payment_state=escrowed` is only an attributed claim. Every candidate has `execution_allowed=false` and `contact_allowed=false` by design.

GitHub Actions runs this read-only scan every 6 hours and stores the report as a private-to-workflow artifact. It never emails a prospect, changes payments or wallets, or starts a paid job.

## Security

No dependency installation, no arbitrary code from job posts, no wallet keys, no authorization headers, no external POST, no auto-follow redirects. A bounded output list and a strict destination-host allowlist limit exposure. Listing titles and descriptions are **untrusted**. Scores rank technical fit, **not** the probability of payment.

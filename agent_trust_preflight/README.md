# Agent Economic Trust Layer: Atomic x402 Quote Preflight (offline alpha)

**Status: independently executable prototype, not deployed to Agent Economy OS 2047.**

This Python 3.10+ standard-library-only tool joins three narrowly-scoped operations:

1. Fail-closed validation of a single x402 v2 *Base USDC exact* offer against a buyer-pinned HTTPS URL, payee, token, chain, timeout and per-call price cap.
2. Atomic SQLite reservation against a local, shared UTC-day budget, enforced with `BEGIN IMMEDIATE` even when several workers run concurrently.
3. One-time request-ID replay detection; reusing an ID cannot create another reservation, including identical retries.

It **never** verifies a wallet's ownership, payment authorization, receipt settlement, identity, completed service delivery, merchant reputation or buyer acceptance. It never signs a transaction, broadcasts anything, or contacts any external URL. Reservation is a conservative local planning action only: even success returns `eligible_for_new_execution: false`, `payment_authorized: false` and `payment_executed: false`.

## Run with a synthetic quote

```bash
python3 -m unittest discover -s tests -v
python3 agent_trust_preflight.py \
  --capture sample_challenge.json \
  --db ./local-reservations.sqlite3 \
  --operation-id localtest-20261119-0001 \
  --expected-url https://api.example.test/v1/verify \
  --expected-payee 0xabababababababababababababababababababab \
  --max-quote-micro 10000 \
  --daily-budget-micro 50000
```

All quantities are **atomic USDC units** (6 decimals): `10000` means 0.01 USDC, and `50000` means 0.05 USDC. The sample uses `example.test` and **makes no payment**. The CLI returns exit code 0 only for a *new local reservation*; other cases return exit code 2.

This is **not** an order-authorization control: an executor must independently authenticate its caller, enforce its own payment mandate, bind the quote and reservation to the intended operation, protect wallet keys and verify final settlement. Do **not** blindly use exit code 0 as permission to pay. Changing `--operation-id` creates a new logical request and consumes more budget; only a trusted orchestrator may create IDs. SQLite's file permissions and disk integrity must be controlled by the same operator. The ledger is not cryptographically tamper-proof, not remote multi-node consensus, and not a distributed idempotency layer. Do not store the ledger on unreliable shared network filesystems.

**Fail-closed by design:** contradictory quotes, changed budget policy on an existing DB, corrupt/unavailable DB, reuse of an operation ID, and daily cap exhaustion all deny new reservations. Reserving budget is deliberately irreversible within the CLI, so a crashed downstream process does not silently restore funds. This can reduce availability; operator reconciliation is required. No secret keys or personal data are necessary.

## Security limitations & deployment gate

Before a production release: (1) verify the controlling service's authenticated identity and principal-scoped permissions; (2) bind operation IDs to a trusted, unforgeable job/order identifier; (3) migrate local SQLite reservations to a managed transactional database for multi-host durability; (4) independently verify payment receipts, chain confirmations and reorgs; (5) enforce request rate limits and observability with no secret leakage; (6) peer review and compliance check. No access to payment execution is supplied here.

This is a prototype intended to differentiate pre-payment *quote consistency + atomic budget reservations + replay checks* from the existing quote-only baseline. It is not a verified security boundary for adversarial remote callers.
# Agent Output Evidence Starter — indicative USD $49

**Offer stage:** non-binding scoping proposal; there is no automatic checkout, accepted purchase, guaranteed turnaround time, or confirmed customer until separately established.

## What this narrowly scoped pilot helps evaluate

A developer or AI-agent team wants to see whether a buyer-controlled acceptance gate catches changed artifacts and a substituted producer-controlled policy before someone accepts an automated handoff. It is **technical consistency checking**, not independent proof that the agent performed work correctly.

**One public or synthetic example only:**
- One public GitHub repository (or a synthetic, reproducible example), up to five artifacts, all non-sensitive files.
- A buyer-reviewed acceptance policy with its SHA-256 digest pinned separately from the producing agent; the buyer remains responsible for that trust root.
- One reproducible GitHub Actions/local verification example using the existing `buyer-gate` tool.
- One expected-positive sample and one deliberate tamper/substitution negative sample, plus a machine-readable local check report.
- A short handoff explaining how to rerun checks and exactly what the result *does not* prove.

## Reproducible no-cost example

[Try the free synthetic browser demonstration](starter-demo.html) for a narrow policy-pin and output-status example. It is a separate illustrative subset, not the complete Python verifier or an independent buyer trust root.

The open-source evidence primitive already lives in `buyer-gate/check.py`. Run this demonstration from the repository root, using only public synthetic artifacts:

```bash
python3 -m automation.starter_49_demo
```

The program evaluates the existing example, then clones it to a temporary directory to demonstrate **two independent failure modes**: a modified artifact fails an expected policy condition, and a substituted policy fails the separately held hash comparison. The original sample is not modified. It emits a JSON result and returns a failing process exit code if any expected check is missing. There are no calls to external APIs, customer systems, or payment services.

**Important boundary:** this demonstration calculates its expected policy SHA-256 from the *same checkout* and so only verifies a local smoke-test mechanism. A real buyer must separately review and protect a policy hash outside the producing agent's control; neither this sample nor passing tests certify provenance, buyer approval, source freshness, paid delivery or an actual customer.

## Proposed acceptance conditions

1. The customer approves the public/synthetic fixtures and a policy fingerprint independently.
2. The unmodified fixture passes the pre-agreed local technical requirements.
3. The altered artifact or swapped policy is rejected; the observed failed requirement is recorded.
4. The submitted example and report contain no customer secrets, no payment information and no proprietary files.
5. The buyer may review the complete delivered sources and test instructions before confirming acceptance under an actual agreement.

**Out of scope:** production rollout, private repository access, customer documents, SSO, signing customer transactions, authentication, financial risk certification, verified authorship, performance benchmarking, compliance certification, guaranteed revenue or a production SLA.

## Pricing and safe request process

**USD $49 is an indicative starting price for the exact starter scope, not a binding offer or a payment link.** Scope, lawful invoicing/payment method and acceptance terms must be agreed separately before any paid work. Additional files, private infrastructure, ongoing support or broader analysis require a separate quotation.

[Request a scoped starter quote](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new?template=service-request.yml) via a **public GitHub Issue**. Select the starter option and describe only public or synthetic acceptance criteria. **Do not include** private code, personal information, secrets, wallet credentials or payment card data. Opening the form does not order or pay for anything.

For a larger enterprise technical assessment, see [the separate indicative USD $750 audit](ENTERPRISE_EVIDENCE_PILOT.md). The experimental machine-generated **750 USDC x402** report is a different product and is not included in this starter.

## Current trust boundary

The project's automated tests and publicly reachable free demos establish only their own scoped behavior, not an independent customer engagement, third-party certification, signing authority or actual paid delivery. Never represent a demo or a quotation as a sale.

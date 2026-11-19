# Agent Economy OS 2047

[![CI](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/workflows/ci.yml/badge.svg)](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/workflows/ci.yml)
[![Work Covenant tests](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/workflows/work-covenant-ci.yml/badge.svg)](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/workflows/work-covenant-ci.yml)
[![MIT License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Evidence integrity and work-verification primitives for AI agents.** Open source, with reproducible local checks and explicit limits on what evidence can prove.

> A passing hash check proves consistency with declared bytes—not who produced the work, whether it is correct, whether a buyer accepted it, or whether anyone paid.

## Try it in one command

Requires Node.js 24 (or a compatible runtime with Web Crypto). No wallet, API key, credentials, package install, or network request:

```sh
node examples/proof-carrying-work/run.mjs
```

The synthetic example compiles acceptance criteria, verifies a JSON artifact, deliberately tampers with the artifact, and confirms that the altered submission **fails**. The output includes a reproducible `contract_id` and `proof_id`—neither is an independent endorsement.

Run the tests:

```sh
node --test tests/work_covenant/*.mjs
python3 -m unittest discover -s tests -v
```

[Quickstart and trust model](docs/QUICKSTART.md) · [Work Covenant technical specification](docs/WORK_COVENANT_2047.md)

## What exists

| Component | What it does | Limit |
| --- | --- | --- |
| [Proof-Carrying Work Covenant](docs/WORK_COVENANT_2047.md) | Stateless task criteria, hashes, JSON-pointer checks, optional Ed25519 technical signatures | Caller-defined checks do not establish independent buyer acceptance or identity |
| [File evidence verifier](verifier.py) | Offline SHA-256 manifest verification for files | Hash equality is not proof of truthful work |
| [Reusable GitHub Action](action.yml) | Adds local artifact verification to another repository's CI | Review and pin a commit SHA before use |
| [Public repository readiness audit](.github/ISSUE_TEMPLATE/free-repo-audit.yml) | Checks seven public maintenance signals through GitHub Issues | Not a vulnerability assessment |
| [BountyTruth beta](docs/BOUNTY_TRUTH_GATE.md) | Reads potentially untrusted public bounty text and detects suspicious claims | Does not prove escrow, funding, or payout |
| [x402 receipt-checking route guide](docs/AGENT402_BUYER_ROUTE.md) | Describes experimental Base USDC receipt evidence APIs and seller discovery | HTTP 402 and synthetic probes are not sales |
| [ProofGate](docs/PROOFGATE.md) | Read-only opportunity/payment-claim preflight | Not proof of payment |

The code in this repository implements only the components explicitly linked here. The public hosted service is **experimental**; verify current availability separately.

## Try the public beta API

- [Work Covenant demonstration](https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047/demo)
- [OpenAPI schema](https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047/openapi.json)
- [BountyTruth synthetic demo](https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-bounty-truth-gate/api/v1/demo)
- [Public site](https://agent-economy-english.floot.app)

These links do **not** authorize external execution, spending, or transactions. Do not submit secrets or customer data to public demos.

## Use the offline verifier in CI

```sh
python3 verifier.py evidence-manifest.json --root . --json-out evidence-report.json
```

To reuse our [composite Action](action.yml), check out your repository and pin the Action to a **reviewed commit SHA**, rather than a moving branch:

```yaml
name: Verify agent evidence
on: [push, pull_request]
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aymanaseriai-cell/agent-economy-os-2047@YOUR_REVIEWED_COMMIT_SHA
        with:
          manifest: evidence-manifest.json
          root: .
```

## Security and commercial transparency

- **No automatically verified customers, revenue, signed contracts, or independent settlement** are implied by demos, listing status, or repository stars.
- The local demo does not transmit artifacts. The hosted Work Covenant beta has no public per-user authentication or rate limiter and does not provide a production SLA.
- Any cryptographic signature is meaningful only after the verifier independently establishes the signer's identity and authority.
- This repository is maintained by one founder with AI-assisted development. Results should be evaluated through code, reproducible tests and independent integrations.

Read [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md), and [scope and limitations](docs/REPOSITORY_SCOPE.md).

## Contribute

We welcome reproducible bug reports, security fixes, safer JSON parsing, interoperable work-evidence formats, independent client examples and small documentation improvements. Please include a failing test before proposing a fix. No exchange or unrelated automation tools are part of this repository.

[Open an issue](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new) · [Request a free public repository audit](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new?template=free-repo-audit.yml) · [Request a nonbinding integration quote](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new?template=service-request.yml)

MIT licensed. Production operations and integrations may be subject to additional terms, fees, and legal review.

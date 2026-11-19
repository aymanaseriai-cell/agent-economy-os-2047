# Agent Economy OS 2047 — open-source competitive intelligence

Snapshot: **2026-11-19**, GitHub API repository metadata. Star counts are ephemeral. These repositories are technical comparisons **not a verified ranking of commercial competitors**. No competitor code is copied into this change.

| Repository | Stars | License report | Function | Proposed benefit |
|---|---:|---|---|---|
| [a2aproject/A2A](https://github.com/a2aproject/A2A) | 26593 | Apache-2.0 | A2A discovery & Agent Card | Original metadata preflight |
| [modelcontextprotocol/typescript-sdk](https://github.com/modelcontextprotocol/typescript-sdk) | 13786 | MIXED MIT / Apache-2.0 | MCP SDK; package-level licenses | Pinned interoperability tests, not wholesale vendoring |
| [x402-foundation/x402](https://github.com/x402-foundation/x402) | 6821 | Apache-2.0 | HTTP payment protocol | Receipt states only pending compliance |
| [microsoft/agent-governance-toolkit](https://github.com/microsoft/agent-governance-toolkit) | 6579 | MIT | Policy guardrails & agent governance | Deny-by-default policy audit |
| [a2aproject/a2a-samples](https://github.com/a2aproject/a2a-samples) | 1839 | Apache-2.0 | Interoperability samples | Independent protocol fixtures |
| [HumanSecurity/human-verified-ai-agent](https://github.com/HumanSecurity/human-verified-ai-agent) | 40 | MIT | Signed HTTP agent traffic | Separate signatures from verified identity |
| [agentrust-io/ca2a](https://github.com/agentrust-io/ca2a) | 9 | MIT | Delegation and signed evidence | Delegation, replay protection research |
| [inamprotocol/inam-protocol](https://github.com/inamprotocol/inam-protocol) | 3 | Apache-2.0 | Agent receipts & reputation | Cryptographic evidence versus settlement |
| [opena2a-standards/agent-identity-protocol](https://github.com/opena2a-standards/agent-identity-protocol) | 3 | Apache-2.0 | Identity/capability claims | Trust root & key rotation review |
| [alokemajumder/OpenAgentPay](https://github.com/alokemajumder/OpenAgentPay) | 2 | Apache-2.0 | Payment routing & receipts | Nonfinancial routing research first |

## Implemented in this PR

An original, Python standard-library, offline preflight for **A2A v1.x Agent Card metadata**. It validates selected required fields, HTTPS public endpoints, suspicious private addresses, duplicate skill IDs and duplicate JSON object keys. It deliberately does **not** fetch URLs, run competitor software, perform cryptographic signature verification or claim A2A protocol conformance.

Usage:

    python automation/a2a_card_audit.py my-agent-card.json --json-out report.json
    python -m unittest discover -s tests -p 'test_a2a_card_audit.py' -v

Passing checks establish only selected metadata structure. Identity, endpoint reachability, signed claims, buyer acceptance, proof of actual execution, or protocol compliance all require independent tests. Do not present this as formal protocol certification.

## Integration sequence

1. A2A Agent Card preflight and CI (this PR).
2. A2A 1.x live transport and task interoperability against official conformance tests in staging.
3. Signatures, scoped delegation, trust roots and revocation, with explicit identity limitations.
4. MCP interoperability pinned to compatible official SDK releases.
5. x402 payment flows **only after** technical security review, idempotency, transaction reconciliation and applicable legal clearance.

## License rules

MIT/Apache-2.0 usually permit commercial adaptation when notices/attribution requirements are met. The official MCP TypeScript SDK is transitioning MIT to Apache-2.0; check the **exact file/package** and maintain copyright/NOTICE requirements. Do not copy undocumented, unlicensed or proprietary code or trademarks. Avoid code from GPL/AGPL projects without evaluating reciprocal obligations. A license is not a security guarantee.

References:
- https://github.com/a2aproject/A2A/blob/main/docs/specification.md
- https://a2a-protocol.org/latest/specification/agent-card/
- https://github.com/modelcontextprotocol/typescript-sdk/blob/main/LICENSE
- https://github.com/x402-foundation/x402

No user adoption, stars, revenue, deployments or commercial outcomes are claimed.

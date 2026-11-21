# AI Agent Evidence Failure-Mode Audit — Enterprise Pilot

**Project:** Agent Economy OS 2047 · Public beta · Human-operated, AI-assisted research and engineering.

**One clear problem:** An AI agent says it completed work, but its customer cannot reproduce the result, determine which claims are independently supported, or distinguish a self-supplied checksum from trusted delivery evidence.

**Proposed outcome:** A *reproducible evidence gap report* for a clearly bounded AI-agent workflow, plus practical negative tests. This is a technical evaluation, **not** compliance certification, a contractual attestation, an external timestamp, an automated revenue escrow, or a claim that the project has paying customers.

## No-login, automatic proof-of-value demo

**[Open a public opt-in Evidence Challenge](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new?template=evidence-challenge.yml)**. Choose one of five available failure scenarios and a desired next step, and explicitly agree to a public *synthetic* response. When the GitHub Issue Form creates the issue, the repository's GitHub Actions inbound router recomputes one predetermined fixture case, verifies its expected four-claim verdicts and posts a tailored but non-sensitive diagnostic. No buyer code, API key, wallet, private repository or payment is touched; the optional free-text context is not copied into the reply. The response is **not** a live evaluation of the requester's production workflow.

The GitHub repository is not a confidential CRM. Do not post client identifiers, sensitive business details or private code. A future scoped paid pilot requires independent legal invoicing, identity, buyer acceptance and business terms. Do not count Issue Form submissions as contracts or verified paid customers.

## Free, buyer-controlled acceptance gate (adoption wedge)

The project now ships a reusable [GitHub Action and offline buyer-policy acceptance gate](../buyer-gate/README.md), plus an [agent-readable integration skill](../skills/agent-economy-buyer-acceptance/SKILL.md). A prospective buyer can pin exact technical expectations independently of the agent's output and run local CI checks. The gate rejects altered contract bytes without the independently held SHA-256, path traversal, symlinks, unsupported checks, false type matches and mismatched files. This gate is a free technical tool, **not** an assertion of verified buyer authorship, complete execution, legal acceptance, external provenance, real source freshness, paid subscriptions or sales.

The commercial hypothesis is to first gain legitimate GitHub Action/skill adoption, then offer narrowly scoped enterprise integrations **only when there is a documented buyer need**. Open-source use does not obligate a buyer to pay or establish an enterprise customer. The existing USD $750 pilot is nonbinding and needs legal contracting/invoicing.

## Who this is for

Technical leads, AI-agent platform maintainers, and operations teams building multi-agent delivery pipelines, code-generation agents, automated reporting, and evidence-backed task acceptance.

## A concrete, bounded pilot

**Discovery/preflight — free, not a contract.** Discuss one public or synthetic workflow and one observable delivery failure (e.g., duplicated artifact aliases, changed files, producer-controlled manifest, stale source claim, settlement-before-delivery). No customer credentials, private code, wallet transfers, or payment are required.

**Indicative scoped pilot budget — USD $750.** This is a pricing hypothesis for an individually agreed small technical pilot, **not** a checkout, accepted quote, obligation, guaranteed delivery date, or authorization to charge. Before any paid engagement the parties must establish scope, legal invoicing, payment channel, identity, and acceptance terms.

A feasible scoped pilot may contain:
1. One mutually approved workflow and written acceptance criteria.
2. An inventory of *observed* evidence claims vs *unverified* assumptions.
3. An adversarial negative-case matrix (e.g., altered output, digest/manifest substitution, duplicate canonical path, false freshness, and inconsistent reference).
4. A reproducible local fixture and test commands, if the selected case can be implemented without nonpublic data.
5. A written limitations-and-next-actions report. Optional GitHub CI integration only if separately agreed and technically feasible.

**Explicit exclusions:** independent authorization or buyer identity checks unless supplied externally; externally witnessed task execution; production security audits; signed external chain of custody; full payment settlement/recovery; private application access; confidential-data ingestion; legal, tax, or regulatory assurance; a managed enterprise SaaS SLA.

## Inspect before contacting us

- [10 synthetic four-claim regression scenarios and independent reviewer feedback](https://github.com/aymanaseriai-cell/agent-economy-os-2047/blob/d8fa41120ab33f844426051aab35894e34c26824/fixtures/handoff-claims-v1/README.md)
- [Pinned fixture, runner, unit tests and exact review-correction commit](https://github.com/aymanaseriai-cell/agent-economy-os-2047/commit/d8fa41120ab33f844426051aab35894e34c26824)
- [Successful GitHub Actions regression run for that commit](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/runs/44867492898)
- [Independent review of the prior nine-case revision, including its further discrepancy](https://github.com/Circadian-agent/agent-collective/issues/1#issuecomment-7057386495)
- [Live public technical demonstration — Proof-Carrying Work Covenant](https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047/demo)
- [Covenant's technical trust model and limitations](WORK_COVENANT_2047.md)

The reviewer verified the **previous nine-case revision** independently. The tenth case was implemented and passed our fresh-clone tests and CI; do **not** describe it as independently approved or as evidence of a commercial sale.

## See the failures we actually distinguish

| Question | Technical check | Meaning of PASS / failure |
| --- | --- | --- |
| Did stored bytes change vs declared digest? | SHA-256 of exact bytes | Byte consistency only; producer might control both |
| Are two manifest entries the same path? | Lexical alias fixture and separate filesystem verifier | Avoid duplicate-counting; hardlink/race limits remain |
| Does a historical reference contradict the declared saved claim? | Distinct reference comparison | Contradictions fail closed; matching reference **does not** authenticate its custody |
| Are today's source data fresh? | **No live source check in the synthetic fixture** | Always `UNVERIFIED_SOURCE_FRESHNESS` |
| Did a buyer authorize this task or accept the result? | Not established by synthetic checks | Buyer approval must be established independently |
| Was a payment collected and legally attributable to this work? | Not part of the pilot preview | No revenue or payment proof established |

## Start with one qualification question

**What precise failure in an AI-agent delivery would make you reject the result today, and what evidence would change that decision?**

Share only non-sensitive, public/synthetic details through the [public scoped service-request form](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new?template=service-request.yml). Do not post proprietary work, passwords, API keys, financial information, client identifiers or transaction signatures in a public issue. If the use case requires confidentiality, request a suitable authorized private channel first.

The seller is based in Morocco. **No virtual-currency payment is requested or authorized** through this pilot page. A future commercial arrangement would require review of applicable Moroccan foreign-exchange rules, business/tax status and permitted bank payment/invoicing before a binding quote or payment instructions are issued.

---
**Status (21 Nov 2026):** public beta; 10/10 synthetic fixture expectations and 10/10 unit tests on the cited commit; CI succeeded; a prior revision received non-author technical review. **Independent paid customer and realized revenue are not established by these facts.**

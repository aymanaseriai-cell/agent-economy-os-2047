# Agent Diff Gate — standalone beta companion

A no-key, standard-library CLI for reviewing changes to JSON artifacts produced by agents. The caller supplies a separately approved baseline file digest and a narrowly scoped allowlist of JSON Pointer prefixes. The result identifies changed paths and rejects any unapproved changes.

This is a new experimental companion to Buyer-Pinned Agent Acceptance Gate, not an independent approval signature, certification, provenance proof, buyer identity check, or proof of payment.

## Usage

    python3 products/agent_diff_gate.py baseline.json candidate.json \
      --baseline-sha256 YOUR_INDEPENDENTLY_PINNED_BASELINE_SHA256 \
      --allow-prefix /metadata \
      --json-out agent-diff-report.json

Exit code 0 means all observed differences are within allowed JSON Pointer paths relative to the supplied, digest-matching baseline. Exit 1 means invalid input, a mismatched baseline digest, or unapproved changes.

For local smoke tests you can use sha256sum baseline.json, but a hash computed from an untrusted agent's own checkout is not independent approval. Store and control the baseline SHA outside the agent-produced workspace.

## Boundaries

- Input: UTF-8 JSON files; at most 512 KiB each, 32 levels of nesting, and 4,000 differences.
- Duplicate JSON object keys fail closed, as do malformed JSON and invalid digest strings.
- Detects additions, deletions, primitive type/value changes, and array element changes. For allowlists, a prefix matches a full JSON Pointer segment, not a lexical partial match. An empty pointer segment is not accepted in an allowlist.
- No credentials, network traffic, file writes except an explicitly requested report, external API calls, payments, or user identity access.
- Never assert a successful CLI exit equals accepted delivery or verified buyer consent.

Suggested use: integrate into a protected buyer-owned CI workflow after checking out agent deliverables. Offer a scoped technical trial; do not claim independent customers or revenue.

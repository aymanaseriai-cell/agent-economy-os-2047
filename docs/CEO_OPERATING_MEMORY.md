# Agent Economy OS 2047 — CEO memory, reality gates

This workflow is a **persistent, conservative research controller**, not an autonomous purchasing or selling agent. It works with the existing GitHub issue-search radar each hour, stores a bounded list of public issue URLs on an **isolated `ceo-state` branch**, and publishes a `ceo-decision.json` file as a workflow artifact. Its presence does not establish any active client or revenue.

## Mechanism

1. Existing `automation/opportunity_scan.py` discovers public candidate issue metadata, not buyers.
2. `automation/ceo_memory.py` rejects invalid/stale radar output and claims that radar alone has verified a buyer.
3. The ledger deduplicates appearances within each day, remembers suppressed entries, and forgets candidates not seen for 45 days. Candidate state is capped at 300 records. Research content is never executed or echoed into shell.
4. A ranked shortlist of up to five **unqualified** issue URLs is available to the separate ChatGPT CEO automation for actual source review. No GitHub issue is contacted automatically.
5. The workflow writes only the isolated `ceo-state` branch when state meaningfully changes. Commit messages include `[skip ci]` to avoid downstream push-loop CI. Existing repository service request bot still handles opt-in inbound inquiries separately.

## What success requires

Evidence stages cannot be promoted just because a candidate reappeared: SEARCH_RESULT (unverified) → independent need confirmed → permission to contact established → invited technical demonstration → buyer pilot requested → legally agreed contract → independently verified legal payment. The tool **never** sets any of those higher states. A separate authenticated review must inspect the original issue/post, sender, procurement authority, channel terms and rejection history.

The CEO automation's remit remains **Agent Economy OS 2047 only**. Review the `ceo-decision.json` artifact and act in allowed opt-in venues, rather than rescanning the same low-quality list and claiming the numbers are sales. When a source provides evidence of business intent, verify independently before contacting.

No purchases, crypto, live financial transfers, GitHub PR spam, identity assertions, or hidden model API costs. All reports label limits explicitly.

## Smoke tests

```bash
python3 -m unittest discover -s tests -p 'test_ceo_memory.py' -v
python3 -m unittest discover -s tests -p 'test_opportunity_scan.py' -v
```

# CEO War Room — execution accountability

This is a deterministic decision control-plane for Agent Economy OS 2047. It is **not** a quantum system, a general autonomous AI, a separate LLM, or proof of commercial success.

## What it actually does

- Reads the already generated `ceo-decision.json` (conservative public issue shortlist) and optionally the project's own public GitHub issues (read-only).
- Gives **explicit external service requests** priority over research-only external issues. Requests by the project's owner or bot are excluded from independent buyer interest.
- Runs independent *policy checks* for demand, technical reproducibility, compliance, red-team input integrity and finance. These are distinct deterministic checks, **not separate reasoning agents**.
- Selects **one task** and writes its queued state on branch `ceo-state` in `ceo-runtime/strategy.json`. A queued task is not a completed action. It will remain pending until a real reviewer supplies external evidence for review/rejection/completion. A link and an outcome are required to close a job.
- Produces `ceo-warroom.json` for the separate ChatGPT autonomous CEO to review and then execute a **permitted real action** using connected GitHub/Gmail tools.
- **Never** assumes a public issue is permission to send an unsolicited pitch, never counts synthetic tests or GitHub clones as customers, and never moves money or signs contracts.

## Why this is a strategic advance

Before this addition, the hourly radar stored sightings but did not have a durable **task-level** decision with a clear uncompleted/completed distinction. The new board avoids silently turning "queued" into "done" every hour and gives the CEO a stable exact URL to investigate and evidence requirements for closing the task.

## CEO instructions for legitimate execution

1. Retrieve latest workflow `ceo-warroom.json`, and `ceo-runtime/strategy.json` on branch `ceo-state`.
2. If `decision` is present and `queued`, read the original GitHub issue and comments, establish sender/need/channel authority, and check if another project agent already replied.
3. If the lead is a vendor, closed, duplicate, prohibited outreach, or lacks buyer need, mark it `rejected` with a **real source `evidence_url`** in strategy, then also mark `reviews[URL] = suppressed` in `ceo-runtime/state.json` only if exclusion is supported.
4. If explicit allowed request and the CEO can do useful work (respond to owner, PR after invitation, code fix for our project), perform that action, store a link and a truthful `effect` (e.g. `published_fixture`). Do not call that paid revenue.
5. Do **not** alter finance counters based on board heuristics. Verified payment must be confirmed by a legal accounting/bank system independently before claiming sales.
6. Never commit secrets, customer data, quoted private discussions, signed contracts, wallets or automation credentials.

## Modes

Public GitHub workflow uses `GITHUB_TOKEN` for **read-only** inbound discovery and GitHub Actions branch write for state. Failures of inbound fetching produce `partial_data`; they do not authorize outreach or invent a buyer.

Local smoke tests:

```bash
python3 -m unittest discover -s tests -p 'test_ceo_board.py' -v
python3 -m unittest discover -s tests -p 'test_ceo_memory.py' -v
```

All automatic work is limited to the existing GitHub Actions and ChatGPT scheduled runs. No independent 24/7 inference loop or external service uptime is guaranteed.

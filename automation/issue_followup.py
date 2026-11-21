#!/usr/bin/env python3
"""Rate-limited replies only to explicitly consented public service inquiries."""
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
import sys
from issue_router import github_api

MARKER = "<!-- agent-economy-inbound-followup-v1"
CONSENT = "I request automated replies to my follow-up comments on this public GitHub issue."
MAX_REPLIES = 2
COOLDOWN = timedelta(hours=24)


def parse_date(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def build_reply(event, comments, now=None):
    now = now or datetime.now(timezone.utc)
    issue, comment = event.get("issue") or {}, event.get("comment") or {}
    if event.get("action") != "created":
        return None
    if not str(issue.get("title", "")).startswith("[Service request]"):
        return None
    if issue.get("pull_request") or issue.get("state") != "open":
        return None
    if not re.search(r"(?im)^-\s*\[[xX]\]\s*" + re.escape(CONSENT) + r"\s*$", issue.get("body") or ""):
        return None
    author = (issue.get("user") or {}).get("login") or ""
    caller = (comment.get("user") or {}).get("login") or ""
    if not author or not caller or author.casefold() != caller.casefold() or caller.endswith("[bot]"):
        return None
    if not isinstance(comment.get("id"), int) or not isinstance(comment.get("body"), str):
        return None
    if not isinstance(comments, list) or len(comments) >= 100:
        return None  # Cannot prove dedupe if earlier pages were omitted.
    existing = [c for c in comments if (c.get("user") or {}).get("login") == "github-actions[bot]"
                and MARKER in (c.get("body") or "")]
    marker = f"{MARKER}:{comment['id']} -->"
    if any(marker in (c.get("body") or "") for c in existing) or len(existing) >= MAX_REPLIES:
        return None
    for old in existing:
        ts = parse_date(old.get("created_at"))
        if ts is None or now - ts < COOLDOWN:
            return None
    body = comment["body"].casefold()
    if len(body) > 5000:
        return None
    if any(x in body for x in ("secret", "private", "nda", "password", "credential", "confidential")):
        response = ("Please do not post private source code, credentials, contracts or personal data on a public issue. "
                    "A private scope requires a separately approved channel and explicit agreement.")
    elif any(x in body for x in ("price", "pricing", "quote", "cost", "$49", "$750", "payment")):
        response = ("The non-binding public technical-review hypothesis starts at USD 49; a separate enterprise "
                    "evidence audit hypothesis is USD 750. Neither is an invoice or accepted order. "
                    "Scope, availability, lawful contract and payment channel require separate written agreement. "
                    "Which one public, reproducible output failure do you want evaluated?")
    elif any(x in body for x in ("demo", "integration", "github actions", "buyer gate", "example", "ci")):
        response = ("The free Buyer-Pinned Agent Acceptance Gate can run in buyer-controlled GitHub CI. "
                    "Read https://github.com/aymanaseriai-cell/agent-economy-os-2047/blob/main/buyer-gate/README.md . "
                    "A checksum PASS does not prove buyer acceptance or agent execution. "
                    "Which public artifact and policy requirement would you test?")
    elif any(x in body for x in ("timeline", "schedule", "when", "start", "availability")):
        response = ("No delivery timing or staff availability is guaranteed by an automated reply. "
                    "Please provide one non-sensitive scope and a measurable acceptance criterion for human review.")
    else:
        return None
    return "\n\n".join((marker,
        "Automated, consented follow-up to the original issue author:",
        response,
        "This is not a contract, sale, payment request or endorsement. No emails are sent. "
        "You can withdraw consent by unchecking the issue-form consent box or closing the issue."))


def prepare_reply(event, api, repo, now=None):
    """Fetch current issue consent and state; webhook snapshots may be stale."""
    original = event.get("issue") or {}
    number = original.get("number")
    if not isinstance(number, int):
        return None
    current = api(f"/repos/{repo}/issues/{number}")
    if not isinstance(current, dict) or current.get("number") != number:
        return None
    prior_author = (original.get("user") or {}).get("login")
    live_author = (current.get("user") or {}).get("login")
    if not prior_author or prior_author != live_author:
        return None
    comments = api(f"/repos/{repo}/issues/{number}/comments?per_page=100")
    return build_reply({**event, "issue": current}, comments, now)


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid repository")
    issue = event.get("issue") or {}
    if not isinstance(issue.get("number"), int):
        return 0
    token = os.environ["GITHUB_TOKEN"]
    def api(path):
        return github_api(path, token)
    message = prepare_reply(event, api, repo)
    if message is None:
        print("No eligible currently consented reply; no public action")
        return 0
    endpoint = f"/repos/{repo}/issues/{issue['number']}/comments"
    github_api(endpoint, token, "POST", {"body": message})
    print("Posted one bounded public opted-in reply")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Follow-up failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)

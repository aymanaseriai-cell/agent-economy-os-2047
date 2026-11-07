#!/usr/bin/env python3
"""Respond to *inbound* audit/quote issues; no outbound spam or paid actions.

Workflow grants issues:write only in this repo. No customer source code is executed.
"""
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from repo_audit import analyze, markdown_report

MARKER = "<!-- agent-economy-automated-response-v1 -->"
URL_PATTERN = re.compile(r"https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9_.-]{1,100})", re.IGNORECASE)


def find_repo(body):
    match = URL_PATTERN.search(body or "")
    if not match:
        return None
    name = match.group(2)
    if name.endswith(".git"):
        name = name[:-4]
    if not name or ".." in name:
        return None
    return match.group(1) + "/" + name


def build_response(issue, fetch=None):
    title = issue.get("title", "")
    category = "free" if title.startswith("[Free audit]") else "service" if title.startswith("[Service request]") else None
    if not category:
        return None
    slug = find_repo(issue.get("body", ""))
    head = [MARKER, "Thanks for your request. This is an automated reply based on public GitHub information only.", ""]
    if slug:
        try:
            data = analyze(slug, fetch=fetch) if fetch else analyze(slug)
            head.append(markdown_report(data))
        except ValueError as exc:
            head.append(f"Unable to complete the automated checklist: {exc}.")
    else:
        head.append("Please include a full public repository link such as `https://github.com/OWNER/REPO` in the form.")
    if category == "service":
        head += ["", "### Custom integration request", "The indicative *starting* price is **USD $49** for a narrowly scoped, publicly shareable repository integration review. This is **not** an invoice or accepted order. Scope, delivery, payment details and any private access must be agreed separately with the project owner."]
    else:
        head += ["", "### Want help implementing the missing items?", "For a scoped integration quote, open the [service-request form](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new?template=service-request.yml). No payment is taken automatically."]
    head += ["", "**Privacy reminder:** GitHub Issues are public. Never post credentials, private source code, financial information, or personal data here."]
    return "\n".join(head)


def github_api(path, token, method="GET", payload=None):
    if not path.startswith("/") or "//" in path:
        raise ValueError("Invalid GitHub request path")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request("https://api.github.com" + path, data=data, method=method, headers={
        "Accept": "application/vnd.github+json", "Content-Type": "application/json",
        "Authorization": "Bearer " + token, "User-Agent": "agent-economy-issue-router/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue = event.get("issue") or {}
    response = build_response(issue)
    if not response:
        print("Not an audit or service request; nothing to do.")
        return 0
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid GITHUB_REPOSITORY")
    issue_number = issue["number"]
    token = os.environ["GITHUB_TOKEN"]
    base = f"/repos/{repo}/issues/{issue_number}/comments"
    # Idempotence: update our own prior bot response when issue is reopened.
    comments = github_api(base + "?per_page=100", token)
    for comment in comments:
        author = (comment.get("user") or {}).get("login", "")
        if author == "github-actions[bot]" and MARKER in (comment.get("body") or ""):
            github_api(f"/repos/{repo}/issues/comments/{comment['id']}", token, "PATCH", {"body": response})
            print(f"Updated bot comment on issue #{issue_number}")
            return 0
    github_api(base, token, "POST", {"body": response})
    print(f"Posted automatic reply on issue #{issue_number}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Issue router failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)

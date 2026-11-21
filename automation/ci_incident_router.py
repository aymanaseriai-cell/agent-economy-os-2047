#!/usr/bin/env python3
"""Issue-only GitHub CI failure escalator: no checked-out run artifacts or automatic merges."""
import json
import os
from pathlib import Path
import re
import sys
from issue_router import github_api

MARKER = "<!-- agent-economy-ci-incident-v1 -->"
PREFIX = "[CTO CI incident]"


def process(event, api, repo):
    run = event.get("workflow_run") or {}
    if event.get("action") != "completed":
        return "IGNORED_NOT_COMPLETED"
    if run.get("name") != "Test and verify" or run.get("head_branch") != "main":
        return "IGNORED_UNSCOPED_WORKFLOW"
    if (run.get("head_repository") or {}).get("full_name") != repo:
        return "IGNORED_EXTERNAL_REPOSITORY"
    sha = run.get("head_sha")
    result = run.get("conclusion")
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        return "IGNORED_INVALID_SHA"
    if result not in ("success", "failure"):
        return "IGNORED_NONTERMINAL"
    head = api(f"/repos/{repo}/commits/main")
    if (head or {}).get("sha") != sha:
        return "IGNORED_SUPERSEDED_MAIN"
    issues = api(f"/repos/{repo}/issues?state=open&per_page=100")
    if not isinstance(issues, list) or len(issues) >= 100:
        return "BLOCKED_INCOMPLETE_ISSUE_PAGE"
    owned = [
        i for i in issues
        if (i.get("user") or {}).get("login") == "github-actions[bot]"
        and MARKER in (i.get("body") or "")
        and (i.get("title") or "").startswith(PREFIX)
        and "pull_request" not in i
    ]
    if result == "failure":
        if any(i.get("title") == f"{PREFIX} main {sha[:12]}" for i in owned):
            return "EXISTS"
        url = run.get("html_url", "")
        if not isinstance(url, str) or not re.fullmatch(
                rf"https://github\.com/{re.escape(repo)}/actions/runs/[0-9]+", url):
            return "IGNORED_INVALID_RUN_URL"
        body = "\n\n".join((
            MARKER,
            "Automatic CTO triage request: latest main failed Test and verify.",
            "Commit: " + sha,
            "Failure evidence: " + url,
            "Acceptance: reproduce failure; distinguish environment failure from product defect; "
            "prepare minimal nonproduction repair, test it, and open a Draft PR for review. "
            "Never auto-merge or deploy, and respect release gate #98.",
            "This is not proof of a buyer, sale, security breach, or accepted delivery."
        ))
        api(f"/repos/{repo}/issues", "POST", {
            "title": f"{PREFIX} main {sha[:12]}", "body": body})
        return "CREATED_CTO_INCIDENT"
    closed = 0
    for i in owned:
        num = i.get("number")
        if not isinstance(num, int):
            continue
        api(f"/repos/{repo}/issues/{num}/comments", "POST", {
            "body": "Automated CI resolution: current main SHA " + sha
            + " passed Test and verify. Closing only a bot-created CI incident; "
              "this does not claim any code merge or production deployment."
        })
        api(f"/repos/{repo}/issues/{num}", "PATCH", {"state": "closed"})
        closed += 1
    return f"CURRENT_MAIN_PASS_CLOSED_{closed}"


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid repository")
    token = os.environ["GITHUB_TOKEN"]
    def api(path, method="GET", payload=None):
        return github_api(path, token, method, payload)
    print(process(event, api, repo))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"CI incident router failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)

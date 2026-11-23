#!/usr/bin/env python3
"""Bounded read-only release audit. Never approves or deploys anything."""
import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, HTTPRedirectHandler, build_opener

OWNER = "aymanaseriai-cell"
REPO = "agent-economy-os-2047"
BASE = "https://api.github.com/repos/" + OWNER + "/" + REPO
PR_URL = BASE + "/pulls/114"
REVIEWS_URL = PR_URL + "/reviews?per_page=100"
GATE_URL = BASE + "/issues/98"
WORKFLOWS = (".github/workflows/ci.yml",
             ".github/workflows/worker-fleet-readonly.yml",
             ".github/workflows/watchdog-verdict-postgres.yml",
             ".github/workflows/codeql-pr-security.yml")

class ReviewError(ValueError):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReviewError("REDIRECT_NOT_ALLOWED")

def runs_url(sha):
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ReviewError("INVALID_HEAD_SHA")
    return BASE + "/actions/runs?head_sha=" + sha + "&per_page=100"

def fetch(url):
    if url not in (PR_URL, REVIEWS_URL, GATE_URL) and not (
        url.startswith(BASE + "/actions/runs?head_sha=")
        and url == runs_url(url.partition("head_sha=")[2].partition("&")[0])
    ):
        raise ReviewError("UNAPPROVED_URL")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "aeos2047-release-audit",
               "X-GitHub-Api-Version": "2022-11-28"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    with build_opener(NoRedirect()).open(Request(url, headers=headers), timeout=12) as resp:
        body = resp.read(2 * 1024 * 1024 + 1)
    if len(body) > 2 * 1024 * 1024:
        raise ReviewError("RESPONSE_LIMIT")
    return json.loads(body)

def audit(get=fetch):
    pr = get(PR_URL)
    if not isinstance(pr, dict) or pr.get("number") != 114 or not isinstance(pr.get("head"), dict):
        raise ReviewError("UNVERIFIED_PR")
    sha = pr["head"].get("sha")
    url = runs_url(sha)
    gate, reviews, run_response = get(GATE_URL), get(REVIEWS_URL), get(url)
    if not isinstance(gate, dict) or gate.get("number") != 98:
        raise ReviewError("UNVERIFIED_GATE")
    if not isinstance(reviews, list) or len(reviews) >= 100:
        raise ReviewError("REVIEW_LIST_UNVERIFIED_OR_TRUNCATED")
    if not isinstance(run_response, dict) or not isinstance(run_response.get("workflow_runs"), list) or len(run_response["workflow_runs"]) >= 100:
        raise ReviewError("WORKFLOW_LIST_UNVERIFIED_OR_TRUNCATED")
    blocked = []
    if pr.get("state") != "open" or pr.get("merged") is not False:
        blocked.append("NOT_OPEN_UNMERGED")
    if pr.get("draft") is not False:
        blocked.append("DRAFT_PR")
    if not isinstance(pr.get("base"), dict) or pr["base"].get("ref") != "main" or not isinstance(pr["head"].get("repo"), dict) or pr["head"]["repo"].get("full_name") != OWNER + "/" + REPO:
        blocked.append("WRONG_SOURCE_OR_BASE")
    if gate.get("state") != "closed":
        blocked.append("P0_GATE_98_OPEN")
    current_reviews = {}
    for review in reviews:
        if not isinstance(review, dict) or not isinstance(review.get("user"), dict):
            continue
        user = review["user"]
        login = user.get("login")
        if not isinstance(login, str) or not login or user.get("type") != "User":
            continue
        order = (str(review.get("submitted_at") or ""), review.get("id") if type(review.get("id")) is int else 0)
        if login.lower() not in current_reviews or order > current_reviews[login.lower()][0]:
            current_reviews[login.lower()] = (order, review)
    approvals = sorted(login for login, (_, review) in current_reviews.items()
                       if login != OWNER and review.get("state") == "APPROVED"
                       and review.get("commit_id") == sha
                       and review.get("author_association") in ("MEMBER", "COLLABORATOR"))
    if not approvals:
        blocked.append("NO_CURRENT_INDEPENDENT_COLLABORATOR_REVIEW")
    ci = {}
    for path in WORKFLOWS:
        matches = [run for run in run_response["workflow_runs"] if isinstance(run, dict)
                   and run.get("head_sha") == sha and run.get("path") == path
                   and run.get("event") == "pull_request"
                   and isinstance(run.get("repository"), dict)
                   and run["repository"].get("full_name") == OWNER + "/" + REPO
                   and type(run.get("id")) is int and run["id"] > 0]
        newest = max(matches, key=lambda run: run["id"]) if matches else None
        passed = bool(newest and newest.get("status") == "completed" and newest.get("conclusion") == "success")
        ci[path] = {"passed": passed, "run_id": newest["id"] if newest else None}
        if not passed:
            blocked.append("NO_CURRENT_CI:" + path)
    after = get(PR_URL)
    if not isinstance(after, dict) or not isinstance(after.get("head"), dict) or after["head"].get("sha") != sha:
        blocked.append("HEAD_CHANGED_DURING_AUDIT")
    blocked.extend(("SOURCE_PARITY_REVIEW_REQUIRED", "ROLLBACK_REVIEW_REQUIRED"))
    return {"schema": "aeos2047-preflight/1", "head_sha": sha, "pr": 114,
            "independent_reviewers": approvals, "ci": ci, "blockers": sorted(set(blocked)),
            "production_authorized": False, "writes": 0, "money_actions": 0,
            "note": "Read-only evidence; never a substitute for #98, independent review or parity."}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("RELEASE_PREFLIGHT_BLOCKED: " + ", ".join(result["blockers"]))
        return 0  # A completed audit is not a release approval.
    except (ReviewError, TypeError, KeyError, OSError, ValueError) as error:
        print("RELEASE_PREFLIGHT_UNVERIFIABLE: " + type(error).__name__)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())

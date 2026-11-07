#!/usr/bin/env python3
"""Read-only readiness snapshot of a PUBLIC GitHub repository, not a security audit.

No code from the target repository is downloaded or executed. Zero dependencies.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}$")
API = "https://api.github.com"
CHECKS = (
    ("readme", "Root README", 20),
    ("license", "License", 15),
    ("security", "Security policy", 15),
    ("ci", "GitHub Actions workflow", 20),
    ("issue_template", "Issue intake template", 10),
    ("dependabot", "Dependabot configuration", 10),
    ("description", "Repository description", 10),
)


def github_json(path):
    """Only request fixed GitHub API origin, never an untrusted host."""
    if not path.startswith("/") or "//" in path:
        raise ValueError("Invalid API path")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "agent-economy-readiness-audit/1.0",
               "X-GitHub-Api-Version": "2022-11-28"}
    # Optional token from environment; it is not printed or stored in audit output.
    token = os.environ.get("AUDIT_GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(API + path, headers=headers)
    try:
        with urlopen(request, timeout=12) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError("Repository is unavailable, private, or not found") from None
        if exc.code == 403:
            raise ValueError("GitHub API denied the request or rate limit was reached") from None
        raise ValueError(f"GitHub API error: HTTP {exc.code}") from None
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"GitHub API unavailable: {type(exc).__name__}") from None


def analyze(repository, fetch=github_json):
    if not REPO_PATTERN.fullmatch(repository) or ".." in repository:
        raise ValueError("Use an owner/repository slug (public GitHub repository only)")
    owner, name = repository.split("/", 1)
    meta = fetch("/repos/" + quote(owner, safe="") + "/" + quote(name, safe=""))
    if not isinstance(meta, dict) or meta.get("private", True):
        raise ValueError("Only public GitHub repositories can be checked")
    default_branch = meta.get("default_branch")
    if not default_branch:
        raise ValueError("Repository has no default branch yet (empty repository)")
    tree = fetch(f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/git/trees/{quote(default_branch, safe='')}?recursive=1")
    paths = {item.get("path", "").lower() for item in tree.get("tree", []) if item.get("type") == "blob"}
    flags = {
        "readme": any("/" not in p and p.startswith("readme") for p in paths),
        "license": bool(meta.get("license")) or any(p in {"license", "license.md", "license.txt", "copying"} for p in paths),
        "security": any(p in {"security.md", ".github/security.md", "docs/security.md"} for p in paths),
        "ci": any(p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")) for p in paths),
        "issue_template": any(p.startswith(".github/issue_template/") and p.endswith((".md", ".yml", ".yaml")) for p in paths),
        "dependabot": any(p in {".github/dependabot.yml", ".github/dependabot.yaml"} for p in paths),
        "description": bool((meta.get("description") or "").strip()),
    }
    scored = [{"key": key, "label": label, "points": points, "present": flags[key]} for key, label, points in CHECKS]
    score = sum(c["points"] for c in scored if c["present"])
    return {
        "repository": repository,
        "url": "https://github.com/" + repository,
        "score": score,
        "score_out_of": 100,
        "partial_tree": bool(tree.get("truncated")),
        "checks": scored,
        "disclaimer": "Readiness checklist based on public metadata and files; NOT a vulnerability scan, security certificate, or proof of agent performance.",
    }


def markdown_report(report):
    parts = ["### Automated public repository readiness snapshot", "",
             f"Repository: [{report['repository']}]({report['url']})",
             f"**Checklist score: {report['score']}/100** (presence-only; not a security score)", "",
             "| Signal | Observed | Weight |", "| --- | :---: | ---: |"]
    for check in report["checks"]:
        parts.append(f"| {check['label']} | {'✅' if check['present'] else '—'} | {check['points']} |")
    if report["partial_tree"]:
        parts.extend(["", "⚠️ GitHub returned an incomplete file tree; some signals may have been missed."])
    parts.extend(["", "**Next step:** Add any missing documentation or automations that suit this repository.",
                  "", "_This checks public files only. It does not examine code security, audit private data, or establish that an AI agent completed a real-world task._"])
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Generate a public GitHub repository readiness snapshot")
    parser.add_argument("repository", help="owner/repository")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    try:
        report = analyze(args.repository)
    except ValueError as exc:
        print(f"Audit unavailable: {exc}", file=sys.stderr)
        return 2
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

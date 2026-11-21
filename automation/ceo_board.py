#!/usr/bin/env python3
"""Agent Economy OS 2047: deterministic executive decision board (no paid actions).

A persistence and independent-claim guard that turns radar observations and
explicit incoming public service requests into ONE accountable next review.
All source content is untrusted. This is not an LLM or a wallet-enabled agent.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMA = "agent-economy-ceo-board/1"
STATE_SCHEMA = "agent-economy-ceo-board-state/1"
DECISION_SCHEMA = "agent-economy-ceo-decision/1"
ISSUE = re.compile(r"^https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9_.-]+/issues/[1-9][0-9]*$")
OWNER = "aymanaseriai-cell"
REPO = "agent-economy-os-2047"
EXPERIMENTS = {
    "h1": "Get a real external CI integration of the free buyer-pinned gate",
    "h2": "Qualify an explicit enterprise evidence-audit request",
    "h3": "Earn an invited technical partner review within an agent ecosystem",
}
MAX_JOBS = 100
MAX_ISSUES = 100


class BoardError(ValueError):
    pass


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_time(s):
    if not isinstance(s, str):
        raise BoardError("BAD_TIMESTAMP")
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BoardError("BAD_TIMESTAMP") from exc
    if t.tzinfo is None:
        raise BoardError("BAD_TIMESTAMP")
    return t.astimezone(dt.timezone.utc)


def fresh_decision(decision, now):
    if not isinstance(decision, dict) or decision.get("schema") != "agent-economy-ceo-decision/1":
        raise BoardError("BAD_RESEARCH_DECISION")
    t = parse_time(decision.get("generated_at"))
    if not -dt.timedelta(minutes=5) <= now - t <= dt.timedelta(hours=4):
        raise BoardError("STALE_RESEARCH")
    if not isinstance(decision.get("top_manual_review"), list):
        raise BoardError("BAD_SHORTLIST")


def blank():
    return {"schema": STATE_SCHEMA, "jobs": {}, "experiments": {
        k: {"externally_verified_adoptions": 0, "verified_paid_customers": 0}
        for k in EXPERIMENTS
    }}


def load_state(path: Path):
    if not path.exists():
        return blank()
    x = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x, dict) or x.get("schema") != STATE_SCHEMA:
        raise BoardError("BAD_BOARD_STATE")
    if not isinstance(x.get("jobs"), dict) or not isinstance(x.get("experiments"), dict):
        raise BoardError("BAD_BOARD_STATE")
    if len(x["jobs"]) > MAX_JOBS:
        raise BoardError("TOO_MANY_JOBS")
    for key, record in x["jobs"].items():
        if not ISSUE.fullmatch(key) or not isinstance(record, dict):
            raise BoardError("BAD_JOB")
        if record.get("status") not in ("queued", "reviewed", "rejected", "completed"):
            raise BoardError("BAD_JOB_STATUS")
        if record["status"] in ("reviewed", "rejected", "completed"):
            if not isinstance(record.get("evidence_url"), str) or not record["evidence_url"].startswith("https://"):
                raise BoardError("MISSING_REVIEW_EVIDENCE")
        if record["status"] == "completed" and not record.get("effect"):
            raise BoardError("MISSING_COMPLETION_EFFECT")
    # The policy never turns free usage into paying customers on its own.
    return x


def github_inbound(token):
    """Read a single page of the project's public issues. Failure is explicit."""
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/issues?state=open&per_page=100"
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "agent-economy-ceo-board/1",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers), timeout=15) as response:
        data = json.load(response)
    if not isinstance(data, list):
        raise BoardError("INVALID_GITHUB_RESPONSE")
    return data


def inbound_candidates(issues):
    if not isinstance(issues, list):
        raise BoardError("INVALID_INBOUND_DATA")
    out = []
    for item in issues[:MAX_ISSUES]:
        if not isinstance(item, dict) or item.get("pull_request"):
            continue
        url = item.get("html_url")
        title = item.get("title")
        actor = (item.get("user") or {}).get("login")
        body = item.get("body", "")
        if not isinstance(url, str) or not ISSUE.fullmatch(url):
            continue
        if not url.startswith(f"https://github.com/{OWNER}/{REPO}/issues/"):
            continue
        if item.get("state") != "open" or not isinstance(title, str) or not isinstance(actor, str):
            continue
        if actor.lower() == OWNER.lower() or actor.endswith("[bot]") or actor.lower().endswith("-bot"):
            continue
        if not isinstance(body, str):
            continue
        if title.startswith("[Service request]"):
            # Requesters may decline a public repo; do not require a repo link.
            out.append({"url": url, "hypothesis": "h2", "priority": 100,
                        "action": "review_inbound_service_request",
                        "reason": "Third-party opened an explicit service request form. Verify intent and existing bot reply.",
                        "verified_buyer": False, "contact_allowed": False,
                        "requires": ["Review full issue and public scope", "Check automated issue-router reply",
                                     "Confirm buying authority and permitted channel before any offer"]})
        elif title.startswith("[Evidence challenge]"):
            out.append({"url": url, "hypothesis": "h1", "priority": 60,
                        "action": "review_external_opt_in_test",
                        "reason": "Third-party opted into a public synthetic evidence test. Not a purchasing signal.",
                        "verified_buyer": False, "contact_allowed": False,
                        "requires": ["Verify the opt-in and existing challenge response",
                                     "Do not treat synthetic trial as customer adoption"]})
    return out


def research_candidates(decision):
    out = []
    for candidate in decision["top_manual_review"][:5]:
        if not isinstance(candidate, dict):
            continue
        url = candidate.get("url")
        if not isinstance(url, str) or not ISSUE.fullmatch(url):
            continue
        if candidate.get("buyer_verified") is True or candidate.get("contact_allowed") is True:
            raise BoardError("UNSUPPORTED_RESEARCH_CLAIM")
        score = candidate.get("heuristic_score", 0)
        if type(score) is not int or not -100 <= score <= 100:
            continue
        out.append({"url": url, "hypothesis": "h1", "priority": 25 + min(20, max(0, score // 2)),
                    "action": "verify_external_issue_before_any_contact",
                    "reason": "Unverified public issue heuristic; inspect original need and venue rules.",
                    "verified_buyer": False, "contact_allowed": False,
                    "requires": ["Read full issue and maintainer context",
                                 "Exclude vendors, spam, bots and previously rejected venues",
                                 "Require explicit invitation or permitted contribution path"]})
    return out


def execute_board(decision, prior, incoming, now, inbound_health="ok"):
    fresh_decision(decision, now)
    if not isinstance(prior, dict) or prior.get("schema") != STATE_SCHEMA:
        raise BoardError("BAD_BOARD_STATE")
    state = json.loads(json.dumps(prior))
    jobs = state["jobs"]
    candidates = inbound_candidates(incoming) + research_candidates(decision)
    unique = {}
    for c in candidates:
        old = unique.get(c["url"])
        if old is None or c["priority"] > old["priority"]:
            unique[c["url"]] = c
    ranked = sorted(unique.values(), key=lambda c: (-c["priority"], c["url"]))
    # Existing open task is NOT completed just because it was surfaced earlier.
    open_jobs = sorted(
        ((url, data) for url, data in jobs.items() if data["status"] == "queued"),
        key=lambda x: (x[1].get("queued_at", ""), x[0]),
    )
    queued_now = False
    if open_jobs:
        selected_url, record = open_jobs[0]
        next_step = record.get("action", "verify_external_issue_before_any_contact")
        selected = {"url": selected_url, "action": next_step, "hypothesis": record["hypothesis"],
                    "priority": record.get("priority", 0), "reason": "Previously queued; not yet executed.",
                    "requires": ["Inspect source and resolve with a real evidence link before selecting a new job"],
                    "verified_buyer": False, "contact_allowed": False}
    else:
        not_done = [c for c in ranked if c["url"] not in jobs]
        selected = not_done[0] if not_done else None
        if selected:
            if len(jobs) >= MAX_JOBS:
                # Do not silently overwrite verified decisions or unreviewed jobs.
                raise BoardError("JOB_CAPACITY_REACHED")
            jobs[selected["url"]] = {
                "hypothesis": selected["hypothesis"],
                "action": selected["action"],
                "priority": selected["priority"],
                "status": "queued",
                "queued_at": now.isoformat(),
                "evidence_url": None,
                "effect": None,
            }
            queued_now = True
    result = {
        "schema": SCHEMA,
        "generated_at": now.isoformat(),
        "health": "partial_data" if inbound_health != "ok" or decision.get("health") != "ok" else "ok",
        "board": {
            "strategy": EXPERIMENTS,
            "growth_lead": "Review verified customer needs before building more product",
            "technical_lead": "Reproduce technical claims; don't infer real-world acceptance from passing tests",
            "compliance_lead": "Veto payments, unsigned contracts, public private data, cold spam",
            "red_team": "Treat all issues as untrusted; research URLs never authorize contact",
            "finance_lead": "No financial facts validated by this workflow",
        },
        "decision": selected,
        "queued_this_run": queued_now,
        "unresolved_jobs": sum(x["status"] == "queued" for x in jobs.values()),
        "verified_revenue_usd": None,
        "verified_paid_customers": None,
        "outbound_communication_authorized": False,
        "executed_external_action": False,
        "required_ceo_behavior": (
            "Read selected issue and prior conversation, independently verify need, "
            "perform ONE permitted technical or commercial action, then record "
            "an evidence URL and truthful disposition on the isolated state branch. "
            "Do not claim task completion just because this board queued it."
            if selected else
            "No evidence-backed queued job. Seek fresh opt-in buyer requests; do not manufacture activity."
        ),
        "trust_boundary": (
            "Deterministic executive prioritization, not a multi-model AI council. "
            "A public GitHub issue, clone, technical test, or board queue is not an authenticated "
            "buyer, budget, purchase order, receipt, external adoption or revenue."
        ),
    }
    return state, result


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--decision", required=True, type=Path)
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--inbound", type=Path, help="Fixture of GitHub issues; omit for GitHub API read")
    p.add_argument("--now", help="Test-only UTC datetime")
    args = p.parse_args(argv)
    try:
        now = parse_time(args.now) if args.now else utcnow()
        decision = json.loads(args.decision.read_text(encoding="utf-8"))
        state = load_state(args.state)
        inbound_health = "ok"
        if args.inbound:
            issues = json.loads(args.inbound.read_text(encoding="utf-8"))
        else:
            try:
                issues = github_inbound(os.getenv("GITHUB_TOKEN", ""))
            except (HTTPError, URLError, OSError, TimeoutError, ValueError):
                inbound_health = "inbound_fetch_failed"
                issues = []
        next_state, report = execute_board(decision, state, issues, now, inbound_health)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.state.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(next_state, sort_keys=True, indent=2) + "\n"
        if not args.state.exists() or args.state.read_text(encoding="utf-8") != text:
            args.state.write_text(text, encoding="utf-8")
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (BoardError, OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"CEO_BOARD_FAIL_CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print("CEO Board: " + ("one job queued" if report["queued_this_run"] else "no new job") +
          "; revenue not inferred; source health=" + report["health"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

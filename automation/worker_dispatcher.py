#!/usr/bin/env python3
"""Bounded, auditable worker dispatch for Agent Economy OS 2047.

This is a real read-only executor/verifier protocol, not an LLM agent, payment
actor or autonomous production deployment mechanism.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMA = "aeos2047-worker-dispatch/1"
OWNER = "aymanaseriai-cell"
REPO = "agent-economy-os-2047"
TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,79}$")
SHA = re.compile(r"^[a-f0-9]{40}$")
GITHUB_RUN = re.compile(rf"^https://api\.github\.com/repos/{OWNER}/{REPO}/actions/runs/([1-9][0-9]*)$")
GITHUB_ISSUE = re.compile(rf"^https://api\.github\.com/repos/{OWNER}/{REPO}/issues/([1-9][0-9]*)$")
GITHUB_ISSUES_LIST = f"https://api.github.com/repos/{OWNER}/{REPO}/issues?state=open&per_page=100"
HEALTH_URL = "https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047/health"
MAIN_BRANCH_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/branches/main"
MAIN_CI_RUNS_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows/ci.yml/runs?branch=main&per_page=20"
ALLOWED = {
    "CEO": frozenset({"github_issues_readonly", "review_gate_readonly"}),
    "CTO": frozenset({"local_file_digest", "github_ci_readonly", "github_issue_readonly"}),
    "CRO": frozenset({"github_issues_readonly", "github_inbound_readonly", "local_file_digest"}),
    "COO_CFO": frozenset({"github_ci_readonly", "github_inbound_readonly", "http_health_readonly"}),
}
MAX_BYTES = 4 * 1024 * 1024


class PolicyError(ValueError):
    """Task violates explicit worker authorization."""


def default_fetch(url: str) -> dict:
    if not (GITHUB_RUN.fullmatch(url) or GITHUB_ISSUE.fullmatch(url) or url in (GITHUB_ISSUES_LIST, HEALTH_URL, MAIN_BRANCH_URL, MAIN_CI_RUNS_URL)):
        raise PolicyError("URL_NOT_ALLOWLISTED")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "agent-economy-worker-dispatch/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = "Bearer " + token
    request = Request(url, headers=headers)
    with urlopen(request, timeout=8) as response:
        payload = json.load(response)
    if not isinstance(payload, (dict, list)):
        raise ValueError("INVALID_PROVIDER_DOCUMENT")
    return payload


def evaluate(task: dict) -> dict:
    if not isinstance(task, dict):
        raise PolicyError("TASK_NOT_OBJECT")
    task_id, role, kind = task.get("id"), task.get("role"), task.get("kind")
    if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
        raise PolicyError("BAD_TASK_ID")
    if role not in ALLOWED or kind not in ALLOWED[role]:
        raise PolicyError("ROLE_KIND_NOT_AUTHORIZED")
    tries = task.get("max_attempts", 2)
    if type(tries) is not int or not 1 <= tries <= 2:
        raise PolicyError("INVALID_RETRY_CAP")
    if task.get("spend_usd", 0) != 0 or task.get("allow_write", False) is not False:
        raise PolicyError("WRITES_OR_SPEND_NOT_AUTHORIZED")
    payload = task.get("payload", {})
    if not isinstance(payload, dict):
        raise PolicyError("BAD_PAYLOAD")
    if kind == "local_file_digest":
        if not isinstance(payload.get("path"), str) or len(payload) != 1:
            raise PolicyError("INVALID_FILE_PAYLOAD")
    elif kind == "github_ci_readonly":
        if set(payload) != {"run_id", "expected_head_sha"}:
            raise PolicyError("INVALID_CI_PAYLOAD")
        if type(payload["run_id"]) is not int or payload["run_id"] < 1:
            raise PolicyError("INVALID_RUN_ID")
        if not isinstance(payload["expected_head_sha"], str) or not SHA.fullmatch(payload["expected_head_sha"]):
            raise PolicyError("INVALID_COMMIT_SHA")
    elif kind == "github_inbound_readonly":
        if set(payload) != {"issue_number"} or type(payload["issue_number"]) is not int or payload["issue_number"] < 1:
            raise PolicyError("INVALID_ISSUE_ID")
    elif kind in ("github_issues_readonly", "review_gate_readonly", "http_health_readonly"):
        if payload:
            raise PolicyError("NO_PARAMETERS_ALLOWED")
    elif kind == "github_issue_readonly":
        if set(payload) != {"issue_number"} or payload["issue_number"] != 98:
            raise PolicyError("RELEASE_GATE_ONLY")
    return {"id": task_id, "role": role, "kind": kind, "payload": payload, "max_attempts": tries,
            "spend_usd": 0, "allow_write": False}


def safe_local_file(root: Path, raw: str) -> Path:
    root = root.resolve()
    if not raw or raw.startswith(("/", "\\")) or "\\" in raw:
        raise PolicyError("INVALID_RELATIVE_PATH")
    parts = Path(raw).parts
    if not parts or any(p in (".", "..", "") for p in parts):
        raise PolicyError("PATH_TRAVERSAL")
    if any(p.startswith(".") or p.lower() in ("secrets", "credentials", "id_rsa") for p in parts):
        raise PolicyError("SENSITIVE_PATH_DISALLOWED")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise PolicyError("SYMLINK_DISALLOWED")
    final = current.resolve()
    if not final.is_relative_to(root) or not final.is_file():
        raise PolicyError("FILE_NOT_AVAILABLE")
    if final.stat().st_size > MAX_BYTES:
        raise PolicyError("FILE_TOO_LARGE")
    return final


def _local_digest(root: Path, path: str) -> dict:
    file = safe_local_file(root, path)
    data = file.read_bytes()
    if len(data) > MAX_BYTES:
        raise PolicyError("FILE_TOO_LARGE")
    return {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def _ci_snapshot(doc: dict, expected_sha: str) -> dict:
    if not isinstance(doc, dict):
        raise ValueError("INVALID_CI_RECEIPT")
    return {"status": doc.get("status"), "conclusion": doc.get("conclusion"),
            "head_sha": doc.get("head_sha"), "html_url": doc.get("html_url"),
            "matches_expected_sha": doc.get("head_sha") == expected_sha}


def _inbound_snapshot(doc: dict, number: int) -> dict:
    if not isinstance(doc, dict) or doc.get("number") != number:
        raise ValueError("ISSUE_ID_MISMATCH")
    actor = (doc.get("user") or {}).get("login", "")
    title = doc.get("title", "")
    if not isinstance(title, str):
        title = ""
    is_external = isinstance(actor, str) and bool(actor) and actor.lower() != OWNER and not actor.lower().endswith(("[bot]", "-bot"))
    eligible_form = title.startswith("[Service request]") or title.startswith("[Evidence challenge]")
    return {"issue_number": number, "state": doc.get("state"), "author": actor,
            "form_type": "service" if title.startswith("[Service request]") else ("challenge" if title.startswith("[Evidence challenge]") else "other"),
            "outside_opt_in_candidate": bool(is_external and eligible_form and doc.get("state") == "open" and not doc.get("pull_request")),
            "verified_buyer": False, "contact_authorized": False, "payment_verified": False}


def _open_inbound_snapshot(docs) -> dict:
    """Bounded public request triage; never treats owner or bot posts as buyers."""
    if not isinstance(docs, list) or len(docs) > 100:
        raise ValueError("BAD_ISSUE_LIST")
    candidates = []
    for doc in docs:
        if not isinstance(doc, dict) or doc.get("pull_request") or doc.get("state") != "open":
            continue
        author = (doc.get("user") or {}).get("login", "")
        title = doc.get("title", "")
        if not isinstance(author, str) or not isinstance(title, str):
            continue
        if not author or author.lower() == OWNER or author.lower().endswith(("[bot]", "-bot")):
            continue
        number = doc.get("number")
        if type(number) is not int or number < 1:
            continue
        if title.startswith("[Service request]") or title.startswith("[Evidence challenge]"):
            candidates.append({"issue_number": number, "actor": author,
                               "kind": "service" if title.startswith("[Service request]") else "demo"})
    candidates.sort(key=lambda c: (c["issue_number"], c["actor"]))
    return {"eligible_external_candidates": candidates[:25],
            "candidate_count": len(candidates),
            "verified_paid_buyers": 0, "outbound_contact_authorized": False}


def _release_gate_snapshot(doc: dict) -> dict:
    if not isinstance(doc, dict) or doc.get("number") != 98:
        raise ValueError("RELEASE_GATE_ID_MISMATCH")
    state = doc.get("state")
    if state not in ("open", "closed"):
        raise ValueError("RELEASE_GATE_STATUS_UNKNOWN")
    # A closed issue is NOT enough to authorize production release.
    return {"issue_number": 98, "state": state, "updated_at": doc.get("updated_at"),
            "production_release_authorized": False, "independent_review_proven": False}


def _health_snapshot(doc: dict) -> dict:
    if not isinstance(doc, dict):
        raise ValueError("INVALID_HEALTH_RESPONSE")
    # Fail closed: generic status strings are not evidence of this service's health.
    # Require the exact Work Covenant identity and complete v4 boolean contract.
    identity_matches = doc.get("service") == "agent-work-covenant-2047"
    full_positive_shape = (doc.get("ok") is True and doc.get("stateless") is True
                           and doc.get("no_paid_actions") is True)
    declared_status = doc.get("status")
    if identity_matches and full_positive_shape and declared_status in (None, "ok", "healthy"):
        status = "healthy"
    elif identity_matches and (doc.get("ok") is False or doc.get("stateless") is False
                               or doc.get("no_paid_actions") is False or declared_status == "error"):
        status = "error"
    elif identity_matches and declared_status == "degraded":
        status = "degraded"
    else:
        status = "unknown"
    return {"reported_health": status, "response_fields": sorted(str(x) for x in doc)[:30],
            "production_release_authorized": False}


def perform(task: dict, root: Path, fetch=default_fetch) -> dict:
    p, kind = task["payload"], task["kind"]
    if kind == "local_file_digest":
        return _local_digest(root, p["path"])
    if kind == "github_ci_readonly":
        url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/runs/{p['run_id']}"
        return _ci_snapshot(fetch(url), p["expected_head_sha"])
    if kind == "github_inbound_readonly":
        url = f"https://api.github.com/repos/{OWNER}/{REPO}/issues/{p['issue_number']}"
        return _inbound_snapshot(fetch(url), p["issue_number"])
    if kind == "github_issues_readonly":
        return _open_inbound_snapshot(fetch(GITHUB_ISSUES_LIST))
    if kind in ("github_issue_readonly", "review_gate_readonly"):
        return _release_gate_snapshot(fetch(f"https://api.github.com/repos/{OWNER}/{REPO}/issues/98"))
    if kind == "http_health_readonly":
        return _health_snapshot(fetch(HEALTH_URL))
    raise PolicyError("NO_WORKER")


def independently_verify(task: dict, result: dict, root: Path, fetch=default_fetch) -> tuple[bool, str]:
    # Independently repeat the observation instead of trusting the executor.
    actual = perform(task, root, fetch)
    if actual != result:
        return False, "INDEPENDENT_RECHECK_MISMATCH"
    if task["kind"] == "github_ci_readonly" and not (
        result["status"] == "completed" and result["conclusion"] == "success" and result["matches_expected_sha"]
    ):
        return False, "CI_NOT_PASSING_ON_EXPECTED_SHA"
    if task["kind"] == "github_inbound_readonly":
        return True, "PROVIDER_RECHECK_PASSED_NOT_BUYER_VERIFICATION"
    if task["kind"] == "http_health_readonly":
        if result["reported_health"] not in ("ok", "healthy"):
            return False, "HEALTH_NOT_CONFIRMED"
        return True, "PROVIDER_RECHECK_PASSED_SELF_REPORTED_HEALTH_NOT_SLA_PROOF"
    if task["kind"] in ("github_issues_readonly", "github_issue_readonly", "review_gate_readonly"):
        return True, "PROVIDER_RECHECK_PASSED_NOT_RELEASE_OR_BUYER_AUTHORIZATION"
    return True, "INDEPENDENT_RECHECK_PASSED"


def dispatch(task: dict, root: Path, fetch=default_fetch) -> dict:
    """Evaluate -> execute -> independently verify -> bounded retry -> receipt."""
    approved = evaluate(task)
    receipt = {"schema": SCHEMA, "task_id": approved["id"], "role": approved["role"],
               "worker_kind": approved["kind"], "status": "BLOCKED", "attempts": 0,
               "outbound_contact": False, "paid_action": False, "production_change": False,
               "evidence": None, "verification": None}
    for attempt in range(approved["max_attempts"]):
        receipt["attempts"] = attempt + 1
        try:
            performed = perform(approved, root, fetch)
            passed, reason = independently_verify(approved, performed, root, fetch)
            receipt["evidence"], receipt["verification"] = performed, reason
            if passed:
                receipt["status"] = "VERIFIED_READONLY"
                break
        except (PolicyError, ValueError, OSError, HTTPError, URLError, TimeoutError) as exc:
            receipt["verification"] = type(exc).__name__ + ": " + str(exc)[:120]
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=Path, required=True, help="JSON list, 1-10 allowlisted workers")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= 10:
            raise PolicyError("TASK_BATCH_CAP")
        approved = [evaluate(task) for task in tasks]
        ids = [item["id"] for item in approved]
        if len(set(ids)) != len(ids):
            raise PolicyError("DUPLICATE_TASK_ID")
        receipts = [dispatch(item, args.root) for item in approved]
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"schema": SCHEMA, "receipts": receipts}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Worker dispatch completed: {sum(x['status'] == 'VERIFIED_READONLY' for x in receipts)}/{len(receipts)} read-only verified")
        return 0 if all(x["status"] == "VERIFIED_READONLY" for x in receipts) else 2
    except (PolicyError, ValueError, OSError, TypeError, KeyError) as exc:
        print(f"WORKER_DISPATCH_FAIL_CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

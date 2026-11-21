#!/usr/bin/env python3
"""Bounded, auditable worker dispatch for Agent Economy OS 2047.

This is a real read-only executor/verifier protocol, not an LLM agent, payment
actor or autonomous production deployment mechanism.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
ALLOWED = {
    "CTO": frozenset({"local_file_digest", "github_ci_readonly"}),
    "CRO": frozenset({"github_inbound_readonly"}),
}
MAX_BYTES = 4 * 1024 * 1024


class PolicyError(ValueError):
    """Task violates explicit worker authorization."""


def default_fetch(url: str) -> dict:
    if not (GITHUB_RUN.fullmatch(url) or GITHUB_ISSUE.fullmatch(url)):
        raise PolicyError("URL_NOT_ALLOWLISTED")
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "agent-economy-worker-dispatch/1",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urlopen(request, timeout=8) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
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
    return {"id": task_id, "role": role, "kind": kind, "payload": payload, "max_attempts": tries}


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

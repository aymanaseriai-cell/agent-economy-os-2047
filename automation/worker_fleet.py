#!/usr/bin/env python3
"""Twelve specialized, review-only operational workers supervised by four executives.

A role-specific capability dispatcher, not twelve independent LLM instances.
The four ChatGPT executive automations may delegate within the approved scope
once this code passes review and is actually deployed. No model, payment,
production-write or customer-contact capability is silently provisioned.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from automation.worker_dispatcher import PolicyError, dispatch, evaluate

SCHEMA = "aeos2047-worker-fleet/1"
MAX_CONCURRENT = 4


@dataclass(frozen=True)
class Worker:
    worker_id: str
    owner_role: str
    name: str
    kind: str
    mission: str
    default_payload: Optional[dict] = None


WORKERS = (
    Worker("AEOS-W01", "CEO", "Opportunity Intelligence", "github_issues_readonly",
           "Detect independently authored opt-in demand without counting owner posts", {}),
    Worker("AEOS-W02", "CEO", "Strategic Prioritization", "review_gate_readonly",
           "Identify the current release bottleneck before prioritizing further changes", {}),
    Worker("AEOS-W03", "CTO", "Product Engineer", "local_file_digest",
           "Validate source-artifact integrity before any proposed review-only fix",
           {"path": "verifier.py"}),
    Worker("AEOS-W04", "CTO", "CI and Regression Tester", "github_ci_readonly",
           "Check exact-source commit against real passing GitHub CI"),
    Worker("AEOS-W05", "CTO", "Reliability and Repair Analyst", "github_ci_readonly",
           "Detect failed CI and escalate reproducible repair work; not an auto-merge"),
    Worker("AEOS-W06", "CTO", "Security and Release Reviewer", "github_issue_readonly",
           "Recheck independent-release gate #98, do not bypass it", {"issue_number": 98}),
    Worker("AEOS-W07", "CRO", "Inbound Lead Researcher", "github_issues_readonly",
           "Detect real opt-in incoming requests in our own repository", {}),
    Worker("AEOS-W08", "CRO", "Buyer Qualification Specialist", "github_inbound_readonly",
           "Recheck one request; issue authorship is not purchase authority"),
    Worker("AEOS-W09", "CRO", "Offer and Proposal Analyst", "local_file_digest",
           "Preserve exact source evidence for nonbinding offer review",
           {"path": "docs/ENTERPRISE_EVIDENCE_PILOT.md"}),
    Worker("AEOS-W10", "CRO", "Customer Onboarding Specialist", "local_file_digest",
           "Check that public self-serve technical documentation is present and stable",
           {"path": "buyer-gate/README.md"}),
    Worker("AEOS-W11", "COO_CFO", "Incident and Operations Monitor", "http_health_readonly",
           "Independently recheck the live allowlisted Work Covenant health endpoint", {}),
    Worker("AEOS-W12", "COO_CFO", "Finance and Revenue Evidence Controller", "github_inbound_readonly",
           "Distinguish an inquiry from independently verified settlement/delivery"),
)

REGISTRY = {worker.worker_id: worker for worker in WORKERS}
assert len(REGISTRY) == 12
assert {w.owner_role for w in WORKERS} == {"CEO", "CTO", "CRO", "COO_CFO"}


def make_task(assignment: dict) -> tuple[Worker, dict]:
    """The worker ID, never untrusted task content, determines its tool and role."""
    if not isinstance(assignment, dict) or set(assignment) - {"worker_id", "payload", "max_attempts", "priority"}:
        raise PolicyError("UNEXPECTED_WORKER_PARAMETERS")
    worker_id = assignment.get("worker_id")
    if not isinstance(worker_id, str) or worker_id not in REGISTRY:
        raise PolicyError("WORKER_NOT_REGISTERED")
    worker = REGISTRY[worker_id]
    payload = assignment.get("payload", worker.default_payload)
    if not isinstance(payload, dict):
        raise PolicyError("MISSING_REQUIRED_WORKER_EVIDENCE")
    # A worker with a fixed public artifact or release gate must not be
    # reassigned to arbitrary repository files or an unrelated issue.
    if worker.default_payload is not None and payload != worker.default_payload:
        raise PolicyError("STATIC_WORKER_SCOPE_OVERRIDE")
    priority = assignment.get("priority", 3)
    if type(priority) is not int or not 1 <= priority <= 5:
        raise PolicyError("INVALID_PRIORITY")
    task = {
        "id": worker.worker_id + "-check",
        "role": worker.owner_role,
        "kind": worker.kind,
        "payload": payload,
        "max_attempts": assignment.get("max_attempts", 2),
        "spend_usd": 0,
        "allow_write": False,
    }
    approved = evaluate(task)
    return worker, approved


def outcome(worker_id: str, receipt: dict) -> str:
    """Business status is distinct from successful technical observation."""
    if receipt["status"] != "VERIFIED_READONLY":
        return "BLOCKED_NO_RELIABLE_EVIDENCE"
    evidence = receipt["evidence"] or {}
    if worker_id in ("AEOS-W01", "AEOS-W07"):
        return ("EXTERNAL_REQUEST_CANDIDATES_NOT_BUYERS"
                if evidence.get("candidate_count", 0) > 0 else "NO_EXTERNAL_OPTIN_OBSERVED")
    if worker_id in ("AEOS-W02", "AEOS-W06"):
        return ("RELEASE_GATE_STILL_OPEN" if evidence.get("state") == "open"
                else "RELEASE_AUTHORIZATION_STILL_UNVERIFIED")
    if worker_id in ("AEOS-W03", "AEOS-W09", "AEOS-W10"):
        return "ARTIFACT_HASH_RECHECKED_NOT_NEW_PRODUCT_DELIVERY"
    if worker_id == "AEOS-W04":
        return "CI_SUCCESS_EXACT_SHA_NOT_PRODUCTION"
    if worker_id == "AEOS-W05":
        return "NO_FAILURE_AT_INSPECTED_RUN_NOT_SELF_REPAIR"
    if worker_id == "AEOS-W08":
        return ("OPTIN_CANDIDATE_NOT_VERIFIED_BUYER"
                if evidence.get("outside_opt_in_candidate") else "NO_EXTERNAL_OPTIN_IN_ISSUE")
    if worker_id == "AEOS-W11":
        return ("REPORTED_HEALTH_OK_NOT_FULL_RELIABILITY"
                if evidence.get("reported_health") in ("ok", "healthy")
                else "HEALTH_UNCERTAIN_OR_DEGRADED")
    if worker_id == "AEOS-W12":
        return "FINANCIAL_REVENUE_UNKNOWN_NEEDS_PAYMENT_AND_DELIVERY_PROOF"
    raise PolicyError("WORKER_OUTCOME_NOT_DEFINED")


def run_one(worker: Worker, approved: dict, root: Path, fetch=None) -> dict:
    if fetch is None:
        receipt = dispatch(approved, root)
    else:
        receipt = dispatch(approved, root, fetch)
    return {
        "worker_id": worker.worker_id,
        "owner_role": worker.owner_role,
        "name": worker.name,
        "technical_status": receipt["status"],
        "business_outcome": outcome(worker.worker_id, receipt),
        "attempts": receipt["attempts"],
        "evidence": receipt["evidence"],
        "verification": receipt["verification"],
        "customer_acquired": False,
        "revenue_verified_usd": None,
        "production_change": False,
        "model_agent_instantiated": False,
    }


def run_fleet(assignments: list, root: Path, fetch=None, max_concurrent: int = 4) -> dict:
    """Priority-aware finite dispatch, restricted roles, duplicate suppression."""
    if type(max_concurrent) is not int or not 1 <= max_concurrent <= MAX_CONCURRENT:
        raise PolicyError("CONCURRENCY_CAP")
    if not isinstance(assignments, list) or not 1 <= len(assignments) <= len(WORKERS):
        raise PolicyError("INVALID_FLEET_SIZE")
    prepared = []
    seen = set()
    for item in assignments:
        worker, approved = make_task(item)
        if worker.worker_id in seen:
            raise PolicyError("DUPLICATE_WORKER_ASSIGNMENT")
        seen.add(worker.worker_id)
        prepared.append((item.get("priority", 3), worker, approved))
    prepared.sort(key=lambda x: (x[0], x[1].worker_id))
    with ThreadPoolExecutor(max_workers=min(max_concurrent, len(prepared))) as pool:
        futures = [pool.submit(run_one, worker, approved, root, fetch)
                   for _, worker, approved in prepared]
        results = [f.result() for f in futures]
    return {
        "schema": SCHEMA,
        "configured_worker_count": len(WORKERS),
        "executive_count": 4,
        "dispatched_count": len(results),
        "technically_verified_readonly_count": sum(r["technical_status"] == "VERIFIED_READONLY" for r in results),
        "verified_customers_from_fleet": None,
        "verified_revenue_usd": None,
        "company_autonomy_percent": None,
        "running_llm_worker_sessions": 0,
        "scope": "NONPRODUCTION_READONLY_EXECUTOR; NOT FULL COMPANY AUTONOMY",
        "receipts": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--jobs", type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--max-concurrent", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        if args.inventory:
            print(json.dumps({"schema": SCHEMA, "workers": [
                {"worker_id": w.worker_id, "owner_role": w.owner_role, "name": w.name,
                 "kind": w.kind, "mission": w.mission} for w in WORKERS]}, indent=2))
            return 0
        if args.jobs is None or args.out is None:
            raise PolicyError("JOBS_AND_OUT_REQUIRED")
        jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
        report = run_fleet(jobs, args.root, max_concurrent=args.max_concurrent)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print("Worker fleet read-only verifications: %s/%s" %
              (report["technically_verified_readonly_count"], report["dispatched_count"]))
        return 0 if report["technically_verified_readonly_count"] == report["dispatched_count"] else 2
    except (PolicyError, ValueError, TypeError, OSError, KeyError) as exc:
        print("WORKER_FLEET_FAIL_CLOSED: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

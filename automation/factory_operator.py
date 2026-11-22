#!/usr/bin/env python3
"""Executive-led, fail-closed specialist dispatch. Nonproduction review-only."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

from automation.worker_fleet import REGISTRY, run_fleet
from automation.worker_dispatcher import PolicyError

SCHEMA = "aeos2047-executive-factory/1"
PREFIX = "AEOS2047:FACTORY:20261121:"
ROLES = ("CEO", "CTO", "CRO", "COO_CFO")
ALLOWED_ACTION = {
    "AEOS-W01": "DETECT_EXTERNAL_MARKET_DEMAND",
    "AEOS-W02": "PRIORITIZE_EXECUTIVE_DELIVERABLE",
    "AEOS-W03": "PROPOSE_TESTED_REVIEW_BRANCH_FIX",
    "AEOS-W04": "VERIFY_CURRENT_SHA_CI",
    "AEOS-W05": "TRIAGE_AND_REPAIR_CI",
    "AEOS-W06": "CHECK_P0_RELEASE_GATE",
    "AEOS-W07": "TRIAGE_OPTIN_INBOUND",
    "AEOS-W08": "QUALIFY_ONE_CONSENTED_BUYER",
    "AEOS-W09": "REVIEW_49_USD_PILOT_OFFER",
    "AEOS-W10": "PROVE_SELF_SERVE_ONBOARDING",
    "AEOS-W11": "MONITOR_AND_TRIAGE_INCIDENT",
    "AEOS-W12": "RECONCILE_SETTLEMENT_VS_INQUIRY",
}
STATES = {"QUEUED", "IN_PROGRESS", "VERIFIED", "BLOCKED", "NEEDS_APPROVAL"}
SAFE_ORDER_FIELDS = frozenset({"work_key", "owner_role", "action_code", "work_status", "priority", "proof_ref"})
assert len(REGISTRY) == len(ALLOWED_ACTION) == 12

def plan_dispatch(orders: list) -> dict:
    """One decision per executive; never represent dispatch as executed work."""
    if not isinstance(orders, list) or len(orders) > 12:
        raise PolicyError("INVALID_FACTORY_QUEUE")
    seen = set()
    grouped = {role: [] for role in ROLES}
    for order in orders:
        if not isinstance(order, dict):
            raise PolicyError("INVALID_WORK_ORDER")
        # Prevent accidental export of customer information or credential-bearing rows.
        if set(order) - SAFE_ORDER_FIELDS:
            raise PolicyError("UNSAFE_WORK_ORDER_EXPORT_FIELDS")
        key = order.get("work_key")
        if not isinstance(key, str) or not key.startswith(PREFIX):
            raise PolicyError("UNTRUSTED_WORK_KEY")
        worker_id = key[len(PREFIX):]
        if worker_id not in REGISTRY or worker_id in seen:
            raise PolicyError("UNREGISTERED_OR_DUPLICATE_WORKER")
        seen.add(worker_id)
        role = order.get("owner_role")
        if role != REGISTRY[worker_id].owner_role:
            raise PolicyError("ROLE_OWNERSHIP_MISMATCH")
        if order.get("action_code") != ALLOWED_ACTION[worker_id]:
            raise PolicyError("UNAPPROVED_WORK_ACTION")
        priority = order.get("priority")
        if type(priority) is not int or not 1 <= priority <= 5:
            raise PolicyError("INVALID_PRIORITY")
        status = order.get("work_status")
        if status not in STATES:
            raise PolicyError("UNAPPROVED_WORK_STATUS")
        if status == "VERIFIED":
            if not isinstance(order.get("proof_ref"), str) or not order["proof_ref"].startswith("https://"):
                raise PolicyError("VERIFIED_WITHOUT_PROOF_REFERENCE")
        grouped[role].append((priority, worker_id, status, key))
    selections = []
    for role in ROLES:
        entries = grouped[role]
        if not entries:
            selections.append({"executive": role, "disposition": "NO_ASSIGNED_WORK",
                               "worker_id": None, "work_key": None})
            continue
        in_progress = [o for o in entries if o[2] == "IN_PROGRESS"]
        queued = [o for o in entries if o[2] == "QUEUED"]
        approvals = [o for o in entries if o[2] == "NEEDS_APPROVAL"]
        blocked = [o for o in entries if o[2] == "BLOCKED"]
        # Reconcile existing work before dispatching a new task for this
        # executive, even when the queued item has higher numeric priority.
        if in_progress:
            priority, worker_id, status, key = min(in_progress, key=lambda x: (x[0], x[1]))
            disposition = "VERIFY_IN_PROGRESS_FIRST"
        elif queued:
            priority, worker_id, status, key = min(queued, key=lambda x: (x[0], x[1]))
            disposition = "REVIEW_ONLY_ACTION_ELIGIBLE"
        elif approvals:
            priority, worker_id, status, key = min(approvals, key=lambda x: (x[0], x[1]))
            disposition = "ESCALATE_INDEPENDENT_APPROVAL"
        elif blocked:
            priority, worker_id, status, key = min(blocked, key=lambda x: (x[0], x[1]))
            disposition = "WAIT_EXTERNAL_EVIDENCE"
        else:
            selections.append({"executive": role, "disposition": "NO_NEW_EVIDENCE",
                               "worker_id": None, "work_key": None})
            continue
        selections.append({"executive": role, "disposition": disposition,
                           "worker_id": worker_id, "work_key": key,
                           "priority": priority, "source_status": status,
                           "action_code": ALLOWED_ACTION[worker_id]})
    digest = hashlib.sha256(json.dumps(orders, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"schema": SCHEMA, "configured_workers": 12, "executives": 4,
            "orders_inspected": len(orders), "source_orders_sha256": digest,
            "selected": selections,
            "execution_status": "DECISION_ONLY_NOT_WORKER_EXECUTION",
            "production_release_authorized": False, "funds_moved": False,
            "customer_contact_authorized": False, "independent_llm_sessions": 0}

def execute_reviewonly(plan: dict, live_jobs: list, root: Path, fetch=None, *, source_orders=None) -> dict:
    """Execute only selected review-only worker probes via existing allowlisted dispatcher."""
    if plan.get("schema") != SCHEMA or plan.get("production_release_authorized") is not False:
        raise PolicyError("INVALID_FACTORY_PLAN")
    choices = plan.get("selected")
    if not isinstance(choices, list) or len(choices) != 4:
        raise PolicyError("FORGED_EXECUTIVE_PLAN")
    allowed_dispositions = {
        "REVIEW_ONLY_ACTION_ELIGIBLE": "QUEUED",
        "VERIFY_IN_PROGRESS_FIRST": "IN_PROGRESS",
        "ESCALATE_INDEPENDENT_APPROVAL": "NEEDS_APPROVAL",
        "WAIT_EXTERNAL_EVIDENCE": "BLOCKED",
    }
    for expected_role, choice in zip(ROLES, choices):
        if not isinstance(choice, dict) or choice.get("executive") != expected_role:
            raise PolicyError("FORGED_EXECUTIVE_PLAN")
        candidate = choice.get("worker_id")
        disposition = choice.get("disposition")
        if candidate is None:
            if disposition not in ("NO_ASSIGNED_WORK", "NO_NEW_EVIDENCE") or choice.get("work_key") is not None:
                raise PolicyError("FORGED_EMPTY_EXECUTIVE_DECISION")
            continue
        if candidate not in REGISTRY or REGISTRY[candidate].owner_role != expected_role:
            raise PolicyError("FORGED_ROLE_ROUTE")
        if choice.get("work_key") != PREFIX + candidate or choice.get("action_code") != ALLOWED_ACTION[candidate]:
            raise PolicyError("FORGED_ACTION_SELECTION")
        if choice.get("source_status") != allowed_dispositions.get(disposition):
            raise PolicyError("PLAN_STATUS_DISPOSITION_MISMATCH")
        priority = choice.get("priority")
        if type(priority) is not int or not 1 <= priority <= 5:
            raise PolicyError("FORGED_PRIORITY")
    # A caller may not mutate a manager decision after planning. Recompute the
    # full plan from the exact bounded source snapshot before ANY dispatch.
    # This binds execution to input consistency, not to independent DB identity.
    if source_orders is None:
        raise PolicyError("SOURCE_WORK_ORDERS_REQUIRED")
    if plan != plan_dispatch(source_orders):
        raise PolicyError("PLAN_SOURCE_SNAPSHOT_MISMATCH")
    # Recheck interrupted read-only probes. This is safe only because the
    # worker fleet has no write, payment, customer-contact or deploy capability.
    selected = [o["worker_id"] for o in choices
                if o["disposition"] in ("REVIEW_ONLY_ACTION_ELIGIBLE",
                                        "VERIFY_IN_PROGRESS_FIRST")]
    if not selected:
        return {"execution_status": "NO_ELIGIBLE_WORK_TO_EXECUTE",
                "dispatched_count": 0, "technically_verified_readonly_count": 0,
                "receipts": [], "production_changes": False,
                "source_orders_sha256": plan["source_orders_sha256"]}
    if not isinstance(live_jobs, list):
        raise PolicyError("MISSING_LIVE_JOBS")
    available = {}
    for job in live_jobs:
        if not isinstance(job, dict) or not isinstance(job.get("worker_id"), str):
            raise PolicyError("INVALID_JOB")
        if job["worker_id"] in available:
            raise PolicyError("DUPLICATE_LIVE_JOB")
        available[job["worker_id"]] = job
    if not set(selected).issubset(available):
        raise PolicyError("MISSING_EXACT_SELECTED_JOB")
    result = run_fleet([available[w] for w in selected], root, fetch=fetch, max_concurrent=4)
    return {"execution_status": "REVIEW_ONLY_PROBES_COMPLETED_NOT_BUSINESS_DELIVERY",
            "dispatched_count": result["dispatched_count"],
            "rechecked_in_progress_count": sum(
                o["disposition"] == "VERIFY_IN_PROGRESS_FIRST" for o in choices),
            "technically_verified_readonly_count": result["technically_verified_readonly_count"],
            "receipts": result["receipts"],
            "production_changes": False, "independent_llm_sessions": 0,
            "source_orders_sha256": plan["source_orders_sha256"]}

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--orders", type=Path, required=True)
    jobs_group = parser.add_mutually_exclusive_group()
    jobs_group.add_argument("--jobs", type=Path)
    jobs_group.add_argument("--auto-live-jobs", action="store_true",
                            help="Discover current public allowlisted read-only worker checks")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args(argv)
    try:
        orders = json.loads(a.orders.read_text(encoding="utf-8"))
        plan = plan_dispatch(orders)
        if a.jobs is not None or a.auto_live_jobs:
            if a.auto_live_jobs:
                eligible = any(c["disposition"] in (
                    "REVIEW_ONLY_ACTION_ELIGIBLE", "VERIFY_IN_PROGRESS_FIRST")
                    for c in plan["selected"])
                if eligible:
                    from automation.worker_fleet_live import prepare_live_jobs
                    live_jobs = prepare_live_jobs()["jobs"]
                else:
                    live_jobs = []  # No provider calls for blocked/approval-only queues.
            else:
                live_jobs = json.loads(a.jobs.read_text(encoding="utf-8"))
            plan["reviewonly_execution"] = execute_reviewonly(
                plan, live_jobs, a.root, source_orders=orders)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("EXECUTIVE_FACTORY: %d validated work orders; %d role decisions; no production actions"
              % (len(orders), len(plan["selected"])))
        return 0
    except (PolicyError, ValueError, TypeError, KeyError, OSError) as exc:
        print("FACTORY_FAIL_CLOSED: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""End-to-end executive/worker CI smoke using live read-only provider evidence.

Orders are deliberately synthetic (not a Supabase production queue). This
exercises actual four-manager selection and four network-backed worker checks,
never code writes, customer contact, paid actions or autonomous deliveries.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from automation.factory_operator import ALLOWED_ACTION, PREFIX, execute_reviewonly, plan_dispatch
from automation.worker_dispatcher import PolicyError
from automation.worker_fleet import REGISTRY
from automation.factory_cycle import run_review_cycle, atomic_json

SMOKE_WORKERS = ("AEOS-W01", "AEOS-W04", "AEOS-W07", "AEOS-W11")
assert {REGISTRY[worker].owner_role for worker in SMOKE_WORKERS} == {"CEO", "CTO", "CRO", "COO_CFO"}


def synthetic_reviewonly_orders() -> list[dict]:
    """A synthetic role-owned queue to test control flow; not a real work order."""
    return [
        {"work_key": PREFIX + worker, "owner_role": REGISTRY[worker].owner_role,
         "action_code": ALLOWED_ACTION[worker], "work_status": "QUEUED",
         "priority": 1, "proof_ref": None}
        for worker in SMOKE_WORKERS
    ]


def run_factory_smoke(live_jobs: list, root: Path, fetch=None) -> dict:
    orders = synthetic_reviewonly_orders()
    plan = plan_dispatch(orders)
    if any(choice["disposition"] != "REVIEW_ONLY_ACTION_ELIGIBLE"
           for choice in plan["selected"]):
        raise PolicyError("FACTORY_SMOKE_ROLE_SELECTION_FAILED")
    receipt = execute_reviewonly(plan, live_jobs, root, fetch=fetch, source_orders=orders)
    results = receipt["receipts"]
    verified = receipt["technically_verified_readonly_count"]
    return {
        "schema": "aeos2047-factory-integration-ci/1",
        "source_orders": "SYNTHETIC_ROLE_OWNED_CI_FIXTURE_NOT_SUPABASE_QUEUE",
        "provider_probes": "LIVE_ALLOWLISTED_READONLY",
        "manager_roles": ["CEO", "CTO", "CRO", "COO_CFO"],
        "selected_worker_ids": list(SMOKE_WORKERS),
        "dispatched_count": receipt["dispatched_count"],
        "verified_readonly_count": verified,
        "integration_status": "PASSED" if verified == 4 and len(results) == 4 else "DEGRADED",
        "production_worker_execution": False,
        "independent_llm_sessions": 0,
        "autonomous_code_repair_verified": False,
        "external_customer_served": False,
        "verified_revenue_usd": None,
        "customer_contact": False,
        "production_change": False,
        "worker_receipts": results,
    }


def run_central_smoke(live_jobs: list, root: Path, fetch=None) -> dict:
    """Exercise the real central multi-round engine without private orders or writes."""
    workers = SMOKE_WORKERS + ("AEOS-W03", "AEOS-W09")
    orders = [
        {"work_key": PREFIX + w, "owner_role": REGISTRY[w].owner_role,
         "action_code": ALLOWED_ACTION[w], "work_status": "QUEUED",
         "priority": 1 if w in SMOKE_WORKERS else 2, "proof_ref": None}
        for w in workers
    ]
    report = run_review_cycle(orders, live_jobs, root, fetch=fetch)
    received = {x["worker_id"] for x in report["receipts"]}
    passed = (report["cycle_status"] == "REVIEW_COMPLETE"
              and report["rounds"] == 2
              and received == set(workers)
              and report["dispatched_count"] == len(workers)
              and report["technically_verified_readonly_count"] == len(workers))
    report.update({
        "source_orders": "SYNTHETIC_CI_FIXTURE_NOT_SUPABASE_QUEUE",
        "integration_status": "PASSED" if passed else "DEGRADED",
        "expected_worker_ids": list(workers),
        "independent_llm_sessions": 0,
        "autonomous_code_repair_verified": False,
        "customer_contact": False,
    })
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--central-cycle", action="store_true")
    args = parser.parse_args(argv)
    try:
        jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
        if args.central_cycle:
            report = run_central_smoke(jobs, args.root)
            atomic_json(args.out, report)
            print("CENTRAL_FACTORY_CYCLE: %s; %d rounds; %d verified checks"
                  % (report["integration_status"], report["rounds"],
                     report["technically_verified_readonly_count"]))
            return 0 if report["integration_status"] == "PASSED" else 2
        report = run_factory_smoke(jobs, args.root)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("FACTORY_INTEGRATION: %d/4 verified provider-backed read-only checks (%s)"
              % (report["verified_readonly_count"], report["integration_status"]))
        return 0 if report["integration_status"] == "PASSED" else 2
    except (PolicyError, ValueError, TypeError, KeyError, OSError) as exc:
        print("FACTORY_INTEGRATION_FAIL_CLOSED: %s: %s"
              % (type(exc).__name__, exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

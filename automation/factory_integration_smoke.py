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
import tempfile
from unittest.mock import patch
from pathlib import Path

from automation.factory_operator import ALLOWED_ACTION, PREFIX, execute_reviewonly, plan_dispatch
from automation.worker_dispatcher import PolicyError
from automation.worker_fleet import REGISTRY
from automation.factory_cycle import run_review_cycle, atomic_json
from automation import factory_cycle

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


def run_recovery_smoke(live_jobs: list, root: Path, fetch=None) -> dict:
    """Inject one interruption before round two; run actual allowlisted probes.

    The queue and interruption are synthetic. Neither the interrupted nor
    recovered checks are independent business deliveries or production work.
    """
    workers = SMOKE_WORKERS + ("AEOS-W03", "AEOS-W09")
    orders = [
        {"work_key": PREFIX + w, "owner_role": REGISTRY[w].owner_role,
         "action_code": ALLOWED_ACTION[w], "work_status": "QUEUED",
         "priority": 1 if w in SMOKE_WORKERS else 2, "proof_ref": None}
        for w in workers
    ]
    with tempfile.TemporaryDirectory(prefix="factory-recovery-smoke-") as tmp:
        directory = Path(tmp)
        inp, jobs, journal, out = [directory / n for n in
                                  ("orders.json", "jobs.json", "journal.json", "out.json")]
        atomic_json(inp, orders)
        atomic_json(jobs, live_jobs)
        original = factory_cycle.execute_reviewonly
        attempts = []
        def inject_once(*args, **kwargs):
            attempts.append(1)
            if len(attempts) == 2:
                raise OSError("SYNTHETIC_CI_INTERRUPTION_BEFORE_SECOND_ROUND")
            return original(*args, **kwargs)
        with patch("automation.factory_cycle.execute_reviewonly", side_effect=inject_once):
            rc = factory_cycle.main(["--orders", str(inp), "--jobs", str(jobs),
                "--root", str(root), "--out", str(out), "--checkpoint", str(journal),
                "--recover-once"], fetch=fetch)
        first = json.loads(journal.read_text()) if journal.exists() else {}
        final = json.loads(out.read_text()) if out.exists() else {}
        historical = final.get("recovery", {}).get("historical_worker_ids_not_reverified", [])
        fresh = [r["worker_id"] for r in final.get("receipts", [])
                 if r["technical_status"] == "VERIFIED_READONLY"]
        passed = (rc == 0 and len(attempts) == 3
                  and first.get("state") == "FAILED_INCOMPLETE"
                  and final.get("automatic_recovery_attempted") is True
                  and set(historical) == set(SMOKE_WORKERS)
                  and len(historical) == 4
                  and set(fresh) == {"AEOS-W03", "AEOS-W09"} and len(fresh) == 2
                  and final.get("technically_verified_readonly_count") == 2
                  and final.get("production_release_authorized") is False)
        return {
            "schema": "aeos2047-factory-recovery-smoke/1",
            "integration_status": "PASSED" if passed else "DEGRADED",
            "source_orders": "SYNTHETIC_CI_FIXTURE_NOT_SUPABASE_QUEUE",
            "interruption": "INJECTED_CI_FAULT_NOT_REAL_OUTAGE",
            "dispatch_attempts": len(attempts),
            "historical_worker_ids": historical,
            "fresh_verified_worker_ids": fresh,
            "fresh_verified_count": len(fresh),
            "historical_receipts_counted_as_new": 0,
            "automatic_recovery_attempted": final.get("automatic_recovery_attempted", False),
            "production_release_authorized": False,
            "persistent_scheduler_installed": False,
            "business_deliveries_verified": 0,
            "verified_revenue_usd": None,
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--central-cycle", action="store_true")
    modes.add_argument("--recovery-cycle", action="store_true")
    args = parser.parse_args(argv)
    try:
        jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
        if args.recovery_cycle:
            report = run_recovery_smoke(jobs, args.root)
            atomic_json(args.out, report)
            print("FACTORY_RECOVERY_SMOKE: " + report["integration_status"])
            return 0 if report["integration_status"] == "PASSED" else 2
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

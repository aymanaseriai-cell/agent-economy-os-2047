#!/usr/bin/env python3
"""Bounded central review cycle, using the existing executive operator."""
from __future__ import annotations
import argparse
import json
import os
import tempfile
from pathlib import Path
from automation.factory_operator import plan_dispatch, execute_reviewonly, PREFIX, ROLES
from automation.worker_dispatcher import PolicyError
from automation.worker_fleet import REGISTRY, make_task

def run_review_cycle(orders: list, live_jobs: list, root: Path, fetch=None) -> dict:
    """Consider each worker once per bounded review-only snapshot.

    Preserve executive ordering, isolate missing job evidence, and never
    mutate the production queue or promote technical probes to delivery.
    """
    initial = plan_dispatch(orders)
    if not isinstance(live_jobs, list) or len(live_jobs) > len(REGISTRY):
        raise PolicyError("INVALID_CYCLE_JOBS")
    available = {}
    for job in live_jobs:
        worker, _ = make_task(job)
        if worker.worker_id in available:
            raise PolicyError("DUPLICATE_LIVE_JOB")
        available[worker.worker_id] = job
    remaining = list(orders)
    receipts, decisions = [], []
    rounds = 0
    eligible = {"REVIEW_ONLY_ACTION_ELIGIBLE", "VERIFY_IN_PROGRESS_FIRST"}
    while remaining:
        plan = plan_dispatch(remaining)
        picked = [c for c in plan["selected"] if c["worker_id"] is not None]
        if not picked:
            break
        rounds += 1
        if rounds > len(REGISTRY):
            raise PolicyError("CYCLE_ROUND_CAP")
        ready_ids = {c["worker_id"] for c in picked
                     if c["disposition"] in eligible and c["worker_id"] in available}
        ready_orders = [o for o in remaining if o["work_key"][len(PREFIX):] in ready_ids]
        batch = execute_reviewonly(plan_dispatch(ready_orders), list(available.values()),
                                   root, fetch=fetch, source_orders=ready_orders)
        by_worker = {x["worker_id"]: x for x in batch["receipts"]}
        if set(by_worker) != ready_ids or len(by_worker) != len(batch["receipts"]):
            raise PolicyError("CYCLE_RECEIPT_SET_MISMATCH")
        receipts.extend(batch["receipts"])
        for choice in picked:
            worker_id = choice["worker_id"]
            receipt = by_worker.get(worker_id)
            if receipt is not None:
                result = ("TECHNICAL_READONLY_VERIFIED" if receipt["technical_status"] == "VERIFIED_READONLY"
                          else "PROBE_FAILED_OR_UNCERTAIN")
            elif choice["disposition"] in eligible:
                result = "BLOCKED_MISSING_JOB_EVIDENCE"
            else:
                result = choice["disposition"]
            decisions.append({**choice, "cycle_result": result})
        considered = {c["work_key"] for c in picked}
        remaining = [o for o in remaining if o["work_key"] not in considered]
    return {
        "schema": "aeos2047-bounded-review-cycle/1",
        "source_orders_sha256": initial["source_orders_sha256"],
        "rounds": rounds, "orders_inspected": len(orders),
        "configured_workers": len(REGISTRY), "executives": len(ROLES),
        "decisions": decisions, "receipts": receipts,
        "previously_verified_not_reexecuted": len(remaining),
        "dispatched_count": len(receipts),
        "technically_verified_readonly_count": sum(
            r["technical_status"] == "VERIFIED_READONLY" for r in receipts),
        "production_changes": False, "production_release_authorized": False,
        "business_deliveries_verified": 0, "verified_revenue_usd": None,
        "persistent_scheduler_installed": False,
        "cycle_status": ("DEGRADED" if any(d["cycle_result"] in ("BLOCKED_MISSING_JOB_EVIDENCE", "PROBE_FAILED_OR_UNCERTAIN") for d in decisions) else "REVIEW_COMPLETE"),
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--orders", type=Path, required=True)
    p.add_argument("--jobs", type=Path, required=True)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    temp = None
    try:
        result = run_review_cycle(json.loads(args.orders.read_text(encoding="utf-8")),
                                  json.loads(args.jobs.read_text(encoding="utf-8")), args.root)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.out.parent,
                                         delete=False) as handle:
            temp = Path(handle.name)
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, args.out)
        return 2 if result["cycle_status"] == "DEGRADED" else 0
    except (PolicyError, OSError, ValueError, TypeError, KeyError) as exc:
        print("FACTORY_CYCLE_FAIL_CLOSED: " + type(exc).__name__)
        return 2
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Bounded central review cycle, using the existing executive operator."""
from __future__ import annotations
import argparse
import json
import os
import tempfile
import uuid
from pathlib import Path
from automation.factory_operator import plan_dispatch, execute_reviewonly, PREFIX, ROLES
from automation.worker_dispatcher import PolicyError
from automation.worker_fleet import REGISTRY, make_task

def run_review_cycle(orders: list, live_jobs: list, root: Path, fetch=None, *, checkpoint=None) -> dict:
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
    def publish():
        if checkpoint is not None:
            checkpoint({
                "source_orders_sha256": initial["source_orders_sha256"],
                "rounds_completed": rounds,
                "decisions": list(decisions), "receipts": list(receipts),
                "orders_remaining": len(remaining),
            })
    publish()
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
        publish()
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


def run_live_review_cycle(orders: list, root: Path, fetch=None, *, checkpoint=None) -> dict:
    """Discover only eligible jobs; isolate provider failures before bounded dispatch."""
    from automation.worker_fleet_live import prepare_live_jobs
    from automation.worker_dispatcher import default_fetch

    # Validate the entire snapshot before any provider access.
    plan_dispatch(orders)
    provider = default_fetch if fetch is None else fetch
    jobs, unavailable = [], []
    for order in orders:
        if order["work_status"] not in ("QUEUED", "IN_PROGRESS"):
            continue
        worker_id = order["work_key"][len(PREFIX):]
        try:
            discovered = prepare_live_jobs(provider, selected_workers=[worker_id])
        except (ValueError, OSError, TypeError, KeyError):
            unavailable.append(worker_id)
            continue
        batch = discovered["jobs"]
        if not isinstance(batch, list) or len(batch) != 1:
            raise PolicyError("CYCLE_DISCOVERY_WORKER_MISMATCH")
        worker, _ = make_task(batch[0])
        if worker.worker_id != worker_id:
            raise PolicyError("CYCLE_DISCOVERY_WORKER_MISMATCH")
        jobs.extend(batch)
    result = run_review_cycle(orders, jobs, root, fetch=provider, checkpoint=checkpoint)
    result["discovery_blocked_worker_ids"] = sorted(unavailable)
    result["job_source"] = "SELECTED_ALLOWLISTED_PROVIDER_DISCOVERY"
    return result


def atomic_json(path: Path, value: dict):
    """Private, atomic local receipt write; never a production state transition."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=path.parent, delete=False) as handle:
            temp = Path(handle.name)
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--orders", type=Path, required=True)
    jobs_group = p.add_mutually_exclusive_group(required=True)
    jobs_group.add_argument("--jobs", type=Path)
    jobs_group.add_argument("--auto-live-jobs", action="store_true")
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--checkpoint", type=Path,
                   help="New private path for partial receipts; never reused as authorization")
    args = p.parse_args(argv)
    journal = None
    try:
        paths = [x.resolve() for x in (args.orders, args.jobs, args.out, args.checkpoint)
                 if x is not None]
        if len(paths) != len(set(paths)):
            raise PolicyError("CYCLE_PATH_COLLISION")
        if args.checkpoint is not None:
            args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation prevents two invocations sharing a journal.
            fd = os.open(args.checkpoint, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            journal = {"schema": "aeos2047-review-cycle-journal/1",
                       "run_id": uuid.uuid4().hex, "state": "IN_PROGRESS",
                       "production_release_authorized": False,
                       "business_deliveries_verified": 0,
                       "verified_revenue_usd": None,
                       "progress": None}
            atomic_json(args.checkpoint, journal)
        def checkpoint(progress):
            if journal is not None:
                journal["progress"] = progress
                atomic_json(args.checkpoint, journal)
        orders = json.loads(args.orders.read_text(encoding="utf-8"))
        if args.auto_live_jobs:
            result = run_live_review_cycle(orders, args.root, checkpoint=checkpoint)
        else:
            result = run_review_cycle(orders, json.loads(args.jobs.read_text(encoding="utf-8")), args.root, checkpoint=checkpoint)
        if journal is not None:
            result["run_id"] = journal["run_id"]
        atomic_json(args.out, result)
        if journal is not None:
            journal["state"] = "FINAL_REPORT_WRITTEN"
            journal["cycle_status"] = result["cycle_status"]
            atomic_json(args.checkpoint, journal)
        return 2 if result["cycle_status"] == "DEGRADED" else 0
    except (PolicyError, OSError, ValueError, TypeError, KeyError) as exc:
        if journal is not None:
            journal["state"] = "FAILED_INCOMPLETE"
            journal["error_class"] = type(exc).__name__
            try:
                atomic_json(args.checkpoint, journal)
            except OSError:
                pass  # Last successfully persisted checkpoint remains incomplete.
        print("FACTORY_CYCLE_FAIL_CLOSED: " + type(exc).__name__)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate twelve allowlisted read-only worker jobs from current GitHub evidence."""
import argparse
import json
import sys
from pathlib import Path
from automation.worker_dispatcher import (default_fetch, GITHUB_ISSUES_LIST,
    MAIN_BRANCH_URL, MAIN_CI_RUNS_URL, CI_WORKFLOW_PATH, CI_REPOSITORY,
    _open_inbound_snapshot, _fetch_open_issues)
from automation.worker_fleet import REGISTRY, make_task


class LivePlanError(ValueError):
    pass


def _current_ci(fetch):
    branch = fetch(MAIN_BRANCH_URL)
    sha = (branch.get("commit") or {}).get("sha") if isinstance(branch, dict) else None
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise LivePlanError("MAIN_SHA_NOT_VERIFIED")
    runs = fetch(MAIN_CI_RUNS_URL)
    if not isinstance(runs, dict) or not isinstance(runs.get("workflow_runs"), list):
        raise LivePlanError("MAIN_CI_UNAVAILABLE")
    # Only the canonical CI workflow in this exact repository can prove CI.
    # An older completed success must not hide a newer queued/failing run.
    matches = [x for x in runs["workflow_runs"][:20] if isinstance(x, dict)
               and x.get("head_sha") == sha
               and x.get("path") == CI_WORKFLOW_PATH
               and isinstance(x.get("repository"), dict)
               and x["repository"].get("full_name") == CI_REPOSITORY
               and type(x.get("id")) is int and x["id"] > 0]
    if not matches:
        raise LivePlanError("NO_CURRENT_MAIN_CANONICAL_CI")
    current_ci = max(matches, key=lambda x: x["id"])
    if current_ci.get("status") != "completed":
        raise LivePlanError("LATEST_CI_NOT_COMPLETED")
    return sha, current_ci["id"]


def prepare_live_jobs(fetch=default_fetch, *, selected_workers=None):
    """Prepare selected capabilities without unrelated provider dependencies."""
    if selected_workers is None:
        selected = list(REGISTRY)
    else:
        if (not isinstance(selected_workers, (list, tuple))
                or not 1 <= len(selected_workers) <= len(REGISTRY)
                or any(not isinstance(w, str) or w not in REGISTRY
                       for w in selected_workers)
                or len(set(selected_workers)) != len(selected_workers)):
            raise LivePlanError("INVALID_SELECTED_WORKERS")
        selected = list(selected_workers)
    sha = run_id = candidate_count = None
    if {"AEOS-W04", "AEOS-W05"}.intersection(selected):
        sha, run_id = _current_ci(fetch)
    issue = None
    if "AEOS-W08" in selected:
        candidates = _open_inbound_snapshot(_fetch_open_issues(fetch))
        candidate_count = candidates["candidate_count"]
        eligible = candidates["eligible_external_candidates"]
        issue = eligible[0]["issue_number"] if eligible else 112
    jobs = []
    for worker_id in selected:
        worker = REGISTRY[worker_id]
        if worker_id in ("AEOS-W04", "AEOS-W05"):
            payload = {"run_id": run_id, "expected_head_sha": sha}
        elif worker_id == "AEOS-W08":
            payload = {"issue_number": issue}
        elif worker_id == "AEOS-W12":
            payload = {"issue_number": 112}
        else:
            payload = worker.default_payload
        job = {"worker_id": worker_id, "payload": payload, "max_attempts": 2}
        make_task(job)
        jobs.append(job)
    return {"jobs": jobs, "head_sha": sha, "ci_run": run_id,
            "candidate_count": candidate_count,
            "verified_customers": None, "verified_revenue_usd": None}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        plan = prepare_live_jobs()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(plan["jobs"], indent=2) + "\n", encoding="utf-8")
        print("WORKER_LIVE_PLAN: 12 read-only tasks; external candidates=%d; revenue unknown" % plan["candidate_count"])
        return 0
    except (LivePlanError, ValueError, TypeError, OSError, KeyError) as exc:
        print("WORKER_LIVE_PLAN_BLOCKED: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

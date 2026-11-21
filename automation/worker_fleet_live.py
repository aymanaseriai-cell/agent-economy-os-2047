#!/usr/bin/env python3
"""Generate twelve allowlisted read-only worker jobs from current GitHub evidence."""
import argparse
import json
import sys
from pathlib import Path
from automation.worker_dispatcher import (default_fetch, GITHUB_ISSUES_LIST,
    MAIN_BRANCH_URL, MAIN_CI_RUNS_URL, _open_inbound_snapshot)
from automation.worker_fleet import REGISTRY, make_task


class LivePlanError(ValueError):
    pass


def prepare_live_jobs(fetch=default_fetch):
    branch = fetch(MAIN_BRANCH_URL)
    sha = (branch.get("commit") or {}).get("sha") if isinstance(branch, dict) else None
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise LivePlanError("MAIN_SHA_NOT_VERIFIED")
    runs = fetch(MAIN_CI_RUNS_URL)
    if not isinstance(runs, dict) or not isinstance(runs.get("workflow_runs"), list):
        raise LivePlanError("MAIN_CI_UNAVAILABLE")
    matches = [x for x in runs["workflow_runs"][:20] if isinstance(x, dict)
               and x.get("head_sha") == sha and x.get("status") == "completed"
               and type(x.get("id")) is int and x["id"] > 0]
    if not matches:
        raise LivePlanError("NO_COMPLETED_CI_FOR_CURRENT_MAIN")
    current_ci = matches[0]  # If failure, dispatcher must report failure, never a pass.
    candidates = _open_inbound_snapshot(fetch(GITHUB_ISSUES_LIST))
    issue = candidates["eligible_external_candidates"][0]["issue_number"] if candidates["eligible_external_candidates"] else 112
    ci = {"run_id": current_ci["id"], "expected_head_sha": sha}
    entries = [
        ("AEOS-W01", {}), ("AEOS-W02", {}), ("AEOS-W03", {"path": "verifier.py"}),
        ("AEOS-W04", ci), ("AEOS-W05", ci), ("AEOS-W06", {"issue_number": 98}),
        ("AEOS-W07", {}), ("AEOS-W08", {"issue_number": issue}),
        ("AEOS-W09", {"path": "docs/ENTERPRISE_EVIDENCE_PILOT.md"}),
        ("AEOS-W10", {"path": "buyer-gate/README.md"}),
        ("AEOS-W11", {}), ("AEOS-W12", {"issue_number": 112}),
    ]
    jobs = [{"worker_id": worker_id, "payload": payload, "max_attempts": 2}
            for worker_id, payload in entries]
    if len(jobs) != len(REGISTRY) or len({j["worker_id"] for j in jobs}) != 12:
        raise LivePlanError("FLEET_NOT_TWELVE")
    for job in jobs:
        make_task(job)
    return {"jobs": jobs, "head_sha": sha, "ci_run": current_ci["id"],
            "candidate_count": candidates["candidate_count"],
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

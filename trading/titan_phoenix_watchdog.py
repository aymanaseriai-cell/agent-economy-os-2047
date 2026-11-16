#!/usr/bin/env python3
"""TITAN Phoenix: conservative GitHub run watchdog for previously authorized LIVE.

A deterministic recovery classifier. It has NO private exchange API access.
It NEVER repairs arbitrary code, bypasses risk vetoes or dispatches orders.
A separate Workflow does the GitHub dispatch only after this module approves
a previously clean, explicitly armed continuous trading session.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

MIN_QUIET_MS = 9 * 60 * 1000
MAX_QUIET_MS = 60 * 60 * 1000
EXPECTED_JOB_STEPS = (
    "Preflight owner stop switches before LIVE worker starts",
    "Five-second continuous worker within bounded GitHub job",
    "Chain another session after 20 seconds (clean bounded exit only)",
)
WORKFLOW_PATH = ".github/workflows/okx-guarded-execution.yml"


def _timestamp_ms(value):
    if not isinstance(value, str):
        raise ValueError("Missing verified GitHub run time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone missing")
    return int(parsed.timestamp() * 1000)


def _decision(status, reason, *, last_run=None):
    return {"mode": "PHOENIX_OWNER_GUARDED_WATCHDOG",
            "action": status, "reason": reason,
            "last_run_id": last_run,
            "order_count": 0,
            "modifies_stop_switches": False,
            "auto_repairs_code": False}


def decide(evidence, *, now_ms=None):
    """Read-only verdict. Unknown evidence always means NO DISPATCH."""
    if not isinstance(evidence, dict):
        return _decision("STOP","invalid_evidence")
    flags=evidence.get("flags")
    if not isinstance(flags, dict):
        return _decision("STOP","missing_owner_flags")
    if flags.get("OKX_STOP_CONTINUOUS") != "NO":
        return _decision("STOP","owner_stop_active_or_unverified")
    if flags.get("OKX_ENABLE_REAL_TRADING") != "YES":
        return _decision("STOP","live_trading_disabled")
    if flags.get("OKX_EXECUTION_MODE") != "live":
        return _decision("STOP","live_mode_unverified")
    # Explicit arm is independent of live permission and must be set by owner
    # after the existing manually disabled workflow is intentionally enabled.
    if flags.get("OKX_PHOENIX_RESUME_ARM") != "YES":
        return _decision("STOP","phoenix_resumption_not_armed")
    if evidence.get("workflow_state") != "active":
        return _decision("STOP","live_workflow_disabled_or_unknown")

    runs=evidence.get("runs")
    if not isinstance(runs,list) or not runs:
        return _decision("STOP","no_prior_verified_run")
    if len(runs)>20 or any(not isinstance(r,dict) for r in runs):
        return _decision("STOP","untrusted_run_collection")
    # Pick latest chronological run, not just arbitrary API array order.
    try:
        ordered=sorted(runs,key=lambda r:(_timestamp_ms(r.get("created_at")),r.get("id",0)),
                       reverse=True)
    except (TypeError,ValueError):
        return _decision("STOP","untrusted_run_chronology")
    last=ordered[0]
    run_id=last.get("id")
    if not isinstance(run_id,int) or run_id<1:
        return _decision("STOP","untrusted_last_run")
    if any(r.get("status") in ("queued","waiting","in_progress","pending","requested")
           for r in ordered):
        return _decision("WAIT","existing_run_active_or_queued",last_run=run_id)
    if last.get("path") != WORKFLOW_PATH:
        return _decision("STOP","unexpected_workflow_identity",last_run=run_id)
    if last.get("event") != "workflow_dispatch" or last.get("head_branch") != "main":
        return _decision("STOP","not_a_prior_manual_main_session",last_run=run_id)
    if last.get("status") != "completed" or last.get("conclusion") != "success":
        return _decision("STOP","failed_or_uncertain_run_requires_review",last_run=run_id)
    try:
        ended=_timestamp_ms(last.get("updated_at"))
        now=int(time.time()*1000) if now_ms is None else int(now_ms)
        idle=now-ended
    except (TypeError,ValueError,OverflowError):
        return _decision("STOP","untrusted_run_completion_time",last_run=run_id)
    if idle<0:
        return _decision("STOP","future_completion_time",last_run=run_id)
    if idle<MIN_QUIET_MS:
        return _decision("WAIT","ordinary_20_second_chaining_window",last_run=run_id)
    if idle>MAX_QUIET_MS:
        return _decision("STOP","old_session_requires_fresh_manual_authorization",
                         last_run=run_id)
    jobs=evidence.get("last_run_jobs")
    if not isinstance(jobs,list) or len(jobs)!=1:
        return _decision("STOP","last_job_evidence_missing_or_ambiguous",last_run=run_id)
    job=jobs[0]
    if job.get("status")!="completed" or job.get("conclusion")!="success":
        return _decision("STOP","last_job_not_successful",last_run=run_id)
    steps=job.get("steps")
    if not isinstance(steps,list):
        return _decision("STOP","missing_workflow_step_evidence",last_run=run_id)
    for required in EXPECTED_JOB_STEPS:
        matching=[s for s in steps if s.get("name")==required]
        if len(matching)!=1 or matching[0].get("conclusion")!="success":
            return _decision("STOP","not_a_verified_continuous_live_session",
                             last_run=run_id)
    return _decision("RESUME_CLEAN_SESSION","clean_chain_stalled_over_nine_minutes",
                     last_run=run_id)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    evidence=json.loads(Path(args.input).read_text(encoding="utf-8"))
    report=decide(evidence)
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("TITAN PHOENIX WATCHDOG: "+report["action"]+" / "+report["reason"])
    print("No order placement. No account keys. No kill-switch changes.")


if __name__ == "__main__":
    main()

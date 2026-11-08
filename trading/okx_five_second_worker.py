#!/usr/bin/env python3
"""TITAN QUANT2037 continuous worker.

A five-second *pause after each completed full scan/decision cycle*, NOT a
guarantee that the original 6+7 analysis finishes within five seconds.
A persistent host can run this as one long-lived process. GitHub Actions
cron cannot schedule every five seconds; its minimum is five minutes.

Uses the ORIGINAL public 6+7 scanner and original guarded executor, unchanged.
NO new order endpoints. Unknown execution status, network failure, blocked
risk check, or any submitted order stops this process instead of blind retries.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from typing import Callable

INTERVAL_SECONDS = 5
ALLOWED_NONORDER_STATUSES = frozenset(("NO_CONSENSUS","DRY_RUN_SIGNAL_ONLY"))

def command(args, *, timeout):
    """Subprocess is sequential, and any unknown-order timeout aborts."""
    try:
        proc = subprocess.run(args, check=False, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        print("Execution or market scan timed out; stop instead of blind retry",
              file=sys.stderr,flush=True)
        return subprocess.CompletedProcess(args,124,"","")
    if proc.stdout:
        print(proc.stdout,end="" if proc.stdout.endswith("\n") else "\n",flush=True)
    if proc.stderr:
        print(proc.stderr,end="" if proc.stderr.endswith("\n") else "\n",
              file=sys.stderr,flush=True)
    return proc

def loop(*, interval_seconds=INTERVAL_SECONDS, max_cycles=0,
         max_runtime_seconds=0, top=12, report="reports/okx_six_agents.json",
         run:Callable=command, clock:Callable=time.monotonic,
         sleep:Callable=time.sleep, graceful_public_deadline=False):
    """Fail-closed full analysis, then executor; 5-sec pause between decisions.

    0 max_cycles = unlimited. 0 max_runtime = unlimited.
    In a GitHub job use a bounded runtime to stay inside job timeouts.
    A persistent machine can use unlimited mode.
    """
    if interval_seconds!=INTERVAL_SECONDS:
        raise ValueError("TITAN 5-second cadence is fixed at 5 seconds")
    if not 1<=top<=12:
        raise ValueError("top must be 1..12")
    if max_cycles<0 or max_runtime_seconds<0:
        raise ValueError("Nonnegative cycle/runtime limits required")
    if not isinstance(report,str) or not report or report.startswith("-"):
        raise ValueError("Invalid report path")
    if graceful_public_deadline:
        # This mode is ONLY for public market research. In particular, never
        # silently treat a timeout during live order execution as success.
        if (os.getenv("OKX_EXECUTION_MODE") != "dry_run"
                or os.getenv("OKX_ENABLE_REAL_TRADING") != "NO"
                or not max_runtime_seconds):
            raise ValueError("Graceful public deadline requires NO/dry_run and bounded runtime")
    start=clock()
    scans=0
    while True:
        if max_cycles and scans>=max_cycles:
            print("TITAN 5-second worker reached cycle limit",flush=True)
            return 0
        remaining=(start+max_runtime_seconds-clock()) if max_runtime_seconds else None
        if remaining is not None and remaining < (35 if graceful_public_deadline else 15):
            print("TITAN bounded runtime reached; no new market scan started", flush=True)
            return 0
        scans+=1
        print(f"TITAN cycle {scans} start; full public council scan",flush=True)
        # Hold back 15 seconds for a controlled exit at the end of a GitHub
        # public-research job. The earlier code gave the scan all remaining
        # seconds and flagged normal deadline exhaustion as a hard failure.
        scan_timeout=(90 if remaining is None else
                      min(90, max(1, remaining - 15 if graceful_public_deadline else remaining)))
        scan=run([sys.executable,"-m","trading.six_agent_council",
                  "--top",str(top),"--out",report],timeout=scan_timeout)
        if scan.returncode!=0:
            if (graceful_public_deadline and scan.returncode==124
                    and scan_timeout<90):
                print("TITAN public research window ended during an incomplete final scan; "
                      "no orders, previous completed scans retained",flush=True)
                return 0
            print("TITAN market scan failed; stop without orders",file=sys.stderr,flush=True)
            return 2
        if graceful_public_deadline and clock()+10 >= start+max_runtime_seconds:
            print("TITAN public research window ended after scan; "
                  "no executor started, no orders",flush=True)
            return 0
        # The existing guarded executor refuses live access unless all original
        # independent arm tokens, configured risk checks and NVIDIA veto pass.
        # Even in dry_run, no private OKX endpoint or order is called.
        result=run([sys.executable,"-m","trading.okx_live_executor",
                    "--report",report],timeout=120)
        if result.returncode!=0:
            print("TITAN executor blocked; stop, no blind retry",
                  file=sys.stderr,flush=True)
            return result.returncode
        statuses=[line.partition("OKX EXECUTION RESULT: ")[2].strip()
                  for line in result.stdout.splitlines()
                  if line.startswith("OKX EXECUTION RESULT: ")]
        if len(statuses)!=1:
            print("TITAN executor missing/ambiguous status; stop",
                  file=sys.stderr,flush=True)
            return 3
        status=statuses[0]
        if status not in ALLOWED_NONORDER_STATUSES:
            # This includes AI_VETO_NO_ORDER: do NOT retry a trade the risk
            # council rejected. Filled/partial/uncertain outcomes also stop.
            # Live execution never treats a missing or error status as safe.
            print("TITAN executor outcome: "+status+
                  "; stop to prevent duplicate or rejected orders",flush=True)
            return 0
        if max_cycles and scans>=max_cycles:
            return 0
        if max_runtime_seconds and clock()+interval_seconds+15>start+max_runtime_seconds:
            print("TITAN bounded runtime reached",flush=True)
            return 0
        print(f"TITAN waiting exactly {INTERVAL_SECONDS}s after completed cycle",
              flush=True)
        sleep(INTERVAL_SECONDS)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval-seconds",type=int,default=INTERVAL_SECONDS)
    parser.add_argument("--max-cycles",type=int,default=0,
                        help="0 means continuous; stop on failure or order")
    parser.add_argument("--max-runtime-seconds",type=int,default=0,
                        help="0 means unbounded; GitHub Actions must use bounded")
    parser.add_argument("--graceful-public-deadline",action="store_true",
                        help="Only in forced NO/dry_run: cleanly stop incomplete final "
                             "public scan at scheduled job deadline")
    parser.add_argument("--top",type=int,default=12)
    parser.add_argument("--report",default="reports/okx_six_agents.json")
    args=parser.parse_args()
    try:
        return loop(interval_seconds=args.interval_seconds,max_cycles=args.max_cycles,
                    max_runtime_seconds=args.max_runtime_seconds,
                    top=args.top,report=args.report,
                    graceful_public_deadline=args.graceful_public_deadline)
    except ValueError as exc:
        print("Invalid TITAN configuration: "+str(exc),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())

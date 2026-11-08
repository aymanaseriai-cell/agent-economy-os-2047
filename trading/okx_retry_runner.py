"""Bounded retry scanner: wait five seconds after NO_CONSENSUS; never retry blocked trades."""
import argparse
import subprocess
import sys
import time

def run_command(args, *, timeout=None):
    try:
        r=subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        print("Public scan exceeded timeout; no trade attempted",file=sys.stderr)
        return subprocess.CompletedProcess(args,124,"","")
    if r.stdout:
        print(r.stdout,end="" if r.stdout.endswith("\n") else "\n",flush=True)
    if r.stderr:
        print(r.stderr,end="" if r.stderr.endswith("\n") else "\n",file=sys.stderr,flush=True)
    return r

def retry_scans(*, max_cycles=8, delay_seconds=5, window_seconds=245,
                report="reports/okx_six_agents.json",
                run=run_command,clock=time.monotonic,sleep=time.sleep):
    """Every full scan takes ~20s; five seconds is the PAUSE, not the scan period."""
    if not 1 <= max_cycles <= 30 or not 1 <= delay_seconds <= 60 or not 30 <= window_seconds <= 540:
        raise ValueError("Invalid retry settings")
    deadline=clock()+window_seconds
    scan_args=[sys.executable,"-m","trading.six_agent_council",
               "--top","12","--out",report]
    execute_args=[sys.executable,"-m","trading.okx_live_executor","--report",report]
    for attempt in range(1,max_cycles+1):
        remaining=deadline-clock()
        if remaining < 15:
            print("Retry session ended: next scheduled run will scan again")
            return 0
        print(f"Public scan {attempt}/{max_cycles}",flush=True)
        scan=run(scan_args,timeout=min(90,remaining))
        if scan.returncode:
            print("Public scan failed, stopping without blind retry",file=sys.stderr)
            return 2
        result=run(execute_args,timeout=None)
        if result.returncode:
            print("Executor blocked or failed: no further retries",file=sys.stderr)
            return result.returncode
        statuses=[line.partition("OKX EXECUTION RESULT: ")[2].strip()
                  for line in result.stdout.splitlines()
                  if line.startswith("OKX EXECUTION RESULT: ")]
        if statuses != ["NO_CONSENSUS"]:
            print("Executor returned a non-empty outcome; stop to prevent duplicate orders")
            return 0
        if attempt==max_cycles or deadline-clock() < delay_seconds+15:
            print("No consensus; bounded retry session complete")
            return 0
        print(f"No consensus; next full scan begins after {delay_seconds} seconds")
        sleep(delay_seconds)
    return 0

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-cycles",type=int,default=8)
    p.add_argument("--delay-seconds",type=float,default=5)
    p.add_argument("--window-seconds",type=float,default=245)
    p.add_argument("--report",default="reports/okx_six_agents.json")
    a=p.parse_args()
    try:
        return retry_scans(max_cycles=a.max_cycles,delay_seconds=a.delay_seconds,
                           window_seconds=a.window_seconds,report=a.report)
    except ValueError as exc:
        print(str(exc),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())

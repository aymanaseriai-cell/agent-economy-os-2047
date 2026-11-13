#!/usr/bin/env python3
"""TITAN 2037 Flight Recorder: GitHub run-log research only, never orders."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re

PATTERNS = {
    "cycle": re.compile(r"TITAN cycle \d+ start"),
    "scan": re.compile(r"SIX AGENTS \+ QUANT2037:\s*selected=\s*(\d+)\s+analyzed=\s*(\d+)\s+signals=\s*(\d+)\s+errors=\s*(\d+)"),
    "universe": re.compile(r"TITAN SAME-BATCH UNIVERSE:.*?screened=\s*(\d+)"),
    "result": re.compile(r"OKX EXECUTION RESULT:\s*([A-Z_]+)"),
    "positions": re.compile(r"OKX PORTFOLIO SLOTS:\s*open=(\d+)\s+limit=(\d+)\s+remaining=(\d+)"),
    "veto": re.compile(r"TITAN VETO BREAKDOWN:\s*advanced=\s*(\{[^{}]{0,1500}\})\s+omega=\s*(\{[^{}]{0,1500}\})"),
    "gates": re.compile(r"TITAN SIGNAL DIAGNOSTICS:.*?consensus_entries=\s*(\d+)"),
    "clock": re.compile(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z"),
}
STATES = {"NO_CONSENSUS", "FILLED_PROTECTED", "REENTRY_COOLDOWN_NO_ORDER",
          "DRY_RUN_SIGNAL_ONLY", "POSITION_OPEN_PROTECTED", "SKIPPED_NO_CAPITAL"}

def timestamp(line):
    m = PATTERNS["clock"].search(line)
    if m is None:
        return None
    try:
        return datetime.fromisoformat(m.group().replace("Z","+00:00")).timestamp()
    except ValueError:
        return None

def parse_log(run_id, log):
    if type(run_id) is not int or run_id < 1 or not isinstance(log,str):
        raise ValueError("Invalid run metadata")
    if len(log.encode("utf-8")) > 6000000:
        raise ValueError("Oversize log")
    results = Counter()
    reasons = Counter()
    scans = 0
    cycles = 0
    analyzed = 0
    errors = 0
    screened = []
    positions = []
    accepted = 0
    observed_times = []
    previous = None
    stopped = False
    for line in log.splitlines():
        if PATTERNS["cycle"].search(line):
            cycles += 1
        m = PATTERNS["scan"].search(line)
        if m:
            scans += 1
            analyzed += int(m.group(2))
            errors += int(m.group(4))
        m = PATTERNS["universe"].search(line)
        if m:
            screened.append(int(m.group(1)))
        m = PATTERNS["positions"].search(line)
        if m:
            opened, maximum, available = [int(x) for x in m.groups()]
            if opened > maximum or available != maximum-opened:
                raise ValueError("Portfolio positions contradict limits")
            positions.append(opened)
        m = PATTERNS["gates"].search(line)
        if m:
            accepted += int(m.group(1))
        m = PATTERNS["veto"].search(line)
        if m:
            for raw in m.groups():
                values = json.loads(raw)
                if not isinstance(values,dict) or len(values)>30:
                    raise ValueError("Malformed veto dictionary")
                for key, value in values.items():
                    if not isinstance(key,str) or not key or len(key)>90 or type(value) is not int or value<0:
                        raise ValueError("Invalid veto counter")
                    reasons[key] += value
        m = PATTERNS["result"].search(line)
        if m:
            state = m.group(1)
            results[state if state in STATES else "OTHER_REDACTED"] += 1
            now = timestamp(line)
            if now is not None:
                if previous is not None and now >= previous:
                    observed_times.append(round(now-previous,3))
                previous = now
        if "STOP INTERLOCK:" in line:
            stopped = True
    observed_times.sort()
    return {
        "run_id":run_id, "cycles":cycles, "scan_count":scans,
        "market_analyses_including_repeats":analyzed,
        "scan_error_count":errors, "max_screened":max(screened) if screened else None,
        "min_screened":min(screened) if screened else None,
        "gated_candidates":accepted,
        "logged_outcomes":dict(sorted(results.items())),
        "veto_counts":dict(sorted(reasons.items())),
        "last_logged_open_positions":positions[-1] if positions else None,
        "max_logged_open_positions":max(positions) if positions else None,
        "median_result_interval_seconds":observed_times[len(observed_times)//2] if observed_times else None,
        "owner_stop_observed":stopped,
        "has_evidence":bool(scans or results or positions),
    }

def summarize(runs):
    if not isinstance(runs,list) or len(runs)>20:
        raise ValueError("Invalid runs list")
    if len({r["run_id"] for r in runs}) != len(runs):
        raise ValueError("Duplicate run id")
    outcomes = Counter()
    vetoes = Counter()
    for r in runs:
        outcomes.update(r["logged_outcomes"])
        vetoes.update(r["veto_counts"])
    deep = sum(r["scan_count"] for r in runs)
    positions = {str(r["run_id"]):r["last_logged_open_positions"] for r in runs}
    return {
        "project":"TITAN_2037_FLIGHT_RECORDER",
        "agents":{
            "cadence_observer":{"status":"OBSERVED_ONLY_NOT_FIVE_SECOND_GUARANTEE","medians_by_run":{str(r["run_id"]):r["median_result_interval_seconds"] for r in runs}},
            "coverage_accountant":{"status":"REPEATED_MARKETS_NOT_UNIQUE_COINS","deep_scans":deep,"market_analyses_including_repeats":sum(r["market_analyses_including_repeats"] for r in runs)},
            "veto_root_cause":{"status":"DESCRIPTIVE_COUNTS_NOT_PNL","reasons":dict(sorted(vetoes.items()))},
            "portfolio_witness":{"status":"HISTORICAL_LOG_ONLY_NOT_CURRENT_ACCOUNT","last_by_run":positions},
            "execution_truth":{"status":"WORKER_RESULT_NOT_INDEPENDENT_EXCHANGE_FILL_PROOF","protected_entries_reported":outcomes["FILLED_PROTECTED"]},
            "cooldown_auditor":{"status":"CANNOT_VERIFY_EXCHANGE_30_SECOND_COOLDOWN_FROM_LOGS","cooldown_results":outcomes["REENTRY_COOLDOWN_NO_ORDER"]},
            "stop_governor":{"status":"READ_ONLY_NO_ORDER_ROUTES","stop_interlock_runs":sum(r["owner_stop_observed"] for r in runs),"auto_enable_live":False},
        },
        "runs_parsed":len(runs),
        "runs_with_evidence":sum(r["has_evidence"] for r in runs),
        "outcomes":dict(sorted(outcomes.items())),
        "runs":runs,
        "orders_submitted":0, "live_settings_changes":0,
        "claim":"Read-only GitHub log metrics. No independent fill, profit or safety guarantee."
    }

def load_directory(path):
    if not path.is_dir():
        raise ValueError("Missing logs directory")
    files = sorted((p for p in path.iterdir() if p.is_file() and re.fullmatch(r"[0-9]{1,20}\.log",p.name)),key=lambda p:int(p.stem))
    if len(files)>20:
        raise ValueError("Too many logs")
    runs = []
    for p in files:
        if p.stat().st_size>6000000:
            raise ValueError("Oversize file")
        runs.append(parse_log(int(p.stem),p.read_text(encoding="utf-8")))
    return summarize(runs)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log-dir",required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()
    result=load_directory(Path(a.log_dir))
    target=Path(a.out)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("FLIGHT RECORDER:",result["runs_parsed"],"runs; zero orders")
if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""Download sampled PUBLIC scan artifacts from this repository with GitHub CLI.

Only the GitHub Actions read-only token is needed; never OKX API credentials.
Artifact downloads are not a permanent immutable ledger.
"""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path
from .shadow_observatory import utc_ms

WINDOW_DAYS=15
BUCKET_MS=2*3600*1000
MAX_DOWNLOADS=180

def choose_runs(runs, now_ms, *, window_days=WINDOW_DAYS,
                bucket_ms=BUCKET_MS,max_downloads=MAX_DOWNLOADS):
    """Predeclared 2h sampling; never select based on signal success/outcome."""
    if not runs:return []
    candidates={}
    cutoff=now_ms-window_days*86_400_000
    for item in runs:
        if item.get("conclusion")!="success":continue
        stamp=utc_ms(item["createdAt"])
        if stamp<cutoff or stamp>now_ms:continue
        key=stamp//bucket_ms
        rid=int(item["databaseId"])
        old=candidates.get(key)
        if old is None or stamp<old[0] or (stamp==old[0] and rid<old[1]):
            candidates[key]=(stamp,rid)
    return [rid for _,rid in sorted(candidates.values())][-max_downloads:]

def run_download(target,limit=180,executor=subprocess.run,now_ms=None):
    import time
    now_ms=int(time.time()*1000) if now_ms is None else now_ms
    target=Path(target);target.mkdir(parents=True,exist_ok=True)
    completed=executor(["gh","run","list","--workflow","okx-six-agent-council.yml",
           "--limit","1750","--json","databaseId,createdAt,conclusion"],
           check=True,capture_output=True,text=True,timeout=90)
    ids=choose_runs(json.loads(completed.stdout),now_ms,max_downloads=limit)
    found=0;missing=0
    for rid in ids:
        folder=target/str(rid)
        folder.mkdir(parents=True,exist_ok=True)
        try:
            executor(["gh","run","download",str(rid),
                       "--name","quant2037-shadow-evidence","--dir",str(folder)],
                     check=True,capture_output=True,text=True,timeout=45)
            if not (folder/"quant2037_snapshot.json").exists():
                raise ValueError("Downloaded artifact missing snapshot")
            found+=1
        except (subprocess.CalledProcessError,ValueError,
                subprocess.TimeoutExpired):
            missing+=1
    return {"selected":len(ids),"downloaded":found,"unavailable":missing,
            "sampling":"earliest successful scan within each fixed 2h UTC bucket",
            "no_signal_or_outcome_based_selection":True}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir",required=True)
    p.add_argument("--limit",type=int,default=180)
    args=p.parse_args()
    if not 1<=args.limit<=180:p.error("limit must be 1..180")
    print(json.dumps(run_download(args.outdir,args.limit),sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())

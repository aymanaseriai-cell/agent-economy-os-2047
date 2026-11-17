#!/usr/bin/env python3
"""Independent 90d 6-market replication of FROZEN TITAN Q6, NO ORDERS.

Exact same Q6 signals, leverage, sizing, 4h feature-to-15m fill conversion,
entry/exit/fee rules, training selection, goal and holdout scoring. Markets
are a new public-name-hash-selected basket, with all previously observed Q4,
Q5, H128 and first Q6 symbols explicitly excluded. No return-based tuning.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from trading import titan_q6_4h_swing_128 as q6
from trading.edge_lab import fetch_history

REPLICATION_ID="TITAN-Q6-UNCHANGED-INDEPENDENT-MARKETS-20261117-R1"
PREVIOUS_BASKETS=set((
    "ATOM ONDO WLD LTC AVAX OP GRT RENDER CHZ WIF ZK MASK "
    "BLUR MINA ETHFI AR YGG LPT ZIL STX BONK PENGU IMX "
    "ARB BCH ETC JUP ZRX NEAR"
).split())
ALLOWED= q6.UNIVERSE-PREVIOUS_BASKETS-q6.FORBIDDEN

def catalogue():
    url="https://www.okx.com/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-Q6-REPLICATION-READ-ONLY"}),
                 timeout=35) as h:raw=json.load(h)
    if raw.get("code")!="0":raise ValueError("Public market list unavailable")
    cutoff=int(time.time()*1000)-120*86400000
    candidates=[]
    for spec in raw.get("data",[]):
        sym=spec.get("instId","")
        if not sym.endswith("-USDT-SWAP"):continue
        coin=sym[:-10]
        if (coin not in ALLOWED or spec.get("state")!="live" or
            spec.get("ctType")!="linear" or spec.get("ctValCcy")!=coin):
            continue
        try:
            if int(spec["listTime"])>cutoff:continue
            val=[float(spec[k]) for k in ("ctVal","lotSz","minSz")]
            if not all(math.isfinite(v) and v>0 for v in val):continue
        except (ValueError,KeyError,TypeError):continue
        candidates.append(spec)
    candidates.sort(key=lambda s:hashlib.sha256(
        (REPLICATION_ID+"|"+s["instId"]).encode()).hexdigest())
    if len(candidates)<q6.N_MARKETS:
        raise ValueError("Not enough new precommitted, non-overlapping markets")
    return candidates[:q6.N_MARKETS],len(candidates)

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True)
    ap.add_argument("--raw-dir",required=True)
    opts=ap.parse_args(argv)
    cohort,n=catalogue()
    print("Q6R INDEPENDENT HASHED COHORT BEFORE RETURNS",n,
          [s["instId"] for s in cohort],flush=True)
    now=int(time.time()*1000);markets={};specs={};sha={}
    raw=Path(opts.raw_dir);raw.mkdir(parents=True,exist_ok=True)
    for spec in cohort:
        sym=spec["instId"]
        bars=fetch_history(sym,q6.DAYS,now_ms=now)
        if len(bars)<q6.MIN_BARS:raise ValueError("Historical data incomplete "+sym)
        payload=json.dumps(bars,separators=(",",":")).encode()
        digest=hashlib.sha256(payload).hexdigest()
        with gzip.open(raw/(sym+".json.gz"),"wb") as h:h.write(payload)
        specs[sym]=spec;markets[sym]=bars;sha[sym]=digest
        print("Q6R REAL UNSEEN 15M OHLC",sym,len(bars),digest,flush=True)
    report=q6.evaluate(markets,specs,sha)
    report["replication_id"]=REPLICATION_ID
    report["replication_of_study"]=q6.STUDY
    report["no_parameter_change_since_initial_q6"]=True
    report["prior_cohort_symbols_excluded"]=sorted(PREVIOUS_BASKETS)
    report["replication_note"]=(
        "Name-hashed new crypto markets, overlapping historical time regime. "
        "A historical market replication is not independent future validation.")
    out=Path(opts.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    for policy,v in report["results"].items():
        print("Q6R RETURN",policy,
              "TRAIN",v["train"]["stress"]["return_pct"],
              "H1",v["holdout_1"]["stress"]["return_pct"],
              "H2",v["holdout_2"]["stress"]["return_pct"],
              "ALL",v["all_holdouts"]["stress"]["return_pct"],flush=True)
    print("Q6R FINAL",report["verdict"],"SELECTED",
          report["train_only_selected"],"NO ORDERS",flush=True)

if __name__=="__main__":main()

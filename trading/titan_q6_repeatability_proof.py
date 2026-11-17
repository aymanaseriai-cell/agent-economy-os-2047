#!/usr/bin/env python3
"""TITAN Q6-R2: pre-registered exact Q6 +128% repeatability falsification.

READ ONLY. Fetch completed genuine OKX 15m history; replay ORIGINAL Q6
4h signal -> next 15m entry, lot sizing, stops, trailing, fees and liquidation
proxy. The preselected primary is q6_coherent_breakout at 10x; no model tuning
or training/holdout selection after seeing the new data. Not real trading.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, math, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from trading import titan_q6_4h_swing_128 as q6
from trading.edge_lab import fetch_history
from trading.titan_regime_research import validate_frozen

PROTOCOL = "TITAN-Q6-R2-LOCKED-180D-3-HOLDOUTS-20261117-V1"
TARGET_PCT = 128.0
START = 4.15
GOAL = 9.462
DAYS = 180
MIN_BARS = 17100
N = 6
LEV = 10.
PRIMARY = "q6_coherent_breakout"
DIAGNOSTIC = ("q6_zero_phase", "q6_volatility_coil", "classical_breakout")
MODELS = (PRIMARY,) + DIAGNOSTIC
EXCLUDED = set((
    "BTC ETH SOL XRP DOGE HYPE ZEC BNB "
    "ATOM ONDO WLD LTC AVAX OP GRT RENDER CHZ WIF ZK MASK "
    "BLUR MINA ETHFI AR YGG LPT ZIL STX BONK PENGU IMX "
    "DYDX JTO XTZ AXS CFX NMR "
    "ARB BCH ETC JUP ZRX NEAR"
).split())
CANDIDATES = set((
    "1INCH ACH AEVO AKT ALT API3 ARKM ASTR BAL BAND BAT CELO "
    "CHR CKB COMP COTI CTSI DASH DCR DENT ENJ FET FIL FLOW FXS "
    "GMX IOST IOTA KAS KAVA KNC LDO LSK NEO QTUM RLC RUNE "
    "SNX SSV STORJ SUSHI THETA TWT UMA VET XEC"
).split())
# Fingerprint of the ORIGINAL published Q6 module; a modified copy is refused.
ORIGINAL_Q6_BLOB_SHA = "61c683a63b37a2d5302d320dbe066d4cee065b33"
COSTS = ("ordinary", "stress")
PARTS = ("holdout_1", "holdout_2", "holdout_3")


def git_blob_sha(payload):
    return hashlib.sha1(b"blob "+str(len(payload)).encode()+b"\x00"+payload).hexdigest()


def validate_original_model():
    payload=Path(q6.__file__).read_bytes()
    if git_blob_sha(payload)!=ORIGINAL_Q6_BLOB_SHA:
        raise ValueError("Q6 source changed: fail closed, no post-hoc tuning")
    if (q6.START!=START or q6.TARGET!=GOAL or
        q6.LEVERAGES!=(3.,10.) or q6.BLOCK!=16 or
        q6.STOP_ATR!=1.9 or q6.PROFIT_ATR!=7. or
        q6.TRAIL_ATR!=2.1 or q6.MAX_HOLD_15M!=640):
        raise ValueError("Original market execution parameters changed")
    if PRIMARY not in q6.POLICIES or set(MODELS)-set(q6.POLICIES):
        raise ValueError("Unregistered model")
    return True


def catalogue():
    url="https://www.okx.com/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-Q6-R2-HISTORICAL-READONLY"}),
                 timeout=35) as response:obj=json.load(response)
    if obj.get("code")!="0": raise ValueError("No verified OKX public catalogue")
    # 180d OHLC needs contracts listed at least 210 days.
    cutoff=int(time.time()*1000)-210*86400000
    found=[]
    for x in obj.get("data",[]):
        sym=x.get("instId","")
        if not sym.endswith("-USDT-SWAP"):continue
        coin=sym[:-10]
        if (coin not in CANDIDATES or coin in EXCLUDED or
            x.get("state")!="live" or x.get("ctType")!="linear" or
            x.get("ctValCcy")!=coin):continue
        try:
            if int(x["listTime"])>cutoff:continue
            v=[float(x[k]) for k in ("ctVal","lotSz","minSz")]
            if not all(math.isfinite(y) and y>0 for y in v):continue
        except (KeyError,ValueError,TypeError):continue
        found.append(x)
    found.sort(key=lambda x:hashlib.sha256(
        (PROTOCOL+"|"+x["instId"]).encode()).hexdigest())
    if len(found)<N: raise ValueError("Fewer than six eligible untouched swaps")
    return found[:N],len(found)


def periods(n):
    if n<MIN_BARS:raise ValueError("Need all 180d of complete OHLC")
    a=int(n*.40);b=int(n*.60);c=int(n*.80)
    if min(b-a,c-b,n-c)<3000: raise ValueError("Too short holdout")
    return {"train":(800,a),"holdout_1":(a,b),
            "holdout_2":(b,c),"holdout_3":(c,n),
            "combined_holdout":(a,n)}


def replay(markets,specs,hashes):
    validate_original_model()
    if len(markets)!=N or set(markets)!=set(specs) or set(markets)!=set(hashes):
        raise ValueError("Six fully audited markets must be present")
    if any(x[:-10] not in CANDIDATES or x[:-10] in EXCLUDED for x in markets):
        raise ValueError("Market contamination")
    n=min(len(z) for z in markets.values())
    splits=periods(n)
    expected=[b["ts"] for b in next(iter(markets.values()))[:n]]
    for rows in markets.values():
        validate_frozen(rows)
        if [b["ts"] for b in rows[:n]]!=expected:
            raise ValueError("Data not synchronised on 15m UTC grid")
    # Signal computation is EXACT original Q6 implementation, no parameter edits.
    sigs={sym:q6.causal_signals(m[:n]) for sym,m in markets.items()}
    results={}
    for policy in MODELS:
        subset={sym:sigs[sym][policy] for sym in markets}
        results[policy]={}
        for pname,(lo,hi) in splits.items():
            results[policy][pname]={}
            for cost in COSTS:
                fee,slip=q6.COSTS[cost]
                results[policy][pname][cost]=q6.paper(
                    markets,specs,subset,LEV,lo,hi,fee,slip)
    # Ex ante rule: must hit the exact target after closed trades in ALL
    # three non-overlapping 36d holdouts and both normal+stress costs.
    primary=results[PRIMARY]
    repeated=all(primary[period][cost]["hit_128_closed_paper"]
                 and not primary[period][cost]["ruin"]
                 for period in PARTS for cost in COSTS)
    combined=all(primary["combined_holdout"][cost]["hit_128_closed_paper"]
                 and not primary["combined_holdout"][cost]["ruin"]
                 for cost in COSTS)
    # Failure if any 36d holdout exceeds 40% max DD even with lucky wins.
    survivable=all(primary[period]["stress"]["max_dd_pct"]<=40.
                   for period in PARTS)
    per_market={}
    for symbol in sorted(markets):
        per_market[symbol]={}
        for cost in COSTS:
            fee,slip=q6.COSTS[cost]
            per_market[symbol][cost]=q6.paper(
                {symbol:markets[symbol]},{symbol:specs[symbol]},
                {symbol:sigs[symbol][PRIMARY]},LEV,*splits["combined_holdout"],
                fee,slip)
    return {
        "precommitted_protocol":PROTOCOL,
        "source":"real OKX public completed 15-minute history",
        "original_q6_source_blob":ORIGINAL_Q6_BLOB_SHA,
        "original_q6_module_unchanged":True,
        "primary_precommitted":PRIMARY,"primary_leverage":LEV,
        "diagnostics_NOT_eligible_for_claim":list(DIAGNOSTIC),
        "start_usdt":START,"target_usdt":GOAL,"target_pct":TARGET_PCT,
        "days_history":DAYS,"market_count":N,
        "markets":sorted(markets),"sha256_original_OHLC":hashes,
        "candles_per_market":n,"total_candles":n*N,"splits":splits,
        "both_costs_repeated_all_three_holdouts":bool(repeated),
        "both_costs_hit_combined_holdout":bool(combined),
        "holdout_drawdown_below_40_pct":bool(survivable),
        "primary_proof_gate_pass":bool(repeated and combined and survivable),
        "verdict":("HISTORICAL_REPLICATION_PASSED_NOT_PROSPECTIVE_PROOF"
                   if repeated and combined and survivable
                   else "NO_PROOF_OF_REPEATABLE_PLUS128"),
        "model_comparison":results,
        "individual_market_primary_checks":per_market,
        "real_orders":0,"physical_quantum_hardware":False,
        "limitations":[
            "Historical market OHLC are true; fills, funding, and liquidation are simulated",
            "Same historical calendar regime across markets, not independent future proof",
            "Original model was chosen from prior exploratory studies",
            "Historical lot sizes use currently published contract specifications",
            "No guarantee of repeating profits in any funded account",
        ],
    }


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    parser.add_argument("--raw-dir",required=True)
    args=parser.parse_args(argv)
    validate_original_model()
    specs,n=catalogue()
    print("R2 FROZEN PRE-RETURN MARKET COHORT",n,
          [x["instId"] for x in specs],flush=True)
    now=int(time.time()*1000)
    raw=Path(args.raw_dir);raw.mkdir(parents=True,exist_ok=True)
    markets={};sha={};specmap={}
    for spec in specs:
        name=spec["instId"]
        candles=fetch_history(name,DAYS,now_ms=now)
        if len(candles)<MIN_BARS:raise ValueError("Incomplete market data "+name)
        payload=json.dumps(candles,separators=(",",":")).encode()
        digest=hashlib.sha256(payload).hexdigest()
        with gzip.open(raw/(name+".json.gz"),"wb") as stream:
            stream.write(payload)
        sha[name]=digest;markets[name]=candles;specmap[name]=spec
        print("R2 FROZEN REAL OHLC",name,len(candles),digest,flush=True)
    report=replay(markets,specmap,sha)
    file=Path(args.out);file.parent.mkdir(parents=True,exist_ok=True)
    file.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    for label,periods in report["model_comparison"].items():
        print("R2 RETURNS",label,
              "TRAIN",periods["train"]["stress"]["return_pct"],
              "H1",periods["holdout_1"]["stress"]["return_pct"],
              "H2",periods["holdout_2"]["stress"]["return_pct"],
              "H3",periods["holdout_3"]["stress"]["return_pct"],
              "ALL",periods["combined_holdout"]["stress"]["return_pct"],
              flush=True)
    print("R2 VERDICT",report["verdict"],"PROOF",
          report["primary_proof_gate_pass"],"NO ORDERS",flush=True)

if __name__=="__main__":
    main()

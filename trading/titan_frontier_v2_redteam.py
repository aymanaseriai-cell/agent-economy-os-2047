#!/usr/bin/env python3
"""Independent hostile auditor for FROZEN Infinite Frontier V2 GitHub artifact.

No import of strategy/model implementation. Verifies true raw public candle
hashes, complete OHLCV, funding hashes, event sequencing, contract lot
precision, per-signal available quote volume, fees/settlement algebra and
model selection WITHOUT reading final model returns during selection.
No live orders. This is a structural audit, not full L2/mark-price proof.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

RAW="frontier_v2_raw_okx/"
REPORT="frontier_v2_result.json"
LEDGER="frontier_v2_all_paper_trades.jsonl.gz"
ONE_HOUR=3600000
BAR_MS=900000

def sha(data):
    return hashlib.sha256(data).hexdigest()

def audit(read):
    errors=[];counters=defaultdict(int)
    try:
        result=json.loads(read(REPORT))
        manifest=json.loads(read(RAW+"manifest.json"))
        record=[json.loads(row) for row in
                gzip.decompress(read(LEDGER)).decode().splitlines() if row]
    except Exception as err:
        return {"passed":False,"errors":["unreadable_artifact:"+str(err)]}
    if len(manifest)!=6 or set(manifest)!=set(result["markets"]):
        errors.append("market_manifest_mismatch")
    candles={};timestamps={};specs={}
    for sym,meta in manifest.items():
        try:
            rbytes=gzip.decompress(read(RAW+sym+"-original-15m.json.gz"))
            fbytes=gzip.decompress(read(RAW+sym+"-funding.json.gz"))
            if sha(rbytes)!=meta["original_price_sha256"]:
                errors.append("price_sha_mismatch:"+sym)
            if sha(fbytes)!=meta["funding_sha256"]:
                errors.append("funding_sha_mismatch:"+sym)
            orig=json.loads(rbytes)
            fund=json.loads(fbytes)
            counters["observed_funding_events"]+=len(fund)
            if not orig or len(orig)<17000 or any(str(x[8])!="1" for x in orig):
                errors.append("incomplete_or_unconfirmed_ohlcv:"+sym)
            ts=[int(x[0]) for x in orig]
            if any(y-x!=BAR_MS for x,y in zip(ts,ts[1:])):
                errors.append("nonconsecutive_market_history:"+sym)
            candles[sym]=orig;timestamps[sym]={int(x[0]):i for i,x in enumerate(orig)}
            specs[sym]=meta["instrument_snapshot"]
            if len(orig)!=result["bars_per_market"]:
                errors.append("historical_bar_count_mismatch:"+sym)
        except Exception as err:
            errors.append("unable_to_audit_market:"+sym+":"+str(err))
    if len(candles)==6:
        first=[int(x[0]) for x in next(iter(candles.values()))]
        for sym,raw in candles.items():
            if [int(x[0]) for x in raw]!=first:
                errors.append("cross_market_timestamp_misalignment:"+sym)
    summaries=result["all_policy_summaries"]
    qualified=[]
    for k,secs in summaries.items():
        train=secs["fit"]["stress"];dev=secs["development"]
        if (train["trades"]>=5 and train["net_return_pct"]>0 and
            dev["stress"]["net_return_pct"]>0 and
            dev["extreme"]["net_return_pct"]>0 and
            dev["extreme"]["max_closed_drawdown_pct"]<=35 and
            not dev["extreme"]["ruin"]):
            qualified.append(k)
    chosen=max(qualified,key=lambda k:summaries[k]["development"]["extreme"]["net_return_pct"]) if qualified else None
    if chosen!=result["selected_before_final"] or qualified!=result["qualified_on_train_development_only"]:
        errors.append("final_holdout_leak_in_policy_selection")
    if result["target_usdt"]!=1_037_504.15 or result["start_usdt"]!=4.15:
        errors.append("wrong_million_percent_target")
    if len(summaries)!=20 or result["executed_period_cost_scenarios"]!=360:
        errors.append("missing_requested_trial_summaries")
    if len(record)!=result["total_paper_trade_records"]:
        errors.append("trade_record_count_mismatch")
    grouped=defaultdict(list)
    for item in record:
        k=(item["model"],item["period"],item["cost"])
        grouped[k].append(item["trade"])
        counters["paper_trade_records"]+=1
    for k,periods in summaries.items():
        for period,results in periods.items():
            for mode,row in results.items():
                trades=grouped[k,period,mode]
                if row["trades"]!=len(trades):
                    errors.append("count_not_in_score:"+repr((k,period,mode)))
                if not trades:continue
                prev_equity=4.15;prev_end=None
                for trade in trades:
                    sym=trade["symbol"]
                    if sym not in specs or sym not in candles:
                        errors.append("unknown_market_order:"+sym);continue
                    start=int(trade["entry_ts"])
                    end=int(trade["exit_ts"])
                    if end<=start or (prev_end is not None and start<prev_end):
                        errors.append("overlapping_position_or_bad_exit:"+sym)
                    if prev_end is not None and abs(trade["equity_before"]-prev_equity)>2e-6:
                        errors.append("reinvesting_unclosed_profit:"+sym)
                    spec=specs[sym]
                    cv=float(spec["ctVal"]);lot=float(spec["lotSz"])
                    minimum=float(spec["minSz"]);q=float(trade["contracts"])
                    if q+1e-8<minimum or abs(q/lot-round(q/lot))>1e-5:
                        errors.append("fictional_contract_quantity:"+sym)
                    if trade["margin_usdt"]>trade["equity_before"]*.303:
                        errors.append("excess_margin:"+sym)
                    j=timestamps[sym].get(start)
                    if j is None or j==0:
                        errors.append("entry_time_missing_from_original_history:"+sym)
                    else:
                        vol=float(candles[sym][j-1][7])
                        notional=q*cv*float(candles[sym][j][1])
                        if vol<=0 or notional>vol*.010001:
                            errors.append("liquidity_cap_violated:"+sym)
                    if (start%(BAR_MS*16))!=0:
                        errors.append("entry_not_after_completed_4h:"+sym)
                    calc=(trade["gross_usdt"]-trade["fees_usdt"]
                          -trade["observed_funding_usdt"]
                          -trade["estimated_funding_usdt"])
                    if trade["exit_reason"]!="liquidation_proxy" and abs(calc-trade["net_usdt"])>6e-6:
                        errors.append("profit_ledger_not_reconciled:"+sym)
                    if abs(trade["equity_before"]+trade["net_usdt"]-trade["equity_after"])>6e-6:
                        errors.append("closed_equity_not_reconciled:"+sym)
                    if trade["equity_after"]<0:
                        errors.append("negative_account_equity:"+sym)
                    prev_end=end;prev_equity=trade["equity_after"]
    counters["market_files_verified"]=len(candles)
    counters["candidate_models"]=len(summaries)
    counters["distinct_trials"]=sum(len(v) for v in summaries.values())*3
    counters["errors_detected"]=len(errors)
    return {"passed":not errors,"errors":errors[:100],
            "counts":dict(counters),"selected_by_train_and_dev_only":chosen,
            "verdict":result["final_verdict"],
            "limitations":[
                "OHLCV trade-candle prices do not prove actual OKX mark-price liquidation",
                "Historical L2 fills/queue positions and exact leverage tier changes unavailable",
                "Archived currently live markets remain vulnerable to survivorship bias",
                "Replay and structural ledger audit are not a test of live future profitability",
            ]}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--zip",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args(argv)
    with ZipFile(a.zip) as f:
        record=audit(f.read)
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(record,indent=2,sort_keys=True)+"\n")
    print("FRONTIER HOSTILE REDTEAM",record["passed"],
          "ERRORS",record["errors"][:10],
          "COUNTS",record.get("counts"),flush=True)
    if not record["passed"]:raise SystemExit(2)

if __name__=="__main__":main()

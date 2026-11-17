#!/usr/bin/env python3
"""Independent hostile auditor of V3 frozen public OKX evidence.

Not importing trading or alpha model source. Performs SHA256 source
verification, complete bar clock consistency, off-book quantity and
prior-bar liquidity limits, PnL/equity accounting, no overlapping paper
positions, selection based solely on fit/development, and failed
assumptions. A pass is STRUCTURAL only, not actual execution proof.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

START=4.15
GOAL=1037504.15
PATH="v3_original_okx_210d/"

def digest(data):return hashlib.sha256(data).hexdigest()

def inspect(read):
    issues=[];stats=defaultdict(int)
    try:
        report=json.loads(read("v3_discovery_evidence.json"))
        manifest=json.loads(read(PATH+"manifest.json"))
        records=[json.loads(line) for line in
             gzip.decompress(read("v3_all_paper_trades.jsonl.gz")).decode().splitlines()
             if line]
    except Exception as e:
        return {"passed":False,"errors":["unreadable:"+str(e)]}
    if len(manifest)!=8 or set(manifest)!=set(report["markets"]):
        issues.append("missing_eight_independent_market_sources")
    panel={};indexes={}
    for sym,src in manifest.items():
        try:
            raw=gzip.decompress(read(PATH+sym+"-original-15m.json.gz"))
            funds=gzip.decompress(read(PATH+sym+"-funding.json.gz"))
            if digest(raw)!=src["ohlcv_sha256"]:
                issues.append("tampered_original_price:"+sym)
            if digest(funds)!=src["funding_sha256"]:
                issues.append("tampered_original_funding:"+sym)
            arr=json.loads(raw);fr=json.loads(funds)
            stats["observed_funding_events"]+=len(fr)
            if len(arr)<20100:issues.append("missing_210d_prices:"+sym)
            ts=[int(x[0]) for x in arr]
            if any(str(x[8])!="1" for x in arr):
                issues.append("unconfirmed_ohlcv:"+sym)
            if any(b-a!=900000 for a,b in zip(ts,ts[1:])):
                issues.append("gaps_or_duplicate_ohlcv:"+sym)
            panel[sym]=arr
            indexes[sym]={int(x[0]):i for i,x in enumerate(arr)}
            if src["ohlcv_sha256"]!=report["source_sha256"].get(sym):
                issues.append("report_manifest_hash_mismatch:"+sym)
        except Exception as e:
            issues.append("missing_candle_source:"+sym+":"+str(e))
    if len(panel)==8:
        timeline=[int(x[0]) for x in next(iter(panel.values()))]
        for sym,arr in panel.items():
            if [int(x[0]) for x in arr]!=timeline:
                issues.append("cross_market_15minute_misalignment:"+sym)
    fitted=report["alpha_discovery"]["fit"]
    dev=report["development_ledger"]
    eligible=[]
    for name,row in dev.items():
        policy=name.rsplit("_",1)[0]
        reasons=row["rejection_reasons"]
        if not fitted[policy]["screen_eligible"] and "no_Holm_adjusted_development_alpha" not in reasons:
            issues.append("economic_alpha_screen_bypassed:"+name)
        if not reasons:eligible.append(name)
    should_be=max(eligible,key=lambda k:dev[k]["development"]["extreme"]["net_return_pct"]) if eligible else None
    if report["selected_before_final"]!=should_be:
        issues.append("lookahead_or_selection_protocol_mismatch")
    if report["rejected_paper_variants"]!=len(dev)-len(eligible):
        issues.append("unrecorded_trial_rejection")
    final=report["selected_final_results"]
    expected={"always_flat","simple_momentum_2x"}
    if should_be:expected.add(should_be)
    if set(final)!=expected:
        issues.append("posthoc_final_model_added_or_missing")
    if report["target_usdt"]!=GOAL or report["starting_usdt"]!=START:
        issues.append("target_falsification")
    if report["hypotheses_with_paper_variants"]!=27:
        issues.append("missing_leverage_hypotheses")
    if report["development_scenarios"]!=27*4*3:
        issues.append("missing_development_trial_cases")
    bycase=defaultdict(list)
    for row in records:
        name=row.get("model",row.get("policy"))
        key=(name,row["period"],row["cost"])
        bycase[key].append(row["trade"])
    for name,row in dev.items():
        for cost in ("ordinary","stress","extreme"):
            if row["development"][cost]["trades"]!=len(bycase[name,"development",cost]):
                issues.append("development_trade_count_mismatch:"+name+":"+cost)
    for name,row in final.items():
        for period in ("final_1","final_2","final_3","final_combined"):
            for cost in ("ordinary","stress","extreme"):
                if row[period][cost]["trades"]!=len(bycase[name,period,cost]):
                    issues.append("final_trade_count_mismatch:"+name+":"+period+":"+cost)
    for (name,period,cost),trades in bycase.items():
        last_end=None;last_eq=START
        for t in trades:
            stats["paper_trade_rows"]+=1
            sym=t["symbol"]
            if sym not in panel:issues.append("unknown_instrument_order:"+sym);continue
            start=int(t["entry_ts"]);end=int(t["exit_ts"])
            if end<=start or (last_end is not None and start<last_end):
                issues.append("overlapping_position:"+name)
            if start%(16*900000)!=0:
                issues.append("entry_before_completed_four_hour_bar:"+sym)
            if abs(float(t["eq_before"])-last_eq)>2e-6:
                issues.append("unrealized_gain_reinvestment:"+name)
            if abs(t["eq_after"]-(t["eq_before"]+t["net_pnl"]))>1e-5:
                issues.append("closed_equity_ledger_mismatch:"+name)
            if t["eq_after"]<0:
                issues.append("negative_closed_equity:"+name)
            if t["margin"]>t["eq_before"]*.202:
                issues.append("over_capital_margin_20pct:"+name)
            original_idx=indexes[sym].get(start)
            if original_idx is None or original_idx<=0:
                issues.append("entry_does_not_exist_at_source_market:"+sym)
            else:
                previous=panel[sym][original_idx-1]
                orig=panel[sym][original_idx]
                spec=manifest[sym]["instrument"]
                q=float(t["contracts"]);cv=float(spec["ctVal"])
                lot=float(spec["lotSz"]);minimum=float(spec["minSz"])
                if q+1e-8<minimum or abs(q/lot-round(q/lot))>1e-5:
                    issues.append("unexecutable_contract_step:"+sym)
                notional=q*cv*float(orig[1])
                if float(previous[7])<=0 or notional>float(previous[7])*.002001:
                    issues.append("unexecutable_volume_cap:"+sym)
            if t["reason"]!="liquidation_PROXY":
                calc=t["gross_pnl"]-t["fee"]-t["funding_observed"]-t["funding_proxy"]
                if abs(calc-t["net_pnl"])>1e-5:
                    issues.append("trade_pnl_cost_not_reconciled:"+name)
            last_end=end;last_eq=t["eq_after"]
    stats["genuine_data_files_verified"]=len(panel)
    stats["candidate_models"]=len(dev)
    stats["failed_variants"]=report["rejected_paper_variants"]
    stats["source_funding_events"]=stats["observed_funding_events"]
    stats["detected_issues"]=len(issues)
    return {"passed":not issues,"issues":issues[:100],
            "checks":dict(stats),"valid_selection_by_train_dev_only":should_be,
            "final_verdict":report["verdict"],
            "limitations":["This does not reconstruct historical L2 bid/ask or exact mark-price liquidation",
                           "Current contract specs and survivor instrument list may not match prior years",
                           "Reproducibility and falsification do NOT prove live future profit"]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--zip",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    with ZipFile(a.zip) as z:
        result=inspect(z.read)
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("V3 INDEPENDENT HOSTILE AUDIT",result["passed"],
          "ISSUES",result["issues"][:10],
          "COUNTS",result.get("checks"),flush=True)
    if not result["passed"]:raise SystemExit(2)

if __name__=="__main__":
    main()

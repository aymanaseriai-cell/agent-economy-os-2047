#!/usr/bin/env python3
"""V4 independent adversarial inspection of frozen original OKX trade+mark+index.

This AUDITOR NEVER IMPORTS V4 STRATEGIES or their PnL functions.
Checks source SHA, market timestamps, nonfuture entry time, tiny contract
quantization, volume, fees, capital compounding, funding proxy, and
2023/24-only selection gate. Structural validity, NOT actual exchange
execution certainty or independent proof of future returns.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math
from pathlib import Path
from zipfile import ZipFile

PREF="v4_original_2023_2025/"
START=1672531200000
END=1767225600000
STEP=14400000
EXPECTED=6576
COSTS={"base":(.0005,.0001),"stress":(.0015,.0005)}
CAPITAL=4.15
TARGET=1037504.15

def inspect(read):
    errors=[];summary={"data_feeds_verified":0,"actual_bars_verified":0,
                       "paper_positions_checked":0,"missing_feeds":0}
    try:
        report=json.loads(read("v4_empirical_results.json"))
        manifest=json.loads(read(PREF+"manifest.json"))
    except Exception as e:
        return {"passed":False,"errors":["missing_report_or_manifest:"+str(e)]}
    cohort=tuple(x+"-USDT-SWAP" for x in (
        "BTC","ETH","SOL","XRP","DOGE","ADA","DOT","LINK","LTC","ETC"))
    valid=manifest.get("actual_verified_triples",[])
    if not set(valid).issubset(cohort):
        errors.append("cohort_substitution_not_predeclared")
    if len(manifest.get("source_manifest",{}))!=10:
        errors.append("incomplete_cohort_metadata")
    originals={};snap={}
    for sym in valid:
        specs=manifest["source_manifest"][sym]["current_spec"]
        if not specs:errors.append("missing_original_market_spec:"+sym)
        snap[sym]=specs
        originals[sym]={}
        for kind in ("trade","mark","index"):
            try:
                blob=gzip.decompress(read(PREF+sym+"-"+kind+".json.gz"))
                expected_sha=manifest["source_manifest"][sym][kind]["sha256"]
                if hashlib.sha256(blob).hexdigest()!=expected_sha:
                    errors.append("TAMPERED_original_exchange_prices:"+sym+":"+kind)
                if report.get("raw_sha256",{}).get(sym,{}).get(kind)!=expected_sha:
                    errors.append("report_candle_sha_inconsistent:"+sym+":"+kind)
                source=json.loads(blob)
                stamps=[int(x[0]) for x in source]
                if (len(source)!=EXPECTED or stamps[0]!=START or
                    stamps[-1]!=END-STEP or any(y-x!=STEP for x,y in
                    zip(stamps,stamps[1:]))):
                    errors.append("missing_2023_2025_original_4h_candles:"+sym+":"+kind)
                if any(str(x[-1])!="1" for x in source):
                    errors.append("unconfirmed_candle:"+sym+":"+kind)
                originals[sym][kind]=source
                summary["data_feeds_verified"]+=1
                summary["actual_bars_verified"]+=len(source)
            except Exception as e:
                errors.append("source_unreadable:"+sym+":"+kind+":"+str(e))
        if len(originals[sym])==3:
            clocks=[[int(x[0]) for x in originals[sym][k]]
                    for k in ("trade","mark","index")]
            if clocks[0]!=clocks[1] or clocks[0]!=clocks[2]:
                errors.append("misaligned_original_mark_index_clock:"+sym)
    for sym,record in manifest.get("source_manifest",{}).items():
        for kind in ("trade","mark","index"):
            if record.get(kind,{}).get("status")!="complete":
                summary["missing_feeds"]+=1
    if report.get("target_usdt")!=TARGET or report.get("start_usdt")!=CAPITAL:
        errors.append("wrong_mathematical_target")
    if len(valid)<6:
        if report.get("verdict")!="UNTESTABLE_MARK_INDEX_NO_6_COMPLETE_MARKETS":
            errors.append("unjustified_claim_without_min_six_original_markets")
        if not report.get("final_not_opened"):
            errors.append("final_opened_without_valid_6market_source")
    else:
        f=report["frozen_discovery"]["fitted"]
        eligible=[k for k in f if k!="always_flat" and f[k].get("eligible",False)]
        candidate=max(eligible,key=lambda h:f[h]["dev_net_log_proxy"]) if eligible else None
        if candidate!=report.get("qualified_before_execution"):
            errors.append("development_only_model_selection_mismatch")
        accepted=report.get("accepted_before_final")
        if accepted is not None and accepted!=candidate:
            errors.append("unqualified_strategy_selected_from_2025")
        if accepted is not None:
            dev=report["development_execution"]
            if not all(dev[c]["net_return_pct"]>0 and
                       dev[c]["trades"]>=8 and
                       dev[c]["closed_max_drawdown_pct"]<=30
                       for c in COSTS):
                errors.append("development_execution_gate_not_passed")
        elif any(x["trades"]>0 for x in report["final_locked"].values()):
            errors.append("forbidden_final_alpha_trade")
        if len(f)!=5:
            errors.append("missing_five_development_hypotheses")
        if report["frozen_discovery"]["train_year"]!=2023 or report["frozen_discovery"]["dev_year"]!=2024:
            errors.append("improper_final_research_time_separation")
        for family,row in f.items():
            if row["eligible"] and not (
                row["dev_events"]>=30 and row["dev_months"]>=8 and
                row["holm_p"]<=.05 and
                row["dev_first_six_months_net"]>0 and
                row["dev_second_six_months_net"]>0):
                errors.append("unjustified_event_economic_advantage:"+family)
    for family,reports in (
        ("approved_final_alpha",report.get("final_locked",{})),
        ("fixed_classical_baseline",report.get("predeclared_classical_2025_baseline",{})),
        ("development_executable_candidate",report.get("development_execution",{})),
    ):
        for cost,out in reports.items():
            if cost not in COSTS:
                errors.append("unknown_fee_scenario")
                continue
            fee_rate,fund_rate=COSTS[cost]
            trades=out.get("ledger",[])
            if len(trades)!=out.get("trades"):
                errors.append("ledger_trade_count_not_reconciled:"+family)
            balance=CAPITAL;previous_end=0
            for t in trades:
                summary["paper_positions_checked"]+=1
                sym=t["sym"];when=int(t["ts"])
                if sym not in originals or "trade" not in originals[sym]:
                    errors.append("unknown_source_in_trade:"+sym);continue
                if t["equity_before"]<=0 or abs(t["equity_before"]-balance)>1e-6:
                    errors.append("uses_unclosed_equity_profit:"+sym)
                if when<=previous_end:
                    errors.append("overlapping_positions:"+sym)
                if t["source_raw_ts"]!=when-STEP:
                    errors.append("lookahead_entry_time:"+sym)
                bars=originals[sym]["trade"]
                index=(when-START)//STEP
                if index<1 or index>=len(bars) or int(bars[index][0])!=when:
                    errors.append("entry_bar_absent_in_original_market:"+sym)
                else:
                    prev=bars[index-1];qty=float(t["contracts"])
                    spec=snap[sym];lot=float(spec["lotSz"]);minq=float(spec["minSz"])
                    if qty+1e-9<minq or abs(qty/lot-round(qty/lot))>1e-5:
                        errors.append("unaffordable_or_fractional_contracts:"+sym)
                    notional=qty*float(spec["ctVal"])*float(bars[index][1])
                    if notional>float(prev[7])*.0010001:
                        errors.append("not_real_quote_liquidity:"+sym)
                    if t["margin"]>t["equity_before"]*.151:  # tolerate bounded adverse entry slip
                        errors.append("excessive_hypothetical_margin:"+sym)
                    try:
                        expectedfee=(
                            abs(qty*float(spec["ctVal"])*t["entry"])+
                            abs(qty*float(spec["ctVal"])*t["exit"]))*fee_rate
                        expectedfund=qty*float(spec["ctVal"])*t["entry"]*fund_rate*.5
                        if abs(t["taker_fees"]-expectedfee)>1e-5:
                            errors.append("incorrect_charged_taker_fee:"+sym)
                        if abs(t["assumed_funding"]-expectedfund)>1e-5:
                            errors.append("fabricated_funding_settlement:"+sym)
                    except Exception:
                        errors.append("cannot_verify_fee_equation:"+sym)
                if abs(t["equity_before"]+t["net"]-t["equity_after"])>1e-5:
                    errors.append("paper_pnl_not_reconciled:"+sym)
                if t["equity_after"]<0:
                    errors.append("negative_capital_without_bankruptcy_stop:"+sym)
                balance=t["equity_after"];previous_end=when+STEP
            if trades and abs(out["equity_end"]-balance)>1e-6:
                errors.append("final_equity_differs_from_trade_ledger:"+family)
    return {
        "passed":not errors,"issues":errors[:100],"metrics":summary,
        "train_development_years":"2023+2024",
        "2025_final_scanned_only_if_preregistered_strategy":True,
        "horizon_2023_to_2025":True,
        "selected_before_final":report.get("accepted_before_final"),
        "limitation":"Independent structural audit is NOT actual OKX matching-engine or maintenance-tier proof",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--zip",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    with ZipFile(a.zip) as archive:
        summary=inspect(archive.read)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("V4 INDEPENDENT REDTEAM",summary["passed"],
          "ISSUES",summary["issues"][:10],"COUNTS",summary["metrics"],flush=True)
    if not summary["passed"]:raise SystemExit(2)

if __name__=="__main__":
    main()

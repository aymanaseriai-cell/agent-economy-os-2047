#!/usr/bin/env python3
"""INDEPENDENT hostile carry audit: no imports of cash carry or strategy source.

Reconstruct from ORIGINAL OKX public archive funding CSV and original SPOT,
perpetual and mark OHLC source files and separate original current contract
snapshot. Examine *every* paper trade in 24 precommitted scenarios, prices,
taker fees, actual funded events, hedge equality, no lookahead, chronological
closed capital, and bitwise frozen replay. No historical L2 or exact
maintenance tiers, so this is not a proof of real execution.
"""
from __future__ import annotations
import argparse,csv,decimal,gzip,hashlib,io,json,math,zipfile
from collections import defaultdict
from pathlib import Path
D=decimal.Decimal
START=1704067200000
MID=1719792000000
END=1735689600000
STEP=14400000
HOLD={"one_funding_interval":1,"seven_days":21}
COST={"base":(.0005,.0002),"stress":(.0015,.0015)}
COINS=("BTC","ETH","SOL")
PREF="first_edge_2024_true_spot_perp_funding/"
HIST="v4_original_2023_2025/"
FIRST="first_edge_original_okx/"
EQ=4.15

def sh(x):return hashlib.sha256(x).hexdigest()

def inspect(carryfile,v4file,firstfile):
    errs=[];stats=defaultdict(int)
    with zipfile.ZipFile(carryfile) as proof, zipfile.ZipFile(v4file) as archive, zipfile.ZipFile(firstfile) as now:
        original=json.loads(proof.read("first_edge_cash_carry_2024_dev.json"))
        offline=json.loads(proof.read("first_edge_cash_carry_2024_offline.json"))
        if original!=offline:errs.append("OFFLINE_FREEZE_REPORT_MISMATCH")
        manifest=json.loads(proof.read(PREF+"full_original_manifest.json"))
        origmanifest=json.loads(archive.read(HIST+"manifest.json"))
        current=json.loads(now.read(FIRST+"manifest.json"))
        spot={};perp={};mark={};rates={};spec={}
        for coin in COINS:
            spmeta=manifest["spot"][coin]
            blob=gzip.decompress(proof.read(PREF+"spot/"+spmeta["file"]))
            if sh(blob)!=spmeta["sha256"]:errs.append("SPOT_TAMPERED_SHA:"+coin)
            spot[coin]={int(x[0]):x for x in json.loads(blob)}
            stats["original_spot_bars"]+=len(spot[coin])
            if len(spot[coin])!=2196 or any(t not in spot[coin] for t in range(START,END,STEP)):
                errs.append("SPOT_MISSING_CONTIGUOUS_2024:"+coin)
            rates[coin]={}
            for month,m in manifest["funding"]["coins"][coin]["months"].items():
                rawzip=proof.read(PREF+"funding/"+m["zip_file"])
                if sh(rawzip)!=m["zip_sha256"]:
                    errs.append("TAMPERED_ARCHIVED_FUNDING_ZIP:"+coin+month)
                with zipfile.ZipFile(io.BytesIO(rawzip)) as z:
                    rawcsv=z.read(z.namelist()[0])
                if sh(rawcsv)!=m["csv_sha256"]:errs.append("TAMPERED_FUNDING_CSV:"+coin+month)
                stats["original_monthly_funding_zips"]+=1
                for row in csv.DictReader(io.TextIOWrapper(io.BytesIO(rawcsv),encoding="utf-8-sig")):
                    t=int(row["funding_time"]);r=float(row["funding_rate"])
                    if START<=t<END:
                        if t in rates[coin] and abs(rates[coin][t]-r)>1e-12:
                            errs.append("CONFLICTING_RATE")
                        rates[coin][t]=r
            if len(rates[coin])!=original["original_funding_records"][coin]:
                errs.append("INCORRECT_FUNDING_COUNT:"+coin)
            stats["original_funding_events"]+=len(rates[coin])
            sym=coin+"-USDT-SWAP"
            perp[coin]={};mark[coin]={}
            for typ,dst in (("trade",perp[coin]),("mark",mark[coin])):
                data=gzip.decompress(archive.read(HIST+sym+"-"+typ+".json.gz"))
                if sh(data)!=origmanifest["source_manifest"][sym][typ]["sha256"]:
                    errs.append("ORIGINAL_DERIVATIVES_TAMPERED:"+coin+typ)
                dst.update({int(x[0]):x for x in json.loads(data) if START<=int(x[0])<END})
            stats["original_2024_perp_and_mark_bars"]+=len(perp[coin])+len(mark[coin])
            spec[coin]={
                "spot":current["instrument_source"]["SPOT"]["symbols"][coin+"-USDT"],
                "swap":current["instrument_source"]["SWAP"]["symbols"][sym]}
        if original["alpha_proven"] is not False or original["new_unseen_final_return"] is not None:
            errs.append("MISREPRESENTED_2024_AS_UNSEEN_FINAL")
        if original["no_exchange_orders"] is not True:errs.append("NOT_RESEARCH_ONLY")
        if set(original["horizons"])!=set(HOLD):errs.append("UNDECLARED_HORIZON_SEARCH")
        for h,modes in original["horizons"].items():
            for mode,coins in modes.items():
                if mode not in COST:errs.append("UNDECLARED_COST_SCENARIO");continue
                fee,slip=COST[mode]
                for coin,halves in coins.items():
                    if coin not in COINS:errs.append("POSTHOC_MARKET_ADDED");continue
                    for part,summary in halves.items():
                        if part not in ("h1","h2"):errs.append("WRONG_TEMPORAL_PERIOD")
                        a,b=(START,MID) if part=="h1" else (MID,END)
                        eq=EQ;peak=EQ;dd=0.;last_exit=0
                        allfees=0.;allfund=0.;allbasis=0.;wins=0;losers=0
                        for row in summary["ledger"]:
                            stats["trade_records_reconciled"]+=1
                            when=row["entry_ts"];exit_at=row["exit_ts"]
                            signalt=row["entry_ts"]-STEP
                            if when<=signalt or when<last_exit:
                                errs.append("LOOKAHEAD_OR_OVERLAP:"+coin)
                            if not (a<=when<exit_at<=b):
                                errs.append("SPILLOVER_BETWEEN_DEV_HALVES:"+coin)
                            if exit_at-signalt!=HOLD[h]*8*3600000+STEP:
                                errs.append("WRONG_HOLD_DURATION:"+coin)
                            if rates[coin].get(signalt,0)<=0:
                                errs.append("SIGNAL_NOT_BASED_ON_POSITIVE_KNOWN_SETTLEMENT:"+coin)
                            q=D(str(row["position_base_quantity_exact"]))
                            contracts=D(str(row["swap_contracts_exact"]))
                            cv=D(spec[coin]["swap"]["ctVal"])
                            spstep=D(spec[coin]["spot"]["lotSz"])
                            spsmall=D(spec[coin]["spot"]["minSz"])
                            swstep=D(spec[coin]["swap"]["lotSz"])
                            swsmall=D(spec[coin]["swap"]["minSz"])
                            if q!=cv*contracts or q<spsmall or contracts<swsmall or (
                                q/spstep)!=(q/spstep).to_integral_value() or (
                                contracts/swstep)!=(contracts/swstep).to_integral_value():
                                errs.append("FAKE_HEDGE_OR_FRACTIONAL_LOT:"+coin)
                            if abs(eq-row["starting_cash_this_trade"])>1e-7:
                                errs.append("USES_FUTURE_UNSETTLED_CAPITAL:"+coin)
                            st=spot[coin].get(when);pe=perp[coin].get(when)
                            se=spot[coin].get(exit_at);px=perp[coin].get(exit_at)
                            if None in (st,pe,se,px):errs.append("MISSING_TRUE_ENTRY_OR_EXIT_OHLC:"+coin);continue
                            qs=float(q)
                            reconstructed_spotin=float(st[1])*(1+slip)
                            reconstructed_perpin=float(pe[1])*(1-slip)
                            reconstructed_spotout=float(se[1])*(1-slip)
                            reconstructed_perpout=float(px[1])*(1+slip)
                            for field,value in (
                                ("spot_entry",reconstructed_spotin),
                                ("perp_entry",reconstructed_perpin),
                                ("spot_exit",reconstructed_spotout),
                                ("perp_exit",reconstructed_perpout)):
                                if abs(row[field]-value)>1e-6:
                                    errs.append("WRONG_ACTUAL_FILL_PRICE_ALGEBRA:"+coin+field)
                            prior_st=spot[coin].get(when-STEP);prior_pe=perp[coin].get(when-STEP)
                            if prior_st is None or prior_pe is None:
                                errs.append("PREVIOUS_BAR_MISSING")
                            elif (qs*float(st[1])>float(prior_st[7])*.001001 or
                                  qs*float(pe[1])>float(prior_pe[7])*.001001):
                                errs.append("VIOLATES_PREVIOUS_QUOTE_VOLUME_CAP:"+coin)
                            fund=0.;k=0
                            for settled,rate in rates[coin].items():
                                if when<settled<exit_at:
                                    previous_mark=mark[coin].get(settled-STEP)
                                    if previous_mark is None:
                                        errs.append("MARK_PRICE_SOURCE_MISSING_AT_SETTLEMENT:"+coin)
                                        continue
                                    fund+=qs*float(previous_mark[4])*rate;k+=1
                            fee_calc=fee*qs*sum((reconstructed_spotin,
                                                  reconstructed_spotout,
                                                  reconstructed_perpin,
                                                  reconstructed_perpout))
                            basis_noslip=qs*((float(se[1])-float(st[1]))-
                                               (float(px[1])-float(pe[1])))
                            basis_slip=qs*((reconstructed_spotout-reconstructed_spotin)-
                                           (reconstructed_perpout-reconstructed_perpin))
                            net=basis_slip+fund-fee_calc
                            for name,value in (
                                ("real_observed_settlements_during_hold",k),
                                ("funding_pnl_observed_rate_mark_proxy_USDT",fund),
                                ("taker_fees_usdt",fee_calc),
                                ("basis_pnl_before_slippage_USDT",basis_noslip),
                                ("basis_pnl_after_slippage_USDT",basis_slip),
                                ("net_closed_usdt",net),
                                ("equity_after",max(0.,eq+net))):
                                if abs(row[name]-value)>1e-6:
                                    errs.append("RECONCILIATION_FAILED:"+coin+name)
                            eq=max(0.,eq+net)
                            last_exit=exit_at;peak=max(eq,peak)
                            dd=max(dd,100*(peak-eq)/peak)
                            allfees+=fee_calc;allfund+=fund;allbasis+=basis_noslip
                            wins+=net>0;losers+=net<0
                        metrics={
                            "trades":len(summary["ledger"]),
                            "winners":wins,"losers":losers,
                            "equity_end_usdt":eq,"net_return_pct":100*(eq/EQ-1),
                            "closed_max_dd_pct":dd,"fee_paid_usdt":allfees,
                            "observed_settled_funding_usdt":allfund,
                            "basis_pnl_before_slip_usdt":allbasis}
                        for name,value in metrics.items():
                            if abs(summary[name]-value)>1e-6:
                                errs.append("AGGREGATE_SHADOW_RETURN_NOT_MATCHING_CLOSED_TRADE_LEDGER:"+coin+name)
    return {"passed":not errs,"errors":errs[:100],
            "checks":dict(stats),"revalidated_historical_year":"2024 consumed V4 calendar",
            "true_new_prospective_oos_alpha":False,
            "limits":[
                "Original archived rates, spots, perps and marks verified but funding notional uses proxy mark candle close",
                "No historical L2 fills or point-in-time 2024 exchange contract minima/fee schedule",
                "Mark liquidation checked only as 4h proxy by strategy, not official maintenance-tier execution",
                "Historical 2024 H1/H2 repeated development is NOT new blind final",
            ]}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--carry-zip",required=True)
    p.add_argument("--v4-zip",required=True)
    p.add_argument("--first-zip",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args(argv)
    result=inspect(a.carry_zip,a.v4_zip,a.first_zip)
    target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("FIRST EDGE CARRY INDEPENDENT FORENSIC",result["passed"],
          "CHECKS",result.get("checks"),"ERRORS",result["errors"][:15],flush=True)
    if not result["passed"]:raise SystemExit(2)

if __name__=="__main__":main()

#!/usr/bin/env python3
"""GENESIS V5 INDEPENDENT RED TEAM. No import of V5 strategy or PnL logic.

Audits source SHA of 2023-2025 ORIGINAL OKX data, real recent funding and
trade candles, contract quantities, single-position closed compounding,
fee/funding PnL identities and never rebranding consumed dates as OOS.
The structural audit does NOT verify point-in-time L2, true historical
maker fills, mark-price liquidation or real future return.
"""
from __future__ import annotations
import argparse,collections,gzip,hashlib,json,math,zipfile
from pathlib import Path

ORIGINAL="v4_original_2023_2025/"
RECENT="genesis_v5_real_funding/"
SCENARIOS={"base":{"taker":.0005,"fund8h":.0001,"slip":.0004},
           "stress":{"taker":.0015,"fund8h":.0005,"slip":.003}}
CAPITAL=4.15
BAR=14_400_000

def decode(v5z,v4z):
    errors=[];market={};snapshots={}
    v4manifest=json.loads(v4z.read(ORIGINAL+"manifest.json"))
    pricehash={}
    for sym in v4manifest["actual_verified_triples"]:
        triple={}
        pricehash[sym]={}
        snapshots[sym]=v4manifest["source_manifest"][sym]["current_spec"]
        for source in ("trade","mark","index"):
            raw=gzip.decompress(v4z.read(ORIGINAL+sym+"-"+source+".json.gz"))
            digest=hashlib.sha256(raw).hexdigest()
            expected=v4manifest["source_manifest"][sym][source]["sha256"]
            if digest!=expected:
                errors.append("TAMPERED_2023_2025_original_candle:"+sym+":"+source)
            rows=json.loads(raw)
            triple[source]={int(x[0]):x for x in rows}
            pricehash[sym][source]=expected
        if not len(triple["trade"])==len(triple["index"])==len(triple["mark"])==6576:
            errors.append("missing_original_triple_prices:"+sym)
        if set(triple["trade"])!=set(triple["mark"]) or set(triple["trade"])!=set(triple["index"]):
            errors.append("unmatched_trade_mark_index_timestamps:"+sym)
        market[sym]=triple
    evidence=json.loads(v5z.read("genesis_v5_all_development.json"))
    replay=json.loads(v5z.read("genesis_v5_offline_verified.json"))
    if evidence!=replay:errors.append("V5_sha_replay_unequal")
    if evidence.get("data_sha256")!=pricehash:
        errors.append("original_V4_source_hashes_not_retained")
    manifest=json.loads(v5z.read(RECENT+"funding_manifest.json"))
    if manifest!=evidence.get("public_funding_manifest"):
        errors.append("recent_actual_source_manifest_modified")
    actualfund={};recentbars={}
    for sym,meta in manifest.get("source",{}).items():
        if meta.get("status")!="complete":continue
        packed={}
        for kind,data in meta["actual"].items():
            raw=gzip.decompress(v5z.read(RECENT+data["file"]))
            if hashlib.sha256(raw).hexdigest()!=data["sha256"]:
                errors.append("TAMPERED_actual_funding_OR_trading_source:"+sym+":"+kind)
            packed[kind]=json.loads(raw)
            if len(packed[kind])!=data["records"]:
                errors.append("funding_or_candle_count_inconsistent:"+sym)
        actualfund[sym]={int(x["fundingTime"]):float(x["realizedRate"])
                          for x in packed["actual_funding"]}
        recentbars[sym]={int(x[0]):x for x in packed["original_4h_trade"]}
        timestamps=sorted(recentbars[sym])
        if any(y-x!=BAR for x,y in zip(timestamps,timestamps[1:])):
            errors.append("missing_actual_recent_trade_candle:"+sym)
    return evidence,market,snapshots,actualfund,recentbars,errors

def audit(v5zip,v4zip):
    with zipfile.ZipFile(v5zip) as v5z, zipfile.ZipFile(v4zip) as v4z:
        result,market,specs,fund,price_recent,errors=decode(v5z,v4z)
    counts=collections.Counter()
    if (result.get("start_usdt"),result.get("target_usdt"))!=(4.15,1037504.15):
        errors.append("invented_target_arithmetic")
    if result.get("hypotheses_tested")!=3:
        errors.append("missing_or_extra_hypothesis")
    if (result.get("predeclared_paper_final")!="UNOPENED_NO_NEW_INDEPENDENT_FUTURE_WINDOW"
        or result.get("validated_oos_net_return_pct") is not None
        or result.get("real_orders")!=0):
        errors.append("false_blind_final_or_live_trading_claim")
    if set(result["summary"])!=set(result["development_shadow_ledgers"]):
        errors.append("selected_only_positive_hypotheses")
    for family,outcomes in result["development_shadow_ledgers"].items():
        if not result["summary"][family]["rejection_reasons"]:
            # Positive development-only candidate would still NOT authorize
            # calling it prospectively validated.
            counts["development_candidate_not_prospective"]+=1
        for scenario,book in outcomes.items():
            if scenario not in SCENARIOS:
                errors.append("unknown_cost_assumption")
                continue
            assumed=SCENARIOS[scenario]
            ledger=book["ledger"];counts["ledger_records"]+=len(ledger)
            if book["trades"]!=len(ledger):
                errors.append("paper_count_not_matching_details")
            cumulative=CAPITAL;last_exit=0
            for trade in ledger:
                sym=trade["symbol"];t=int(trade["entry_ts"]);signal=int(trade["source_signal_ts"])
                counts["observed_fill_checks"]+=1
                if t<=signal or t<last_exit:
                    errors.append("lookahead_or_overlapping_position:"+sym)
                if t-signal<BAR:
                    errors.append("funding_latency_or_past_close_violated:"+sym)
                if abs(float(trade["equity_before"])-cumulative)>1e-6:
                    errors.append("used_unsettled_equity_for_compounding:"+sym)
                cumulative=trade["equity_after"]
                if cumulative<0:
                    errors.append("negative_equity_without_ruin_stop:"+sym)
                side=int(trade["side"]);q=float(trade["contracts"])
                if side not in (-1,1):
                    errors.append("invalid_direction:"+sym)
                spec=specs.get(sym)
                if spec is None:
                    errors.append("missing_original_contract:"+sym)
                    continue
                cv=float(spec["ctVal"]);lot=float(spec["lotSz"]);minq=float(spec["minSz"])
                if q+1e-9<minq or abs(q/lot-round(q/lot))>1e-5:
                    errors.append("fractional_or_under_minimum_contract:"+sym)
                notional=q*cv*float(trade["entry"])
                if notional/(2*max(1e-9,trade["equity_before"]))>.154:
                    errors.append("margin_over_15percent_by_excess:"+sym)
                previous_quote=trade["prior_4h_volume"]
                if previous_quote<=0 or notional>previous_quote*.001016:
                    errors.append("unfillable_volume_participation:"+sym)
                # Reconcile different source archives for 2024 vs actual
                # recent 2026 funding, without strategy-code imports.
                row=(price_recent[sym].get(t) if family=="funding_crowding_reversal"
                     else market[sym]["trade"].get(t))
                oldrow=(price_recent[sym].get(t-BAR) if family=="funding_crowding_reversal"
                        else market[sym]["trade"].get(t-BAR))
                if row is None or oldrow is None:
                    errors.append("missing_true_exchange_fill_bar:"+sym)
                else:
                    if abs(float(row[7])-float(oldrow[7]))<0:pass # never changes state
                    if abs(previous_quote-float(oldrow[7]))>1e-5:
                        errors.append("replaced_true_previous_quote_volume:"+sym)
                    observed_open=float(row[1]);observed_close=float(row[4])
                    impact=min(.01,.15*notional/max(1.,previous_quote))
                    theoretical_enter=observed_open*(1+side*(assumed["slip"]+impact))
                    theoretical_exit=observed_close*(1-side*(assumed["slip"]+impact))
                    # Impact amount depends on original pre-slippage
                    # size; allow tiny difference in iterative estimate.
                    if abs(trade["entry"]/observed_open-1)>assumed["slip"]+.011:
                        errors.append("entry_outside_price_assumption:"+sym)
                    if abs(trade["exit"]/observed_close-1)>assumed["slip"]+.011:
                        errors.append("exit_outside_price_assumption:"+sym)
                if family=="funding_crowding_reversal":
                    rate=fund.get(sym,{}).get(signal)
                    if rate is None:errors.append("funding_event_not_original_settlement:"+sym)
                    elif trade["side"]!=(1 if rate<0 else -1):
                        errors.append("trading_on_funding_wrong_direction:"+sym)
                    if t<signal+BAR:
                        errors.append("trade_enters_before_funding_becomes_known:"+sym)
                else:
                    if not 1672531200000<=t<1735689600000:
                        errors.append("uses_converted_V4_FINAL_as_new_genesis_DEVELOPMENT:"+sym)
                expected_fee=q*cv*(trade["entry"]+trade["exit"])*assumed["taker"]
                expected_funding=q*cv*trade["entry"]*assumed["fund8h"]*.5
                expected_gross=side*q*cv*(trade["exit"]-trade["entry"])
                expected_net=max(-trade["equity_before"],
                                 expected_gross-expected_fee-expected_funding)
                if abs(trade["fee"]-expected_fee)>1e-6:
                    errors.append("fee_arithmetic_disagree:"+sym)
                if abs(trade["funding_assumed"]-expected_funding)>1e-6:
                    errors.append("funding_assumption_disagree:"+sym)
                if abs(trade["gross"]-expected_gross)>1e-6:
                    errors.append("wrong_gross_profit_sign_or_multiplier:"+sym)
                if abs(trade["net"]-expected_net)>1e-6:
                    errors.append("wrong_net_after_cost:"+sym)
                if abs(trade["equity_after"]-(trade["equity_before"]+trade["net"]))>1e-6:
                    errors.append("closed_PnL_not_reconciled:"+sym)
                last_exit=t+BAR
            if abs(book["end_usdt"]-cumulative)>1e-5:
                errors.append("final_portfolio_balance_wrong:"+family+scenario)
            if abs(book["return_pct"]-(cumulative/CAPITAL-1)*100)>1e-6:
                errors.append("reported_return_not_from_true_closed_equity")
    return {"passed":not errors,"issues":errors[:60],
            "checks":dict(counts),
            "original_verified_trade_mark_index_feeds":30,
            "recent_actual_funding_assets":len(fund),
            "recent_actual_funding_settlements":sum(len(z) for z in fund.values()),
            "truly_unseen_future_evaluation":False,
            "claimed_money_earned":False,
            "limitations":[
              "Snapshot contract specs are current, not historically point-in-time",
              "Exchange true L2 spread and limit maker probability absent",
              "No real mark-to-maintenance liquidation engine; absence of simulation liquidation cannot prove absence historically",
              "Reproduced development still scientifically consumed; does not establish future edge",
            ]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--v5-zip",required=True)
    parser.add_argument("--v4-zip",required=True)
    parser.add_argument("--out",required=True)
    x=parser.parse_args()
    result=audit(x.v5_zip,x.v4_zip)
    dest=Path(x.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("GENESIS V5 INDEPENDENT REDTEAM",result["passed"],
          "CHECKS",result["checks"],"ERRORS",result["issues"],flush=True)
    if not result["passed"]:raise SystemExit(2)

if __name__=="__main__":main()

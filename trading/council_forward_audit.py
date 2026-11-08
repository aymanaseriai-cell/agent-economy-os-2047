#!/usr/bin/env python3
"""Audit actual archived 6-agent + 7-quant research labels using frozen OKX bars.

This is NOT a six-agent historical backtest and does not model NVIDIA advisory
decisions, exchange account state, or actual orders. Never calls the network,
uses keys, or places trades. Locked hypothetical 1h and 4h outcomes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

BAR_MS = 15 * 60 * 1000
TAKER_FEE = .0005  # each side, assumed
SLIPPAGE = .0003  # unfavorable each side, assumed
FUNDING_8H = .0001  # modeled debit, NOT actual historical funding
HORIZONS = (4, 16)  # 1h, 4h


def utc_ms(iso: str) -> int:
    dt=datetime.fromisoformat(iso.replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Signal timestamp requires UTC timezone")
    return int(dt.timestamp()*1000)


def validate_bars(bars):
    if not isinstance(bars,list) or len(bars)<4:
        raise ValueError("At least four completed price candles required")
    for b in bars:
        values=(b["open"],b["high"],b["low"],b["close"])
        if not all(isinstance(v,(float,int)) and math.isfinite(v) for v in values):
            raise ValueError("Invalid OHLC candle")
        if not 0<b["low"]<=min(b["open"],b["close"])<=max(b["open"],b["close"])<=b["high"]:
            raise ValueError("Invalid candle range")
    if any(b["ts"]-a["ts"]!=BAR_MS for a,b in zip(bars,bars[1:])):
        raise ValueError("Missing candles or out-of-order history")
    return True


def audit_signal(signal, bars, horizon: int, *, fee=TAKER_FEE, slip=SLIPPAGE,
                 funding=FUNDING_8H):
    """No lookahead: entry at first next grid-aligned open after publication.

    Require ALL horizon bars to have completed in frozen data.
    Conservative: any candle touching both stop and target exits at STOP.
    """
    validate_bars(bars)
    if horizon not in HORIZONS or min(fee,slip,funding)<0:
        raise ValueError("Unsupported horizon or negative trading cost")
    posted=utc_ms(signal["published_utc"])
    start=((posted + BAR_MS-1)//BAR_MS)*BAR_MS
    by_ts={b["ts"]:b for b in bars}
    if start not in by_ts:
        return {"status":"not_observed","reason":"Entry candle not in historical sample"}
    batch=[by_ts.get(start+BAR_MS*i) for i in range(horizon)]
    if any(bar is None for bar in batch):
        return {"status":"not_matured","reason":"Horizon extends beyond completed history"}
    d=1 if signal["side"]=="LONG" else -1
    start_open=batch[0]["open"]
    entry=start_open*(1+d*slip)
    stop=signal["stop"]
    target=signal["target"]
    if d==1 and not (0<stop<entry<target):
        return {"status":"invalid_entry","reason":"Gap made original stops/targets invalid"}
    if d==-1 and not (0<target<entry<stop):
        return {"status":"invalid_entry","reason":"Gap made original stops/targets invalid"}
    outcome="horizon_close"
    exit_price=batch[-1]["close"]
    bars_held=horizon
    for n,bar in enumerate(batch,1):
        if d==1:
            if bar["open"]<=stop:
                exit_price=bar["open"];outcome="stop_gap";bars_held=n;break
            if bar["low"]<=stop:
                exit_price=stop;outcome="stop";bars_held=n;break
            if bar["high"]>=target:
                exit_price=target;outcome="target";bars_held=n;break
        else:
            if bar["open"]>=stop:
                exit_price=bar["open"];outcome="stop_gap";bars_held=n;break
            if bar["high"]>=stop:
                exit_price=stop;outcome="stop";bars_held=n;break
            if bar["low"]<=target:
                exit_price=target;outcome="target";bars_held=n;break
    fill=exit_price*(1-d*slip)
    gross=d*(fill-entry)/entry
    roundtrip_fee=fee*(1+fill/entry)
    funding_debit=funding*bars_held/32
    net=gross-roundtrip_fee-funding_debit
    return {"status":"matured","entry_ts":start,"exit_end_ts":start+bars_held*BAR_MS,
            "entry_open":start_open,"modeled_entry":entry,"modeled_exit":fill,
            "outcome":outcome,"bars_held":bars_held,
            "gross_after_slippage_pct":round(gross*100,5),
            "fee_pct":round(roundtrip_fee*100,5),
            "modeled_funding_pct":round(funding_debit*100,5),
            "net_unlevered_notional_pct":round(net*100,5)}


def build_audit(provenance, histories):
    signals=provenance.get("signals",[])
    if not signals:
        raise ValueError("No recorded research signals")
    rows=[]
    for row in signals:
        if row["symbol"] not in histories:
            raise ValueError("Missing recorded instrument price history")
        bars=histories[row["symbol"]]
        for horizon in HORIZONS:
            result=audit_signal(row,bars,horizon)
            rows.append({"run_id":row["run_id"],"published_utc":row["published_utc"],
                         "symbol":row["symbol"],"side":row["side"],
                         "source_url":row["source_url"],"horizon_minutes":horizon*15,
                         "advanced_confirmations":row["advanced_confirmations"],**result})
    summary={"candidate_quant_signals":len(signals),
             "unique_instruments":sorted({x["symbol"] for x in signals}),
             "modern_public_council_runs":len(provenance["original_council_runs"]),
             "additional_live_path_research_scans":1,
             "candidate_signals_across_modern_public_runs":
                  sum(x["signal_count"] for x in provenance["original_council_runs"]),
             "no_nvidia_approvals_recorded":True,
             "independence_warning":"Repeated ZEC and PEPE signals are overlapping, not statistically independent trades",
             "outcomes":{}}
    for horizon in (60,240):
        valid=[x for x in rows if x["horizon_minutes"]==horizon and x["status"]=="matured"]
        returns=[x["net_unlevered_notional_pct"] for x in valid]
        summary["outcomes"][str(horizon)]={
           "matured_count":len(valid),"not_yet_matured_count":
                 sum(x["horizon_minutes"]==horizon and x["status"]=="not_matured" for x in rows),
           "positive_count":sum(v>0 for v in returns),
           "negative_count":sum(v<0 for v in returns),
           "average_net_unlevered_pct":round(sum(returns)/len(returns),5) if returns else None,
           "median_net_unlevered_pct":round(sorted(returns)[len(returns)//2],5) if len(returns)%2 else
             (round((sorted(returns)[len(returns)//2-1]+sorted(returns)[len(returns)//2])/2,5) if returns else None)}
    return {"mode":"HISTORICAL_PUBLIC_RESEARCH_SIGNAL_OUTCOME_AUDIT_NO_TRADES",
            "scope":"Actual archived 6+7 research signals only; NVIDIA veto not historically observed",
            "assumptions":{"entry":"next_15m_open_after_report_publication",
              "exit":"reported_stop_or_target_first_else_horizon_close",
              "both_hit":"assume_stop_first",
              "taker_fee_each_side":TAKER_FEE,"slippage_each_side":SLIPPAGE,
              "funding_debit_8h_model":FUNDING_8H,
              "returns":"unlevered percentage of notional; not equity or live fills"},
            "summary":summary,"rows":rows}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--base",default="reports")
    parser.add_argument("--out",default="reports/actual_council_forward_20261108.json")
    args=parser.parse_args()
    base=Path(args.base)
    provenance=json.loads((base/"actual_council_signals_20261108.json").read_text())
    symbols={x["symbol"] for x in provenance["signals"]}
    histories={}
    for symbol in symbols:
        path=base/(symbol+".outcome_candles_20261108.json")
        histories[symbol]=json.loads(path.read_text())
    report=build_audit(provenance,histories)
    report["data_sha256"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(base.glob("*outcome_candles_20261108.json"))}
    target=Path(args.out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    for row in report["rows"]:
        print(row["symbol"],row["side"],row["horizon_minutes"],
              row["status"],row.get("outcome"),row.get("net_unlevered_notional_pct"))
    print("SUMMARY",json.dumps(report["summary"]["outcomes"]))
    return 0

if __name__=="__main__":
    raise SystemExit(main())

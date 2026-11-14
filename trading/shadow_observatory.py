#!/usr/bin/env python3
"""QUANT2037 Shadow Observatory: prospective decision attribution and forward validation.

Only archived PUBLIC six-agent+seven-quant scans and OKX PUBLIC OHLC data.
Never uses OKX private endpoints, account credentials, NVIDIA API, or order API.
Measures signals and WAITs, and identifies correlated repeat hypotheses.
It is an evidence collector, NOT a trade signal enhancer or live execution gate.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BAR_MS = 900_000
HORIZONS = (4, 16)  # 1h and 4h, fixed before evaluation
TAKER_FEE = .0005
SLIPPAGE = .0003
FUNDING_PER_8H = .0001
MIN_EPISODES = 100
MIN_SPAN_DAYS = 14
MAX_DAYS = 15

def utc_ms(s):
    dt=datetime.fromisoformat(s.replace("Z","+00:00"))
    if dt.tzinfo is None: raise ValueError("UTC timezone required")
    return int(dt.timestamp()*1000)

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,
                      allow_nan=False).encode("utf-8")

def sha(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()

def policy_fingerprint():
    """Fingerprint ONLY decision code, not arbitrary README or deployment commits."""
    root=Path(__file__).resolve().parent
    files=[root/"six_agent_council.py",root/"quant2037.py",
           root/"titan_fast_entry_router.py"]
    if not all(p.is_file() for p in files):
        return "unavailable_local_fixture"
    h=hashlib.sha256()
    for file in files:
        h.update(file.name.encode("utf-8"))
        h.update(b"\0")
        h.update(file.read_bytes())
    return h.hexdigest()


def freeze(report):
    """Immutable-by-value research snapshot of EVERY decision, including WAIT and errors."""
    if report.get("mode")!="SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY":
        raise ValueError("Unexpected research report mode")
    timestamp=report["utc_timestamp"]
    utc_ms(timestamp)
    rows=[]
    seen=set()
    for item in report.get("results",[]):
        sym=item["symbol"]
        if sym in seen or not sym.endswith("-USDT-SWAP"):
            raise ValueError("Invalid/duplicate market in scan")
        seen.add(sym)
        direction=item.get("signal")
        if direction not in ("LONG","SHORT","WAIT"):raise ValueError("Unknown decision")
        core=item.get("core_signal_before_advanced")
        roles=item.get("agents",[])
        advanced=item.get("advanced_systems",[])
        if len(roles)!=6 or len(advanced)!=7:raise ValueError("Missing council evidence")
        risk=next((x.get("evidence",{}) for x in roles
                   if x.get("agent")=="06_risk_marshal"),{})
        row={
          "symbol":sym,"decision":direction,"core_before_filters":core,
          "source_price":float(item["quote_price"]),
          "spread_bp":next((x.get("evidence",{}).get("spread_bp") for x in roles
                       if x.get("agent")=="01_liquidity_sentinel"),None),
          "last_complete_15m_candle_ms":item.get("last_complete_15m_candle_ms"),
          "buy_points":item.get("ordinal_buy_points"),"sell_points":item.get("ordinal_sell_points"),
          "advanced_confirmations":item.get("advanced_confirmations"),
          "advanced_contradictions":item.get("advanced_contradictions"),
          "advanced_veto_reasons":list(item.get("advanced_veto_reasons",[])),
          "derivatives_data_warnings":list(item.get("derivatives_data_warnings",[])),
          "role_votes":[{"name":x.get("agent"),"vote":x.get("vote"),
                         "strength":x.get("strength"),"veto":x.get("veto")} for x in roles],
          "quant_votes":[{"name":x.get("system"),"vote":x.get("vote"),
                          "risk":x.get("risk")} for x in advanced],
          "stop":risk.get("indicative_stop_not_an_order"),
          "target":risk.get("indicative_target_not_an_order")
        }
        if not math.isfinite(row["source_price"]) or row["source_price"]<=0:
            raise ValueError("Invalid source price")
        # Optional v1 research-only strategy output. Older snapshots remain valid.
        # Snapshot the actual public-time decision BEFORE future bars are known.
        fast=item.get("fast_entry_research")
        if fast is not None:
            if (not isinstance(fast,dict) or
                fast.get("model")!="fast-entry-research-v1" or
                fast.get("permission")!="RESEARCH_ONLY_NO_ORDERS" or
                fast.get("live_execution_allowed") is not False or
                type(fast.get("order_count")) is not int or fast["order_count"]!=0 or
                fast.get("direction") not in ("LONG","SHORT","WAIT")):
                raise ValueError("Invalid fast research envelope")
            side=fast["direction"]
            if side in ("LONG","SHORT"):
                stop,target=fast.get("stop"),fast.get("target")
                if (any(isinstance(v,bool) or not isinstance(v,(int,float)) or
                        not math.isfinite(v) or v<=0 for v in (stop,target)) or
                    (not stop<row["source_price"]<target if side=="LONG"
                     else not target<row["source_price"]<stop)):
                    raise ValueError("Invalid fast research protection")
                if fast.get("strategy") not in (
                    "20_bar_breakout","ema20_pullback","10_bar_liquidity_sweep"):
                    raise ValueError("Unrecognized prospective strategy")
            row["fast_entry_research"]={
                "direction":side,
                "strategy":fast.get("strategy") if side!="WAIT" else None,
                "stop":fast.get("stop") if side!="WAIT" else None,
                "target":fast.get("target") if side!="WAIT" else None,
                "research_only_no_orders":True
            }
        rows.append(row)
    errors=list(report.get("errors",[]))
    result={
      "schema":"quant2037-shadow-v1","mode":"PUBLIC_ONLY_NO_TRADES",
      "timestamp_utc":timestamp,"source_report_sha256":sha(report),
      "decision_policy_sha256":policy_fingerprint(),
      "selected":report.get("markets_selected"),"analyzed":len(rows),
      "decisions":rows,"errors":errors,
      "nvidia_gate":"NOT_EVALUATED_IN_READ_ONLY_SCAN",
      "orders_placed":0
    }
    result["snapshot_sha256"]=sha(result)
    return result

def verify_snapshot(snapshot):
    if snapshot.get("schema")!="quant2037-shadow-v1" or snapshot.get("mode")!="PUBLIC_ONLY_NO_TRADES":
        raise ValueError("Unrecognized snapshot")
    digest=snapshot.get("snapshot_sha256")
    without={k:v for k,v in snapshot.items() if k!="snapshot_sha256"}
    if sha(without)!=digest: raise ValueError("Changed or corrupt evidence")
    utc_ms(snapshot["timestamp_utc"])
    return True

def parse_bars(rows):
    by_ts={}
    for row in rows:
        if len(row)<9 or str(row[8])!="1":
            continue
        try:
            ts=int(row[0])
            op,hi,lo,cl=(float(x) for x in row[1:5])
            if all(math.isfinite(v) for v in (op,hi,lo,cl)) and 0<lo<=min(op,cl)<=max(op,cl)<=hi:
                by_ts[ts]={"ts":ts,"open":op,"high":hi,"low":lo,"close":cl}
        except (ValueError,TypeError,OverflowError):
            continue
    return [by_ts[t] for t in sorted(by_ts)]

def fetch_public_candles(symbol, oldest_ms, *, now_ms=None, max_pages=20):
    """Historical public endpoint only. Strict completed-bar and pagination checks."""
    if not symbol.endswith("-USDT-SWAP") or "/" in symbol:
        raise ValueError("Invalid instrument")
    now_ms=int(time.time()*1000) if now_ms is None else now_ms
    by_ts={}
    cursor=None
    for page in range(max_pages):
        params={"instId":symbol,"bar":"15m","limit":"100"}
        if cursor is not None:params["after"]=str(cursor)
        url="https://www.okx.com/api/v5/market/history-candles?"+urlencode(params)
        with urlopen(Request(url,headers={"Accept":"application/json",
                                         "User-Agent":"Quant2037-ResearchOnly/1.0"}),timeout=20) as resp:
            payload=json.load(resp)
        if payload.get("code")!="0" or not isinstance(payload.get("data"),list):
            raise RuntimeError("Public OKX market history error")
        rows=payload["data"]
        if not rows:break
        parsed=parse_bars(rows)
        if not parsed:raise ValueError("No valid complete history rows")
        oldest=min(int(x[0]) for x in rows)
        if cursor is not None and oldest>=cursor:
            raise ValueError("History pagination stalled")
        for bar in parsed:
            if bar["ts"]>=oldest_ms and bar["ts"]+BAR_MS<=now_ms:
                by_ts[bar["ts"]]=bar
        if oldest<=oldest_ms or len(rows)<100:
            break
        cursor=oldest
        time.sleep(.08)
    else:
        raise ValueError("History exceeded page safety bound")
    bars=[by_ts[k] for k in sorted(by_ts)]
    # A newly recorded research decision may not yet have even one completed
    # future candle. That is PENDING evidence, not a scanner or market failure.
    # outcome() marks its horizons immature until enough real bars are present.
    # Market API failures and missing bars inside an observed sequence still
    # fail closed instead of manufacturing a return.
    if any(b["ts"]-a["ts"]!=BAR_MS for a,b in zip(bars,bars[1:])):
        raise ValueError("Incomplete history: missing 15m bars")
    return bars

def outcome(decision, timestamp_utc, bars, horizon, *, fee=TAKER_FEE,
            slippage=SLIPPAGE, funding=FUNDING_PER_8H):
    """Next candle open after publication; no same-bar clairvoyance."""
    if horizon not in HORIZONS:raise ValueError("Horizon not fixed")
    posted=utc_ms(timestamp_utc)
    start=((posted+BAR_MS-1)//BAR_MS)*BAR_MS
    by_ts={bar["ts"]:bar for bar in bars}
    span=[by_ts.get(start+i*BAR_MS) for i in range(horizon)]
    if any(x is None for x in span):
        return {"status":"immature_or_missing"}
    side=decision["decision"]
    if side=="WAIT":
        return {"status":"abstained","next_horizon_abs_move_pct":
             round(abs(span[-1]["close"]/span[0]["open"]-1)*100,5)}
    if side not in ("LONG","SHORT"):raise ValueError("Unsupported direction")
    d=1 if side=="LONG" else -1
    start_open=span[0]["open"]
    entry=start_open*(1+d*slippage)
    stop=decision.get("stop")
    target=decision.get("target")
    # Evaluate directional return even if stop is missing, but do not impute fills.
    valid_stop=all(isinstance(v,(float,int)) and math.isfinite(v) and v>0
                   for v in (stop,target)) and (
                       stop<entry<target if d==1 else target<entry<stop)
    if not valid_stop:
        return {"status":"invalid_original_protection"}
    exit_raw=span[-1]["close"];exit_reason="time";bars_held=horizon
    for n,bar in enumerate(span,1):
        if d==1:
            if bar["open"]<=stop:
                exit_raw=bar["open"];exit_reason="stop_gap";bars_held=n;break
            if bar["low"]<=stop:
                exit_raw=stop;exit_reason="stop";bars_held=n;break
            if bar["high"]>=target:
                exit_raw=target;exit_reason="target";bars_held=n;break
        else:
            if bar["open"]>=stop:
                exit_raw=bar["open"];exit_reason="stop_gap";bars_held=n;break
            if bar["high"]>=stop:
                exit_raw=stop;exit_reason="stop";bars_held=n;break
            if bar["low"]<=target:
                exit_raw=target;exit_reason="target";bars_held=n;break
    fill=exit_raw*(1-d*slippage)
    gross=d*(fill-entry)/entry
    cost=fee*(1+fill/entry)+funding*(bars_held/32)
    return {"status":"matured","net_unlevered_pct":round(100*(gross-cost),6),
            "gross_after_slippage_pct":round(100*gross,6),
            "outcome":exit_reason,"bars_held":bars_held}

def diagnostic(record):
    """Attribution of gate causes, not an AI agent or calibrated profit prediction."""
    if record.get("decision")!="WAIT":return ["candidate_signal"]
    causes=[]
    if record.get("core_before_filters")=="WAIT":causes.append("core_no_consensus")
    if record.get("advanced_veto_reasons"):causes.append("seven_quant_veto")
    if record.get("derivatives_data_warnings"):causes.append("derivatives_data_quality")
    for role in record.get("role_votes",[]):
        if role["veto"]:causes.append(role["name"]+":hard_veto")
    return sorted(set(causes)) or ["unknown_abstain"]

def score(snapshots, bars_by_symbol):
    """All decisions included. Primary performance uses one episode per asset / 4h.

    Correlated repeated signals remain visible but excluded from PRIMARY stats.
    """
    unique={}
    for snap in snapshots:
        verify_snapshot(snap)
        unique[snap["snapshot_sha256"]]=snap
    snapshots=sorted(unique.values(),key=lambda s:utc_ms(s["timestamp_utc"]))
    rows=[];errors=[]
    last_episode={}
    for snap in snapshots:
        posted=utc_ms(snap["timestamp_utc"])
        for e in snap["errors"]:
            errors.append({"timestamp_utc":snap["timestamp_utc"],"error":e})
        for record in snap["decisions"]:
            sym=record["symbol"]
            if sym not in bars_by_symbol:raise ValueError("Missing OHLC history for "+sym)
            active=record["decision"]!="WAIT"
            key=sym
            correlated=bool(active and key in last_episode and
                        posted-last_episode[key] < 4*3600*1000)
            if active and not correlated:last_episode[key]=posted
            row={"snapshot_sha256":snap["snapshot_sha256"],
                 "timestamp_utc":snap["timestamp_utc"],"symbol":sym,
                 "decision_policy_sha256":snap["decision_policy_sha256"],
                 "decision":record["decision"],"episode_primary":active and not correlated,
                 "correlated_repeat":correlated,
                 "diagnostics":diagnostic(record),
                 "advanced_confirmations":record["advanced_confirmations"],
                 "advanced_veto_reasons":record["advanced_veto_reasons"],
                 "nvidia_approval":"NOT_OBSERVED"}
            for horizon in HORIZONS:
                row[str(horizon*15)+"m"]=outcome(record,snap["timestamp_utc"],
                                              bars_by_symbol[sym],horizon)
            rows.append(row)
    latest_policy=snapshots[-1]["decision_policy_sha256"] if snapshots else None
    # NEVER blend different strategy source-code versions into one "edge" statistic.
    eligible=[x for x in rows if x["episode_primary"] and
              x["decision_policy_sha256"]==latest_policy and
              x["60m"]["status"]=="matured"]
    vals=[x["60m"]["net_unlevered_pct"] for x in eligible]
    earliest=utc_ms(snapshots[0]["timestamp_utc"]) if snapshots else 0
    latest=utc_ms(snapshots[-1]["timestamp_utc"]) if snapshots else 0
    duration=(latest-earliest)/86_400_000 if snapshots else 0
    bycause=collections.Counter(c for r in rows for c in r["diagnostics"])
    report={"mode":"PREQUENTIAL_PUBLIC_SHADOW_RESEARCH","trading_allowed":False,
      "source":"Archived 6-core + 7-quant research decisions; NVIDIA not evaluated",
      "cost_model":{"taker_each_side":TAKER_FEE,"slippage_each_side":SLIPPAGE,
                    "modeled_funding_each_8h":FUNDING_PER_8H,
                    "not_actual_exchange_fills":True},
      "summary":{"snapshots":len(snapshots),"all_market_decisions":len(rows),
        "current_decision_policy_sha256":latest_policy,
        "unique_decision_policy_versions":len({s["decision_policy_sha256"] for s in snapshots}),
        "primary_statistics_restricted_to_latest_policy":True,
        "wait_count":sum(x["decision"]=="WAIT" for x in rows),
        "candidate_count":sum(x["decision"]!="WAIT" for x in rows),
        "primary_matured_1h_count":len(eligible),
        "correlated_repeat_count":sum(x["correlated_repeat"] for x in rows),
        "mean_1h_pct_primary":round(statistics.mean(vals),5) if vals else None,
        "positive_primary":sum(v>0 for v in vals),
        "negative_primary":sum(v<0 for v in vals),
        "first_utc":snapshots[0]["timestamp_utc"] if snapshots else None,
        "last_utc":snapshots[-1]["timestamp_utc"] if snapshots else None,
        "history_span_days":round(duration,3),
        "attribution_counts":dict(bycause),
        "errors_in_original_reports":len(errors),
        "minimum_primary_episodes_for_eligibility":MIN_EPISODES,
        "minimum_days_for_eligibility":MIN_SPAN_DAYS,
        "edge_established":False,
        "status":"INSUFFICIENT_PROSPECTIVE_EVIDENCE" if len(eligible)<MIN_EPISODES or duration<MIN_SPAN_DAYS
          else "REVIEW_REQUIRED_NOT_PROFIT_PROOF"},
      "rows":rows,"source_errors":errors,
      "limitations":["Decisions may have overlapping horizons; episodes are conservatively deduplicated by asset.",
        "WAIT is an abstention, not a profitable or unprofitable trade.",
        "No NVIDIA advisory approval or live execution can be inferred.",
        "OHLC stop-first, modeled fees and funding, no market latency or actual fills.",
        "Even 100 candidates do not alone establish statistical significance.",
        "Prior run artifacts are retained only while available on GitHub.",
        "Changing thresholds after reviewing results invalidates prospective claims.",
        "Primary statistics include only the latest fingerprint of the two quantitative policy modules."]}
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="cmd",required=True)
    cap=sub.add_parser("capture");cap.add_argument("--scan",required=True);cap.add_argument("--out",required=True)
    audit=sub.add_parser("audit");audit.add_argument("--archive-dir",required=True)
    audit.add_argument("--out",required=True);audit.add_argument("--now-ms",type=int)
    args=p.parse_args()
    target=Path(args.out);target.parent.mkdir(parents=True,exist_ok=True)
    if args.cmd=="capture":
        report=json.loads(Path(args.scan).read_text())
        output=freeze(report)
    else:
        snapshots=[]
        for file in sorted(Path(args.archive_dir).glob("**/quant2037_snapshot.json")):
            try:snapshots.append(json.loads(file.read_text()))
            except (OSError,json.JSONDecodeError) as exc:
                raise ValueError("Unparseable archived research snapshot") from exc
        if not snapshots:
            output={"mode":"PREQUENTIAL_PUBLIC_SHADOW_RESEARCH","trading_allowed":False,
                    "status":"NO_ARCHIVED_REPORTS_YET","snapshots":0}
        else:
            cutoff_ms=min(utc_ms(s["timestamp_utc"]) for s in snapshots)
            now_ms=args.now_ms or int(time.time()*1000)
            if cutoff_ms < now_ms-MAX_DAYS*86_400_000:
                snapshots=[s for s in snapshots
                           if utc_ms(s["timestamp_utc"])>=now_ms-MAX_DAYS*86_400_000]
            symbols=sorted({r["symbol"] for s in snapshots for r in s["decisions"]})
            histories={symbol:fetch_public_candles(symbol,
                        max(cutoff_ms-BAR_MS,now_ms-MAX_DAYS*86_400_000),now_ms=now_ms)
                       for symbol in symbols}
            output=score(snapshots,histories)
    target.write_bytes(canonical(output)+b"\n")
    print(json.dumps({"status":"completed","mode":output["mode"],
                      "summary":output.get("summary",{}),"path":str(target)}))
    return 0

if __name__=="__main__":
    raise SystemExit(main())

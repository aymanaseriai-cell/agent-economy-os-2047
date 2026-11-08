#!/usr/bin/env python3
"""QUANT2037 Microstructure Adversarial Twin.

Replays the EXACT original six agents and seven QUANT2037 functions against
frozen public OKX snapshots and deterministic stress mutations.
Does NOT access account/private OKX API, place trades, or call NVIDIA.
Stress scenarios are artificial falsification checks, NOT prediction evidence.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import time
from datetime import datetime,timezone
from pathlib import Path

from . import six_agent_council as council
from .quant2037 import evaluate_advanced

MILD_SCENARIOS = (
 "bid_depth_minus_20pct", "ask_depth_minus_20pct",
 "recent_trade_flip_10pct", "spread_plus_3bp",
 "last_up_5bp", "last_down_5bp",
)
HOSTILE_SCENARIOS = (
 "fake_bid_wall_x3", "fake_ask_wall_x3",
 "recent_trade_flip_30pct", "spread_plus_20bp",
 "stale_book_150sec",
)
SCENARIOS = MILD_SCENARIOS + HOSTILE_SCENARIOS
API_ALLOWLIST = frozenset({
 "/api/v5/market/tickers", "/api/v5/market/candles",
 "/api/v5/market/books", "/api/v5/market/trades",
 "/api/v5/public/funding-rate", "/api/v5/public/open-interest",
 "/api/v5/public/mark-price",
})

def checksum(obj):
    b=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,
                 allow_nan=False).encode("utf-8")
    return hashlib.sha256(b).hexdigest()

def public_get(path,params):
    if path not in API_ALLOWLIST:
        raise ValueError("Nonpublic or unapproved endpoint forbidden: "+path)
    return council.okx_get(path,params)

def capture_market(ticker, get=public_get, *, clock_ms=None):
    """Public market feeds only. Every input is frozen BEFORE any mutation."""
    symbol=ticker["symbol"]
    if not symbol.endswith("-USDT-SWAP"):raise ValueError("Invalid symbol")
    def q(path,params):
        return get(path,{"instId":symbol,**params})
    raw={
      "ticker":dict(ticker),
      "bars15":q("/api/v5/market/candles",{"bar":"15m","limit":"210"}),
      "bars1h":q("/api/v5/market/candles",{"bar":"1H","limit":"80"}),
      "bars4h":q("/api/v5/market/candles",{"bar":"4H","limit":"50"}),
      "book":q("/api/v5/market/books",{"sz":"50"})[0],
      "trades":q("/api/v5/market/trades",{"limit":"200"}),
    }
    missing=[]
    for name,path,params in (
       ("funding","/api/v5/public/funding-rate",{}),
       ("interest","/api/v5/public/open-interest",{"instType":"SWAP"}),
       ("mark","/api/v5/public/mark-price",{"instType":"SWAP"})):
        try:
            rows=q(path,params)
            raw[name]=rows[0] if rows else {}
            if not rows:missing.append(name)
        except (RuntimeError,ValueError,KeyError,IndexError) as exc:
            raw[name]={};missing.append(name)
    raw["missing_derivative_feeds"]=missing
    raw["captured_at_ms"]=int(time.time()*1000) if clock_ms is None else int(clock_ms)
    raw["source"]="OKX_PUBLIC_MARKET_ENDPOINTS_ONLY"
    return raw

def replay_original(frozen):
    """Full original 6+7 algorithm, with its book-age clock fixed to capture time."""
    if frozen.get("source")!="OKX_PUBLIC_MARKET_ENDPOINTS_ONLY":
        raise ValueError("Unverified public-data snapshot")
    bars15=council.candles(frozen["bars15"])
    h1=council.candles(frozen["bars1h"])
    h4=council.candles(frozen["bars4h"])
    if len(bars15)<192 or len(h1)<30 or len(h4)<15:
        raise ValueError("Insufficient completed real OHLCV history")
    core=council.summarize_agents(
        frozen["ticker"],bars15,h1,h4,frozen["book"],frozen["trades"],
        frozen["funding"],frozen["interest"],frozen["mark"],
        asof_epoch=frozen["captured_at_ms"]/1000)
    advanced=evaluate_advanced(bars15,frozen["book"],frozen["trades"],core)
    core.update(advanced)
    if frozen["missing_derivative_feeds"]:
        core["advanced_veto_reasons"].append("missing_or_unavailable_derivatives_data")
        core["signal"]="WAIT"
    return core

def _size_multiply(frozen,which,factor,first=10):
    levels=frozen["book"][which]
    if not levels: raise ValueError("Cannot stress empty book")
    for level in levels[:first]:
        level[1]=str(float(level[1])*factor)

def _flip_recent_trades(frozen, fraction):
    rows=frozen["trades"]
    valid=[(int(x.get("ts",0)),i) for i,x in enumerate(rows)
           if x.get("side") in ("buy","sell") and x.get("ts")]
    if not valid:raise ValueError("Cannot stress missing trade tape")
    n=max(1,math.ceil(len(valid)*fraction))
    for _,i in sorted(valid,reverse=True)[:n]:
        trade=rows[i]
        trade["side"]="sell" if trade["side"]=="buy" else "buy"

def _spread_increment(frozen,added_bp):
    t=frozen["ticker"]
    bid,ask=float(t["bid"]),float(t["ask"])
    mid=(bid+ask)/2
    spread=(ask-bid)+mid*added_bp/10000
    if spread >= 2*mid: raise ValueError("Implausible stressed bid/ask")
    t["bid"]=mid-spread/2
    t["ask"]=mid+spread/2
    t["spread_bp"]=round(10000*(t["ask"]-t["bid"])/mid,3)

def mutate(frozen,mode):
    if mode not in SCENARIOS:raise ValueError("Unregistered experiment")
    candidate=copy.deepcopy(frozen)
    if mode=="bid_depth_minus_20pct":_size_multiply(candidate,"bids",.8)
    elif mode=="ask_depth_minus_20pct":_size_multiply(candidate,"asks",.8)
    elif mode=="fake_bid_wall_x3":_size_multiply(candidate,"bids",3.0,first=5)
    elif mode=="fake_ask_wall_x3":_size_multiply(candidate,"asks",3.0,first=5)
    elif mode=="recent_trade_flip_10pct":_flip_recent_trades(candidate,.1)
    elif mode=="recent_trade_flip_30pct":_flip_recent_trades(candidate,.3)
    elif mode=="spread_plus_3bp":_spread_increment(candidate,3)
    elif mode=="spread_plus_20bp":_spread_increment(candidate,20)
    elif mode=="last_up_5bp":candidate["ticker"]["last"]*=1.0005
    elif mode=="last_down_5bp":candidate["ticker"]["last"]*=.9995
    elif mode=="stale_book_150sec":
        candidate["book"]["ts"]=str(candidate["captured_at_ms"]-150_000)
    # No modifications ever propagate back to the frozen original.
    return candidate

def gate_signature(record):
    roles=[(x["agent"],x["vote"],x["veto"]) for x in record["agents"]]
    quant=[(x["system"],x["vote"],x["risk"]) for x in record["advanced_systems"]]
    return {"signal":record["signal"],
            "core_signal":record["core_signal_before_advanced"],
            "six_roles":roles,"seven_systems":quant,
            "advanced_confirmations":record["advanced_confirmations"],
            "advanced_veto_reasons":record["advanced_veto_reasons"]}

def analyze_frozen(frozen):
    before=checksum(frozen)
    base=gate_signature(replay_original(frozen))
    attacks=[]
    for mode in SCENARIOS:
        try:
            variant=gate_signature(replay_original(mutate(frozen,mode)))
            error=None
        except (ValueError,TypeError,IndexError,KeyError,ZeroDivisionError) as exc:
            variant=None;error=type(exc).__name__+":"+str(exc)[:160]
        role_changes=([x[0] for x,y in zip(base["six_roles"],variant["six_roles"])
                       if x!=y] if variant else [])
        quant_changes=([x[0] for x,y in zip(base["seven_systems"],variant["seven_systems"])
                        if x!=y] if variant else [])
        attacks.append({
          "experiment":mode,
          "severity":"MILD" if mode in MILD_SCENARIOS else "HOSTILE",
          "result":variant,
          "error":error,
          "changed_final_decision":variant["signal"]!=base["signal"] if variant else None,
          "changed_core_vote":variant["core_signal"]!=base["core_signal"] if variant else None,
          "changed_roles":role_changes,"changed_quant_systems":quant_changes,
          "changed_role_count":len(role_changes),
          "changed_quant_count":len(quant_changes),
          "opposite_entry":bool(base["signal"] in ("LONG","SHORT") and
                    variant and variant["signal"] in ("LONG","SHORT") and
                    variant["signal"]!=base["signal"])
        })
    if checksum(frozen)!=before:raise RuntimeError("Original evidence mutated")
    mild=[x for x in attacks if x["severity"]=="MILD"]
    hostile=[x for x in attacks if x["severity"]=="HOSTILE"]
    return {
      "symbol":frozen["ticker"]["symbol"],"source_sha256":before,
      "captured_at_utc":datetime.fromtimestamp(
        frozen["captured_at_ms"]/1000,timezone.utc).isoformat(),
      "baseline":base,"stress":attacks,
      "mild_changed_count":sum(x["changed_final_decision"] is True for x in mild),
      "mild_failed_count":sum(x["result"] is None for x in mild),
      "mild_role_vote_changes":sum(x["changed_role_count"] for x in mild),
      "mild_quant_system_changes":sum(x["changed_quant_count"] for x in mild),
      "hostile_role_vote_changes":sum(x["changed_role_count"] for x in hostile),
      "hostile_quant_system_changes":sum(x["changed_quant_count"] for x in hostile),
      "hostile_changed_count":sum(x["changed_final_decision"] is True for x in hostile),
      "opposite_direction_cases":sum(x["opposite_entry"] for x in attacks),
      "baseline_market_decision_stable_under_all_mild":
        all(x["changed_final_decision"] is False for x in mild),
      "mild_input_fragility_if_candidate":
        (any(x["changed_final_decision"] is True or x["result"] is None for x in mild)
          if base["signal"] in ("LONG","SHORT") else None),
      "note":"Synthetic perturbation of public feeds; stability is NOT predictive alpha."
    }

def verify_package(package):
    if package.get("schema")!="quant2037-adversary-public-v1":
        raise ValueError("Unrecognized market evidence")
    if checksum({k:v for k,v in package.items() if k!="evidence_sha256"})!=package.get("evidence_sha256"):
        raise ValueError("Market evidence checksum mismatch")
    return True

def build_report(package):
    verify_package(package)
    results=[]
    errors=list(package["capture_errors"])
    for frozen in package["markets"]:
        try:results.append(analyze_frozen(frozen))
        except (ValueError,TypeError,IndexError,KeyError,ZeroDivisionError) as exc:
            errors.append({"symbol":frozen.get("ticker",{}).get("symbol"),
                           "stage":"offline_exact_model_replay",
                           "error":type(exc).__name__+":"+str(exc)[:180]})
    candidate=[x for x in results if x["baseline"]["signal"]!="WAIT"]
    return {
       "mode":"QUANT2037_ADVERSARIAL_PUBLIC_ONLY_NO_TRADES",
       "source_evidence_sha256":package["evidence_sha256"],
       "replayed_using":"EXACT_6_SPECIALIST_PLUS_7_QUANT_PYTHON_FUNCTIONS",
       "synthetic_stress":True,"nvidia_evaluated":False,"order_count":0,
       "experiment_registry":{"mild":list(MILD_SCENARIOS),"hostile":list(HOSTILE_SCENARIOS)},
       "summary":{"markets_captured":len(package["markets"]),
         "markets_evaluated":len(results),"candidate_signals":len(candidate),
         "candidate_with_mild_instability":
           sum(x["mild_input_fragility_if_candidate"] is True for x in candidate),
         "opposite_decision_under_attack":
           sum(x["opposite_direction_cases"] for x in results),
         "mild_changed_core_role_votes":sum(x["mild_role_vote_changes"] for x in results),
         "mild_changed_seven_quant_verdicts":sum(x["mild_quant_system_changes"] for x in results),
         "hostile_changed_core_role_votes":sum(x["hostile_role_vote_changes"] for x in results),
         "hostile_changed_seven_quant_verdicts":sum(x["hostile_quant_system_changes"] for x in results),
         "mild_decision_change_events":sum(x["mild_changed_count"] for x in results),
         "hostile_decision_change_events":sum(x["hostile_changed_count"] for x in results),
         "market_errors":len(errors),"not_validated_profit_edge":True},
       "markets":results,"errors":errors,
       "limitations":[
         "Synthetic book/tape/spread perturbations do not establish market manipulation.",
         "One public L2 snapshot cannot detect spoofing or measure real fill probability.",
         "Inputs from sequential API calls are not exchange-atomic.",
         "Robustness on a few snapshots is not evidence of profitable trading.",
         "Original live NVIDIA veto cannot be reconstructed or authorized here.",
         "Experimental attacks never change the production trading decision or live gates."
       ]
    }

def collect(top):
    if not 1<=top<=6:raise ValueError("1..6 public symbols only")
    selected=council.select_markets(public_get("/api/v5/market/tickers",
                                              {"instType":"SWAP"}),top)
    package={"schema":"quant2037-adversary-public-v1",
             "captured_at_utc":datetime.now(timezone.utc).isoformat(),
             "captured_selected":len(selected),"markets":[],"capture_errors":[]}
    for ticker in selected:
        try:package["markets"].append(capture_market(ticker))
        except (RuntimeError,ValueError,KeyError,IndexError) as exc:
            package["capture_errors"].append({"symbol":ticker["symbol"],
                                              "error":type(exc).__name__+":"+str(exc)[:160]})
        time.sleep(.2)
    package["evidence_sha256"]=checksum(package)
    return package

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="cmd",required=True)
    cap=sub.add_parser("capture")
    cap.add_argument("--top",type=int,default=3)
    cap.add_argument("--evidence",default="reports/adversary_public_inputs.json")
    cap.add_argument("--out",default="reports/adversary_decisions.json")
    rep=sub.add_parser("replay")
    rep.add_argument("--evidence",required=True)
    rep.add_argument("--out",required=True)
    args=parser.parse_args()
    if args.cmd=="capture":
        package=collect(args.top)
        evidence=Path(args.evidence);evidence.parent.mkdir(parents=True,exist_ok=True)
        evidence.write_text(json.dumps(package,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    else:
        package=json.loads(Path(args.evidence).read_text())
    result=build_report(package)
    output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print("ADVERSARIAL 2037",json.dumps(result["summary"],sort_keys=True))
    print("FROZEN AUDIT SHA256",result["source_evidence_sha256"])
    print("REPORT",output)
    return 0 if result["summary"]["markets_evaluated"] else 2

if __name__=="__main__":
    raise SystemExit(main())

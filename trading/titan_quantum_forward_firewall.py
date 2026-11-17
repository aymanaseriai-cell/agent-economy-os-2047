#!/usr/bin/env python3
"""TITAN Ω QUANTUM FORWARD FIREWALL — public OKX shadow only.

Lock QSI robust quantum vs identical-information classical before future entry.
A SHA256-sealed, GitHub Actions artifact is the only basis for later scoring.
The scorer NEVER recomputes decisions and refuses premature/untrusted seals.
All hypothetically executable quantities use public OKX minSz, lotSz, ctVal,
a real-sized PAPER 4.15-USDT single-position portfolio, modeled fees/slippage,
conservative stop/liquidation proxy and a stress test. NO PRIVATE API/ORDERS.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

from trading.edge_lab import (
    BAR_MS, TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE, STRESS_SLIPPAGE,
    FUNDING_PER_8H, atr_simple, fetch_history
)
from trading.titan_regime_research import validate_frozen
from trading.titan_quantum_survival_interferometer import (
    START, TARGET, RUIN, SCAN_STRIDE, WARMUP, DECISION_CUTOFF,
    MAX_MARGIN_PART, MAX_PLANNED_STOP_RISK, STOP_MULT,
    interferometer, classical_probability, affordable_contracts, sim_one
)

LOCKED_SYMBOLS=("1INCH-USDT-SWAP","CFX-USDT-SWAP","XTZ-USDT-SWAP",
                "BLUR-USDT-SWAP","ZK-USDT-SWAP","LPT-USDT-SWAP")
LOCKED_ORIGINAL_SOURCE="trading/titan_quantum_survival_interferometer.py"
HISTORY_DAYS=5
HORIZON=4
RESEARCH_LEVERAGE=3.
MAX_STALE_MS=BAR_MS*2
MODE="SEALED_FUTURE_QUANTUM_MICRO_PUBLIC_ONLY_V1"
FAMILIES=("quantum_phase_robust","classical_same_features")


def _canon(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


def _hash(value):
    return hashlib.sha256(_canon(value)).hexdigest()


def _utc(milliseconds):
    return datetime.fromtimestamp(milliseconds/1000,timezone.utc).isoformat()


def _public_spec(symbol):
    if symbol not in LOCKED_SYMBOLS:
        raise ValueError("Unlisted symbol")
    url="https://www.okx.com/api/v5/public/instruments?"+urlencode(
        {"instType":"SWAP","instId":symbol})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-Forward-Firewall/1.0"}),
                 timeout=20) as response:
        obj=json.load(response)
    rows=obj.get("data",[])
    if obj.get("code")!="0" or len(rows)!=1 or rows[0].get("instId")!=symbol:
        raise ValueError("Public min contract metadata unavailable")
    z=rows[0]
    if z.get("ctType")!="linear" or z.get("state")!="live":
        raise ValueError("Nonlive/nonlinear public contract")
    return {k:z.get(k) for k in
            ("instId","ctValCcy","ctVal","minSz","lotSz","state","ctType")}


def _decision(bars):
    """Reimplement precisely QSI robust/candidate rules at latest completed i.

    This is a forward-scanning adaptation: candidate_stream originally skips
    the final candle. A signal here uses ONLY that last completed candle.
    """
    validate_frozen(bars)
    i=len(bars)-1
    close=[float(b["close"]) for b in bars]
    atr=atr_simple(bars,i,14)
    af=atr/close[i]
    # Prospective cadence must be anchored to absolute UTC bar time, NOT
    # a rolling fetch array index (which can have the same modulo forever).
    # This is a one-time clock-alignment correction before the first seal.
    if i<WARMUP or (bars[i]["ts"]//BAR_MS)%SCAN_STRIDE!=0 or not .0012<=af<=.05:
        return {"quantum_phase_robust":0,"classical_same_features":0,
                "quantum_strength":0.0,"classical_strength":0.0,
                "atr":round(atr,10),"scan_eligible":False}
    f=tuple(max(-3,min(3,math.log(close[i]/close[i-lag])/
                    max(af*math.sqrt(lag),1e-8))) for lag in (8,32,96))
    qp,_=interferometer(f)
    qlo,_=interferometer(f,phase=.7)
    qhi,_=interferometer(f,phase=1.3)
    cp=classical_probability(f)
    quantum=(1 if min(qp,qlo,qhi)>=DECISION_CUTOFF
             else -1 if max(qp,qlo,qhi)<=1-DECISION_CUTOFF else 0)
    classical=(1 if cp>=DECISION_CUTOFF
               else -1 if cp<=1-DECISION_CUTOFF else 0)
    strength=(min(qp,qlo,qhi)-.5 if quantum>0 else
              .5-max(qp,qlo,qhi) if quantum<0 else 0)
    return {"quantum_phase_robust":quantum,
            "classical_same_features":classical,
            "quantum_strength":round(max(0.,strength),8),
            "classical_strength":round(abs(cp-.5) if classical else 0.,8),
            "atr":round(atr,10),"scan_eligible":True}


def capture(*,now_ms=None,get_bars=fetch_history,get_spec=_public_spec,
            git_sha="unknown",run_id="unknown"):
    timestamp=int(time.time()*1000) if now_ms is None else int(now_ms)
    # TWO subsequent 15m-bar boundaries ensures entry remains in the future.
    entry=(timestamp//BAR_MS+2)*BAR_MS
    mature=entry+HORIZON*BAR_MS
    rows=[]
    for sym in LOCKED_SYMBOLS:
        bars=get_bars(sym,HISTORY_DAYS,now_ms=timestamp)
        validate_frozen(bars)
        last=bars[-1]["ts"]
        if (last+BAR_MS>timestamp or
            timestamp-last-BAR_MS>MAX_STALE_MS):
            raise ValueError("Last completed candle stale/unconfirmed for "+sym)
        specs=get_spec(sym)
        if specs.get("instId")!=sym:
            raise ValueError("Missing public instrument verification for "+sym)
        signal=_decision(bars)
        qty,notional=affordable_contracts(specs,bars[-1]["close"],
                                          signal["atr"],START,RESEARCH_LEVERAGE)
        rows.append({
            "symbol":sym,"latest_completed_bar_start_ms":last,
            "latest_completed_candle_sha256":_hash(bars[-1]),
            "latest_completed_close":bars[-1]["close"],
            "signals":{k:signal[k] for k in FAMILIES},
            "signal_strengths":{"quantum_phase_robust":signal["quantum_strength"],
                                "classical_same_features":signal["classical_strength"]},
            "stop_atr_observed":signal["atr"],
            "scan_eligible":signal["scan_eligible"],
            "public_frozen_contract":specs,
            "approx_public_3x_min_lot_feasible":qty>0,
            "public_test_quantity":qty,
            "public_test_notional_usdt":round(notional,7),
        })
    proof={
        "mode":MODE,
        "created_at_ms":timestamp,
        "created_at_utc":_utc(timestamp),
        "source_commit_sha":git_sha,
        "source_github_run_id":str(run_id),
        "model_source_locked":LOCKED_ORIGINAL_SOURCE,
        "trade_execution_mode":"PAPER_ONLY",
        "market_symbols_locked":list(LOCKED_SYMBOLS),
        "families_locked":list(FAMILIES),
        "entry_future_bar_start_ms":entry,
        "maturity_not_before_ms":mature,
        "horizon_completed_15m_candles":HORIZON,
        "start_usdt_not_real_account":START,
        "target_usdt":TARGET,
        "ruin_usdt":RUIN,
        "leverage_research_only":RESEARCH_LEVERAGE,
        "initial_margin_budget":MAX_MARGIN_PART,
        "planned_stop_risk_budget":MAX_PLANNED_STOP_RISK,
        "ordinary_costs":{"fee":TAKER_FEE,"slippage":BASE_SLIPPAGE,
                          "funding_per_8h":FUNDING_PER_8H},
        "stress_costs":{"fee":STRESS_FEE,"slippage":STRESS_SLIPPAGE,
                        "funding_per_8h":FUNDING_PER_8H},
        "source_completed_candles_only":True,
        "no_private_okx_api_no_orders":True,
        "rows":rows,
    }
    proof["seal_sha256"]=_hash(proof)
    if entry<=timestamp:
        raise AssertionError("Prospective entry not after seal")
    return proof


def _validate(proof):
    if not isinstance(proof,dict) or proof.get("mode")!=MODE:
        raise ValueError("Missing foreign/signed forward record")
    data={k:v for k,v in proof.items() if k!="seal_sha256"}
    if proof.get("seal_sha256")!=_hash(data):
        raise ValueError("Forward seal was changed after creation")
    if (proof.get("families_locked")!=list(FAMILIES)
        or proof.get("market_symbols_locked")!=list(LOCKED_SYMBOLS)
        or proof.get("horizon_completed_15m_candles")!=HORIZON
        or proof.get("start_usdt_not_real_account")!=START
        or proof.get("target_usdt")!=TARGET
        or proof.get("ruin_usdt")!=RUIN
        or proof.get("source_completed_candles_only") is not True
        or proof.get("no_private_okx_api_no_orders") is not True
        or proof.get("leverage_research_only")!=RESEARCH_LEVERAGE):
        raise ValueError("Forward model/control specification mutated")
    created=proof["created_at_ms"];entry=proof["entry_future_bar_start_ms"]
    mature=proof["maturity_not_before_ms"]
    if (not all(type(x)==int and x>0 for x in (created,entry,mature)) or
        not entry>created or entry%BAR_MS or mature!=entry+HORIZON*BAR_MS):
        raise ValueError("Invalid prospective horizon")
    if len(proof.get("rows",[]))!=len(LOCKED_SYMBOLS):
        raise ValueError("Missing public market snapshot")
    if sorted(z["symbol"] for z in proof["rows"])!=sorted(LOCKED_SYMBOLS):
        raise ValueError("Duplicate or missing symbol")
    for z in proof["rows"]:
        if z["latest_completed_bar_start_ms"]+BAR_MS>created:
            raise ValueError("Post-seal market input")
        if set(z["signals"])!=set(FAMILIES) or any(
            type(v)!=int or v not in (-1,0,1) for v in z["signals"].values()):
            raise ValueError("Unexpected prospective side")
        if (not isinstance(z["stop_atr_observed"],(int,float)) or
            z["stop_atr_observed"]<=0):
            raise ValueError("Invalid sealed stop")
    return True


def score(proof,*,now_ms=None,get_bars=fetch_history):
    _validate(proof)
    timestamp=int(time.time()*1000) if now_ms is None else int(now_ms)
    if timestamp<proof["maturity_not_before_ms"]:
        raise ValueError("Future market candles not yet complete")
    records={family:[] for family in FAMILIES}
    all_market_rows=[]
    entry=proof["entry_future_bar_start_ms"]
    for frozen in proof["rows"]:
        sym=frozen["symbol"]
        market=get_bars(sym,HISTORY_DAYS,now_ms=timestamp)
        validate_frozen(market)
        by_time={b["ts"]:idx for idx,b in enumerate(market)}
        needed=[entry+k*BAR_MS for k in range(HORIZON)]
        if any(t not in by_time or t+BAR_MS>timestamp for t in needed):
            raise ValueError("Unverified future completed bars for "+sym)
        first=by_time[entry]
        if first==0 or [by_time[t] for t in needed]!=list(range(first,first+HORIZON)):
            raise ValueError("Forward history has gaps or missing signal predecessor")
        for family in FAMILIES:
            side=frozen["signals"][family]
            rec={"symbol":sym,"family":family,"side_frozen_before_entry":side,
                 "status":"WAIT" if side==0 else "PAPER_CANDIDATE",
                 "signal_strength":frozen["signal_strengths"][family],
                 "seal_sha256":proof["seal_sha256"],
                 "future_entry_ms":entry,
                 "future_horizon_complete_ms":proof["maturity_not_before_ms"]}
            if side:
                signal=(first-1,side,frozen["stop_atr_observed"],
                        frozen["signal_strengths"][family])
                normal=sim_one(market,signal,frozen["public_frozen_contract"],
                               equity=START,leverage=RESEARCH_LEVERAGE,
                               fee=TAKER_FEE,slip=BASE_SLIPPAGE,end=first+HORIZON)
                stress=sim_one(market,signal,frozen["public_frozen_contract"],
                               equity=START,leverage=RESEARCH_LEVERAGE,
                               fee=STRESS_FEE,slip=STRESS_SLIPPAGE,end=first+HORIZON)
                if normal is None or stress is None:
                    rec["status"]="PUBLIC_LOT_UNFILLABLE_OR_BUDGET_REJECTED"
                else:
                    rec["hypothetical_normal_net_usdt"]=normal["net_usdt"]
                    rec["hypothetical_stress_net_usdt"]=stress["net_usdt"]
                    rec["paper_normal_end_usdt"]=normal["equity_after"]
                    rec["paper_stress_end_usdt"]=stress["equity_after"]
                    rec["paper_close_reason"]=normal["status"]
                    rec["paper_contract_quantity"]=normal["min_contract_quantity"]
            records[family].append(rec)
            all_market_rows.append(rec)
    outcomes={}
    for family,rows in records.items():
        eligible=[r for r in rows if r["status"]=="PAPER_CANDIDATE"]
        ranked=sorted(eligible,key=lambda r:(-r["signal_strength"],r["symbol"]))
        best=ranked[0] if ranked else None
        outcomes[family]={
            "signal_count":sum(r["side_frozen_before_entry"]!=0 for r in rows),
            "shadow_filled_count_this_window":1 if best else 0,
            "best_frozen_symbol":best["symbol"] if best else None,
            "paper_start_usdt":START,
            "paper_end_usdt":best["paper_normal_end_usdt"] if best else START,
            "paper_stress_end_usdt":best["paper_stress_end_usdt"] if best else START,
            "hit_target":bool(best and best["paper_normal_end_usdt"]>=TARGET),
            "hit_ruin":bool(best and best["paper_normal_end_usdt"]<=RUIN),
            "verified_repeatable_edge":False,
        }
    return {
        "mode":"SCORED_MATURED_SEALED_QUANTUM_SHADOW_NO_ORDERS",
        "seal_sha256":proof["seal_sha256"],
        "captured_at_utc":proof["created_at_utc"],
        "scored_at_utc":_utc(timestamp),
        "entry_after_seal_verified":entry>proof["created_at_ms"],
        "complete_15m_horizon_verified":True,
        "source_run_id":proof["source_github_run_id"],
        "no_real_orders":True,
        "no_private_account_read":True,
        "comparison":outcomes,
        "all_recorded_markets":all_market_rows,
        "warning":"Single future snapshot is not independent evidence of repeated profits; public 15m OHLC is not actual executed OKX fill, funding or liquidation.",
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("capture");a.add_argument("--out",required=True)
    b=sub.add_parser("score");b.add_argument("--sealed",required=True);b.add_argument("--out",required=True)
    options=p.parse_args(argv)
    out=Path(options.out)
    if options.command=="capture":
        report=capture(git_sha=os.environ.get("GITHUB_SHA","unknown"),
                       run_id=os.environ.get("GITHUB_RUN_ID","unknown"))
        if int(time.time()*1000)>=report["entry_future_bar_start_ms"]:
            raise ValueError("Too late to capture before prescribed entry")
        print("QUANTUM FORWARD SEALED",report["seal_sha256"],
              "run_id",report["source_github_run_id"],
              "future_entry_utc",_utc(report["entry_future_bar_start_ms"]),
              "score_after_utc",_utc(report["maturity_not_before_ms"]),
              "signal_counts",{f:sum(z["signals"][f]!=0 for z in report["rows"])
                               for f in FAMILIES},"NO ORDERS",flush=True)
    else:
        proof=json.loads(Path(options.sealed).read_text(encoding="utf-8"))
        report=score(proof)
        print("QUANTUM FORWARD SCORED",report["seal_sha256"],
              report["comparison"],"NO ORDERS",flush=True)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

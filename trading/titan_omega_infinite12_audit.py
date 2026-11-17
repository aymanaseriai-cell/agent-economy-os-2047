"""Independent ledger/source/accounting auditor. No strategy-module imports."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

MILLIS=900000
COST={"ordinary":0.0005,"stress":0.0015}
MAX_MARGIN=0.25
PARTICIPATION=0.001


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),
        allow_nan=False).encode()).hexdigest()


def close(a,b):
    return math.isclose(a,b,rel_tol=1e-7,abs_tol=1e-8)


def audit(raw,report):
    errors=[]
    def require(c,message):
        if not c:
            errors.append(message)
    require(raw.get("seal_sha256")==digest({k:v for k,v in raw.items() if k!="seal_sha256"}),"source seal mismatch")
    require(raw.get("real_orders")==0 and report.get("real_orders")==0,"non-paper operation")
    require(report.get("source_seal_sha256")==raw.get("seal_sha256"),"wrong input source")
    require(report.get("scientific_verdict")=="NO_NEW_INDEPENDENT_OUT_OF_SAMPLE_PROOF","false scientific verdict")
    require(report.get("best_independent_net_pct") is None,"independent results fabricated")
    verify_count=0
    summary={}
    for sym, data in raw.get("markets",{}).items():
        for f,obj in (("bar_sha256",data["bars"]),("funding_sha256",data["funding"]),("spec_sha256",data["spec"])):
            require(data.get(f)==digest(obj),"market source hash "+sym+" "+f)
        for first,second in zip(data["bars"],data["bars"][1:]):
            require(second["ts"]-first["ts"]==MILLIS,"bar discontinuity")
    for w in report.get("windows",[]):
        sym=w["symbol"];model=w["model"];case=w["cost"]
        require(sym in raw["markets"],"undeclared instrument")
        if sym not in raw["markets"]:
            continue
        bars=raw["markets"][sym]["bars"]
        require(w["end_idx"]-w["start_idx"]==48,"not a 12h window")
        require(w["end_ts"]-w["start_ts"]==48*MILLIS,"wrong time horizon")
        require(close(w["start_equity"],4.15),"wrong initial capital")
        require(w["start_idx"]>=33,"noncausal warmup")
        equity=4.15
        prev_exit=-1
        for t in w["trades"]:
            verify_count+=1
            start=t["entry_idx"];finish=t["exit_idx"]
            require(start>prev_exit,"overlapping positions")
            prev_exit=finish
            require(w["start_idx"]<=start<=finish<w["end_idx"],"trade outside window")
            require(t["symbol"]==sym and t["model"]==model and t["cost"]==case,"ledger provenance mismatch")
            require(t["signal_last_completed_ts"]+MILLIS==t["entry_ts"],"future signal or wrong entry")
            require(t["entry_ts"]==bars[start]["ts"] and t["exit_ts"]==bars[finish]["ts"]+MILLIS,"wrong candle timestamps")
            require(t["side"] in (-1,1),"zero side for filled position")
            require(t["exit_type"] in ("time","stop","liquidation_proxy"),"unrecognized exit")
            require(0<t["qty_contracts"] and 0<t["ct_val"] and 0<t["leverage"]<=min(100,t["contract_leverage_cap"]),"bad notional/leverage")
            require(t["qty_contracts"]+1e-9>=t["min_sz"],"below minimum quantity")
            require(close(t["qty_contracts"]/t["lot_sz"],round(t["qty_contracts"]/t["lot_sz"])),"lot not quantized")
            require(t["margin"] <= MAX_MARGIN*equity*(1+0.002),"margin exceeds cap")
            require(t["qty_contracts"]*t["ct_val"]*t["entry_px"]<=t["previous_quote_volume"]*PARTICIPATION*(1+0.002),"future or excess volume participation")
            gross=t["side"]*(t["exit_px"]-t["entry_px"])*t["qty_contracts"]*t["ct_val"]
            fee=COST[case]*t["qty_contracts"]*t["ct_val"]*(t["entry_px"]+t["exit_px"])
            require(close(t["gross_usdt"],gross),"gross mismatch")
            require(close(t["fees_usdt"],fee),"fees mismatch")
            require(t["fees_usdt"]>=0,"negative fee")
            require(t["funding_basis"] in ("original_realized_public_events","conservative_assumption_not_observed"),"funding provenance absent")
            if t["funding_basis"]=="conservative_assumption_not_observed":
                require(t["funding_usdt"]>=0,"proxy financing must not create free money")
            require(close(t["net_usdt"],gross-fee-t["funding_usdt"]),"net PnL mismatch")
            require(close(t["equity_before"],equity),"noncompounded or floating equity")
            equity=max(0,equity+t["net_usdt"])
            require(close(t["equity_after"],equity),"closed equity mismatch")
        require(close(equity,w["end_equity"]),"window balance mismatch")
        require(w["liquidations"]==sum(t["exit_type"]=="liquidation_proxy" for t in w["trades"]),"liquidation count mismatch")
        key=model+"/"+case
        s=summary.setdefault(key,{"windows":0,"fills":0,"hits":0,"liqs":0})
        s["windows"]+=1;s["fills"]+=len(w["trades"]);s["hits"]+=equity>=8.30;s["liqs"]+=w["liquidations"]
    for key,s in summary.items():
        recorded=report["summary"][key]
        require(recorded["windows"]==s["windows"],"window count drift")
        require(recorded["filled_trades"]==s["fills"],"filled trade count drift")
        require(recorded["target_hit_windows"]==s["hits"],"100% hit count drift")
        require(recorded["liquidation_proxy_events"]==s["liqs"],"liquidation count drift")
    return {"auditor":"TITAN-INFINITE12-INDEPENDENT-LEDGER-AUDIT-V1",
            "status":"PASS" if not errors else "FAIL","checked_windows":len(report.get("windows",[])),
            "checked_fills":verify_count,"error_count":len(errors),"errors":errors[:100],
            "limits":["Historical mark-price liquidation schedule not reconstructed",
                      "OHLC gaps and stop-before-target priority are proxy fills",
                      "Historical 2026 data are already consumed, not unseen holdout",
                      "Source hashes prove internal identity, not exchange signatures"],
            "no_real_orders":True}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True);p.add_argument("--report",required=True);p.add_argument("--out",required=True)
    a=p.parse_args()
    result=audit(json.loads(Path(a.input).read_text()),json.loads(Path(a.report).read_text()))
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,sort_keys=True))
    if result["status"]!="PASS":
        raise SystemExit(2)


if __name__=="__main__":
    main()

"""Independent TITAN Omega24 accounting audit. NO strategy imports or order APIs."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

START,TARGET,N,WARM=4.15,8.30,96,33
COST={"ordinary":.0005,"stress":.0015}
PARTICIPATION=.001
MODELS=("causal_hamiltonian_phasewalk","fisher_bayes_regime","classical_momentum")


def sha(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def near(x,y):
    return math.isclose(x,y,rel_tol=1e-6,abs_tol=1e-7)


def audit(source,report):
    errors=[]
    def check(condition,message):
        if not condition: errors.append(message)
    check(source.get("seal_sha256")==sha({k:v for k,v in source.items() if k!="seal_sha256"}),"SOURCE_SEAL")
    check(report.get("source_seal")==source.get("seal_sha256"),"REPORT_SOURCE")
    check(source.get("real_orders")==report.get("real_orders")==0,"REAL_ORDERS")
    check(report.get("fresh_independent_prospective") is False and report.get("independent_hit_rate") is None,"FALSE_INDEPENDENCE")
    check(report.get("window_bars")==N and report.get("target_usdt")==TARGET,"GOAL_HORIZON")
    seen=set(); totals={}; fills=0
    for sym,data in source.get("markets",{}).items():
        for key,v in (("bar_sha256",data["bars"]),("spec_sha256",data["spec"]),
                      ("funding_sha256",data["funding"])):
            check(data.get(key)==sha(v),"SOURCE_SUBHASH:"+sym+":"+key)
        for a,b in zip(data["bars"],data["bars"][1:]):
            check(b["ts"]-a["ts"]==900000,"TIME_GAP:"+sym)
    for w in report.get("windows",[]):
        sym=w["symbol"];model=w["model"];case=w["cost"]
        if sym not in source.get("markets",{}) or model not in MODELS or case not in COST:
            errors.append("UNKNOWN_MARKET_MODEL_CASE")
            continue
        bars=source["markets"][sym]["bars"]
        start=w["start_idx"];end=w["end_idx"]
        check(start>=WARM and end-start==N and end<=len(bars) and (start-WARM)%N==0,"WINDOW_BOUNDS")
        check(w["start_ts"]==bars[start]["ts"] and w["end_ts"]==bars[end-1]["ts"]+900000,"WINDOW_TIME")
        cutoff=max(1,int(.6*len(list(range(WARM,len(bars)-N+1,N)))))
        fold="train" if (start-WARM)//N<cutoff else "chronological_holdout_consumed"
        check(w["fold"]==fold,"FOLD_MISMATCH")
        key=(sym,start,model,case)
        check(key not in seen,"DUPLICATE_WINDOW")
        seen.add(key)
        eq=START;peak=START;maxdd=0;previous_exit=start-1
        for t in w["trades"]:
            fills+=1
            i=t["entry_idx"];j=t["exit_idx"];side=t["side"]
            check(start<=i<=j<end and i>previous_exit,"OVERLAPPING_OR_INVALID_FILL")
            check(t["signal_idx"]==i-1,"FUTURE_LEAK")
            check(t["side"] in (-1,1),"INVALID_SIDE")
            check(10<=t["lev"]<=min(100,t["lev_cap"]),"INVALID_LEVERAGE")
            check(t["qty"]+1e-9>=t["min_sz"],"MIN_CONTRACT")
            check(near(t["qty"]/t["lot_sz"],round(t["qty"]/t["lot_sz"])),"LOT_STEP")
            notion=t["qty"]*t["ct_val"]*t["entry"]
            check(near(t["margin"],notion/t["lev"]) and t["margin"]<=.25*eq*(1+1e-5),"MARGIN")
            check(notion<=bars[i-1]["quote"]*PARTICIPATION*(1+1e-5),"PRIOR_VOLUME")
            check(near(t["previous_quote"],bars[i-1]["quote"]),"FUTURE_VOLUME")
            slip=.0005 if case=="ordinary" else .002
            check(near(t["entry"],bars[i]["open"]*(1+side*slip)),"ENTRY_PRICE")
            gross=side*(t["exit"]-t["entry"])*t["qty"]*t["ct_val"]
            fee=COST[case]*t["qty"]*t["ct_val"]*(t["entry"]+t["exit"])
            check(near(t["gross"],gross) and near(t["fee"],fee),"FEE_GROSS")
            check(t["financing_source"] in ("observed_public_events","conservative_proxy"),"FUNDING_PROVENANCE")
            ordinary=gross-fee-t["financing"]
            net=min(ordinary,-t["margin"]-fee-t["financing"]) if t["exit_type"]=="liquidation_proxy" else ordinary
            check(near(net,t["net"]),"NET_LEDGER")
            check(near(eq,t["equity_before"]),"FLOATING_PNL")
            eq=max(0.,eq+net)
            check(near(eq,t["equity_after"]),"CLOSED_BALANCE")
            peak=max(peak,eq);maxdd=max(maxdd,1-eq/peak)
            previous_exit=j
        check(near(eq,w["end_equity"]),"FINAL_EQUITY")
        check(near(maxdd*100,w["max_dd_pct"]),"DRAWDOWN")
        check(w["liquidations"]==sum(t["exit_type"]=="liquidation_proxy" for t in w["trades"]),"LIQ_COUNT")
        tally=totals.setdefault((fold,model,case),{"windows":0,"hits":0,"failures":0,"fills":0,"liquidations":0,"blocked":0})
        tally["windows"]+=1
        tally["hits"]+=eq>=TARGET
        tally["failures"]+=eq<TARGET
        tally["fills"]+=len(w["trades"])
        tally["liquidations"]+=w["liquidations"]
        tally["blocked"]+=w["blocked"]
    expected=set()
    for sym,data in source.get("markets",{}).items():
        for start in range(WARM,len(data["bars"])-N+1,N):
            for model in MODELS:
                for case in COST:expected.add((sym,start,model,case))
    check(seen==expected,"MISSING_OR_EXTRA_WINDOWS")
    for (fold,model,case),counts in totals.items():
        row=report["summary"].get(fold+"/"+model+"/"+case,{})
        for k,v in counts.items():
            check(row.get(k)==v,"SUMMARY:"+fold+"/"+model+"/"+case+"/"+k)
    # Reconstruct frozen model choice exclusively from training stress; never holdout.
    m={}
    for model in MODELS:
        eqs=[w["end_equity"] for w in report["windows"]
             if w["fold"]=="train" and w["model"]==model and w["cost"]=="stress"]
        m[model]=sum(eqs)/len(eqs) if eqs else 0.
    winner=max(MODELS,key=lambda k:(m[k],-MODELS.index(k)))
    check(winner==report.get("selected_using_train_only"),"HOLDOUT_SELECTION_LEAK")
    check(all(near(m[k],report["training_stress_mean_equity"][k]) for k in MODELS),"TRAIN_SELECTION_ARITH")
    return {"status":"PASS" if not errors else "FAIL","errors":errors[:100],
            "error_count":len(errors),"windows_checked":len(seen),
            "paper_fills_checked":fills,"real_orders":0,
            "independent_proof":False,
            "warning":"OHLC liquidation and current contract metadata are proxies, not actual point-in-time exchange fills"}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True);p.add_argument("--report",required=True);p.add_argument("--out",required=True)
    a=p.parse_args()
    result=audit(json.loads(Path(a.input).read_text()),json.loads(Path(a.report).read_text()))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result))
    if result["status"]!="PASS":raise SystemExit(2)


if __name__=="__main__":
    main()

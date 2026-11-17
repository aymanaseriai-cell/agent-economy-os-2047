#!/usr/bin/env python3
"""Development-only multiobjective pruning ledger; NEVER reads final holdouts.

This is a Pareto + pruning audit of frozen tried strategies, not full Bayesian
optimization. The result cannot be used to reselect a historical final winner.
"""
import argparse,json
from pathlib import Path

def pareto(report):
    trace=[];qualified=[]
    for name,sec in report["all_policy_summaries"].items():
        train=sec["fit"]["stress"]
        dev=sec["development"]
        ordinary=dev["ordinary"];stress=dev["stress"];extreme=dev["extreme"]
        failures=[]
        if train["trades"]<5:failures.append("less_than_5_fit_trades")
        if train["net_return_pct"]<=0:failures.append("no_fit_net_edge")
        if stress["net_return_pct"]<=0:failures.append("no_development_stress_edge")
        if extreme["net_return_pct"]<=0:failures.append("no_development_extreme_edge")
        if extreme["max_closed_drawdown_pct"]>35:
            failures.append("development_drawdown_exceeds_35pct")
        if extreme["ruin"]:failures.append("development_ruin")
        item={
            "name":name,"fit_trades":train["trades"],
            "fit_net_pct":train["net_return_pct"],
            "development_extreme_net_pct":extreme["net_return_pct"],
            "development_stress_net_pct":stress["net_return_pct"],
            "development_closed_dd_pct":extreme["max_closed_drawdown_pct"],
            "development_executed_trades":extreme["trades"],
            "cost_sensitivity_pp":ordinary["net_return_pct"]-extreme["net_return_pct"],
            "rejected":bool(failures),"reasons":failures}
        trace.append(item)
        if not failures:qualified.append(item)
    def dominates(a,b):
        xa=(a["development_extreme_net_pct"],-a["development_closed_dd_pct"],
            -a["cost_sensitivity_pp"])
        xb=(b["development_extreme_net_pct"],-b["development_closed_dd_pct"],
            -b["cost_sensitivity_pp"])
        return all(x>=y for x,y in zip(xa,xb)) and any(x>y for x,y in zip(xa,xb))
    front=[a["name"] for a in qualified if not any(
           dominates(b,a) for b in qualified if b is not a)]
    return {
        "total_recorded_candidates":len(trace),
        "pruned_candidates":sum(a["rejected"] for a in trace),
        "qualified_candidates":[x["name"] for x in qualified],
        "pareto_front_selected_without_final_data":front,
        "all_development_only_trial_records":trace,
        "selection_data_scopes":["fit","development"],
        "uses_final_holdout_data_for_selection":False,
        "method":"Multiobjective Pareto/pruning on fixed already-run 20 hypotheses",
        "not_claimed":"Full Bayesian Optimization, broad genetic population search",
        "real_trades":0}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    result=pareto(json.loads(Path(args.report).read_text()))
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("DEVELOPMENT-ONLY PARETO PRUNED",result["pruned_candidates"],
          "OF",result["total_recorded_candidates"],
          "QUALIFIED",result["qualified_candidates"],flush=True)
if __name__=="__main__":main()

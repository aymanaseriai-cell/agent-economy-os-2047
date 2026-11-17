#!/usr/bin/env python3
"""Read-only same-market OMEGA V1 vs Infinite Frontier Gen2 audit.

Uses FROZEN identical OKX original 180d candles, funding and contract
snapshot from Gen2. Re-runs pre-existing OMEGA V1 model selection as-is;
compares its pre-final selected candidate with Gen2 independently selected
candidate under shared ordinary/stress execution fee assumptions.
NOTE: Gen2 adds quote-volume cap, so this is not strict identical fill model.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from trading import titan_frontier_v2_research as gen2
from trading import titan_omega_25m_engine as old

def compare(raw_dir,new_report):
    markets,specs,funding,sha=gen2.load_raw_folder(raw_dir)
    report=json.loads(Path(new_report).read_text())
    if set(markets)!=set(report["markets"]):
        raise ValueError("Cannot compare different market cohorts")
    if any(report["raw_market_sha256"].get(s)!=sha[s] for s in markets):
        raise ValueError("Cannot compare altered price sources")
    earlier=old.study(markets,specs,funding,sha)
    oldchoice=earlier["development_selected_before_final"]
    newchoice=report["selected_before_final"]
    oldfocus=oldchoice or earlier["plot_focus"]
    newfocus=newchoice or report["focus_model"]
    oldfinal=earlier["all_hypothesis_summaries"][oldfocus]["final_combined"]["stress"]
    newfinal=report["all_policy_summaries"][newfocus]["final_combined"]["stress"]
    return {
        "same_real_market_candles":True,
        "same_observed_funding_and_contract_snapshots":True,
        "same_180d_cohort":sorted(markets),
        "old_v1":{ "selected_before_final":oldchoice,
            "focus":oldfocus,"fallback_diagnostic_only":oldchoice is None,
            "final_stress_return_pct":oldfinal["net_return_pct"],
            "final_stress_max_closed_dd_pct":oldfinal["max_closed_drawdown_pct"],
            "final_stress_trades":oldfinal["trades"],
            "ordinary_fee":old.COSTS["ordinary"][0],
            "stress_fee":old.COSTS["stress"][0]},
        "new_v2":{ "selected_before_final":newchoice,
            "focus":newfocus,"fallback_diagnostic_only":newchoice is None,
            "final_stress_return_pct":newfinal["net_return_pct"],
            "final_stress_max_closed_dd_pct":newfinal["max_closed_drawdown_pct"],
            "final_stress_trades":newfinal["trades"],
            "ordinary_fee":gen2.COSTS["ordinary"][0],
            "stress_fee":gen2.COSTS["stress"][0]},
        "selection_both_training_and_development_only":True,
        "limitations":[
          "V1 and V2 evaluated on same cohort, but execution filters differ",
          "V2 adds strict one-percent prior quote volume cap",
          "History is one already-overlapping 2026 calendar regime",
          "Mark-price liquidation and historical contract tiers unavailable",
          "Do not declare a tested strategy profitable if either uses diagnostic fallback",
          "This is a retrospective offline comparison, not prospective live validation",
        ],
        "no_live_exchange_orders":True,
    }

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--raw-dir",required=True)
    p.add_argument("--new-report",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args(argv)
    result=compare(a.raw_dir,a.new_report)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("SAME-DATA OLD VS GEN2",result["old_v1"],
          result["new_v2"],"NO ORDERS",flush=True)

if __name__=="__main__":
    main()

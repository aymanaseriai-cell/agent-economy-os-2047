#!/usr/bin/env python3
"""TITAN SURVIVAL-8: eight audited public-only agents. No credentials or orders."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

AGENTS = (
    "01_evidence_integrity", "02_six_agent_consensus",
    "03_execution_cost_adversary", "04_volatility_regime_sentinel",
    "05_tail_shock_stress_test", "06_dynamic_leverage_research",
    "07_portfolio_concentration_defense", "08_out_of_sample_integrity_judge",
)
REPORT_MODE = "SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY"
MAX_AGE_SECONDS = 1800
# Illustrative research constraints, not a promise of maximum realized loss.
MAX_LEVERAGE = 8
MAX_MARGIN_SHARE = 0.20
MAX_PLANNED_STOP_EQUITY = 0.01
MAX_STRESS_EQUITY = 0.03

def number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean market value")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Missing/invalid public numeric evidence") from exc
    if not math.isfinite(result):
        raise ValueError("Nonfinite public market evidence")
    return result

def read_public_report(report, *, now=None):
    if not isinstance(report, dict) or report.get("mode") != REPORT_MODE:
        raise ValueError("Unrecognized public research source")
    records = report.get("results")
    if (report.get("market_scan_complete") is not True or report.get("errors") or
            not isinstance(records, list) or not records or
            report.get("markets_analyzed") != len(records)):
        raise ValueError("Incomplete or inconsistent public scan")
    try:
        stamp = datetime.fromisoformat(report["utc_timestamp"].replace("Z", "+00:00"))
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError("Missing/invalid scan time") from exc
    if stamp.tzinfo is None or not 0 <= age <= MAX_AGE_SECONDS:
        raise ValueError("Stale, future, or timezone-free public scan")
    return records

def omega(item, name):
    rows = [x["evidence"] for x in item.get("omega_systems", [])
            if isinstance(x, dict) and x.get("name") == name]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("Missing/ambiguous Omega evidence: " + name)
    return rows[0]

def role(name, status, **evidence):
    return {"agent": name, "status": status, "evidence": evidence}

def assess(item):
    """Fail-closed public evidence review; never emits executable instructions."""
    symbol = str(item.get("symbol", ""))
    direction = item.get("signal")
    output = {"symbol": symbol, "direction": direction, "decision": "WAIT",
              "agents": [], "risk_scenario": None, "can_trade": False}
    agents = output["agents"]
    try:
        if direction not in ("LONG", "SHORT") or not symbol.endswith("-USDT-SWAP"):
            raise ValueError("No directional USDT-perpetual research signal")
        if item.get("advanced_system_count") != 7 or len(item.get("agents") or []) != 6:
            raise ValueError("Missing 6+7 independent research evidence")
        if (item.get("advanced_veto_reasons") or item.get("omega_veto_reasons") or
                item.get("derivatives_data_warnings") or item.get("omega_system_count") != 10 or
                item.get("advanced_confirmations", 0) < 1 or
                number(item.get("omega_rank_score")) <= 0):
            raise ValueError("No fully vetted research consensus")
        agents.append(role(AGENTS[0], "PASS", complete_public_evidence=True))
        agents.append(role(AGENTS[1], "PASS", omega_rank=number(item["omega_rank_score"])))
        r = item["agents"][-1]["evidence"]
        price = number(item.get("quote_price"))
        stop = number(r["indicative_stop_not_an_order"])
        target = number(r["indicative_target_not_an_order"])
        if min(price, stop, target) <= 0 or not (
                stop < price < target if direction == "LONG" else target < price < stop):
            raise ValueError("Invalid direction or protective levels")
        stop_fraction = abs(stop-price)/price
        reward_fraction = abs(target-price)/price
        if not 0.001 <= stop_fraction <= 0.035:
            raise ValueError("Stop outside executor's validated range")
        costs = number(omega(item, "04_exchange_digital_twin")["estimated_round_trip_cost_bp"])
        if not 0 <= costs < 70 or reward_fraction <= costs/10000:
            raise ValueError("Insufficient reward after estimated costs")
        agents.append(role(AGENTS[2], "PASS", estimated_round_trip_bp=round(costs, 2),
                           fees_are_not_verified=True))
        vol_ratio = number(omega(item, "05_regime_mutation_detector")["volatility_ratio"])
        if not 0 < vol_ratio < 2:
            raise ValueError("Volatility regime shift")
        agents.append(role(AGENTS[3], "PASS", volatility_ratio=round(vol_ratio, 3)))
        tails = omega(item, "07_extreme_tail_risk")
        lower = number(tails["historical_lower_tail_mean_bp"])
        upper = number(tails["historical_upper_tail_mean_bp"])
        if lower > 0 or upper < 0:
            raise ValueError("Inconsistent tail signs")
        tail_fraction = max(abs(lower), abs(upper))/10000
        shock = max(0.03, stop_fraction*2, tail_fraction*3)
        if shock >= 0.25:
            raise ValueError("Extreme market-shock stress")
        agents.append(role(AGENTS[4], "STRESS_ONLY", hypothetical_adverse_move=round(shock,6),
                           liquidation_price_not_calculated=True))
        # NO live leverage selection. Stress-buffer heuristic for research.
        leverage = min(MAX_LEVERAGE, int(0.25/shock))
        if leverage < 1:
            raise ValueError("Excessive research leverage stress")
        notional = min(MAX_MARGIN_SHARE*leverage,
                       MAX_PLANNED_STOP_EQUITY/(stop_fraction+costs/10000),
                       MAX_STRESS_EQUITY/(shock+costs/10000))
        margin_share = notional/leverage
        planned_loss = notional*(stop_fraction+costs/10000)
        stress_loss = notional*(shock+costs/10000)
        if (not 0 < margin_share <= MAX_MARGIN_SHARE+1e-12 or
                planned_loss > MAX_PLANNED_STOP_EQUITY+1e-12 or
                stress_loss > MAX_STRESS_EQUITY+1e-12):
            raise ValueError("Research risk calculation invariant")
        scenario = {
            "proposed_leverage_x_research_only": leverage,
            "proposed_margin_share_of_equity": round(margin_share,6),
            "equity_not_deployed_fraction": round(1-margin_share,6),
            "planned_equity_loss_if_stop_fills": round(planned_loss,6),
            "illustrative_stress_equity_loss": round(stress_loss,6),
            "no_loss_or_liquidation_guarantee": True,
        }
        output["risk_scenario"] = scenario
        agents.append(role(AGENTS[5], "RESEARCH_ONLY", **scenario))
        agents.append(role(AGENTS[6], "ONE_CANDIDATE_ONLY",
                           multi_position_correlation_not_validated=True))
        agents.append(role(AGENTS[7], "UNVERIFIED",
                           walk_forward_positive_edge_not_proven=True,
                           promote_to_live=False))
        output["decision"] = "PAPER_CANDIDATE_AWAITING_OUT_OF_SAMPLE_PROOF"
    except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError) as exc:
        agents.append(role(AGENTS[min(len(agents),len(AGENTS)-1)], "REJECT",
                           reason=str(exc)[:180]))
    return output

def review(report, *, now=None):
    records = read_public_report(report, now=now)
    assessed = [assess(r) for r in records if r.get("signal") in ("LONG","SHORT")]
    canonical = json.dumps(report, sort_keys=True, ensure_ascii=True, allow_nan=False)
    return {
        "name": "TITAN_SURVIVAL_8", "agent_count": len(AGENTS),
        "agent_names": list(AGENTS),
        "report_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "markets_reviewed": len(records), "signals_reviewed": len(assessed),
        "paper_candidates": sum(x["decision"].startswith("PAPER_") for x in assessed),
        "assessments": assessed, "real_orders_sent": 0,
        "live_orders_permitted": False,
        "full_capital_investment_enforced": False,
        "guaranteed_to_avoid_liquidation": False,
        "limitations": "Public-only, uncalibrated stress scenarios; no proven alpha, quantum advantage, real loss cap or guarantee.",
    }

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--summary")
    args = p.parse_args()
    try:
        outcome = review(json.loads(Path(args.report).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print("SURVIVAL-8: invalid public research, FAIL CLOSED:", exc)
        return 2
    path=Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(outcome, indent=2, sort_keys=True)+"\n",encoding="utf-8")
    if args.summary:
        with Path(args.summary).open("a", encoding="utf-8") as f:
            f.write("### TITAN SURVIVAL-8: NO ORDERS\n\n")
            f.write("Reviewed "+str(outcome["markets_reviewed"])+" markets; "+
                    str(outcome["paper_candidates"])+" unproven paper candidates.\n")
            f.write("This research cannot place trades and does NOT guarantee safety or profit.\n")
    print("SURVIVAL-8: "+str(outcome["paper_candidates"])+" paper candidates; NO ORDERS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

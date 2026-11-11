#!/usr/bin/env python3
"""TITAN Omega read-only multi-position allocation study.

Creates a hypothetical 100%-margin allocation at 20x isolated leverage.
NEVER connects to private OKX endpoints, handles keys, or sends orders.
This is NOT a safe/live capital-allocation recommendation; high likelihood
of liquidation or total equity loss is possible under stressed movement.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


class PlanningError(ValueError):
    pass


def decimal(v):
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PlanningError("Invalid numeric input") from exc
    if not d.is_finite():
        raise PlanningError("Non-finite numeric input")
    return d


def eligible(signal):
    if signal.get("signal") not in ("LONG", "SHORT"):
        return False
    if not str(signal.get("symbol", "")).endswith("-USDT-SWAP"):
        return False
    if signal.get("advanced_system_count") != 7 or len(signal.get("agents", [])) != 6:
        return False
    if signal.get("advanced_veto_reasons") or signal.get("derivatives_data_warnings"):
        return False
    if signal.get("omega_system_count") != 10 or signal.get("omega_veto_reasons"):
        return False
    if signal.get("advanced_confirmations", 0) < 1:
        return False
    score = decimal(signal.get("omega_rank_score", 0))
    if score <= 0:
        return False
    price = decimal(signal.get("quote_price", 0))
    if price <= 0:
        return False
    risk = signal["agents"][-1].get("evidence", {})
    stop = decimal(risk.get("indicative_stop_not_an_order", 0))
    target = decimal(risk.get("indicative_target_not_an_order", 0))
    if signal["signal"] == "LONG" and not (0 < stop < price < target):
        return False
    if signal["signal"] == "SHORT" and not (0 < target < price < stop):
        return False
    return True


def plan(report, slots=3, leverage=20):
    if not 2 <= slots <= 5:
        raise PlanningError("Research planning slots must be 2..5")
    if leverage != 20:
        raise PlanningError("Research assumes exactly 20x isolated leverage")
    if report.get("mode") != "SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY":
        raise PlanningError("Unrecognized public research report")
    if report.get("errors"):
        raise PlanningError("Unresolved scan errors; no hypothetical allocation")
    by_symbol = {}
    for signal in report.get("results", []):
        if not eligible(signal):
            continue
        sym = signal["symbol"]
        if sym not in by_symbol or decimal(signal["omega_rank_score"]) > decimal(
                by_symbol[sym]["omega_rank_score"]):
            by_symbol[sym] = signal
    vetted = sorted(by_symbol.values(),
                    key=lambda x: decimal(x["omega_rank_score"]), reverse=True)[:slots]
    if len(vetted) < 2:
        return {
            "status": "NO_HYPOTHETICAL_PLAN",
            "eligible_symbols": len(vetted),
            "reason": "Fewer than two independently qualified symbols",
            "orders_sent": 0,
            "live_trading_enabled": False,
        }
    weights = [Decimal("1")/len(vetted)] * (len(vetted)-1)
    weights.append(Decimal("1")-sum(weights))
    positions = []
    worst_planned_stop_loss_pct = Decimal("0")
    for candidate, weight in zip(vetted, weights):
        entry = decimal(candidate["quote_price"])
        stop = decimal(candidate["agents"][-1]["evidence"]["indicative_stop_not_an_order"])
        stop_fraction = abs(entry-stop)/entry
        stop_loss = Decimal(leverage)*weight*stop_fraction*100
        worst_planned_stop_loss_pct += stop_loss
        positions.append({
            "symbol": candidate["symbol"],
            "direction": candidate["signal"],
            "margin_fraction_of_total_equity": float(weight),
            "hypothetical_notional_fraction_of_equity": float(weight*leverage),
            "stop_distance_pct": float(stop_fraction*100),
            "planned_loss_at_stop_pct_of_equity": float(stop_loss),
            "omega_rank_heuristic": float(decimal(candidate["omega_rank_score"])),
        })
    return {
        "status": "HYPOTHETICAL_ONLY_NOT_SAFE_TO_AUTO_EXECUTE",
        "orders_sent": 0,
        "live_trading_enabled": False,
        "is_a_real_executable_strategy": False,
        "leverage_assumed": leverage,
        "margin_use_fraction_of_total_equity": 1.0,
        "gross_notional_multiple_of_equity": 20.0,
        "planned_loss_if_all_stops_fill_pct_of_equity": float(worst_planned_stop_loss_pct),
        "stress_equity_loss_1pct_adverse_move_pct_before_fees": 20.0,
        "stress_equity_loss_3pct_adverse_move_pct_before_fees": 60.0,
        "stress_equity_loss_5pct_adverse_move_pct_before_fees": 100.0,
        "positions": positions,
        "warning": "Research only. 100% margin at 20x may liquidate the account. "
                   "Stops can fail; fees, funding, spread and maintenance margin are excluded. "
                   "No trade can be guaranteed and no actual order is submitted.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", default="reports/okx_six_agents.json")
    p.add_argument("--out", default="reports/okx_multi_position_research.json")
    p.add_argument("--slots", type=int, default=3)
    args = p.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    study = plan(report, args.slots)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(study, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print("MULTI-POSITION RESEARCH:", study["status"],
          "hypothetical_slots:", len(study.get("positions", [])), "NO ORDERS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

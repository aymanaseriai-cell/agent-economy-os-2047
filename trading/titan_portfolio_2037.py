#!/usr/bin/env python3
"""TITAN 2037: high leverage and multiple-position PUBLIC research only.

No OKX credentials, orders, private endpoints, or leverage-setting capability.
10x-100x and 100% margin are stress inputs, not live recommendations.
"""
import argparse
import json
from pathlib import Path
from trading.titan_survival_council import assess, number, omega, read_public_report

MIN_LEV, MAX_LEV, MAX_SLOTS = 10, 100, 10
SHOCKS = (0.005, 0.01, 0.03, 0.05, 0.10)

def model_leverage(stop_fraction, fee_fraction):
    """Hypothetical dynamic 10x..100x, with conservative abstention."""
    s, c = number(stop_fraction), number(fee_fraction)
    if not (0 < s <= .035 and 0 <= c <= .007):
        raise ValueError("Invalid stop distance or transaction cost")
    for lev in range(MAX_LEV, MIN_LEV - 1, -1):
        if lev*(2*s+c) <= .5 and lev*(.01+c) <= .6:
            return lev
    return None

def candidate(item):
    if assess(item)["decision"] != "PAPER_CANDIDATE_AWAITING_OUT_OF_SAMPLE_PROOF":
        return None
    price = number(item["quote_price"])
    stop = number(item["agents"][-1]["evidence"]["indicative_stop_not_an_order"])
    fee = number(omega(item,"04_exchange_digital_twin")
                 ["estimated_round_trip_cost_bp"])/10000
    stop_fraction = abs(price-stop)/price
    lev = model_leverage(stop_fraction, fee)
    if lev is None:
        return None
    return {
        "symbol":item["symbol"],"direction":item["signal"],
        "ordinal_score_not_probability":number(item["omega_rank_score"]),
        "modeled_leverage_x_not_exchange_verified":lev,
        "illustrative_stop_fraction":stop_fraction,
        "illustrative_round_trip_cost_fraction":fee,
        "exchange_leverage_tier_verified":False,
    }

def simulate(report, *, margin_share=1.0, max_positions=5, now=None):
    share = number(margin_share)
    if not 0 < share <= 1:
        raise ValueError("Margin share must be between 0 and 1")
    if (type(max_positions) is not int or
            not 1 <= max_positions <= MAX_SLOTS):
        raise ValueError("Invalid maximum concurrent research positions")
    records = read_public_report(report,now=now)
    seen=set()
    possible=[]
    rejected=0
    for item in records:
        if item.get("signal") not in ("LONG","SHORT"):
            continue
        symbol=item.get("symbol")
        if symbol in seen:
            raise ValueError("Duplicate research symbol")
        seen.add(symbol)
        leg=candidate(item)
        if leg is None:
            rejected+=1
        else:
            possible.append(leg)
    possible.sort(key=lambda leg:(-leg["ordinal_score_not_probability"],
                                  leg["symbol"]))
    chosen=possible[:max_positions]
    per_leg=share/len(chosen) if chosen else 0.
    positions=[]
    stop_loss=0.
    gross=0.
    for leg in chosen:
        lev=leg["modeled_leverage_x_not_exchange_verified"]
        notional=per_leg*lev
        planned=notional*(leg["illustrative_stop_fraction"]+
                          leg["illustrative_round_trip_cost_fraction"])
        positions.append({**leg,
            "margin_fraction_of_equity":round(per_leg,10),
            "notional_multiple_of_equity":round(notional,8),
            "planned_stop_loss_fraction_of_equity":round(planned,8)})
        gross+=notional
        stop_loss+=planned
    stresses=[]
    for shock in SHOCKS:
        estimate=sum(p["margin_fraction_of_equity"]*
                     p["modeled_leverage_x_not_exchange_verified"]*
                     (shock+p["illustrative_round_trip_cost_fraction"])
                     for p in positions)
        depleted=[p["symbol"] for p in positions if
                  p["modeled_leverage_x_not_exchange_verified"]*
                  (shock+p["illustrative_round_trip_cost_fraction"])>=1]
        stresses.append({
            "simultaneous_adverse_move_fraction":shock,
            "illustrative_gross_linear_loss_fraction_of_equity":round(estimate,6),
            "isolated_margin_could_be_exhausted_before_this_shock":depleted,
            "liquidation_threshold_not_estimated":True})
    return {
        "model":"TITAN_2037_PORTFOLIO_STRESS_RESEARCH_ONLY",
        "range_10x_to_100x_inclusive":list(range(MIN_LEV,MAX_LEV+1)),
        "max_simultaneous_positions_requested":max_positions,
        "simulated_positions":len(positions),
        "requested_margin_fraction_of_equity":share,
        "illustrative_margin_deployed_fraction_of_equity":round(per_leg*len(positions),10),
        "no_forced_entry_when_no_safe_signal":True,
        "unaccepted_or_unsafe_signals":rejected,
        "positions":positions,
        "gross_notional_multiple_of_equity":round(gross,8),
        "planned_stops_linear_loss_fraction_of_equity":round(stop_loss,6),
        "over_5_percent_account_risk_warning":stop_loss>.05,
        "simultaneous_adverse_shock_stress":stresses,
        "real_orders_placed":0,
        "live_leverage_changes":0,
        "live_trading_permitted":False,
        "full_capital_deployment_safe_for_live":False,
        "instrument_leverage_limits_verified":False,
        "margin_maintenance_or_funding_modelled":False,
        "potential_total_loss":True,
        "profits_or_no_liquidation_guaranteed":False,
        "limitations":(
            "No contract tier verification or liquidation modeling. Correlated "
            "stress assumes all positions move adversely; losses are illustrative "
            "linear exposures before actual liquidation, gaps, funding and slippage. "
            "No proven predictive edge or permission to execute any order."),
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--margin-share",type=float,default=1.0)
    p.add_argument("--max-positions",type=int,default=5)
    p.add_argument("--summary")
    args=p.parse_args()
    try:
        raw=json.loads(Path(args.report).read_text(encoding="utf-8"))
        result=simulate(raw,margin_share=args.margin_share,max_positions=args.max_positions)
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
        print("TITAN 2037 public research unavailable:",str(exc)[:180])
        return 2
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    if args.summary:
        with Path(args.summary).open("a",encoding="utf-8") as f:
            f.write("### TITAN 2037 leverage 10x-100x portfolio STRESS ONLY\n\n")
            f.write("Simulated positions: "+str(result["simulated_positions"])+"\n")
            f.write("Margin deployed (hypothetical): "+
                    str(result["illustrative_margin_deployed_fraction_of_equity"])+"\n")
            f.write("**No orders. Total capital loss possible.**\n")
    print("TITAN 2037: portfolio stress complete; NO ORDERS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

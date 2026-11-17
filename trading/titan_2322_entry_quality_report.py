"""Historical / read-only quality assessment for TITAN Omega 23:22.

No exchange clients, credentials, leverage changes or order submission.
Does not authorize live trading. Signal thresholds are uncalibrated heuristics.
"""
from decimal import Decimal, InvalidOperation

def decimal(value):
    try:
        x = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError("Invalid evidence") from exc
    if not x.is_finite():
        raise ValueError("Non-finite evidence")
    return x

def evaluate_candidate(row):
    """Return why a public LONG/SHORT signal would fail stricter checks."""
    reasons=[]
    try:
        side=row["signal"]
        if side not in ("LONG","SHORT"):
            return ["NO_LONG_OR_SHORT"]
        if row.get("advanced_veto_reasons") or row.get("omega_veto_reasons"):
            reasons.append("UPSTREAM_VETO")
        if row.get("derivatives_data_warnings"):
            reasons.append("DERIVATIVES_UNCERTAIN")
        if row.get("omega_system_count") != 10:
            reasons.append("INCOMPLETE_OMEGA")
        q=row["agents"][0]
        if q.get("agent") != "01_liquidity_sentinel":
            reasons.append("MISSING_LIQUIDITY_SENTINEL")
        e=q["evidence"]
        turnover=decimal(e["turnover_usdt_est"])
        spread=decimal(e["spread_bp"])
        age=decimal(e["orderbook_age_sec"])
        bid=decimal(e["bid_depth_contracts_20_levels"])
        ask=decimal(e["ask_depth_contracts_20_levels"])
        if turnover < 18000000: reasons.append("TURNOVER_LT_18M")
        if not Decimal(0) <= spread <= Decimal(8): reasons.append("SPREAD_GT_8BP")
        if not Decimal(0) <= age <= Decimal(30): reasons.append("BOOK_STALE")
        if min(bid,ask)<=0: reasons.append("MISSING_TWO_SIDED_DEPTH")
        elif max(bid/ask,ask/bid)>Decimal(4):reasons.append("ORDERBOOK_IMBALANCE_GT_4")
        if decimal(row["omega_rank_score"]) < Decimal("1.5"):
            reasons.append("OMEGA_RANK_LT_1_5")
        twin=next(x for x in row["omega_systems"] if x.get("name")=="04_exchange_digital_twin")
        if not Decimal(0) <= decimal(twin["evidence"]["estimated_round_trip_cost_bp"]) <= Decimal(30):
            reasons.append("MODEL_COST_GT_30BP")
        if int(row["advanced_confirmations"])<1: reasons.append("NO_QUANT_CONFIRMATION")
        contradictions=int(row["advanced_contradictions"])
        if contradictions>1 or contradictions<0: reasons.append("QUANT_CONTRADICTIONS")
        speed=decimal(row["speed_matrix_rank_factor"])
        if contradictions==1 and not (turnover>=20000000 and speed>=Decimal("1.05")):
            reasons.append("WEAK_SINGLE_CONTRADICTION_OVERRIDE")
        a=int(row["ordinal_buy_points"]);b=int(row["ordinal_sell_points"])
        lead=(a-b if side=="LONG" else b-a)
        votes=row.get("num_bullish_agents" if side=="LONG" else "num_bearish_agents",0)
        if lead<3 or int(votes)<2:reasons.append("WEAK_DIRECTIONAL_CONSENSUS")
        price=decimal(row["quote_price"])
        risk=row["agents"][-1]["evidence"]
        stop=decimal(risk["indicative_stop_not_an_order"])
        target=decimal(risk["indicative_target_not_an_order"])
        if side=="LONG":
            if not Decimal(0)<stop<price<target:return reasons+["BAD_LONG_LEVELS"]
        else:
            if not Decimal(0)<target<price<stop:return reasons+["BAD_SHORT_LEVELS"]
        stop_distance=abs(price-stop)
        if not Decimal(".001") <=stop_distance/price<=Decimal(".025"):
            reasons.append("STOP_DISTANCE_OUTSIDE_0_1_TO_2_5PCT")
        if abs(price-target)/stop_distance < Decimal("1.8"):
            reasons.append("REWARD_TO_RISK_LT_1_8")
    except (KeyError,TypeError,ValueError,InvalidOperation,StopIteration,ZeroDivisionError,AttributeError):
        reasons.append("MISSING_OR_INVALID_PUBLIC_EVIDENCE")
    return reasons

def audit_report(report):
    """Only analyze candidate public reports: never returns an order instruction."""
    out=[]
    for rec in report.get("results",[]):
        if rec.get("signal") not in ("LONG","SHORT"):
            continue
        reasons=evaluate_candidate(rec)
        out.append({"symbol":rec.get("symbol"),"original_signal":rec.get("signal"),
                    "quality_status":"PASS" if not reasons else "REJECT",
                    "reasons":reasons})
    return out

def main():
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser(description="Read-only public-market candidate audit")
    parser.add_argument("--report",required=True)
    args=parser.parse_args()
    report=json.loads(Path(args.report).read_text(encoding="utf-8"))
    print(json.dumps(audit_report(report),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""Independent arithmetic for 2-leg CASH-AND-CARRY minimal-capital feasibility.

Long **actual SPOT** coins, short **actual same-asset USDT SWAP**
contracts; NOT a direction-only funding 'strategy' and NOT unhedged
basis index fiction. Current order-book + contract snapshot only.
Market-neutral only if exact matched base units and both legs executable.

Leg prices require actual depth. Fee tiers, exit spreads, future
funding/price/basis changes and historical point-in-time contract rules
are unknown -> never call a profitable executed live edge.
"""
from __future__ import annotations
import argparse,decimal,json,math
from pathlib import Path

D=decimal.Decimal
BUDGET=D("4.15")
LEVER=D("2")
SCENARIOS={"assumed_taker_5bp":D("0.0005"),
           "assumed_taker_15bp":D("0.0015")}
MAX_ENUMERATED_LOTS=500

def d(v):return D(str(v))

def ceil_lot(q,step):
    return (q/step).to_integral_value(rounding=decimal.ROUND_CEILING)*step

def is_quantized(q,lot):
    return lot>0 and q>0 and q/lot==(q/lot).to_integral_value()

def vwap_from_books(levels,required):
    """Consume public book depth, not fictional best price for all quantity."""
    if required<=0:return None
    remaining=required
    cost=D("0")
    for price,quantity,*_ in levels:
        p=d(price);n=d(quantity)
        if p<=0 or n<=0:continue
        used=min(remaining,n)
        cost+=p*used
        remaining-=used
        if remaining<=0:return cost/required
    return None

def limit_no_quote_guess(info,bbo_spot,bbo_swap,budget=BUDGET):
    """Return least expensive **exact-neutral** current snapshot both-leg fill.

    Swap depth size is in contracts; spot depth size is base currency.
    The user has 4.15 total USDT in a hypothetical cross-account. This
    ignores any additional exchange-specific min-notional/transfer cap.
    So a 'feasible' finding is only a LOWER-BOUND engineering candidate.
    """
    coin=info["coin"];spot=info["spot"];swap=info["swap"]
    for item in (spot,swap):
        if not item or item.get("state")!="live":
            return {"coin":coin,"status":"missing_live_instrument"}
    if swap.get("ctType")!="linear" or swap.get("ctValCcy")!=coin:
        return {"coin":coin,"status":"non_base_linear_swap_not_supported"}
    try:
        sp_min=d(spot["minSz"]);sp_lot=d(spot["lotSz"])
        sw_min=d(swap["minSz"]);sw_lot=d(swap["lotSz"])
        cv=d(swap["ctVal"])
        if min(sp_min,sp_lot,sw_min,sw_lot,cv)<=0:raise ValueError("nonpositive instrument quantity")
        ask_spot=bbo_spot["asks"];bid_swap=bbo_swap["bids"]
        spotbid=bbo_spot["bids"];swapask=bbo_swap["asks"]
        if any(not x for x in (ask_spot,bid_swap,spotbid,swapask)):
            raise ValueError("missing orderbook side")
        ask0=d(ask_spot[0][0]);bid0=d(bid_swap[0][0])
        if ask0<=0 or bid0<=0:raise ValueError("malformed bid ask")
    except (KeyError,ValueError,decimal.InvalidOperation) as e:
        return {"coin":coin,"status":"incomplete_contract_or_orderbook","error":str(e)}
    smallest=None
    for j in range(MAX_ENUMERATED_LOTS):
        contracts=ceil_lot(sw_min,sw_lot)+j*sw_lot
        base_qty=contracts*cv
        if base_qty<sp_min or not is_quantized(base_qty,sp_lot):
            continue
        spot_buy=vwap_from_books(ask_spot,base_qty)
        swap_short=vwap_from_books(bid_swap,contracts)
        if spot_buy is None or swap_short is None:
            # Do not extrapolate beyond visible L2 book.
            continue
        spot_exit_bid=vwap_from_books(spotbid,base_qty)
        swap_exit_ask=vwap_from_books(swapask,contracts)
        if None in (spot_exit_bid,swap_exit_ask):continue
        spot_cost=base_qty*spot_buy
        short_notional=base_qty*swap_short
        # 15% margin sizing not imposed; genuine cash-and-carry holds
        # paid-for SPOT plus separate short swap 2x margin.
        margin=short_notional/LEVER
        percase={}
        for label,fee in SCENARIOS.items():
            # 4 entry+exit orders (spot buy/sell, swap short/buyback).
            entryfee=(spot_cost+short_notional)*fee
            closefee=(base_qty*spot_exit_bid+base_qty*swap_exit_ask)*fee
            # No funding profits realized yet; fee reserve is conservative
            # but excludes future funding reversal, basis and liquidations.
            mincapital=spot_cost+margin+entryfee+closefee
            visible_spread=(spot_cost-base_qty*spot_exit_bid)+(
                base_qty*swap_exit_ask-short_notional)
            break_even_rate=(entryfee+closefee+visible_spread)/max(short_notional,D(".000000001"))
            percase[label]={
                "minimum_cash_USDT_excluding_extra_historical_tier_rules":float(mincapital),
                "entry_exit_taker_fee_USDT":float(entryfee+closefee),
                "round_trip_observed_book_spread_cost_USDT":float(visible_spread),
                "minimum_one_interval_funding_rate_to_pay_roundtrip_cost_pct":float(100*max(D(0),break_even_rate)),
                "fits_4_15_USDT":bool(mincapital<=budget),
            }
        row={
            "coin":coin,"status":"exact_base_delta_matched_quote_snapshot",
            "exact_hedge_base_amount":str(base_qty),
            "spot_min_base":str(sp_min),"spot_step":str(sp_lot),
            "perp_contracts":str(contracts),"swap_min_contracts":str(sw_min),
            "swap_contract_lot":str(sw_lot),"perp_ctVal_base":str(cv),
            "entry_spot_vwap_ask_USDT":float(spot_buy),
            "entry_perp_vwap_bid_USDT":float(swap_short),
            "spot_purchase_USDT":float(spot_cost),
            "short_margin_2x_USDT":float(margin),
            "assumptions":"Contemporaneous public 5-level BBO, same base quantity, two-leg taker entry/exit; no historical fill/fee guarantee",
            "cost_scenarios":percase,
        }
        if smallest is None or row["spot_purchase_USDT"]+row["short_margin_2x_USDT"]<(
            smallest["spot_purchase_USDT"]+smallest["short_margin_2x_USDT"]):
            smallest=row
        # For higher lot count, minimum notional increases; preserve strict
        # smallest first candidate, not faked fractional minimum.
        if smallest is not None:break
    return smallest or {"coin":coin,"status":"no_exact_hedge_within_500_swap_lots_and_5level_depth"}

def run(data_dir,out):
    data_dir=Path(data_dir)
    manifest=json.loads((data_dir/"manifest.json").read_text())
    originals={}
    for pair,entry in manifest["bbo_snapshots"].items():
        if "file" not in entry:continue
        contents=(data_dir/entry["file"]).read_bytes()
        if __import__("hashlib").sha256(contents).hexdigest()!=entry["sha256"]:
            raise ValueError("Tampered original public orderbook "+pair)
        originals[pair]=json.loads(contents)["data"][0]
    status={};rows=[]
    for coin in ("BTC","ETH","SOL"):
        try:
            spot=manifest["instrument_source"]["SPOT"]["symbols"][coin+"-USDT"]
            swap=manifest["instrument_source"]["SWAP"]["symbols"][coin+"-USDT-SWAP"]
            if not spot or not swap:raise ValueError("Missing original pair metadata")
            x=originals[coin+"-USDT"];y=originals[coin+"-USDT-SWAP"]
            obs_x=int(x["ts"]);obs_y=int(y["ts"])
            # Different sampling milliseconds -> not an executable single
            # synchronized book; only comparable indicative snapshots.
            lag=abs(obs_x-obs_y)
            row=limit_no_quote_guess({"coin":coin,"spot":spot,"swap":swap},x,y)
            row["actual_spot_swap_book_timestamp_gap_ms"]=lag
            row["snapshot_synchronization"]="approximately_coincident_not_atomic"
            if lag>60000:
                row["snapshot_synchronization"]="MORE_THAN_60s_APART_NOT_RELIABLE_PRICE_COMPARISON"
            rows.append(row)
        except (ValueError,TypeError,KeyError) as err:
            rows.append({"coin":coin,"status":"UNVERIFIABLE","error":str(err)})
    eligible=sum(any(v["fits_4_15_USDT"] for v in r.get("cost_scenarios",{}).values())
                 for r in rows)
    report={"asof_utc_ms":manifest["captured_utc_ms"],
            "source_manifest":"manifest.json SHA archived","starting_usdt":4.15,
            "legs":"LONG SPOT paid-in-full, SHORT equal base-quantity linear USDT SWAP; 2x margin",
            "scenario_results":rows,"number_of_markets":len(rows),
            "snapshot_feasible_count_not_live_guarantee":eligible,
            "provisional_decision":"NO_TRADING_APPROVAL; NO_INDEPENDENT_ALPHA_PROOF",
            "limits":[
              "Current 5-level public book snapshots are non-atomic and can change before either leg fills",
              "Funding sign and magnitude of next settlement is not known in advance",
              "True exact spot minimum notional and all account restrictions may be larger than published base minSz",
              "Spot/perpetual minimums and max leverage may differ historically",
              "Two-leg settlement, margin balance transfer, exchange fees and liquidation risk not modeled exactly",
              "Hedge may be basis-exposed even with equal base currency units; basis convergence is not a guarantee",
              "Funding return alone is NOT delta-neutral portfolio PnL",
            ]}
    target=Path(out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    for row in rows:
        print("EXACT_HEDGE_MINIMUM",row["coin"],row["status"],
              row.get("cost_scenarios"),flush=True)
    print("HEDGE FEASIBLE 4_15 COUNT",eligible,"OF",len(rows),flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--sources",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    run(a.sources,a.out)

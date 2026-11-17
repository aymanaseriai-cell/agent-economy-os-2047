#!/usr/bin/env python3
"""TITAN Quantum Recurrence Trial: demand MULTIPLE net-positive periods, NO ORDERS.

Not a profitable-live-trading system. Uses a CLASSICALLY simulated, physically
valid single-qubit open quantum density channel from the prior research branch,
with predeclared classical trend/breakout readings. Three fixed quantum action
rules face a classical EMA control, and a no-trade baseline. Only independently
selected training-positive candidates are eligible for forward-paper study.
Unseen TEST intervals must be positive AFTER fees, slippage, and stress,
contain many independent trade-days, and survive per-market breakdowns.
Data acquired AFTER model code committed; no access to OKX account or orders.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
import statistics
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

from trading.edge_lab import (
    BAR_MS,TAKER_FEE,BASE_SLIPPAGE,STRESS_FEE,STRESS_SLIPPAGE,
    ema_series,atr_simple,trade_simulation,fetch_history
)
from trading.titan_regime_research import validate_frozen
from trading.titan_open_quantum_adversarial import density_step

# Precommitted new instruments not part of earlier 18-market research.
SYMBOLS=("TRX-USDT-SWAP","FIL-USDT-SWAP","AAVE-USDT-SWAP",
         "OP-USDT-SWAP","ARB-USDT-SWAP","INJ-USDT-SWAP")
FAMILIES=("q_density_trend","q_zeno_breakout",
          "q_density_reversion","classical_trend_control")
DAYS=90
TRAIN_FRACTION=.60
WARMUP=320
MIN_BARS=8200
MIN_TRAIN_TRADES=60
MIN_HOLDOUT_TRADES=40
MIN_PROFITABLE_TRAIN_SYMBOLS=4
MIN_HOLDOUT_POSITIVE_SYMBOLS=4
MIN_PROFIT_DAYS_TRAIN=12
MIN_PROFIT_DAYS_EACH_HALF=6
TARGET_EQUITY=8.30
START_EQUITY=4.15
RESEARCH_LEVERAGE_CEILING=3.0
RESEARCH_MAX_MARGIN_FRACTION=.20
RESEARCH_MAX_PLANNED_STOP_FRACTION=.01


def _utc(ts):
    return datetime.fromtimestamp(ts/1000,timezone.utc).isoformat()


def _get_public_specs(symbol):
    """EXCHANGE PUBLIC instrument metadata: not an account/risk authorization."""
    if symbol not in SYMBOLS:
        raise ValueError("Symbol is outside predeclared basket")
    url="https://www.okx.com/api/v5/public/instruments?"+urlencode(
        {"instType":"SWAP","instId":symbol})
    request=Request(url,headers={"User-Agent":"TITAN-Recurrent-Research/1.0",
                                 "Accept":"application/json"})
    with urlopen(request,timeout=20) as handle:
        data=json.load(handle)
    rows=data.get("data",[])
    if data.get("code")!="0" or len(rows)!=1 or rows[0].get("instId")!=symbol:
        raise ValueError("Public OKX contract metadata unverified: "+symbol)
    obj=rows[0]
    if obj.get("ctType")!="linear" or obj.get("instType")!="SWAP":
        raise ValueError("Not an OKX linear perpetual")
    return {key:obj.get(key) for key in
            ("instId","ctVal","ctValCcy","lotSz","minSz","lever","state","ctType")}


def capital_feasibility(symbol,bars,public_specs):
    """Minimal *illustrative* initial-margin and one-stop budget test.

    Doesn't check user account tier, exchange execution spread, trading volume,
    or liquidation mark; never authorizes real orders. Missing specs = WAIT.
    """
    if not isinstance(public_specs,dict) or public_specs.get("instId")!=symbol:
        return {"can_place_guarded_min_lot":False,"reason":"PUBLIC_SPECS_UNAVAILABLE"}
    base=symbol.partition("-")[0]
    if (public_specs.get("ctValCcy")!=base or
        public_specs.get("state")!="live"):
        return {"can_place_guarded_min_lot":False,"reason":"UNSUPPORTED_INSTRUMENT"}
    try:
        val=float(public_specs["ctVal"])
        sz=float(public_specs["minSz"])
        lot=float(public_specs["lotSz"])
        price=float(bars[-1]["close"])
        if not all(math.isfinite(x) and x>0 for x in (val,sz,lot,price)):
            raise ValueError("Nonfinite min contract")
        min_notional=sz*val*price
        stop_frac=1.5*atr_simple(bars,len(bars)-1,14)/price
        margin=min_notional/RESEARCH_LEVERAGE_CEILING
        planned_loss=min_notional*stop_frac
        feasible=(margin<=START_EQUITY*RESEARCH_MAX_MARGIN_FRACTION
                  and planned_loss<=START_EQUITY*RESEARCH_MAX_PLANNED_STOP_FRACTION
                  and sz+1e-10>=lot)
        return {"can_place_guarded_min_lot":feasible,
                "reason":"PUBLIC_MIN_LOT_WITHIN_ILLUSTRATIVE_CAP"
                         if feasible else "MIN_LOT_EXCEEDS_SMALL_CAPITAL_BUDGET",
                "public_min_notional_usdt":round(min_notional,6),
                "illustrative_required_margin_at_3x_usdt":round(margin,6),
                "illustrative_planned_initial_stop_loss_usdt":round(planned_loss,6),
                "user_actual_account_checked":False,
                "price_snapshot_ms":bars[-1]["ts"]}
    except (KeyError,TypeError,ValueError,ZeroDivisionError,OverflowError):
        return {"can_place_guarded_min_lot":False,"reason":"INVALID_CONTRACT_METADATA"}


def quantum_family_signals(bars):
    """No future read: z of one-qubit density channel on completed bar i."""
    validate_frozen(bars)
    n=len(bars)
    cl=[float(b["close"]) for b in bars]
    ema24=ema_series(cl,24)
    ema96=ema_series(cl,96)
    ema192=ema_series(cl,192)
    bloch=(0.0,0.0,0.0)
    rows={name:[] for name in FAMILIES}
    for i in range(64,n-1):
        atr=atr_simple(bars,i,14)
        if not math.isfinite(atr) or atr<=0:
            raise ValueError("Bad ATR")
        af=atr/cl[i]
        last_ret=math.log(cl[i]/cl[i-1])
        trend96=math.log(cl[i]/cl[i-96]) if i>=96 else 0.
        trend24=math.log(cl[i]/cl[i-24])
        bloch=density_step(
            bloch,rotation=max(-.5,min(.5,18*last_ret)),
            dephasing=max(0.,min(.92,.23+1.5*abs(last_ret)/max(af,1e-8))),
            reset=.20,
            bias=math.tanh(trend96/max(af*5,1e-8)))
        if i<WARMUP or i%8 or not .0012<=af<=.045:
            continue
        z=bloch[2]
        lead=1 if z>=.15 else -1 if z<=-.15 else 0
        classical=(1 if ema24[i]>ema96[i]+.4*atr else
                   -1 if ema24[i]<ema96[i]-.4*atr else 0)
        aligned=(lead and
                 lead*(ema24[i]-ema96[i])>0 and
                 lead*(ema96[i]-ema192[i])>0 and lead*trend24>=0)
        if aligned and abs(z)>=.24:
            rows["q_density_trend"].append((i,lead,atr))
        recent=bars[i-48:i]
        if aligned and abs(z)>=.15:
            if (lead>0 and cl[i]>max(b["high"] for b in recent)) or (
                lead<0 and cl[i]<min(b["low"] for b in recent)):
                rows["q_zeno_breakout"].append((i,lead,atr))
        # Quantum-state-neutral mean reversion under low directional trend.
        if abs(z)<.26 and abs(ema24[i]-ema96[i])<1.4*atr:
            closes=cl[i-48:i]
            dev=statistics.pstdev(closes)
            if dev>0:
                zprice=(cl[i]-statistics.mean(closes))/dev
                if zprice<=-1.75 and trend24>-.04:
                    rows["q_density_reversion"].append((i,1,atr))
                elif zprice>=1.75 and trend24<.04:
                    rows["q_density_reversion"].append((i,-1,atr))
        if classical and classical*trend96>0 and classical*trend24>=0:
            rows["classical_trend_control"].append((i,classical,atr))
    return rows


def trade_day_stats(trades):
    """Exit-day observation unit; multiple correlated fills on a day collapse."""
    gains={}
    for t in trades:
        day=int(t["exit_ts"])//86_400_000
        gains[day]=gains.get(day,0.)+float(t["net_usd"])
    return {"unique_exit_days":len(gains),
            "positive_exit_days":sum(v>0 for v in gains.values()),
            "negative_exit_days":sum(v<0 for v in gains.values()),
            "sum_positive_daily_usdt":round(sum(x for x in gains.values() if x>0),6),
            "sum_negative_daily_usdt":round(sum(x for x in gains.values() if x<0),6)}


def _score_segments(bars,signal,split):
    """Chronological non-overlapping intervals. Results are not order fills."""
    mid=split+(len(bars)-split)//2
    parts=((WARMUP,split),(split,mid),(mid,len(bars)))
    scored=[]
    for a,b in parts:
        base=trade_simulation(bars,signal,start_index=a,end_index=b)
        stress=trade_simulation(bars,signal,start_index=a,end_index=b,
                                fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
        scored.append({"net_pct":base["return_pct"],
                       "stress_net_pct":stress["return_pct"],
                       "trades":base["trades"],
                       "drawdown_pct":base["max_drawdown_pct"],
                       **trade_day_stats(base["trade_log"])})
    return scored


def _aggregate(per_market,name,phase):
    rows=[per_market[s]["strategy_results"][name][phase] for s in SYMBOLS]
    return {"trades":sum(r["trades"] for r in rows),
            "net_mean_pct":round(statistics.mean(r["net_pct"] for r in rows),5),
            "stress_net_mean_pct":round(
                statistics.mean(r["stress_net_pct"] for r in rows),5),
            "positive_markets":sum(r["net_pct"]>0 for r in rows),
            "profitable_exit_days":sum(r["positive_exit_days"] for r in rows),
            "negative_exit_days":sum(r["negative_exit_days"] for r in rows),
            "max_symbol_drawdown_pct":max(r["drawdown_pct"] for r in rows)}


def assess(data,contract_specs,*, data_hashes=None,now_ms=None):
    if set(data)!=set(SYMBOLS):
        raise ValueError("Cannot silently exclude a failed/unprofitable symbol")
    per_market={}
    for symbol in SYMBOLS:
        bars=data[symbol]
        validate_frozen(bars)
        if len(bars)<MIN_BARS:
            raise ValueError("Insufficient 90d public OHLC for "+symbol)
        split=int(len(bars)*TRAIN_FRACTION)
        rows=quantum_family_signals(bars)
        results={}
        for name in FAMILIES:
            tr,h1,h2=_score_segments(bars,rows[name],split)
            results[name]={"train":tr,"holdout_1":h1,"holdout_2":h2}
        per_market[symbol]={
            "bars":len(bars),
            "first_complete_utc":_utc(bars[0]["ts"]),
            "last_complete_utc":_utc(bars[-1]["ts"]),
            "blind_holdout_start_utc":_utc(bars[split]["ts"]),
            "contract_small_equity_gate":capital_feasibility(
                symbol,bars,contract_specs.get(symbol)),
            "strategy_results":results}
    aggregate={name:{ph:_aggregate(per_market,name,ph)
                     for ph in ("train","holdout_1","holdout_2")}
               for name in FAMILIES}
    # The selection step NEVER reads holdout metrics.
    qualified=[]
    for name in FAMILIES:
        tr=aggregate[name]["train"]
        if (tr["trades"]>=MIN_TRAIN_TRADES and
            tr["net_mean_pct"]>0 and tr["stress_net_mean_pct"]>0 and
            tr["positive_markets"]>=MIN_PROFITABLE_TRAIN_SYMBOLS and
            tr["profitable_exit_days"]>=MIN_PROFIT_DAYS_TRAIN and
            tr["max_symbol_drawdown_pct"]<=12):
            qualified.append(name)
    selected=(max(qualified,key=lambda f:(
        aggregate[f]["train"]["stress_net_mean_pct"],f))
        if qualified else None)
    # Shadow diagnose all families, but only TRAIN-eligible one may be judged.
    live_test=False
    reasons=[]
    if selected is None:
        reasons.append("NO_TRAINING_PROFIT_EDGE_AT_RECURRENT_TRADE_COUNT")
    else:
        h1=aggregate[selected]["holdout_1"]
        h2=aggregate[selected]["holdout_2"]
        if h1["trades"]+h2["trades"]<MIN_HOLDOUT_TRADES:
            reasons.append("INSUFFICIENT_RECURRENT_HOLDOUT_TRADES")
        for label,h in (("H1",h1),("H2",h2)):
            if (h["net_mean_pct"]<=0 or h["stress_net_mean_pct"]<=0 or
                h["profitable_exit_days"]<MIN_PROFIT_DAYS_EACH_HALF):
                reasons.append(label+"_NOT_REPEATEDLY_NET_PROFITABLE")
        positive_combined=sum(
            per_market[s]["strategy_results"][selected]["holdout_1"]["net_pct"]+
            per_market[s]["strategy_results"][selected]["holdout_2"]["net_pct"]>0
            for s in SYMBOLS)
        if positive_combined<MIN_HOLDOUT_POSITIVE_SYMBOLS:
            reasons.append("LOW_POSITIVE_MARKET_BREADTH")
        live_test=not reasons
    actionable_small=sum(x["contract_small_equity_gate"].get(
        "can_place_guarded_min_lot",False) for x in per_market.values())
    if actionable_small==0:
        reasons.append("NO_PUBLIC_MIN_LOT_VALID_FOR_4_15_USDT_ILLUSTRATIVE_BUDGET")
    # Even a passed historical trial is NOT live approval.
    return {
        "mode":"CLASSICALLY_SIMULATED_OPEN_QUANTUM_RECURRENT_PROFIT_FALSIFICATION_NO_ORDERS",
        "at_utc":_utc(now_ms) if now_ms else None,
        "source":"OKX public completed 15m historical candles /api/v5/market/history-candles",
        "market_set_fixed_pre_download":list(SYMBOLS),
        "requested_days":DAYS,
        "all_completed_market_bars":sum(len(v) for v in data.values()),
        "raw_data_sha256":data_hashes or {},
        "signal_rule_set_predeclared":list(FAMILIES),
        "train_split":TRAIN_FRACTION,
        "holdout_halves":2,
        "quantum_hardware_used":False,
        "simulation_is_not_quantum_advantage":True,
        "initial_equity_in_trade_sim_per_symbol_usdt":1000,
        "user_start_equity_usdt_unverified":START_EQUITY,
        "user_target_equity_usdt":TARGET_EQUITY,
        "account_profit_goal_percent":100.0,
        "actual_live_account_read":False,
        "model_initial_equity_differs_from_user_account":True,
        "small_account_metadata_viable_symbols_illustrative_only":actionable_small,
        "candidate_selected_on_training_alone":selected,
        "eligible_train_candidates":qualified,
        "historical_recurrence_research_gate_met":live_test,
        "no_trade_reasons":reasons,
        "live_trading_permitted":False,
        "no_orders":True,
        "zero_trade_baseline_net_pct":0,
        "aggregate":aggregate,
        "per_market":per_market,
        "result":"HISTORICAL_CANDIDATE_ONLY_NEEDS_UNTOUCHED_FORWARD_PROOF"
                 if live_test and actionable_small
                 else "NO_TRADE_NO_PROVEN_RECURRING_EDGE",
        "caveats":[
            "95% confidence on profitability NOT established by these descriptive thresholds",
            "Two backtest holdout halves and six correlated coins do not replace prospective independent execution",
            "Model assumes separately funded $1000 accounts per symbol and indicative fees",
            "No true orderbook fills, actual funding, exchange-native liquidation, or account permissions modeled",
            "Public minimum contract metadata is NOT proof of actual leverage, tier or ability to place order",
            "No unattended real-money orders should follow from this experiment",
        ],
    }


def main(argv=None):
    arg=argparse.ArgumentParser(description=__doc__)
    arg.add_argument("--output",default="reports/titan_quantum_recurrence_90d.json")
    arg.add_argument("--data-dir",default="reports/titan_quantum_recurrence_90d_raw")
    opts=arg.parse_args(argv)
    timestamp_ms=int(time.time()*1000)
    target=Path(opts.output);data_dir=Path(opts.data_dir)
    target.parent.mkdir(exist_ok=True,parents=True)
    data_dir.mkdir(exist_ok=True,parents=True)
    frozen={};hashes={};specs={}
    for symbol in SYMBOLS:
        print("RECURRENCE REAL PUBLIC OKX FETCH",symbol,flush=True)
        bars=fetch_history(symbol,DAYS,now_ms=timestamp_ms)
        if len(bars)<MIN_BARS:
            raise ValueError("Missing completed public 90d candles")
        raw=json.dumps(bars,separators=(",",":")).encode()
        hashes[symbol]=hashlib.sha256(raw).hexdigest()
        frozen[symbol]=bars
        with gzip.open(data_dir/(symbol+".json.gz"),"wb",compresslevel=6) as f:
            f.write(raw)
        try:
            specs[symbol]=_get_public_specs(symbol)
        except (OSError,TimeoutError,ValueError) as e:
            specs[symbol]={"instId":symbol,"metadata_error_type":type(e).__name__}
        print("RECURRENCE RAW DATA",symbol,len(bars),hashes[symbol],
              "minSz",specs[symbol].get("minSz","UNKNOWN"),flush=True)
    result=assess(frozen,specs,data_hashes=hashes,now_ms=timestamp_ms)
    target.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    for fam in FAMILIES:
        x=result["aggregate"][fam]
        print("RECURRENCE RESULT",fam,
              "TRAIN",x["train"],
              "HOLDOUT1",x["holdout_1"],
              "HOLDOUT2",x["holdout_2"],flush=True)
    print("RECURRENCE VERDICT",result["result"],
          "selected_train_only",result["candidate_selected_on_training_alone"],
          "small_equity_public_gate",result["small_account_metadata_viable_symbols_illustrative_only"],
          "NO ORDERS",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())

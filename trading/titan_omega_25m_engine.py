#!/usr/bin/env python3
"""OMEGA SINGULARITY 25M: historical event-driven PAPER backtest and audit.

No real orders. Any 25,000,000% claim must survive real-data chronology,
train-only selection, independent holdouts, fee/funding/lot/liq proxies and
multiple-testing checks; not guaranteed by any algorithm.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,random,time
from pathlib import Path
from trading.edge_lab import BAR_MS,TAKER_FEE,BASE_SLIPPAGE,STRESS_FEE,STRESS_SLIPPAGE,FUNDING_PER_8H
from trading import titan_omega_25m_market as market
from trading import titan_omega_25m_families as fam

START=4.15
TARGET_PCT=25_000_000.
TARGET=START*(1+TARGET_PCT/100)
LEVS=(3.,10.)
COSTS={"ordinary":(TAKER_FEE,BASE_SLIPPAGE),
       "stress":(STRESS_FEE,STRESS_SLIPPAGE)}
STOP_ATR=1.8
PROFIT_ATR=6.
TRAIL_ATR=2.3
MAX_HOLD=16*32
MARGIN_PART=.30
PLANNED_STOP_RISK=.12
MAINTENANCE_PROXY=.015
PURGE=192
PERMUTATIONS=499
HOLDOUTS=("final_1","final_2","final_3")

def windows(n):
    if n<market.MIN_BARS:raise ValueError("180d completed OHLC mandatory")
    a=int(n*.35)
    b=int(n*.5)
    c=b+(n-b)//3
    d=c+(n-b)//3
    if min(c-b,d-c,n-d)<2700:raise ValueError("Independent segment too short")
    return {"fit":(market.WARM*market.BLOCK,a-PURGE),
            "development":(a+PURGE,b-PURGE),
            "final_1":(b+PURGE,c-PURGE),
            "final_2":(c+PURGE,d-PURGE),
            "final_3":(d+PURGE,n),
            "final_combined":(b+PURGE,n)}

def affordable(spec,equity,price,atr,leverage):
    if equity<=.83:return 0.,0.
    try:
        cv,step,min_qty=(float(spec[k]) for k in ("ctVal","lotSz","minSz"))
        if (min(cv,step,min_qty,price,atr)<=0 or
            spec.get("state")!="live" or
            spec.get("ctValCcy")!=spec["instId"].split("-")[0]):
            return 0.,0.
        frac=STOP_ATR*atr/price
        if not 0<frac<.25:return 0.,0.
        exposure=min(equity*MARGIN_PART*leverage,
                     equity*PLANNED_STOP_RISK/frac)
        qty=math.floor(exposure/(cv*price)/step+1e-10)*step
        actual_min=math.ceil(min_qty/step-1e-10)*step
        if qty+1e-10<actual_min:return 0.,0.
        return round(qty,10),qty*cv*price
    except (TypeError,ValueError,KeyError,ZeroDivisionError,OverflowError):
        return 0.,0.

def simulate(bars,signal,spec,actual_funding,equity,leverage,fee,slip,end):
    """One paper position, open on next real 15m bar, exit stop before target.
    Mark-price liquidation is NOT available: adverse OHLC proxy only.
    """
    i,side,atr,_=signal
    j=i+1
    if j>=end:return None
    anchor=bars[j]["open"]
    qty,notional=affordable(spec,equity,anchor,atr,leverage)
    if qty<=0:return None
    before_vol=max(1.,bars[i]["vol_quote"])
    impact=min(.003,.2*notional/before_vol)
    entry=anchor*(1+side*(slip+impact))
    notional=qty*float(spec["ctVal"])*entry
    margin=notional/leverage
    enterfee=notional*fee
    if enterfee+margin>=equity:return None
    stop=entry-side*STOP_ATR*atr
    target=entry+side*PROFIT_ATR*atr
    liq=entry*(1-side*max(.001,1/leverage-MAINTENANCE_PROXY))
    if min(stop,target,liq)<=0:return None
    last=min(end-1,j+MAX_HOLD-1)
    fill=bars[last]["close"]
    status="time_exit"
    for k in range(j,last+1):
        b=bars[k]
        adverse=b["low"] if side>0 else b["high"]
        gap=(b["open"]<=liq if side>0 else b["open"]>=liq)
        if gap or (adverse<=liq if side>0 else adverse>=liq):
            fill=b["open"] if gap else liq
            status="liquidation_proxy"
            last=k
            break
        if b["open"]<=stop if side>0 else b["open"]>=stop:
            fill=b["open"];status="stop_gap";last=k;break
        if adverse<=stop if side>0 else adverse>=stop:
            fill=stop;status="stop";last=k;break
        favorable=b["high"] if side>0 else b["low"]
        if favorable>=target if side>0 else favorable<=target:
            fill=target;status="target";last=k;break
        # Trailing threshold updates only AFTER candle closes.
        if side>0 and b["close"]>entry+2*atr:
            stop=max(stop,b["close"]-TRAIL_ATR*atr)
        if side<0 and b["close"]<entry-2*atr:
            stop=min(stop,b["close"]+TRAIL_ATR*atr)
    exit_vol=max(1.,bars[max(0,last-1)]["vol_quote"])
    impact2=min(.003,.2*notional/exit_vol)
    exit_price=fill*(1-side*(slip+impact2))
    exitfee=abs(qty*float(spec["ctVal"])*exit_price)*fee
    t0=bars[j]["ts"];t1=bars[last]["ts"]+BAR_MS
    measured=[(t,v) for t,v in actual_funding if t0<t<=t1]
    actual_cost=sum(side*notional*rate for _,rate in measured)
    # The public funding endpoint only retrieves ~3 months. Missing
    # settlement intervals are conservatively charged as an ASSUMPTION.
    missing=max(0.,(t1-t0)/(8*3600000)-len(measured))
    estimated=notional*FUNDING_PER_8H*missing
    gross=side*(exit_price-entry)*qty*float(spec["ctVal"])
    net=gross-enterfee-exitfee-actual_cost-estimated
    if status=="liquidation_proxy":
        net=min(net,-margin-enterfee-exitfee)
    net=max(-equity,net)
    return {
        "symbol":spec["instId"],"ts":bars[last]["ts"],
        "entry_ts":t0,"exit_ts":t1,
        "side":side,"contracts":qty,
        "entry_price":round(entry,10),"exit_price":round(exit_price,10),
        "margin_usdt":round(margin,8),"gross_usdt":round(gross,8),
        "fees_usdt":round(enterfee+exitfee,8),
        "observed_funding_usdt":round(actual_cost,8),
        "estimated_funding_usdt":round(estimated,8),
        "observed_funding_settlements":len(measured),
        "net_usdt":round(net,8),"equity_before":round(equity,8),
        "equity_after":round(max(0.,equity+net),8),
        "exit_bar_index":last,"exit_reason":status
    }

def paper(markets,specs,funding,signals,leverage,start,end,fee,slip):
    book={}
    for sym,events in signals.items():
        for signal in events:
            if start<=signal[0] and signal[0]+1<end:
                book.setdefault(signal[0],[]).append((signal[3],sym,signal))
    equity=START;peak=START;dd=0.;available=start
    ledger=[];curve=[{"ts":markets[next(iter(markets))][start]["ts"],"equity":START}]
    for i in sorted(book):
        if i<available or equity<=.83 or equity>=TARGET:continue
        for _,sym,sig in sorted(book[i],key=lambda x:(-x[0],x[1])):
            trade=simulate(markets[sym],sig,specs[sym],
                           funding.get(sym,[]),equity,leverage,fee,slip,end)
            if trade is None:continue
            equity=trade["equity_after"];available=trade["exit_bar_index"]+1
            peak=max(peak,equity);dd=max(dd,100*(peak-equity)/peak)
            ledger.append(trade)
            curve.append({"ts":trade["ts"],"equity":equity})
            break
    return {
        "end_usdt":round(equity,8),
        "net_return_pct":round(100*(equity/START-1),5),
        "max_closed_drawdown_pct":round(dd,5),
        "trades":len(ledger),
        "fee_usdt":round(sum(x["fees_usdt"] for x in ledger),7),
        "measured_funding_usdt":round(sum(x["observed_funding_usdt"] for x in ledger),7),
        "estimated_funding_usdt":round(sum(x["estimated_funding_usdt"] for x in ledger),7),
        "liquidation_proxies":sum(x["exit_reason"]=="liquidation_proxy" for x in ledger),
        "hit_25m_closed":equity>=TARGET,
        "ruin":equity<=.83,
        "ledger":ledger,"curve":curve,
    }

def score_only(row):
    return {k:v for k,v in row.items() if k not in ("ledger","curve")}

def training_selection(all_scores):
    qualified=[]
    for key,periods in all_scores.items():
        a=periods["fit"]["stress"]
        b=periods["development"]["stress"]
        if (a["trades"]>=5 and a["net_return_pct"]>0 and
            b["net_return_pct"]>0 and b["max_closed_drawdown_pct"]<=35
            and periods["development"]["ordinary"]["net_return_pct"]>0
            and not b["ruin"]):
            qualified.append(key)
    chosen=max(qualified,key=lambda k:all_scores[k]["development"]["stress"]["net_return_pct"]) if qualified else None
    return chosen,qualified

def weekly_signflip(trades,hypotheses,rounds=PERMUTATIONS):
    weekly={}
    for t in trades:
        if t["equity_before"]<=0 or t["equity_after"]<=0:return 1.
        week=t["ts"]//(7*86400000)
        weekly[week]=weekly.get(week,0)+math.log(t["equity_after"]/t["equity_before"])
    values=list(weekly.values())
    if len(values)<5:return 1.
    rng=random.Random(25_000_000_2047)
    observed=sum(values);success=0
    for i in range(rounds):
        x=sum(y*(1 if rng.randrange(2) else -1) for y in values)
        success+=x>=observed
    return round(min(1.,(success+1)/(rounds+1)*hypotheses),5)

def weekly_bootstrap(trades,rounds=300):
    week={}
    for trade in trades:
        if trade["equity_before"]<=0 or trade["equity_after"]<=0:return None
        i=trade["ts"]//(7*86400000)
        week[i]=week.get(i,0)+math.log(trade["equity_after"]/trade["equity_before"])
    values=list(week.values())
    if len(values)<5:return None
    rng=random.Random(25_000_000_2047);returns=[]
    for i in range(rounds):
        loggain=sum(values[rng.randrange(len(values))] for _ in values)
        returns.append(100*math.expm1(min(50,loggain)))
    returns.sort()
    return [round(returns[int(rounds*.025)],5),
            round(returns[int(rounds*.975)],5)]

def curve_svg(curve,path):
    values=[z["equity"] for z in curve]
    if not values:return
    high=max(values);low=min(0,min(values));scale=max(1e-6,high-low)
    coords=" ".join("%.2f,%.2f"%(90+850*i/max(1,len(values)-1),
                                    410-325*(v-low)/scale)
                    for i,v in enumerate(values))
    doc=('<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="500">'
         '<rect width="1000" height="500" fill="#ffffff"/>'
         '<text x="90" y="35" font-size="19">TITAN OMEGA 25M - historical PAPER equity, USDT</text>'
         '<text x="90" y="480" font-size="14">Actual OKX OHLCV; approximated fills. No real trades.</text>'
         '<polyline fill="none" stroke="#1764c0" stroke-width="2" points="'
         +coords+'"/>'
         '<text x="8" y="90" font-size="14">'+str(round(high,2))+'</text>'
         '<text x="8" y="410" font-size="14">'+str(round(low,2))+'</text></svg>')
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(doc)

def study(markets,specs,funding,hashes):
    if len(markets)!=market.MARKETS or set(markets)!=set(specs) or set(markets)!=set(hashes):
        raise ValueError("Six unique fully documented original market files required")
    if any(sym[:-10] not in market.POOL for sym in markets):
        raise ValueError("Outside frozen crypto universe")
    n=min(len(b) for b in markets.values())
    w=windows(n)
    axis=[x["ts"] for x in next(iter(markets.values()))[:n]]
    for rows in markets.values():
        if [x["ts"] for x in rows[:n]]!=axis:
            raise ValueError("Misaligned genuine cross-market history")
    candles={s:b[:n] for s,b in markets.items()}
    streams,fit_params,fit_summary=market.signal_panel(candles,w["fit"][1])
    scores={};all_trials=[];all_trades=[]
    for policy in fam.ACTIVE:
        signals={s:streams[s][policy] for s in candles}
        for lev in LEVS:
            name=policy+"_"+str(int(lev))+"x"
            scores[name]={}
            for pname,(start,end) in w.items():
                scores[name][pname]={}
                for cost,(fee,slip) in COSTS.items():
                    row=paper(candles,specs,funding,signals,lev,start,end,fee,slip)
                    scores[name][pname][cost]=score_only(row)
                    all_trials.append({"model":name,"period":pname,"cost":cost,
                                       "score":score_only(row)})
                    for t in row["ledger"]:
                        all_trades.append({"model":name,"period":pname,
                                           "cost":cost,"trade":t})
    chosen,qualified=training_selection(scores)
    # When no model passed fit + development, plot only a labeled diagnostic.
    diagnostic=max(scores,key=lambda k:scores[k]["development"]["stress"]["net_return_pct"])
    focus=chosen or diagnostic
    model,lev=focus.rsplit("_",1)
    signals={s:streams[s][model] for s in candles}
    retest={}
    for p,(start,end) in w.items():
        retest[p]=paper(candles,specs,funding,signals,float(lev[:-1]),
                        start,end,*COSTS["stress"])
    final=retest["final_combined"]
    repeated=bool(chosen) and all(scores[chosen][p][cost]["hit_25m_closed"]
                                   and not scores[chosen][p][cost]["ruin"]
                                   for p in HOLDOUTS for cost in COSTS)
    combined=bool(chosen) and all(scores[chosen]["final_combined"][c]["hit_25m_closed"]
                                   for c in COSTS)
    adjusted=weekly_signflip(final["ledger"],len(scores))
    highest=max(((m,p,c,rows[p][c]["net_return_pct"])
                  for m,rows in scores.items() for p in HOLDOUTS for c in COSTS),
                key=lambda x:x[3])
    return {
        "study":market.STUDY,"target_pct":TARGET_PCT,
        "starting_usdt":START,"required_final_balance_usdt":TARGET,
        "source":"Public original OKX 15m OHLCV and actual volCcyQuote",
        "markets":sorted(candles),"raw_source_sha256":hashes,
        "bars_per_market":n,"total_true_market_bars":n*len(candles),
        "family_count":len(fam.MODELS)-1,
        "families_active":list(fam.ACTIVE),
        "families_unavailable_without_raw_feeds":fam.UNAVAILABLE,
        "candidate_model_leverage_pairs":len(scores),
        "executed_period_cost_trials":len(all_trials),
        "all_hypothesis_summaries":scores,
        "dev_qualified":qualified,"development_selected_before_final":chosen,
        "plot_focus":focus,"plot_is_validated_candidate":bool(chosen),
        "fitted_on_first_35pct_only":fit_summary,
        "fitted_parameters":fit_params,
        "periods":w,
        "focus_curve_closed":final["curve"],
        "focus_final_trade_ledger":final["ledger"],
        "focus_score_by_period":{k:score_only(v) for k,v in retest.items()},
        "highest_retrospective_holdout_NOT_validated":{
             "model":highest[0],"period":highest[1],
             "cost":highest[2],"return_pct":highest[3]},
        "week_block_signflip_bonferroni_exploratory":adjusted,
        "week_bootstrap_95pct_exploratory":weekly_bootstrap(final["ledger"]),
        "pass_repeated_25million":bool(repeated and combined and adjusted<=.05),
        "verdict":("HISTORICAL_PAPER_ONLY_NOT_FUTURE_PROOF"
                   if repeated and combined and adjusted<=.05
                   else "NO_VALIDATED_REPEATED_25M_RETURN"),
        "all_trial_summaries":all_trials,
        "all_trial_trades":all_trades,
        "real_orders":0,"physical_quantum_hardware":False,
        "limitations":[
            "Actual funding only from last ~3 months, earlier is an explicit assumption",
            "No historical mark-price liquidation or L2 order book from OHLCV",
            "Current contract specs cannot guarantee historical contract executability",
            "Closed-trade drawdown excludes adverse intratrade mark-to-market",
            "Three data-dependent hypothesis families were correctly NOT tested",
            "Block signflip and bootstrap are exploratory, not rigorous DSR or PBO",
            "Multiple previous user-guided studies raise overall overfitting exposure",
            "No real cash profit and no guaranteed future returns",
        ]
    }

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out",required=True)
    ap.add_argument("--raw-dir",required=True)
    ap.add_argument("--curve",required=True)
    ap.add_argument("--trades",required=True)
    a=ap.parse_args(argv)
    now=int(time.time()*1000)
    specs,pool=market.catalogue(now)
    print("OMEGA PRECOMMITTED UNIVERSE",pool,[s["instId"] for s in specs],flush=True)
    rawdir=Path(a.raw_dir);rawdir.mkdir(parents=True,exist_ok=True)
    candles={};funder={};hashes={};manifest={}
    for spec in specs:
        sym=spec["instId"]
        rows,original=market.fetch_candles(sym,now)
        blob=json.dumps(original,separators=(",",":")).encode()
        digest=hashlib.sha256(blob).hexdigest()
        with gzip.open(rawdir/(sym+"-original-15m.json.gz"),"wb") as stream:
            stream.write(blob)
        print("OMEGA ORIGINAL OKX OHLCV",sym,len(rows),"SHA256",digest,flush=True)
        candles[sym]=rows;hashes[sym]=digest
        try:
            fr=market.fetch_funding(sym,now)
        except (RuntimeError,ValueError,KeyError) as err:
            print("OMEGA FUNDING API UNAVAILABLE",sym,type(err).__name__,flush=True)
            fr=[]
        funder[sym]=[(t,v) for t,v,_ in fr]
        rawfund=json.dumps([x[2] for x in fr],separators=(",",":")).encode()
        with gzip.open(rawdir/(sym+"-observed-funding.json.gz"),"wb") as h:
            h.write(rawfund)
        manifest[sym]={
            "candle_url_base":"https://www.okx.com/api/v5/market/history-candles",
            "funding_url_base":"https://www.okx.com/api/v5/public/funding-rate-history",
            "download_timestamp_ms":now,
            "original_price_ohlcv_sha256":digest,
            "funding_observed_sha256":hashlib.sha256(rawfund).hexdigest(),
            "funding_observed_count":len(fr),
            "current_instrument_snapshot":spec,
        }
    report=study(candles,{z["instId"]:z for z in specs},funder,hashes)
    audit=report.pop("all_trial_trades")
    with gzip.open(a.trades,"wt",encoding="utf-8") as h:
        for obj in audit:h.write(json.dumps(obj,separators=(",",":"))+"\n")
    report["all_candidate_trade_rows_in_gzip"]=len(audit)
    report["source_manifest"]=manifest
    target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    curve_svg(report["focus_curve_closed"],a.curve)
    print("OMEGA TOTAL MODELS",report["candidate_model_leverage_pairs"],
          "BACKTEST RUNS",report["executed_period_cost_trials"],
          "TRADE ROWS",len(audit),flush=True)
    print("OMEGA SELECTED",report["development_selected_before_final"],
          "FOCUS",report["plot_focus"],flush=True)
    for name,row in report["focus_score_by_period"].items():
        print("OMEGA PERIOD",name,"RETURN",row["net_return_pct"],
              "TRADES",row["trades"],"MAX_DD",row["max_closed_drawdown_pct"],
              "FEES",row["fee_usdt"],"FUNDING_MEASURED",
              row["measured_funding_usdt"],"FUNDING_ESTIMATED",
              row["estimated_funding_usdt"],"LIQ_PROXY",row["liquidation_proxies"],flush=True)
    print("OMEGA FINAL",report["verdict"],"RETROSPECTIVE_TOP",
          report["highest_retrospective_holdout_NOT_validated"],
          "BONFERRONI_WEEK_P",report["week_block_signflip_bonferroni_exploratory"],
          "NO ORDERS",flush=True)
    pts=report["focus_curve_closed"]
    print("OMEGA CURVE_SAMPLE",json.dumps(pts[::max(1,len(pts)//12)]),flush=True)

if __name__=="__main__":main()

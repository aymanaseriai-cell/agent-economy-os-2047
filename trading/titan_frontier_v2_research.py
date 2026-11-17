#!/usr/bin/env python3
"""TITAN Ω INFINITE FRONTIER Gen2: honest 180d OKX read-only research.

Precommitted 6 new markets; exact OHLCV and observed funding where available;
Kalman DLM, true explicit-duration HSMM, online BOCPD, ridge Koopman, split
conformal, distributionally robust forecast, selective regime ensemble,
quantum-inspired annealing versus exact combinatorial baseline.
Training-only fitting, DEVELOPMENT-only threshold calibration and selection,
3 chronologically embargoed FINAL holdouts. NO REAL ORDERS.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,statistics,time
from pathlib import Path
from trading.edge_lab import BAR_MS,TAKER_FEE,BASE_SLIPPAGE,STRESS_FEE,STRESS_SLIPPAGE
from trading import titan_omega_25m_market as market
from trading import titan_omega_25m_engine as old
from trading import titan_frontier_v2_models as model

STUDY="TITAN-INFINITE-FRONTIER-2-NEW-MARKETS-20261117-LOCKED"
START=4.15
TARGET=1_037_504.15
LEVERAGES=(3.,10.)
MARKETS=6
COHORT_EXCLUDE=set(("TRB BICO SSV YFI BAT THETA").split())
POLICIES=("kalman","hsmm","koopman","conformal","distribution_robust",
          "changepoint","regime_ensemble","quantum_anneal",
          "exact_enumeration","classic")
THRESHOLD={"kalman":.45,"hsmm":.42,"koopman":.32,"conformal":.001,
           "distribution_robust":.01,"changepoint":.30,
           "regime_ensemble":.26,"quantum_anneal":.15,
           "exact_enumeration":.15,"classic":.85}
COSTS={
    "ordinary":(TAKER_FEE,BASE_SLIPPAGE),
    "stress":(STRESS_FEE,STRESS_SLIPPAGE),
    "extreme":(.0015,.003),
}
CANDIDATE_COUNT=len(POLICIES)*len(LEVERAGES)
DEVELOPMENT_CALIBRATION_ALPHA=.1
MAX_PORTION_REAL_QUOTE_VOLUME=.01
HOLDOUTS=("final_1","final_2","final_3")

def catalogue(now):
    raw=market.public("/api/v5/public/instruments",{"instType":"SWAP"})
    selected=[]
    for item in raw:
        name=item.get("instId","")
        if not name.endswith("-USDT-SWAP"):continue
        coin=name[:-10]
        if (coin not in market.POOL or coin in COHORT_EXCLUDE or
            item.get("state")!="live" or item.get("ctType")!="linear"
            or item.get("ctValCcy")!=coin):continue
        try:
            if int(item["listTime"])>now-210*86400000:continue
            if any(float(item[k])<=0 for k in ("minSz","lotSz","ctVal")):continue
        except (KeyError,ValueError,TypeError):continue
        selected.append(item)
    selected.sort(key=lambda x:hashlib.sha256(
        (STUDY+"|"+x["instId"]).encode()).hexdigest())
    if len(selected)<MARKETS:raise ValueError("Not enough untested crypto swaps")
    return selected[:MARKETS],len(selected)

def windows(n):
    # Purge 2 days from both sides of dev and each final holdout.
    return old.windows(n)

def fit_and_streams(bars,cut_fit,cal_start,cal_end):
    hours={sym:market.aggregate(row) for sym,row in bars.items()}
    count=min(len(x) for x in hours.values())
    axis=[x["ts"] for x in next(iter(hours.values()))[:count]]
    if any([x["ts"] for x in h[:count]]!=axis for h in hours.values()):
        raise ValueError("Asynchronous 4h bars - refuse prediction")
    fast={s:market.ema([z["close"] for z in h],8) for s,h in hours.items()}
    slow={s:market.ema([z["close"] for z in h],30) for s,h in hours.items()}
    observations=[];train=[];cal=[]
    for t in range(market.WARM,count-1):
        breadth=sum(1 if z[t]["close"]>z[t-6]["close"] else -1
                    for z in hours.values())/len(hours)
        for sym in sorted(hours):
            h=hours[sym]
            feature,atr=market.causal_feature(h,t,fast[sym],slow[sym],breadth)
            idx=h[t]["idx"];next_i=h[t+1]["idx"]
            if not .002<atr/h[t]["close"]<.15:continue
            obsret=math.log(h[t]["close"]/h[t-1]["close"])
            y=math.log(h[t+1]["close"]/h[t]["close"])
            observations.append((t,sym,idx,feature,atr,obsret))
            if next_i+market.BLOCK*2<cut_fit:
                train.append((feature,y,sym,t))
            elif idx>=cal_start and next_i+market.BLOCK*2<cal_end:
                cal.append((feature,y,sym,t))
    fitted=model.fit(train)
    errs=[abs(y-model.koopman_forecast(f,fitted)) for f,y,_,_ in cal]
    q=model.conformal_threshold(errs,DEVELOPMENT_CALIBRATION_ALPHA)
    calibration_coverage=sum(abs(y-model.koopman_forecast(f,fitted))<=q
                             for f,y,_,_ in cal)/len(cal)
    # Both controls and signals are computed CAUSALLY on all 4h observations,
    # using train-frozen parameters and development-calibrated q only.
    states={sym:(
        model.BayesianKalman(fitted["kalman_phi"],fitted["y_sigma"]),
        model.DurationHSMM(fitted["y_sigma"]),
        model.BOCPD(fitted["y_sigma"])
    ) for sym in hours}
    out={s:{k:[] for k in POLICIES} for s in hours}
    obsbytime={}
    for t,sym,idx,f,a,r in observations:
        obsbytime.setdefault(t,[]).append((sym,idx,f,a,r))
    exact_objective_matches=0;anneal_abstentions=0;quantum_actions=0
    for t in sorted(obsbytime):
        bysym={}
        for sym,idx,f,a,ret in obsbytime[t]:
            kal,hsmm,cp=states[sym]
            k=kal.update(ret)
            h=hsmm.update(ret)
            changepoint=cp.update(ret)
            bysym[sym]=(idx,f,a,k,h,changepoint)
            for policy in POLICIES:
                if policy in ("quantum_anneal","exact_enumeration"):continue
                score=model.conditionally_score(f,policy,fitted,k,h,changepoint,q)
                if not math.isfinite(score):raise ArithmeticError("Invalid conditional forecast")
                if abs(score)>=THRESHOLD[policy]:
                    out[sym][policy].append((
                        idx,1 if score>0 else -1,a,round(min(2.,abs(score)),7)))
        # A true apples-to-apples experiment: both portfolio optimizers
        # see exactly the same one-position robust objective, same symbols.
        symbols=sorted(bysym)
        if len(symbols)!=MARKETS:continue
        objectives=[.25]
        for sym in symbols:
            idx,f,a,k,h,change=bysym[sym]
            forecast=model.koopman_forecast(f,fitted)
            v=max(1e-5,fitted["residual_sigma"])
            utility=max(0.,abs(forecast)/v-.30)
            objectives.append(utility)
        qchoice=model.softmax_anneal(objectives)
        exact=model.exact_enumeration(objectives)
        exact_objective_matches+=qchoice==exact
        for policy,choice in (("quantum_anneal",qchoice),
                              ("exact_enumeration",exact)):
            if choice==0:
                if policy=="quantum_anneal":anneal_abstentions+=1
                continue
            sym=symbols[choice-1]
            idx,f,a,k,h,change=bysym[sym]
            prediction=model.koopman_forecast(f,fitted)
            if prediction==0:continue
            if objectives[choice]<=objectives[0]:continue
            if policy=="quantum_anneal":quantum_actions+=1
            out[sym][policy].append((
                idx,1 if prediction>0 else -1,a,
                round(min(2.,objectives[choice]),7)))
    meta={"train_samples":len(train),"development_calibration_samples":len(cal),
          "conformal_q":q,"empirical_development_coverage":calibration_coverage,
          "quantum_exact_same_objective_match_fraction":
              exact_objective_matches/max(1,len(obsbytime)),
          "quantum_abstentions":anneal_abstentions,
          "quantum_eligible_actions":quantum_actions,
          "kooopman_ridge_weights":fitted["koopman_weights"],
          "train_fit_parameters":fitted,
          "data_source_is_original_ohlcv":True}
    return out,meta

def conservative_paper(bars,specs,funding,signals,lev,start,end,fee,slip):
    """Extends old paper engine with a point-in-time <=1% quote-volume cap.

    Every order is still a next-15m-open hypothetical fill. The maker book,
    mark-price liquidation and actual exchange matching are UNKNOWN.
    Only CLOSED equity from settled trades can be reinvested.
    """
    events={}
    for sym,stream in signals.items():
        for sig in stream:
            if start<=sig[0] and sig[0]+1<end:
                events.setdefault(sig[0],[]).append((sig[3],sym,sig))
    eq=START;peak=START;dd=0.;next_entry=start;ledger=[]
    rejections={"insufficient_lot":0,"insufficient_quote_volume":0,
                "other_execution":0}
    start_t=bars[next(iter(bars))][start]["ts"]
    curve=[{"ts":start_t,"equity":eq}]
    for i in sorted(events):
        if i<next_entry or eq<=.83 or eq>=TARGET:continue
        for _,sym,signal in sorted(events[i],key=lambda x:(-x[0],x[1])):
            bar=bars[sym];j=i+1
            q,notional=old.affordable(specs[sym],eq,bar[j]["open"],signal[2],lev)
            if q<=0:
                rejections["insufficient_lot"]+=1
                continue
            quoted=bar[i]["vol_quote"]
            if quoted<=0 or notional>quoted*MAX_PORTION_REAL_QUOTE_VOLUME:
                rejections["insufficient_quote_volume"]+=1
                continue
            r=old.simulate(bar,signal,specs[sym],funding.get(sym,[]),
                           eq,lev,fee,slip,end)
            if r is None:
                rejections["other_execution"]+=1
                continue
            eq=r["equity_after"]
            next_entry=r["exit_bar_index"]+1
            peak=max(peak,eq)
            dd=max(dd,100*(peak-eq)/peak)
            ledger.append(r)
            curve.append({"ts":r["ts"],"equity":eq})
            break
    return {
        "end_usdt":round(eq,8),"net_return_pct":round(100*(eq/START-1),5),
        "max_closed_drawdown_pct":round(dd,5),"trades":len(ledger),
        "fee_usdt":round(sum(x["fees_usdt"] for x in ledger),7),
        "funding_measured_usdt":round(sum(x["observed_funding_usdt"] for x in ledger),7),
        "funding_estimated_usdt":round(sum(x["estimated_funding_usdt"] for x in ledger),7),
        "liquidation_proxies":sum(x["exit_reason"]=="liquidation_proxy" for x in ledger),
        "rejected":rejections,"target_hit_closed":eq>=TARGET,
        "ruin":eq<=.83,"ledger":ledger,"curve":curve,
    }

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def evaluate(bars,specs,funding,manifest):
    if len(bars)!=MARKETS or set(bars)!=set(specs) or set(bars)!=set(manifest):
        raise ValueError("Need exactly six documented OHLCV instrument samples")
    n=min(len(rows) for rows in bars.values())
    spans=windows(n)
    axis=[z["ts"] for z in next(iter(bars.values()))[:n]]
    for sym,rows in bars.items():
        if [z["ts"] for z in rows[:n]]!=axis:raise ValueError("Historical panel misalignment")
        if any(b["ts"]-a["ts"]!=BAR_MS for a,b in zip(rows,rows[1:])):
            raise ValueError("Missing true OHLCV bar")
        if sym[:-10] not in market.POOL or sym[:-10] in COHORT_EXCLUDE:
            raise ValueError("Overlapping original OMEGA cohort")
    bars={sym:rows[:n] for sym,rows in bars.items()}
    streams,meta=fit_and_streams(
        bars,spans["fit"][1],spans["development"][0],spans["development"][1])
    scores={};audits=[];ledger=[]
    for policy in POLICIES:
        votes={s:streams[s][policy] for s in bars}
        for lev in LEVERAGES:
            name=policy+"_"+str(int(lev))+"x"
            scores[name]={}
            for label,(lo,hi) in spans.items():
                scores[name][label]={}
                for cost,(fee,slip) in COSTS.items():
                    r=conservative_paper(bars,specs,funding,votes,lev,lo,hi,fee,slip)
                    summary={k:v for k,v in r.items() if k not in ("ledger","curve")}
                    scores[name][label][cost]=summary
                    audits.append({"model":name,"period":label,"cost":cost,
                                   "score":summary})
                    for trade in r["ledger"]:
                        ledger.append({"model":name,"period":label,
                                       "cost":cost,"trade":trade})
    # Frozen ex ante selection; no final holdout data used to select winner.
    acceptable=[k for k,sections in scores.items() if
                sections["fit"]["stress"]["trades"]>=5
                and sections["fit"]["stress"]["net_return_pct"]>0
                and sections["development"]["stress"]["net_return_pct"]>0
                and sections["development"]["extreme"]["net_return_pct"]>0
                and sections["development"]["extreme"]["max_closed_drawdown_pct"]<=35
                and not sections["development"]["extreme"]["ruin"]]
    selected=(max(acceptable,key=lambda k:scores[k]["development"]["extreme"]["net_return_pct"])
              if acceptable else None)
    diagnostic=max(scores,key=lambda k:scores[k]["development"]["stress"]["net_return_pct"])
    focus=selected or diagnostic
    pol,lev=focus.rsplit("_",1)
    votes={s:streams[s][pol] for s in bars}
    full=conservative_paper(bars,specs,funding,votes,float(lev[:-1]),
                            *spans["final_combined"],*COSTS["extreme"])
    repeated=bool(selected) and all(
        scores[selected][p][case]["target_hit_closed"] and
        not scores[selected][p][case]["ruin"]
        for p in HOLDOUTS for case in COSTS)
    combined=bool(selected) and all(scores[selected]["final_combined"][c]["target_hit_closed"]
                                    for c in COSTS)
    best=max(((m,p,c,sec[p][c]["net_return_pct"]) for m,sec in scores.items()
              for p in HOLDOUTS for c in COSTS),key=lambda z:z[3])
    return {
        "study":STUDY,"start_usdt":START,"target_pct":25_000_000.,
        "target_usdt":TARGET,"raw_market_sha256":manifest,
        "markets":sorted(bars),"bars_per_market":n,"market_bars_total":n*MARKETS,
        "train_and_dev_only_params":meta,
        "policy_families":list(POLICIES),"leverage_cases":list(LEVERAGES),
        "candidate_count":len(scores),"executed_period_cost_scenarios":len(audits),
        "periods":spans,"all_policy_summaries":scores,
        "qualified_on_train_development_only":acceptable,
        "selected_before_final":selected,"focus_model":focus,
        "focus_is_qualified":bool(selected),
        "retrospective_best_final_not_selected":{
            "model":best[0],"period":best[1],"cost":best[2],"net_return_pct":best[3]},
        "selected_reached_25million_in_three_holdouts":bool(repeated),
        "selected_reached_25million_in_combined_holdout":bool(combined),
        "final_verdict":("HISTORICAL_PAPER_CANDIDATE_NOT_LIVE_PROOF" if repeated and combined
                          else "NO_VALIDATED_25M_REPEATABLE_RETURN"),
        "focal_final_extreme":{k:v for k,v in full.items() if k not in ("ledger","curve")},
        "focal_equity_curve":full["curve"],
        "focal_trades":full["ledger"],"all_trade_records":ledger,
        "all_trial_summaries":audits,"real_orders":0,
        "quantum_hardware":False,
        "limitations":[
            "New asset cohort still same 2026 market calendar regime, historical not live unseen future",
            "Current-spec survivor-selection bias remains; historical listing changes unavailable",
            "Mark price, historical leverage tiers and order book L2 were NOT reconstructed",
            "Volume is real, but 1% cap and impact/slippage are policy approximations",
            "Observed funding only public recent history; older settlements estimated",
            "Conformal 90% coverage calibrated on dev is descriptive, not exchangeable time-series guarantee",
            "Closed-equity drawdown excludes adverse intratrade mark-to-market",
            "Cross-study multiple testing and observational correlations remain",
        ],
    }

def save_csv_svg(report,path):
    old.curve_svg(report["focal_equity_curve"],path)

def load_raw_folder(folder):
    root=Path(folder)
    manifest=json.loads((root/"manifest.json").read_text())
    bars={};specs={};funding={};rawhash={}
    for sym,meta in manifest.items():
        orig=gzip.decompress((root/(sym+"-original-15m.json.gz")).read_bytes())
        if digest(orig)!=meta["original_price_sha256"]:
            raise ValueError("Corrupted frozen historical data: "+sym)
        rows=json.loads(orig)
        parsed=[market.decode(x) for x in rows]
        if any(x is None for x in parsed):raise ValueError("Unconfirmed bar in archive")
        funding_bytes=gzip.decompress((root/(sym+"-funding.json.gz")).read_bytes())
        if digest(funding_bytes)!=meta["funding_sha256"]:
            raise ValueError("Corrupted historical funding")
        funding[sym]=[(int(x["fundingTime"]),float(x["realizedRate"]))
                      for x in json.loads(funding_bytes)]
        bars[sym]=parsed
        specs[sym]=meta["instrument_snapshot"]
        rawhash[sym]=meta["original_price_sha256"]
    return bars,specs,funding,rawhash

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    parser.add_argument("--raw-dir",required=True)
    parser.add_argument("--curve",required=True)
    parser.add_argument("--trades",required=True)
    parser.add_argument("--offline",action="store_true")
    parser.add_argument("--compare-report")
    a=parser.parse_args(argv)
    raw=Path(a.raw_dir);raw.mkdir(parents=True,exist_ok=True)
    if a.offline:
        data,specs,funding,raw_sha=load_raw_folder(raw)
        print("FRONTIER OFFLINE verified frozen source",len(data),flush=True)
    else:
        now=int(time.time()*1000)
        cohort,pool=catalogue(now)
        print("FRONTIER NEW HASH-SELECTED COHORT BEFORE RETURNS",pool,
              [z["instId"] for z in cohort],flush=True)
        data={};funding={};specs={};raw_sha={};manifest={}
        for spec in cohort:
            name=spec["instId"]
            rows,original=market.fetch_candles(name,now)
            payload=json.dumps(original,separators=(",",":")).encode()
            dg=digest(payload)
            with gzip.open(raw/(name+"-original-15m.json.gz"),"wb") as handle:
                handle.write(payload)
            try:
                fund=market.fetch_funding(name,now)
            except (RuntimeError,ValueError,KeyError):
                fund=[]
            funding_bytes=json.dumps([v[2] for v in fund],separators=(",",":")).encode()
            with gzip.open(raw/(name+"-funding.json.gz"),"wb") as handle:
                handle.write(funding_bytes)
            data[name]=rows
            funding[name]=[(t,rate) for t,rate,_ in fund]
            specs[name]=spec
            raw_sha[name]=dg
            manifest[name]={"original_price_sha256":dg,
                            "funding_sha256":digest(funding_bytes),
                            "download_ms":now,"observed_funding_events":len(fund),
                            "instrument_snapshot":spec}
            print("FRONTIER VERIFIED REAL PUBLIC OHLCV",name,len(rows),dg,flush=True)
        (raw/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    report=evaluate(data,specs,funding,raw_sha)
    all_trades=report.pop("all_trade_records")
    report["total_paper_trade_records"]=len(all_trades)
    aud=Path(a.trades);aud.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(aud,"wt",encoding="utf-8") as fp:
        for item in all_trades:fp.write(json.dumps(item,separators=(",",":"))+"\n")
    if a.compare_report:
        expected=json.loads(Path(a.compare_report).read_text())
        checkkeys=("all_policy_summaries","selected_before_final",
                   "focal_equity_curve","focal_trades","final_verdict",
                   "total_paper_trade_records")
        mismatch=[k for k in checkkeys if expected.get(k)!=report.get(k)]
        if mismatch:raise ValueError("Frozen offline mismatch "+",".join(mismatch))
        print("FRONTIER OFFLINE SHA AND RESULTS REPLAY EXACT",len(checkkeys),flush=True)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    save_csv_svg(report,a.curve)
    print("FRONTIER TOTAL",report["candidate_count"],"PARAMETER CASES",
          report["executed_period_cost_scenarios"],"PAPER TRADES",len(all_trades),flush=True)
    print("FRONTIER PRESELECTED",report["selected_before_final"],
          "FOCUS",report["focus_model"],flush=True)
    for key in ("fit","development","final_1","final_2","final_3","final_combined"):
        row=report["all_policy_summaries"][report["focus_model"]][key]["extreme"]
        print("FRONTIER PERIOD",key,"RETURN",row["net_return_pct"],
              "TRADES",row["trades"],"DD",row["max_closed_drawdown_pct"],
              "REJECT",row["rejected"],flush=True)
    print("FRONTIER FINAL",report["final_verdict"],"BEST POSTHOC",
          report["retrospective_best_final_not_selected"],flush=True)

if __name__=="__main__":
    main()

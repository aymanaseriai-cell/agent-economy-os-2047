#!/usr/bin/env python3
"""TITAN Ω V3: NEW economic alpha discovery, small-account constraints, original OKX.

A fixed 8-market 210-day blind-cohort attempt: 35% fit, 25% development,
40% untouched chronological final (three disjoint windows). Strategies are
screened for interpretable after-cost edge with Holm-adjusted week signflip
BEFORE any final result. If none qualifies, final trading is ALWAYS_FLAT.
This deliberately avoids optimistic ex-post 'best strategy' selection.
Read only; no private API, live orders or physical quantum hardware.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,random,time
from pathlib import Path
from trading.edge_lab import BAR_MS,TAKER_FEE,BASE_SLIPPAGE,STRESS_FEE,STRESS_SLIPPAGE,FUNDING_PER_8H
from trading import titan_omega_25m_market as market
from trading import titan_v3_alpha_discovery as alpha

PROTOCOL="TITAN-V3-BEYOND-SINGULARITY-210D-EIGHT-SYMBOLS-20261117-01"
MARKETS=8
DAYS=210
MIN_BARS=20100
START=4.15
TARGET=1037504.15
LEVERAGES=(2.,3.,5.)
STOP_MULT=1.8
PROFIT_MULT=5.2
TRAIL_MULT=2.0
MAX_HOLD=16*25
LIQ_PROXY_MAINT=.015
CAPITAL_MARGIN_MAX=.20
STOP_EQUITY_RISK_MAX=.04
MAX_BAR_QUOTE_VOLUME_SHARE=.002
COSTS={"ordinary":(TAKER_FEE,BASE_SLIPPAGE),
       "stress":(STRESS_FEE,STRESS_SLIPPAGE),
       "extreme":(.0015,.003)}
REFERENCE_EXCLUDE=set((
    "TRB BICO SSV YFI BAT THETA 1INCH DASH ENJ GLM GMX SNX"
).split())
MODELS=alpha.HYPOTHESES+("simple_momentum",)
PAPER_CONTROL="always_flat"
HOLDOUTS=("final_1","final_2","final_3")
SEED=25000003

def catalogue(now):
    raw=market.public("/api/v5/public/instruments",{"instType":"SWAP"})
    eligible=[]
    for s in raw:
        sym=s.get("instId","")
        if not sym.endswith("-USDT-SWAP"):continue
        coin=sym[:-10]
        if (coin not in market.POOL or coin in REFERENCE_EXCLUDE or
            s.get("ctType")!="linear" or
            s.get("ctValCcy")!=coin or s.get("state")!="live"):continue
        try:
            if int(s["listTime"])>now-(DAYS+1)*86400000:continue
            if any(float(s[k])<=0 for k in ("lotSz","minSz","ctVal")):continue
        except (TypeError,KeyError,ValueError):continue
        eligible.append(s)
    eligible.sort(key=lambda x:hashlib.sha256(
        (PROTOCOL+"|"+x["instId"]).encode()).hexdigest())
    if len(eligible)<MARKETS:raise ValueError(
        "Less than eight precommitted sufficiently old OKX markets; refuse data snooping")
    return eligible[:MARKETS],len(eligible)

def download_ohlcv(symbol,now):
    cutoff=now-DAYS*86400000;older=None;raw={}
    for page in range(250):
        args={"instId":symbol,"bar":"15m","limit":"100"}
        if older is not None:args["after"]=str(older)
        page_rows=market.public("/api/v5/market/history-candles",args)
        if not page_rows:break
        decoded=[(r,market.decode(r)) for r in page_rows]
        observed=[(r,d) for r,d in decoded if d is not None]
        if not observed:raise ValueError("Only unconfirmed source candles")
        earliest=min(d["ts"] for _,d in observed)
        if older is not None and earliest>=older:raise ValueError("History cursor stalled")
        for orig,bar in observed:
            if cutoff<=bar["ts"] and bar["ts"]+BAR_MS<=now:
                raw[bar["ts"]]=orig
        if earliest<cutoff or len(page_rows)<100:break
        older=earliest;time.sleep(.07)
    else:raise ValueError("OKX public history pagination exhausted")
    orig=[raw[t] for t in sorted(raw)]
    bars=[market.decode(x) for x in orig]
    if len(bars)<MIN_BARS or any(
        y["ts"]-x["ts"]!=BAR_MS for x,y in zip(bars,bars[1:])):
        raise ValueError("Incomplete original 210d data: "+symbol)
    return bars,orig

def windows(n):
    if n<MIN_BARS:raise ValueError("Need 210 completed days, no shorter fallback")
    a=int(n*.35);b=int(n*.60)
    c=b+(n-b)//3;d=c+(n-b)//3
    embargo=96*2
    w={"train":(80*16,a-embargo),"development":(a+embargo,b-embargo),
       "dev_early":(a+embargo,(a+b)//2-embargo),
       "dev_late":((a+b)//2+embargo,b-embargo),
       "final_1":(b+embargo,c-embargo),
       "final_2":(c+embargo,d-embargo),
       "final_3":(d+embargo,n),
       "final_combined":(b+embargo,n)}
    if any(hi-lo<350 for lo,hi in w.values()):
        raise ValueError("Window too short after embargo")
    return w

def signals(rows,discovery,policy):
    if policy==PAPER_CONTROL:return {}
    fit=discovery["fit"][policy]
    beta=fit["beta"];threshold=fit["threshold"]
    if beta==0:return {}
    sig={}
    for r in rows:
        x=r["features"][policy]
        if abs(x)<max(.01,threshold):continue
        mu=beta*x
        if abs(mu)<.0003:continue
        s=1 if mu>0 else -1
        sym=r["sym"]
        # Conservative fractional Kelly; fitted mu, sigma only, CAP 20% margin.
        sigma=max(.001,fit["sigma"])
        kelly=max(0.,min(.20,.125*abs(mu)/(sigma*sigma)))
        portion=max(.04,min(CAPITAL_MARGIN_MAX,kelly))
        sig.setdefault(sym,[]).append((r["i"],s,r["atr"],
                                       round(abs(mu),9),portion))
    return sig

def affordable(spec,eq,price,atr,leverage,portion):
    if eq<=.83:return 0.,0.
    try:
        cv,step,minsz=(float(spec[k]) for k in ("ctVal","lotSz","minSz"))
        if min(cv,step,minsz,eq,price,atr)<=0:return 0.,0.
        risk=STOP_MULT*atr/price
        if not 0<risk<.25:return 0.,0.
        cap=min(eq*portion*leverage,eq*STOP_EQUITY_RISK_MAX/risk)
        q=math.floor(cap/(price*cv)/step+1e-10)*step
        minimum=math.ceil(minsz/step-1e-10)*step
        if q+1e-10<minimum:return 0.,0.
        return round(q,10),q*cv*price
    except (TypeError,ValueError,KeyError,ZeroDivisionError,OverflowError):
        return 0.,0.

def simulated_trade(candles,sig,spec,fund,eq,lev,fee,slip,hi):
    """Next true 15m open; stop first; unknown mark/liquidation labelled PROXY."""
    i,side,atr,conf,part=sig;j=i+1
    if j>=hi:return None
    price=candles[j]["open"]
    contracts,notional=affordable(spec,eq,price,atr,lev,part)
    if contracts==0:return None
    impact=min(.006,notional/max(1.,candles[i]["vol_quote"])*.25)
    price*=1+side*(slip+impact)
    cv=float(spec["ctVal"]);notional=contracts*cv*price
    initial_margin=notional/lev;enter_fee=notional*fee
    if initial_margin+enter_fee>eq:return None
    stop=price-side*STOP_MULT*atr
    take=price+side*PROFIT_MULT*atr
    liq=price*(1-side*max(.001,1/lev-LIQ_PROXY_MAINT))
    if min(stop,take,liq)<=0:return None
    end=min(hi-1,j+MAX_HOLD-1)
    fill=candles[end]["close"];reason="max_hold"
    for k in range(j,end+1):
        b=candles[k]
        adverse=b["low"] if side>0 else b["high"]
        gap=(b["open"]<=liq if side>0 else b["open"]>=liq)
        if gap or (adverse<=liq if side>0 else adverse>=liq):
            fill=b["open"] if gap else liq;end=k;reason="liquidation_PROXY";break
        if b["open"]<=stop if side>0 else b["open"]>=stop:
            fill=b["open"];end=k;reason="stop_gap";break
        if adverse<=stop if side>0 else adverse>=stop:
            fill=stop;end=k;reason="stop";break
        favorable=b["high"] if side>0 else b["low"]
        if favorable>=take if side>0 else favorable<=take:
            fill=take;end=k;reason="take_profit";break
        # Only after completion of current bar is trailing updated.
        if side>0 and b["close"]>price+2*atr:
            stop=max(stop,b["close"]-TRAIL_MULT*atr)
        if side<0 and b["close"]<price-2*atr:
            stop=min(stop,b["close"]+TRAIL_MULT*atr)
    exitimpact=min(.006,notional/max(1.,candles[max(j,end-1)]["vol_quote"])*.25)
    closeprice=fill*(1-side*(slip+exitimpact))
    exit_fee=abs(contracts*cv*closeprice)*fee
    start_ts=candles[j]["ts"];exit_ts=candles[end]["ts"]+BAR_MS
    measured=[(t,rate) for t,rate in fund if start_ts<t<=exit_ts]
    funding_real=sum(side*notional*rate for _,rate in measured)
    funding_missing=max(0.,(exit_ts-start_ts)/(8*3600000)-len(measured))
    funding_proxy=notional*FUNDING_PER_8H*funding_missing
    gross=side*(closeprice-price)*contracts*cv
    net=gross-enter_fee-exit_fee-funding_real-funding_proxy
    if reason=="liquidation_PROXY":net=min(net,-initial_margin-enter_fee-exit_fee)
    net=max(-eq,net)
    return {"symbol":spec["instId"],"entry_ts":start_ts,"exit_ts":exit_ts,
            "exit_bar_index":end,"direction":side,
            "contracts":contracts,"entry_price":round(price,10),
            "exit_price":round(closeprice,10),"margin":round(initial_margin,8),
            "fee":round(enter_fee+exit_fee,8),"funding_observed":round(funding_real,8),
            "funding_proxy":round(funding_proxy,8),"gross_pnl":round(gross,8),
            "net_pnl":round(net,8),"eq_before":round(eq,8),
            "eq_after":round(max(0.,eq+net),8),"reason":reason}

def replay(markets,specs,funding,book,lev,start,end,fees,slippage):
    """Single open position, closed capital only, no exchange requests."""
    if not book:return {"equity":START,"net_return_pct":0.,"closed_max_dd_pct":0.,
                        "trades":0,"winners":0,"fees":0.,"funding":0.,
                        "liquidations_proxy":0,"rejected_min_lot":0,
                        "rejected_volume":0,"ledger":[],"curve":[]}
    events={}
    for sym,signals_for in book.items():
        for s in signals_for:
            if start<=s[0]<end-1:
                events.setdefault(s[0],[]).append((s[3],sym,s))
    eq=START;peak=START;dd=0.;free=start;ledger=[]
    rejections={"min_lot":0,"liquidity":0,"execution":0}
    curve=[{"ts":markets[next(iter(markets))][start]["ts"],"equity":START}]
    for t in sorted(events):
        if t<free or eq<=.83 or eq>=TARGET:continue
        for conf,sym,signal in sorted(events[t],key=lambda x:(-x[0],x[1])):
            j=t+1
            qty,notional=affordable(specs[sym],eq,markets[sym][j]["open"],
                                    signal[2],lev,signal[4])
            if qty==0:
                rejections["min_lot"]+=1;continue
            if (markets[sym][t]["vol_quote"]<=0 or
                notional>MAX_BAR_QUOTE_VOLUME_SHARE*markets[sym][t]["vol_quote"]):
                rejections["liquidity"]+=1;continue
            trade=simulated_trade(markets[sym],signal,specs[sym],
                                 funding.get(sym,[]),eq,lev,fees,slippage,end)
            if trade is None:
                rejections["execution"]+=1;continue
            eq=trade["eq_after"];free=trade["exit_bar_index"]+1
            peak=max(peak,eq);dd=max(dd,100*(peak-eq)/peak)
            ledger.append(trade);curve.append({"ts":trade["exit_ts"],"equity":eq})
            break
    return {"equity":round(eq,8),"net_return_pct":round(100*(eq/START-1),6),
            "closed_max_dd_pct":round(dd,5),"trades":len(ledger),
            "winners":sum(x["net_pnl"]>0 for x in ledger),
            "fees":round(sum(x["fee"] for x in ledger),7),
            "funding":round(sum(x["funding_observed"]+x["funding_proxy"] for x in ledger),7),
            "liquidations_proxy":sum(x["reason"]=="liquidation_PROXY" for x in ledger),
            "rejected_min_lot":rejections["min_lot"],
            "rejected_volume":rejections["liquidity"],
            "ledger":ledger,"curve":curve}

def score(report):
    return {k:v for k,v in report.items() if k not in ("ledger","curve")}

def estimate_ruin(trades,seed=SEED):
    """TRAIN/DEV-only toy IID trade bootstrap ruin proxy, not empirical reality."""
    if len(trades)<8:return None
    returns=[x["net_pnl"]/max(1e-8,x["eq_before"]) for x in trades]
    rng=random.Random(seed);ruin=0
    for _ in range(1000):
        equity=START
        for j in range(100):
            equity*=max(0.,1+returns[rng.randrange(len(returns))])
            if equity<=START*.2:
                ruin+=1;break
    return {"hypothetical_100_trade_ruin_probability":ruin/1000,
            "threshold_usdt":START*.2,
            "assumptions":"IID bootstrap of past closed DEV trade returns; not future forecast"}

def evaluate(markets,specs,funding,sha):
    if len(markets)!=MARKETS or set(markets)!=set(specs) or set(markets)!=set(sha):
        raise ValueError("Exactly eight frozen real-data markets needed")
    n=min(len(v) for v in markets.values())
    splits=windows(n)
    timeline=[x["ts"] for x in next(iter(markets.values()))[:n]]
    for sym,rows in markets.items():
        if sym[:-10] not in market.POOL or sym[:-10] in REFERENCE_EXCLUDE:
            raise ValueError("Prior tested symbol in final cohort")
        if any(b["ts"]-a["ts"]!=BAR_MS for a,b in zip(rows,rows[1:])):
            raise ValueError("Real historical bars missing")
        if [x["ts"] for x in rows[:n]]!=timeline:
            raise ValueError("Different market time alignments")
    markets={s:v[:n] for s,v in markets.items()}
    obs=alpha.observations(markets)
    discovery=alpha.frozen_discovery(
        obs,splits["train"][1],splits["development"][0],splits["development"][1])
    development_scores={};audit_trades=[];eligible=[];risk_by_policy={}
    for policy in MODELS:
        book=signals(obs,discovery,policy)
        for lev in LEVERAGES:
            name=policy+"_"+str(int(lev))+"x";development_scores[name]={}
            for period in ("train","development","dev_early","dev_late"):
                lo,hi=splits[period];development_scores[name][period]={}
                for cost,(fee,slip) in COSTS.items():
                    r=replay(markets,specs,funding,book,lev,lo,hi,fee,slip)
                    development_scores[name][period][cost]=score(r)
                    if period=="development":
                        audit_trades.extend({"policy":name,"period":period,
                                             "cost":cost,"trade":t} for t in r["ledger"])
            fit=discovery["fit"][policy]
            dev=development_scores[name]["development"]
            reasons=[]
            if not fit["screen_eligible"]:reasons.append("no_Holm_adjusted_development_alpha")
            if development_scores[name]["train"]["stress"]["net_return_pct"]<=0:
                reasons.append("training_after_cost_loss")
            if dev["stress"]["net_return_pct"]<=0:reasons.append("development_net_loss")
            if dev["extreme"]["net_return_pct"]<=0:reasons.append("extreme_cost_not_robust")
            if dev["extreme"]["trades"]<8:reasons.append("insufficient_executable_trades")
            if dev["extreme"]["closed_max_dd_pct"]>30:reasons.append("development_dd_over_30")
            if any(development_scores[name][p]["stress"]["net_return_pct"]<=0
                   for p in ("dev_early","dev_late")):
                reasons.append("nonrepeatable_across_development_halves")
            dev_real=replay(markets,specs,funding,book,lev,*splits["development"],
                            *COSTS["stress"])
            risk_by_policy[name]=estimate_ruin(dev_real["ledger"])
            development_scores[name]["rejection_reasons"]=reasons
            if not reasons:eligible.append(name)
    selected=(max(eligible,key=lambda k:development_scores[k]["development"]
                  ["extreme"]["net_return_pct"]) if eligible else None)
    # FINAL is opened ONCE only for preselected model and predeclared
    # classical/flat controls. Do not evaluate the rejected models OOS.
    final_names=[PAPER_CONTROL, "simple_momentum_2x"]
    if selected:final_names.append(selected)
    final_scores={};final_trade_ledger=[]
    for name in final_names:
        if name==PAPER_CONTROL:book={};lev=1.
        else:
            policy,lv=name.rsplit("_",1)
            book=signals(obs,discovery,policy);lev=float(lv[:-1])
        final_scores[name]={}
        for p in HOLDOUTS+("final_combined",):
            final_scores[name][p]={}
            for cost,(fee,slip) in COSTS.items():
                r=replay(markets,specs,funding,book,lev,*splits[p],fee,slip)
                final_scores[name][p][cost]=score(r)
                final_trade_ledger.extend(
                    {"model":name,"period":p,"cost":cost,"trade":x}
                    for x in r["ledger"])
    summary=final_scores.get(selected,final_scores[PAPER_CONTROL])
    repeated=bool(selected) and all(
        summary[p][c]["equity"]>=TARGET for p in HOLDOUTS for c in COSTS)
    full=selected or PAPER_CONTROL
    fullcurve=replay(markets,specs,funding,
        signals(obs,discovery,selected.rsplit("_",1)[0]) if selected else {},
        float(selected.rsplit("_",1)[1][:-1]) if selected else 1.,
        *splits["final_combined"],*COSTS["extreme"])
    return {
        "study":PROTOCOL,"target_pct":25_000_000.,
        "starting_usdt":START,"target_usdt":TARGET,
        "data":"Original public confirmed OKX 15min OHLCV with real quote volume",
        "markets":sorted(markets),"source_sha256":sha,
        "bars_per_market":n,"genuine_candles":MARKETS*n,
        "train_dev_final_splits":splits,
        "hypotheses_with_paper_variants":len(MODELS)*len(LEVERAGES),
        "development_scenarios":len(MODELS)*len(LEVERAGES)*4*len(COSTS),
        "final_scenarios":len(final_trade_ledger),
        "alpha_discovery":discovery,
        "development_ledger":development_scores,
        "development_risk_of_ruin_assumptions":risk_by_policy,
        "selected_before_final":selected,
        "rejected_paper_variants":len(MODELS)*len(LEVERAGES)-len(eligible),
        "selected_final_results":final_scores,
        "final_rule_passed":bool(repeated and selected and
            all(summary["final_combined"][c]["equity"]>=TARGET for c in COSTS)),
        "verdict":("REPEATABLE_HISTORICAL_PAPER_25M_NOT_LIVE"
                   if repeated else "NO_VALIDATED_REPEATED_25M_EDGE"),
        "focal_final_model":full,"focal_final_extreme":score(fullcurve),
        "focal_final_curve":fullcurve["curve"],
        "focal_final_trades":fullcurve["ledger"],
        "all_dev_trade_rows":audit_trades,
        "all_final_trade_rows":final_trade_ledger,
        "real_orders":0,
        "limitations":[
            "210 historical calendar days on new symbols; not prospective unseen future time",
            "Current live contract survivor universe and present lot specs carry survivorship bias",
            "Actual L2, mark-price liquidation, true market slippage and historic leverage tiers unavailable",
            "Risk-of-ruin IID development bootstrap is an assumption, not calibrated probability",
            "Holm correction is within V3; V1/V2/Q4-Q8 prior research multiplicity remains",
            "Funding exact only where public history available; rest conservatively proxied",
            "Causal feature hypotheses are correlations, not intervention-identified causality",
            "Only one final look at preselected strategy and predefined baselines",
        ],
    }

def sha(x):return hashlib.sha256(x).hexdigest()

def source_load(root):
    manifest=json.loads((root/"manifest.json").read_text())
    b={};s={};f={};hashes={}
    for sym,entry in manifest.items():
        raw=gzip.decompress((root/(sym+"-original-15m.json.gz")).read_bytes())
        fund=gzip.decompress((root/(sym+"-funding.json.gz")).read_bytes())
        if sha(raw)!=entry["ohlcv_sha256"] or sha(fund)!=entry["funding_sha256"]:
            raise ValueError("Frozen source SHA256 mismatch")
        b[sym]=[market.decode(x) for x in json.loads(raw)]
        if any(x is None for x in b[sym]):raise ValueError("Unconfirmed original candle")
        s[sym]=entry["instrument"]
        f[sym]=[(int(x["fundingTime"]),float(x["realizedRate"])) for x in json.loads(fund)]
        hashes[sym]=entry["ohlcv_sha256"]
    return b,s,f,hashes

def curve_svg(points,path):
    if not points:points=[{"equity":START}]
    y=[x["equity"] for x in points];low=min(0,min(y));hi=max(y)
    pathcoords=" ".join("%.1f,%.1f"%(90+950*i/max(1,len(y)-1),
        390-300*(v-low)/max(1e-10,hi-low)) for i,v in enumerate(y))
    Path(path).write_text(
       '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="480">'
       '<rect width="1100" height="480" fill="white"/>'
       '<text x="90" y="28" font-size="18">TITAN V3 — PRESELECTED CLOSED PAPER EQUITY</text>'
       '<polyline fill="none" stroke="#2361b4" stroke-width="2" points="'
       +pathcoords+'"/><text x="90" y="458" font-size="13">'
       'True OKX OHLCV; exchange fills and liquidation are hypothetical; no real orders'
       '</text></svg>')

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--raw-dir",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--trades",required=True)
    p.add_argument("--curve",required=True)
    p.add_argument("--offline",action="store_true")
    p.add_argument("--compare-report")
    a=p.parse_args(argv)
    raw=Path(a.raw_dir);raw.mkdir(parents=True,exist_ok=True)
    if a.offline:
        b,s,f,h=source_load(raw)
        print("V3 OFFLINE SOURCE VERIFIED",len(b),flush=True)
    else:
        now=(int(time.time()*1000)//BAR_MS)*BAR_MS
        cohort,candidates=catalogue(now)
        print("V3 PRECOMMITTED 210D 8-MARKET COHORT BEFORE RETURNS",candidates,
              [x["instId"] for x in cohort],flush=True)
        b={};s={};f={};h={};manifest={}
        for spec in cohort:
            sym=spec["instId"]
            candles,original=download_ohlcv(sym,now)
            rawblob=json.dumps(original,separators=(",",":")).encode()
            with gzip.open(raw/(sym+"-original-15m.json.gz"),"wb") as fp:fp.write(rawblob)
            try:
                funding=market.fetch_funding(sym,now)
            except (RuntimeError,ValueError,KeyError):
                funding=[]
            fundingblob=json.dumps([z[2] for z in funding],separators=(",",":")).encode()
            with gzip.open(raw/(sym+"-funding.json.gz"),"wb") as fp:fp.write(fundingblob)
            b[sym]=candles;s[sym]=spec;f[sym]=[(t,rate) for t,rate,_ in funding]
            h[sym]=sha(rawblob)
            manifest[sym]={"ohlcv_sha256":h[sym],"funding_sha256":sha(fundingblob),
                "download_utc_ms":now,"funding_real_events":len(funding),
                "instrument":spec,"api":"/api/v5/market/history-candles"}
            print("V3 ACTUAL OKX SOURCE",sym,len(candles),h[sym],flush=True)
        (raw/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True))
    r=evaluate(b,s,f,h)
    alltrades=r.pop("all_dev_trade_rows")+r.pop("all_final_trade_rows")
    r["all_trade_records_saved"]=len(alltrades)
    out=Path(a.trades);out.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(out,"wt",encoding="utf-8") as fp:
        for item in alltrades:fp.write(json.dumps(item,separators=(",",":"))+"\n")
    if a.compare_report:
        other=json.loads(Path(a.compare_report).read_text())
        keys=("alpha_discovery","development_ledger","selected_before_final",
              "selected_final_results","focal_final_curve","verdict","all_trade_records_saved")
        diff=[key for key in keys if other.get(key)!=r.get(key)]
        if diff:raise ValueError("Offline frozen replay mismatch "+repr(diff))
        print("V3 EXACT OFFLINE REPLAY MATCH",len(keys),flush=True)
    destination=Path(a.out);destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(r,indent=2,sort_keys=True))
    curve_svg(r["focal_final_curve"],a.curve)
    print("V3 DISCOVERY PASS",r["alpha_discovery"]["economic_screen_passed"],
          "DEVELOPMENT QUALIFIED",len(MODELS)*len(LEVERAGES)-r["rejected_paper_variants"],flush=True)
    print("V3 SELECTED BEFORE FINAL",r["selected_before_final"],
          "FINAL CONTROL",r["focal_final_model"],flush=True)
    for key,record in r["selected_final_results"].items():
        x=record["final_combined"]["extreme"]
        print("V3 FINAL",key,"NET",x["net_return_pct"],
              "TRADES",x["trades"],"DD",x["closed_max_dd_pct"],flush=True)
    print("V3 FINAL VERDICT",r["verdict"],"REAL_ORDERS",r["real_orders"],flush=True)

if __name__=="__main__":
    main()

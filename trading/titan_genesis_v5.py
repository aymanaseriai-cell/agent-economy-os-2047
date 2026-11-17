#!/usr/bin/env python3
"""TITAN GENESIS V5 — research DEVELOPMENT on consumed historical dates.

Three economically defined mechanisms: (A) real 2026 settlement funding
crowding, (B) cross-coin lagged shock transmission and (C) liquidity
elasticity/price impact. NO unseen final validation data yet exists.
Original 2023-25 V4 trade/mark/index sources used as development only;
2026 rates are publicly observed, not invented, and 2026 was also consumed
by prior TITAN work. Prior final outcomes NEVER become a new blind test.

No real orders, private keys, maker fill guarantees or quantum superiority.
"""
from __future__ import annotations
import argparse,collections,datetime,gzip,hashlib,json,math,random,statistics,time,zipfile
from pathlib import Path
from trading import titan_omega_25m_market as public_okx

ID="GENESIS-V5-ECONOMIC-EVENT-FIRST-CONSUMED-DATA-20261117"
START=4.15
GOAL=1037504.15
FOUR_H=14_400_000
WEEK=7*86_400_000
SOURCES=("BTC","ETH","SOL","XRP","DOGE","ADA","DOT","LINK","LTC","ETC")
FUNDED=("BTC","ETH","SOL")
HYPOTHESES=("funding_crowding_reversal","leader_laggard_spillover",
            "liquidity_impact_continuation")
FEES={"base":{"taker":.0005,"slip_spread":.0004,"fund8h":.0001},
      "stress":{"taker":.0015,"slip_spread":.003,"fund8h":.0005}}
LEVERAGE=2.
MARGIN=.15
RISK=.025
VOLUME_PARTICIPATION=.001
ALPHA=.05

def digest(data):return hashlib.sha256(data).hexdigest()

def month(ts):
    return datetime.datetime.fromtimestamp(ts/1000,datetime.timezone.utc).strftime("%Y-%m")

def safe_stdev(values):
    return max(1e-8,statistics.pstdev(values) if len(values)>1 else 1e-8)

def percentile(values,q):
    if not values:raise ValueError("Cannot calibrate quantile on absent past")
    vals=sorted(values)
    return vals[max(0,min(len(vals)-1,math.ceil(q*len(vals))-1))]

def unpack_previous(archive):
    """Use V4 frozen source SHA records, not old PnL as new validation."""
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read("v4_original_2023_2025/manifest.json"))
        market={};raw_sha={}
        for sym in manifest["actual_verified_triples"]:
            triple={}
            raw_sha[sym]={}
            for kind in ("trade","mark","index"):
                name=f"v4_original_2023_2025/{sym}-{kind}.json.gz"
                decompressed=gzip.decompress(z.read(name))
                expected=manifest["source_manifest"][sym][kind]["sha256"]
                if digest(decompressed)!=expected:
                    raise ValueError("Original V4 exchange SHA mismatch: "+sym+":"+kind)
                rows=json.loads(decompressed)
                if len(rows)!=6576 or any(x[-1]!="1" for x in rows):
                    raise ValueError("Unconfirmed or partial original exchange candles")
                triple[kind]=[{"ts":int(x[0]),"open":float(x[1]),
                    "high":float(x[2]),"low":float(x[3]),
                    "close":float(x[4]),"quote":float(x[7]) if kind=="trade" else None}
                    for x in rows]
                raw_sha[sym][kind]=expected
            clock=[[x["ts"] for x in triple[k]] for k in ("trade","mark","index")]
            if not clock[0]==clock[1]==clock[2]:
                raise ValueError("Mark/index/trade historical UTC misalignment")
            market[sym]={"bars":triple,"spec":manifest["source_manifest"][sym]["current_spec"]}
        if len(market)!=10:raise ValueError("No complete ten-market V4 original dataset")
        return market,raw_sha

def fetch_recent_funding(folder):
    """Archive ACTUAL public OKX realizedRate AND 4H quotes; current 2026 R&D only."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    evidence={}
    now=int(time.time()*1000)//FOUR_H*FOUR_H
    cutoff=now-94*86_400_000
    for coin in FUNDED:
        sym=f"{coin}-USDT-SWAP"
        settlements=public_okx.fetch_funding(sym,now)
        if not settlements:
            evidence[sym]={"status":"no_original_realized_funding"}
            continue
        raw_funding=[x[2] for x in settlements]
        oldest=now;records={};last=None
        for iteration in range(72):
            args={"instId":sym,"bar":"4H","limit":"100"}
            if last is not None:args["after"]=str(last)
            response=public_okx.public("/api/v5/market/history-candles",args)
            if not response:break
            valid=[x for x in response if len(x)>=9 and str(x[8])=="1"]
            if not valid:break
            stamp=min(int(x[0]) for x in valid)
            if last is not None and stamp>=last:raise ValueError("Funding-price OHLC history cursor stalled")
            for x in valid:
                t=int(x[0])
                if cutoff<=t<now:records[t]=x
            if stamp<cutoff or len(response)<100:break
            last=stamp;time.sleep(.07)
        if not records:raise ValueError("Historical quote candles missing for "+sym)
        raw_prices=[records[t] for t in sorted(records)]
        if any(int(b[0])-int(a[0])!=FOUR_H for a,b in zip(raw_prices,raw_prices[1:])):
            raise ValueError("Actual 2026 OHLC price gap cannot be interpolated")
        packed={}
        for label,raw in (("actual_funding",raw_funding),("original_4h_trade",raw_prices)):
            blob=json.dumps(raw,separators=(",",":")).encode()
            name=f"{sym}-{label}.json.gz"
            with gzip.open(folder/name,"wb") as z:z.write(blob)
            packed[label]={"sha256":digest(blob),"records":len(raw),"file":name}
        evidence[sym]={"status":"complete","actual":packed}
        print("GENESIS ORIGINAL FUNDING",sym,len(raw_funding),
              "PRICE 4H",len(raw_prices),flush=True)
    manifest={"download_utc_ms":now,"cohort":list(FUNDED),"source":evidence,
              "api_funding":"/api/v5/public/funding-rate-history",
              "api_price":"/api/v5/market/history-candles",
              "research_date_status":"ALL 2026 OBSERVATIONS DEVELOPMENT ONLY; CONSUMED"}
    (folder/"funding_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    return read_recent_funding(folder)

def read_recent_funding(folder):
    folder=Path(folder)
    meta=json.loads((folder/"funding_manifest.json").read_text())
    out={}
    for sym,record in meta["source"].items():
        if record["status"]!="complete":continue
        loaded={}
        for label,source in record["actual"].items():
            raw=gzip.decompress((folder/source["file"]).read_bytes())
            if digest(raw)!=source["sha256"]:
                raise ValueError("TAMPERED actual funding source "+sym+":"+label)
            loaded[label]=json.loads(raw)
        out[sym]=loaded
    return out,meta

def historic_events(market):
    """ONLY use 2023 for train and 2024 as CONSUMED development; NO 2025 labels."""
    train={k:[] for k in HYPOTHESES}
    dev={k:[] for k in HYPOTHESES}
    btc=market["BTC-USDT-SWAP"]["bars"]["trade"]
    btc_returns=[0.]+[math.log(btc[i]["close"]/btc[i-1]["close"])
                      for i in range(1,len(btc))]
    for sym,src in sorted(market.items()):
        if sym=="BTC-USDT-SWAP":continue
        trade=src["bars"]["trade"]
        returns=[0.]+[math.log(trade[i]["close"]/trade[i-1]["close"])
                      for i in range(1,len(trade))]
        for i in range(75,len(trade)-1):
            year=datetime.datetime.fromtimestamp(trade[i]["ts"]/1000,
                  datetime.timezone.utc).year
            if year not in (2023,2024):continue
            nxt=trade[i+1]
            if datetime.datetime.fromtimestamp(nxt["ts"]/1000,
                  datetime.timezone.utc).year!=year:continue
            prev=trade[i];btcvol=safe_stdev(btc_returns[i-48:i])
            ownvol=safe_stdev(returns[i-48:i])
            btc_shock=btc_returns[i]
            # Economic mechanism B: shock already visible in BTC now,
            # but a slow follower has not yet repriced; ONLY t+1 return is label.
            if (abs(btc_shock)>=2.2*btcvol and
                abs(returns[i])<=.35*abs(btc_shock)):
                side=1 if btc_shock>0 else -1
                train_or_dev=train if year==2023 else dev
                train_or_dev["leader_laggard_spillover"].append(
                    build_event(sym,i,prev,nxt,side,"leader_laggard_spillover"))
            # Economic mechanism C: high price impact per quote turnover,
            # combined with a thin-current-volume shock -> continuation test.
            prevquotes=[v["quote"] for v in trade[i-48:i]]
            price_impact=abs(returns[i])/(1+prev["quote"])
            impact_history=[abs(returns[k])/(1+trade[k]["quote"])
                            for k in range(i-48,i)]
            if (price_impact>percentile(impact_history,.90)
                and abs(returns[i])>1.25*ownvol
                and prev["quote"]<statistics.median(prevquotes)):
                side=1 if returns[i]>0 else -1
                train_or_dev=train if year==2023 else dev
                train_or_dev["liquidity_impact_continuation"].append(
                    build_event(sym,i,prev,nxt,side,"liquidity_impact_continuation"))
    return train,dev

def build_event(sym,i,prev,nxt,side,family):
    gross=side*math.log(nxt["close"]/nxt["open"])
    return {"family":family,"symbol":sym,"signal_ts":prev["ts"],
        "entry_ts":nxt["ts"],"i":i+1,"side":side,"gross_log_return":gross,
        "prior_range_pct":(prev["high"]-prev["low"])/max(1e-8,prev["close"]),
        "prior_quote_volume":prev["quote"],"next_open":nxt["open"],
        "next_close":nxt["close"],"month":month(prev["ts"])}

def recent_funding_events(recent):
    """2026 real funding can only be used in development, not new final."""
    train=[];dev=[]
    for sym,source in sorted(recent.items()):
        parsed=sorted([(int(x["fundingTime"]),float(x["realizedRate"]))
                       for x in source["actual_funding"]])
        if len(parsed)<120:continue
        midpoint=len(parsed)//2
        calibrated=percentile([abs(v) for _,v in parsed[:midpoint]],.85)
        candle={}
        for x in source["original_4h_trade"]:
            if len(x)>=9 and str(x[8])=="1":
                candle[int(x[0])]=x
        for ordinal,(timestamp,rate) in enumerate(parsed):
            if abs(rate)<calibrated or rate==0:continue
            # Settlement becomes public at t; enter >= t+4h for latency.
            entry=((timestamp+FOUR_H-1)//FOUR_H)*FOUR_H+FOUR_H
            x=candle.get(entry);prev=candle.get(entry-FOUR_H)
            if x is None or prev is None:continue
            o=float(x[1]);c=float(x[4])
            prior={k:float(prev[j]) for k,j in
                   (("high",2),("low",3),("close",4),("quote",7))}
            side=-1 if rate>0 else 1
            record={"family":"funding_crowding_reversal","symbol":sym,
                "signal_ts":timestamp,"entry_ts":entry,"i":None,
                "side":side,"gross_log_return":side*math.log(c/o),
                "prior_range_pct":(prior["high"]-prior["low"])/prior["close"],
                "prior_quote_volume":prior["quote"],"next_open":o,"next_close":c,
                "month":month(timestamp),"actual_funding_rate":rate}
            (train if ordinal<midpoint else dev).append(record)
    return train,dev

def cost_one(case):
    c=FEES[case]
    return 2*c["taker"]+2*c["slip_spread"]+c["fund8h"]*.5

def signflip_month_p(events,case,seed=9):
    monthly=collections.defaultdict(float)
    for e in events:monthly[e["month"]]+=e["gross_log_return"]-cost_one(case)
    vals=list(monthly.values());n=len(vals)
    if n<6:return 1.
    actual=sum(vals)
    if n<=15:
        positives=sum(sum(v if (mask>>j)&1 else -v for j,v in enumerate(vals))
                      >=actual-1e-15 for mask in range(1<<n))
        return positives/(1<<n)
    rng=random.Random(seed);hits=0
    for j in range(8191):
        v=sum(x*(1 if rng.randrange(2) else -1) for x in vals)
        hits+=v>=actual-1e-15
    return (hits+1)/8192

def holm(p):
    pairs=sorted(p,key=lambda k:(p[k],k))
    out={};running=0.
    for i,name in enumerate(pairs):
        running=max(running,min(1.,p[name]*(len(pairs)-i)))
        out[name]=running
    return out

def month_bootstrap(events,cost,draws=1200):
    grouped=collections.defaultdict(list)
    for e in events:grouped[e["month"]].append(e["gross_log_return"]-cost)
    keys=list(grouped)
    if len(keys)<3:return None
    rng=random.Random(20261117);samples=[]
    for _ in range(draws):
        chosen=[grouped[keys[rng.randrange(len(keys))]] for j in keys]
        vals=[x for block in chosen for x in block]
        samples.append(statistics.mean(vals))
    samples.sort()
    return [samples[int(draws*.025)],samples[int(draws*.975)]]

def wilson_lower(wins,n,z=1.96):
    if n==0:return None
    p=wins/n;den=1+z*z/n
    return max(0,(p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/den)

def size_contract(spec,eq,px,range_pct):
    try:
        cv,lot,mn=(float(spec[k]) for k in ("ctVal","lotSz","minSz"))
        if min(cv,lot,mn,eq,px)<=0:return (0.,0.)
        risk=max(.005,min(.25,range_pct*2))
        cap=min(eq*MARGIN*LEVERAGE,eq*RISK/risk)
        size=math.floor(cap/(px*cv)/lot+1e-10)*lot
        required=math.ceil(mn/lot-1e-10)*lot
        if size+1e-10<required:return (0.,0.)
        return round(size,10),size*cv*px
    except (TypeError,KeyError,ValueError,OverflowError,ZeroDivisionError):
        return (0.,0.)

def paper(events,market,specs,case,initial=START):
    """DEVELOPMENT-only one-bar event probe; not an approved strategy."""
    c=FEES[case];eq=initial;peak=eq;dd=0.;next_t=0;ledger=[];rejected=collections.Counter()
    for ev in sorted(events,key=lambda z:(z["entry_ts"],z["symbol"])):
        t=ev["entry_ts"]
        if t<next_t or eq<=initial*.2:continue
        sym=ev["symbol"];spec=specs.get(sym)
        if not spec:rejected["contract_snapshot_missing"]+=1;continue
        q,notional=size_contract(spec,eq,ev["next_open"],ev["prior_range_pct"])
        if q==0:rejected["min_contract_or_risk"]+=1;continue
        if notional>ev["prior_quote_volume"]*VOLUME_PARTICIPATION:
            rejected["quote_liquidity"]+=1;continue
        d=ev["side"]
        impact=min(.01,.15*notional/max(1.,ev["prior_quote_volume"]))
        entry=ev["next_open"]*(1+d*(c["slip_spread"]+impact))
        exitp=ev["next_close"]*(1-d*(c["slip_spread"]+impact))
        fee=q*float(spec["ctVal"])*(entry+exitp)*c["taker"]
        funded=q*float(spec["ctVal"])*entry*c["fund8h"]*.5
        gross=d*q*float(spec["ctVal"])*(exitp-entry)
        net=max(-eq,gross-fee-funded)
        margin=q*float(spec["ctVal"])*entry/LEVERAGE
        if margin+fee>eq:rejected["margin"]+=1;continue
        end=max(0,eq+net)
        ledger.append({"symbol":sym,"entry_ts":t,"side":d,"contracts":q,
                       "entry":entry,"exit":exitp,"gross":gross,
                       "fee":fee,"funding_assumed":funded,
                       "net":net,"equity_before":eq,"equity_after":end,
                       "source_signal_ts":ev["signal_ts"],
                       "prior_4h_volume":ev["prior_quote_volume"],
                       "has_exact_mark_price_liquidation":False})
        eq=end;peak=max(peak,eq);dd=max(dd,100*(peak-eq)/peak)
        next_t=t+FOUR_H
    winners=[x["net"] for x in ledger if x["net"]>0]
    losers=[x["net"] for x in ledger if x["net"]<0]
    return {"return_pct":100*(eq/initial-1),"end_usdt":eq,
            "trades":len(ledger),"winners":len(winners),"losers":len(losers),
            "profit_factor":sum(winners)/(-sum(losers)) if losers else None,
            "max_closed_dd_pct":dd,
            "avg_win_usdt":statistics.mean(winners) if winners else None,
            "avg_loss_usdt":statistics.mean(losers) if losers else None,
            "fee_usdt":sum(x["fee"] for x in ledger),
            "funding_assumed_usdt":sum(x["funding_assumed"] for x in ledger),
            "rejections":dict(rejected),"ledger":ledger}

def simple_ruin(ledger,seed=9):
    """Declared IID bootstrap DEV trade returns, not future ruin probability."""
    if len(ledger)<8:return None
    pnl=[x["net"]/max(1e-12,x["equity_before"]) for x in ledger]
    rng=random.Random(seed);ruined=0
    for j in range(500):
        eq=START
        for t in range(100):
            eq*=max(0.,1+pnl[rng.randrange(len(pnl))])
            if eq<=.83:ruined+=1;break
    return {"illustrative_100_trade_ruin_rate":ruined/500,
            "threshold":.83,"assumptions":"IID resampling 2024 DEVELOPMENT closed paper trade return, ignores serial dependence"}

def evaluate(market,raw_sha,recent,manifest):
    train,dev=historic_events(market)
    ftrain,fdev=recent_funding_events(recent)
    train["funding_crowding_reversal"]=ftrain
    dev["funding_crowding_reversal"]=fdev
    snapshots={s:rec["spec"] for s,rec in market.items()}
    # Only current 2026 specs, not point-in-time 2024 order limits.
    all_specs={s:snapshots[s] for s in snapshots}
    results={};pvalues={}
    ledgers={}
    for h in HYPOTHESES:
        hist_train=train[h];hist_dev=dev[h]
        n=len(hist_dev);wins=sum(x["gross_log_return"]>0 for x in hist_dev)
        prior=(sum(x["gross_log_return"]>0 for x in hist_train)+1)/(len(hist_train)+2)
        n_pos=sum(x["gross_log_return"]>0 for x in hist_dev)
        actual=n_pos/n if n else None
        avg_gross=statistics.mean([x["gross_log_return"] for x in hist_dev]) if n else None
        p=signflip_month_p(hist_dev,"stress")
        pvalues[h]=p
        condition={}
        for case in FEES:
            cost=cost_one(case)
            net=[x["gross_log_return"]-cost for x in hist_dev]
            condition[case]={
              "assumed_all_in_log_cost_per_position":cost,
              "mean_net_log_return":statistics.mean(net) if net else None,
              "monthly_block_bootstrap_mean_net_95pct":month_bootstrap(hist_dev,cost),
              "total_net_log_event_proxy":sum(net),
            }
        periods=sorted(set(x["month"] for x in hist_dev))
        halves=(hist_dev[:len(hist_dev)//2],hist_dev[len(hist_dev)//2:])
        # Hypothesis-level prefilter before any "strategy" acceptance.
        asset_feasible=0
        for e in hist_dev:
            q,notional=size_contract(all_specs.get(e["symbol"],{}),
                                    START,e["next_open"],e["prior_range_pct"])
            if q>0 and notional<=VOLUME_PARTICIPATION*e["prior_quote_volume"]:
                asset_feasible+=1
        results[h]={
          "train_events":len(hist_train),"development_events":n,
          "development_calendar_months":periods,
          "source_period":"2026 recent, already consumed" if h.startswith("funding")
                          else "2023 train / 2024 development, already consumed",
          "train_bernoulli_smoothed_hit":prior,
          "development_direction_hit":actual,
          "development_direction_wilson_lower95":wilson_lower(wins,n),
          "forecast_calibration_abs_error":abs(prior-actual) if actual is not None else None,
          "gross_mean_log_return":avg_gross,
          "break_even_max_roundtrip_cost":max(0.,avg_gross) if avg_gross is not None else None,
          "cost_cases":condition,"feasible_initial_4_15_signals":asset_feasible,
          "p_month_block_stress":p,
          "half_development_net_stress":[sum(x["gross_log_return"]-cost_one("stress")
                for x in half) for half in halves],
          "distinct_months":len(periods),
        }
    adjusted=holm(pvalues)
    for h in HYPOTHESES:
        d=results[h];d["holm_p"]=adjusted[h]
        requirements=[
            ("months_below_6",d["distinct_months"]<6),
            ("too_few_events",d["development_events"]<30),
            ("not_significant_after_Holm",adjusted[h]>.05),
            ("base_not_positive",d["cost_cases"]["base"]["mean_net_log_return"] is None
                  or d["cost_cases"]["base"]["mean_net_log_return"]<=0),
            ("stress_not_positive",d["cost_cases"]["stress"]["mean_net_log_return"] is None
                  or d["cost_cases"]["stress"]["mean_net_log_return"]<=0),
            ("instability_between_halves",min(d["half_development_net_stress"])<=0),
            ("fewer_than_8_4_15USDT_executable_events",
                  d["feasible_initial_4_15_signals"]<8),
            ("direction_confidence_lower_below_50pct",
                  d["development_direction_wilson_lower95"] is None
                  or d["development_direction_wilson_lower95"]<=.5),
        ]
        d["rejection_reasons"]=[name for name,failed in requirements if failed]
        d["accepted_development_only"]=not d["rejection_reasons"]
        # Even failed hypotheses are run as clearly marked DEVELOPMENT
        # shadow execution probes, not approved final strategies.
        ledgers[h]={}
        for case in FEES:
            probe=paper(dev[h],market,all_specs,case)
            ledgers[h][case]=probe
        d["development_shadow"]={
            case:{k:v for k,v in ledgers[h][case].items() if k!="ledger"}
            for case in FEES}
        d["iid_ruin_assumption"]=simple_ruin(ledgers[h]["stress"]["ledger"])
    return {
        "study":ID,"start_usdt":START,"target_usdt":GOAL,
        "hypotheses_tested":len(HYPOTHESES),"hypotheses_rejected":sum(
            not results[h]["accepted_development_only"] for h in HYPOTHESES),
        "summary":results,"data_sha256":raw_sha,
        "public_funding_manifest":manifest,
        "development_shadow_ledgers":ledgers,
        "predeclared_paper_final":"UNOPENED_NO_NEW_INDEPENDENT_FUTURE_WINDOW",
        "confirmed_future_real_or_paper_25M_edge":False,
        "validated_oos_net_return_pct":None,
        "validated_final_trade_count":None,
        "policy":("ALWAYS_FLAT_UNTIL_PROSPECTIVE_EVIDENCE" if
                   not any(results[h]["accepted_development_only"] for h in HYPOTHESES)
                   else "DEVELOPMENT_CANDIDATE_ONLY_NOT_PROSPECTIVE_VALIDATED"),
        "real_orders":0,
        "limitations":[
           "V1-V4 consumed 2023-2026 dates; NO uncontaminated prospectively future period exists as of 2026-11-17",
           "Source 2023-25 current-live survivors and current contract minimums not historical point-in-time",
           "Funding settlement events from ~90d 2026 are observational and previously exposed calendar",
           "True historical orderbook bid/ask depth and order queue unavailable; maker notional fills NOT assumed",
           "Slippage, funding after entry and liquidation are modeled assumptions, not observed",
           "Blocked signflip only controls three NEW tests; prior OMEGA hundreds of variants not adjusted globally",
           "Small-account and million-USDT capacity change with real quote turnover; no constant fill scaling",
           "IID ruin bootstrap diagnostic cannot establish future tail or liquidation probability",
           "No DSR/PBO: insufficient genuinely independent research trials/correlated return series",
        ]}
    
def write_report(result,output):
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--v4-zip",required=True)
    p.add_argument("--funding-dir",required=True)
    p.add_argument("--report",required=True)
    p.add_argument("--offline",action="store_true")
    p.add_argument("--compare")
    args=p.parse_args(argv)
    market,sha=unpack_previous(args.v4_zip)
    if args.offline:
        recent,manifest=read_recent_funding(args.funding_dir)
    else:
        recent,manifest=fetch_recent_funding(args.funding_dir)
    result=evaluate(market,sha,recent,manifest)
    if args.compare:
        baseline=json.loads(Path(args.compare).read_text())
        if result!=baseline:raise ValueError("GENESIS frozen offline SHA replay DISAGREES")
        print("GENESIS FULL EXACT OFFLINE REPLAY",flush=True)
    write_report(result,args.report)
    for name,r in result["summary"].items():
        print("GENESIS HYPOTHESIS",name,"N",r["development_events"],
              "GROSS",r["gross_mean_log_return"],"HOLM",r["holm_p"],
              "QUALIFIED",r["accepted_development_only"],
              "FEASIBLE",r["feasible_initial_4_15_signals"],flush=True)
    print("GENESIS FINAL",result["policy"],"NEW_INDEPENDENT_FINAL",
          result["predeclared_paper_final"],"REAL_ORDERS",result["real_orders"],flush=True)

if __name__=="__main__":
    main()

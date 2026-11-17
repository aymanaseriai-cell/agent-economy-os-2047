#!/usr/bin/env python3
"""TITAN 6H -- paper-only six-hour OKX futures research.
Inputs are frozen, SHA-verified PUBLIC 5m OKX trade/mark candles, current
instrument/tier snapshots and observed funding. All 2026 data in this run
are DEVELOPMENT, not unseen independent confirmation.
No credential input, order routes, exchange trading or automated scheduling.
"""
from __future__ import annotations
import argparse, collections, datetime as dt, gzip, hashlib, json, math, statistics, zipfile
from pathlib import Path
from decimal import Decimal, ROUND_FLOOR

START=4.15
TARGET=8.30
BAR_MS=300000
BARS=72
LEVERAGES=(3,5,10,20,30,50,75,100)
FAMILIES=("shock_continuation","shock_reversal","trade_mark_reversion")
SCENARIOS={"base":{"fee":0.0005,"slip":0.0004,"extra":0.0002},
           "stress":{"fee":0.0015,"slip":0.0025,"extra":0.001}}
MARGIN_FRACTION=.45
MAX_HOLD=6
STOP_PCT=.006
TAKE_PCT=.012
RUIN=.83
SEED=20261117
EQUITY_EPS=1e-9

def digest(raw):return hashlib.sha256(raw).hexdigest()

def load(path):
    with zipfile.ZipFile(path) as z:
        manifest=json.loads(z.read("manifest.json"))
        market={}
        for name,info in sorted(manifest["records"].items()):
            raw=gzip.decompress(z.read(info["file"]))
            if digest(raw)!=info["sha256"]:raise ValueError("SOURCE_SHA_MISMATCH:"+name)
            rows=json.loads(raw)
            if len(rows)!=info["rows"]:raise ValueError("SOURCE_COUNT_MISMATCH:"+name)
            if not rows or any(str(x[-1])!="1" for x in rows):raise ValueError("UNCONFIRMED_CANDLE:"+name)
            if any(int(b[0])-int(a[0])!=BAR_MS for a,b in zip(rows,rows[1:])):raise ValueError("PRICE_GAP:"+name)
            if any(not 0<float(x[4]) for x in rows):raise ValueError("BAD_CANDLE:"+name)
            sym,kind=name.rsplit("-",1)
            market.setdefault(sym,{})[kind]=rows
        for sym,item in market.items():
            if set(item)!={"trade","mark"}:raise ValueError("MISSING_TRADE_MARK:"+sym)
            if [x[0] for x in item["trade"]]!=[x[0] for x in item["mark"]]:
                raise ValueError("TRADE_MARK_TIMESTAMPS:"+sym)
            sp=manifest["specs"][sym]
            if sp.get("state")!="live" or sp.get("ctType")!="linear" or sp.get("settleCcy")!="USDT":
                raise ValueError("UNSUPPORTED_INSTRUMENT:"+sym)
            if not isinstance(manifest["tiers"].get(sym),list) or not manifest["tiers"][sym]:
                raise ValueError("MISSING_CURRENT_TIER:"+sym)
        clocks=[[int(r[0]) for r in pair["trade"]] for pair in market.values()]
        if not all(clock==clocks[0] for clock in clocks):raise ValueError("MULTIMARKET_CLOCK_MISMATCH")
        return manifest,market,clocks[0]

def current_tier(manifest,sym):
    # Only first-tier position sizing is modeled. Tier boundaries are
    # snapshotted TODAY and NOT historic point-in-time guarantees.
    rows=manifest["tiers"][sym]
    tier=next((x for x in rows if str(x.get("tier"))=="1"),None)
    if tier is None:raise ValueError("MISSING_TIER1")
    return tier

def min_max_leverage(manifest,sym):
    s=manifest["specs"][sym];tier=current_tier(manifest,sym)
    return min(float(s["lever"]),float(tier["maxLever"]))

def contract_size(manifest,sym,capital,price,lever,case):
    """Lot-rounded, 1st tier, isolated margin, fee reserve, volume filter elsewhere."""
    spec=manifest["specs"][sym]
    if lever>min_max_leverage(manifest,sym)+1e-9:return 0.,0.,0.,"leverage_cap"
    contract=float(spec["ctVal"]);lot=Decimal(str(spec["lotSz"]))
    minimum=Decimal(str(spec["minSz"]))
    if min(contract,float(lot),float(minimum),price,capital)<=0:return 0.,0.,0.,"bad_inputs"
    # Cap equity at risk. Sizing by liquidation is an approximation.
    stop_risk=max(.002,STOP_PCT)
    cap=min(capital*MARGIN_FRACTION*lever,capital*.30/stop_risk)
    reserve=1+lever*(SCENARIOS[case]["fee"]+SCENARIOS[case]["slip"])*2
    cap=cap/reserve
    max_contracts=Decimal(str(cap/(price*contract)))
    rounded=(max_contracts/lot).to_integral_value(rounding=ROUND_FLOOR)*lot
    if rounded<minimum:return 0.,0.,0.,"min_contract"
    q=float(rounded);notional=q*contract*price
    margin=notional/lever
    fee=notional*(SCENARIOS[case]["fee"]+SCENARIOS[case]["slip"])
    if margin+fee>capital+EQUITY_EPS:return 0.,0.,0.,"margin"
    # Keep inside first tier even if exchange denominator is in contracts
    if float(current_tier(manifest,sym)["maxSz"])<q:return 0.,0.,0.,"tier1_contract_cap"
    return q,notional,margin,None

def calc_signal(market,sym,i,family):
    """Only *completed* bars 0..i-1; entry at OPEN i, no future candle access."""
    trade=market[sym]["trade"];mark=market[sym]["mark"]
    if i<50:return None
    h=trade[i-1]; prev=trade[i-2]
    r=math.log(float(h[4])/float(prev[4]))
    history=[math.log(float(trade[j][4])/float(trade[j-1][4])) for j in range(i-48,i-1)]
    sigma=max(.00025,statistics.pstdev(history))
    vol=float(h[7]);pastvol=[float(x[7]) for x in trade[i-13:i-1]]
    med=max(1.,statistics.median(pastvol))
    if family=="shock_continuation":
        if abs(r)<1.7*sigma or vol<1.6*med:return None
        side=1 if r>0 else -1
        strength=min(5.,abs(r)/sigma)*min(3.,vol/med)
    elif family=="shock_reversal":
        if abs(r)<2.2*sigma or vol<med:return None
        side=-1 if r>0 else 1
        strength=min(7.,abs(r)/sigma)
    else:
        basis=(float(h[4])-float(mark[i-1][4]))/float(mark[i-1][4])
        if abs(basis)<.0008:return None
        side=-1 if basis>0 else 1
        strength=min(8.,abs(basis)/.0008)
    return {"sym":sym,"side":side,"strength":round(strength,8),"sigma":sigma,
            "signal_ts":int(h[0]),"volume_usdt":vol,
            "family":family}

def choose(market,i,family):
    choices=[x for sym in sorted(market) if (x:=calc_signal(market,sym,i,family))]
    if not choices:return None
    return max(choices,key=lambda x:(x["strength"],x["sym"]))

def liquidation_price(entry,side,lever,mmr,extra=.001):
    # A deliberately simplified initial-isolated model. The real exchange
    # includes account mode, fee reserve, tier adjustments, and liquidation rules.
    cushion=1/lever-mmr-extra
    if cushion<=0:return entry
    return entry*(1-side*cushion)

def exit_trade(position,exit_raw,exit_index,reason,eq,case,funding,mark_price=None):
    c=SCENARIOS[case]; side=position["side"]
    fill=max(1e-12,exit_raw*(1-side*(c["slip"]+c["extra"])))
    entry=position["entry_fill"];q=position["q"];ct=position["ctVal"]
    notional_entry=position["notional"]
    gross=side*q*ct*(fill-entry)
    fee=notional_entry*c["fee"]+q*ct*fill*c["fee"]
    paid=0.;fund_missing=0
    for ts,rate in funding:
        if position["entry_ts"]<ts<=exit_index:
            paid+=side*notional_entry*rate
    if reason=="liquidated_proxy":
        # Conservatively wipe the isolated margin. Does NOT assert exact
        # historical OKX liquidation fill or bankruptcy price.
        net=-position["margin"]-notional_entry*c["fee"]-notional_entry*c["slip"]
    else:net=gross-fee-paid
    end=max(0.,eq+net)
    return {"sym":position["sym"],"family":position["family"],
            "signal_ts":position["signal_ts"],"entry_ts":position["entry_ts"],
            "exit_ts":exit_index,"side":side,"leverage":position["lever"],
            "q":q,"ctVal":ct,"entry_fill":entry,"exit_fill":fill,
            "entry_mark":position["entry_mark"],"exit_mark":mark_price,
            "notional":notional_entry,"margin":position["margin"],"gross":gross,
            "fee":fee,"funding_net_cost":paid,"net":net,"equity_before":eq,
            "equity_after":end,"reason":reason,"liquidation_proxy":reason=="liquidated_proxy",
            "liquidation_exact":False,"point_in_time_spec":False}

def adaptive_leverage_optimizer(manifest,sig,capital,entry_price,case,prior_net_per_notional):
    """Prequential Bayesian-style shrinkage of realized past net edge.
    No proof of edge => abstention. Optimize actual executable lot sizes,
    mark-price liquidation buffer, sigma, liquidity and worst-case cost.
    The calling policy may supply ONLY completed chronological past trades.
    """
    if len(prior_net_per_notional)<16:return None
    n=len(prior_net_per_notional)
    mean=statistics.mean(prior_net_per_notional)
    dev=max(.002,statistics.stdev(prior_net_per_notional))
    posterior_mean=mean*n/(n+10)   # 10 zero-return prior observations
    lower=posterior_mean-1.96*dev/math.sqrt(n)
    if lower<=0:return None
    sym=sig["sym"]; mmr=float(current_tier(manifest,sym)["mmr"])
    c=SCENARIOS[case];liquidity=sig["volume_usdt"]*.001
    # empirical sigma is 5-minute log-return; 30-minute shock proxy
    tail=4.0*sig["sigma"]*math.sqrt(MAX_HOLD)
    best=None
    for lev in LEVERAGES:
        if lev>min_max_leverage(manifest,sym):continue
        liqdist=1/lev-mmr-c["fee"]-c["extra"]-.001
        if liqdist<=max(.003,1.25*tail):continue
        q,notional,margin,error=contract_size(manifest,sym,capital,entry_price,lev,case)
        if error or notional>liquidity:continue
        # Model uncertainty, compounding risk and drawdown explicitly.
        conservative_gain=notional*lower
        shock_penalty=notional*min(.03,tail)*.06
        logscore=math.log(max(.001,1+(conservative_gain-shock_penalty)/capital))
        rank=logscore-.025*(margin/capital)**2-.001*(lev/100)**2
        if rank>0 and (best is None or rank>best[0]):best=(rank,lev)
    return best[1] if best else None

def simulation(manifest,market,clock,start_idx,lever,family,case="base",prior_evidence=None):
    """Exactly 72 contiguous 5m bars, one isolated position, forced flat at end."""
    eq=START;peak=eq;dd=0.;liqs=0;fills=[];reject=collections.Counter()
    end_idx=start_idx+BARS
    if end_idx>len(clock):raise ValueError("SHORT_WINDOW")
    funding={}
    for sym in market:
        recs=manifest.get("funding",{}).get(sym,[])
        funding[sym]=sorted((int(x["fundingTime"]),float(x["realizedRate"])) for x in recs)
    pos=None
    for i in range(start_idx,end_idx):
        ts=clock[i];last=i==end_idx-1
        # Decision at the opening of bar i, strictly based on bars <i.
        if pos is None and not last and eq>RUIN:
            sig=choose(market,i,family)
            if sig:
                sym=sig["sym"];bar=market[sym]["trade"][i];px=float(bar[1])
                actual_lev=lever
                if lever=="adaptive":
                    actual_lev=adaptive_leverage_optimizer(manifest,sig,eq,px,case,
                         [] if prior_evidence is None else prior_evidence)
                    if actual_lev is None:reject["no_positive_past_edge_or_safe_leverage"]+=1
                if actual_lev is None:q,notional,margin,reason=0.,0.,0.,"no_positive_past_edge_or_safe_leverage"
                else:q,notional,margin,reason=contract_size(manifest,sym,eq,px,actual_lev,case)
                if reason:reject[reason]+=1
                elif notional>float(market[sym]["trade"][i-1][7])*.001:
                    reject["quote_participation"]+=1
                else:
                    c=SCENARIOS[case];side=sig["side"]
                    entry=px*(1+side*(c["slip"]+c["extra"]))
                    mt=float(market[sym]["mark"][i][1])
                    mmr=float(current_tier(manifest,sym)["mmr"])
                    pos={**sig,"entry_ts":ts,"entry_i":i,"entry_fill":entry,
                         "entry_mark":mt,"q":q,"notional":q*float(manifest["specs"][sym]["ctVal"])*entry,
                         "margin":margin,"ctVal":float(manifest["specs"][sym]["ctVal"]),
                         "lever":actual_lev,"mmr":mmr,"stop":entry*(1-side*STOP_PCT),
                         "take":entry*(1+side*TAKE_PCT),
                         "liquidation_mark":liquidation_price(mt,side,actual_lev,mmr,
                                   c["fee"]+c["extra"]+.001)}
        if pos:
            sym=pos["sym"];side=pos["side"]
            bar=market[sym]["trade"][i];mb=market[sym]["mark"][i]
            high=float(mb[2]);low=float(mb[3])
            worse=low if side>0 else high
            adverse=eq+side*pos["q"]*pos["ctVal"]*(worse-pos["entry_fill"])-pos["notional"]*SCENARIOS[case]["fee"]
            dd=max(dd,100*(peak-max(0.,adverse))/max(peak,1e-9))
            lprice=pos["liquidation_mark"]
            liquidation=(low<=lprice if side>0 else high>=lprice)
            stop=(low<=pos["stop"] if side>0 else high>=pos["stop"])
            take=(high>=pos["take"] if side>0 else low<=pos["take"])
            if liquidation:reason="liquidated_proxy";xp=lprice
            elif stop:reason="stop";xp=pos["stop"]
            elif take:reason="take";xp=pos["take"]
            elif i-pos["entry_i"]+1>=MAX_HOLD or last:
                reason="forced_6h_close" if last else "timeout"
                xp=float(bar[4])
            else:continue
            out=exit_trade(pos,xp,ts+BAR_MS,reason,eq,case,funding[sym],float(mb[4]))
            eq=out["equity_after"];fills.append(out)
            liqs+=int(out["liquidation_proxy"])
            peak=max(peak,eq);dd=max(dd,100*(peak-eq)/max(peak,1e-9))
            pos=None
    if pos:raise AssertionError("OPEN_EXPOSURE_AT_SIX_HOURS")
    if fills and (fills[-1]["exit_ts"]>clock[end_idx-1]+BAR_MS):
        raise AssertionError("EXCEEDED_6H")
    return {"start_ts":clock[start_idx],"end_ts":clock[end_idx-1]+BAR_MS,
            "start_usdt":START,"final_usdt":eq,"return_pct":(eq/START-1)*100,
            "success":eq+1e-8>=TARGET,"ruined":eq<=RUIN,"liquidations":liqs,
            "trades":len(fills),"max_dd_pct":min(100.,dd),"ledger":fills,
            "rejections":dict(reject)}

def starts(clock,step=BARS):
    # Prespecified UTC times at 00:00, 06:00, 12:00, 18:00. The
    # first 48 bars are warmup. Never pick the best times after seeing PnL.
    return [i for i,t in enumerate(clock)
            if i>=50 and i+BARS<=len(clock)
            and t%(BARS*BAR_MS)==0
            and i%step>=0]

def stats(results):
    n=len(results)
    if not n:return {"n":0}
    rets=[x["return_pct"] for x in results]
    return {"n":n,"successes":sum(x["success"] for x in results),
            "success_pct":100*sum(x["success"] for x in results)/n,
            "loss_pct":100*sum(v<0 for v in rets)/n,
            "liquidation_window_pct":100*sum(x["liquidations"]>0 for x in results)/n,
            "liquidation_events":sum(x["liquidations"] for x in results),
            "ruin_window_pct":100*sum(x["ruined"] for x in results)/n,
            "mean_return_pct":statistics.mean(rets),
            "median_return_pct":statistics.median(rets),
            "worst_max_dd_pct":max(x["max_dd_pct"] for x in results),
            "max_return_pct":max(rets),"min_return_pct":min(rets),
            "trades":sum(x["trades"] for x in results),
            "feasible_trading_windows":sum(x["trades"]>0 for x in results),
            "final_equity_min":min(x["final_usdt"] for x in results)}

def wilson_upper(wins,n,z=1.96):
    if n==0:return None
    p=wins/n;d=1+z*z/n
    return (p+z*z/(2*n)+z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/d

def run_grid(manifest,market,clock):
    index=starts(clock)
    # All same windows every leverage / family. Leave 3-day initial prefix
    # as consumed calibration, late days DEVELOPMENT; no final blind claims.
    all_results={};score={}
    for fam in FAMILIES:
        for case in SCENARIOS:
            for lev in LEVERAGES:
                key=f"{fam}|{case}|{lev}x"
                vals=[simulation(manifest,market,clock,i,lev,fam,case) for i in index]
                all_results[key]=vals
                score[key]={**stats(vals),
                    "max_leverage_allowed_for_all_markets":all(lev<=min_max_leverage(manifest,s) for s in market),
                    "95pct_wilson_upper_success":wilson_upper(sum(v["success"] for v in vals),len(vals))}
    # An adaptive policy should only act after a qualifying POSITIVE edge
    # on development prefix. Train selector uses early 4 days only.
    cutoff=index[0]+16*BARS if len(index)>16 else index[-1]
    early=[k for k,i in enumerate(index) if i<cutoff]
    later=[k for k,i in enumerate(index) if i>=cutoff]
    qualified=[]
    for fam in FAMILIES:
        ref=[all_results[f"{fam}|stress|3x"][k]["return_pct"] for k in early]
        if len(ref)>=12 and statistics.mean(ref)>0 and statistics.median(ref)>0 and sum(x>0 for x in ref)>len(ref)*.55:
            qualified.append(fam)
    # Use only early development losses/mean for selection; no retuning
    # on late historical results; insufficient for independent future claim.
    adaptive=[]
    chosen=None
    if qualified:
        ranks=[]
        for fam in qualified:
            for lev in LEVERAGES:
                base=[all_results[f"{fam}|stress|{lev}x"][k] for k in early]
                mean=statistics.mean(x["return_pct"] for x in base)
                tail=sorted(x["return_pct"] for x in base)[max(0,int(len(base)*.1)-1)]
                risk=sum(x["liquidations"]>0 for x in base)/len(base)
                rank=mean+tail*.5-50*risk
                if mean>0 and tail>-35 and risk<.10:ranks.append((rank,fam,lev))
        if ranks:chosen=max(ranks)
    if chosen:
        _,fam,lev=chosen
        # Never select a future-sample-specific global best. The per-entry
        # adaptive policy uses only early closed trade outcomes, then expands
        # its evidence with later trades after each 6h window closes.
        evidence=[tr["net"]/tr["notional"]
                  for k in early for tr in all_results[f"{fam}|stress|3x"][k]["ledger"]]
        for k in later:
            result=simulation(manifest,market,clock,index[k],"adaptive",fam,"stress",evidence)
            adaptive.append(result)
            evidence.extend(t["net"]/t["notional"] for t in result["ledger"])
    else:
        adaptive=[{"start_ts":clock[index[k]],"end_ts":clock[index[k]+BARS-1]+BAR_MS,
                   "start_usdt":START,"final_usdt":START,"return_pct":0.,
                   "success":False,"ruined":False,"liquidations":0,
                   "trades":0,"max_dd_pct":0.,"ledger":[],"rejections":{"NO_PROVEN_POSITIVE_EDGE":1}} for k in later]
    return {
        "protocol":"PAPER_ONLY_6H_DEVELOPMENT_NO_NEW_INDEPENDENT_TEST",
        "capital":START,"goal":TARGET,"six_hour_bars":BARS,"bar_ms":BAR_MS,
        "windows_selection":"Nonoverlapping UTC aligned 00/06/12/18, 48 prior warmup bars, all outcomes retained",
        "market_sources":{k:{"sha256":v["sha256"],"rows":v["rows"],"gaps":v["gaps"]}
                          for k,v in manifest["records"].items()},
        "instrument_lever_caps":{s:min_max_leverage(manifest,s) for s in market},
        "windows_per_combination":len(index),
        "starts_utc_ms":[clock[i] for i in index],
        "initial_development_windows":len(early),"later_development_windows":len(later),
        "strategy_family_eligible_after_early_development":qualified,
        "adaptive_selection":None if chosen is None else {"rank":chosen[0],"family":chosen[1],"leverage":chosen[2]},
        "adaptive_later_development":stats(adaptive),
        "forward_oos_validated":False,"real_orders":0,
        "assumptions":{"stop_pct":STOP_PCT,"take_pct":TAKE_PCT,
          "max_hold_bars":MAX_HOLD,"margin_fraction":MARGIN_FRACTION,
          "capital_ruin":RUIN,"first_tier_only":True,
          "mark_liquidation":"CONSERVATIVE_PROXY_NOT_EXACT",
          "point_in_time_specs":False,
          "historical_spread_L2":False,
          "funding":"observed settlement if event available; gaps for periods outside recent 100 records NOT safe to equate with zero",
          "data_status":"All dates are already exposed 2026 DEVELOPMENT, never independent OOS"},
        "grid_scores":score,"grid_ledgers":all_results,
        "adaptive_later_ledger":adaptive}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",required=True);p.add_argument("--out",required=True)
    a=p.parse_args()
    m,market,clock=load(a.data)
    result=run_grid(m,market,clock)
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("CHECKED_WINDOWS",result["windows_per_combination"])
    print("ADAPTIVE",result["adaptive_later_development"])
    for k,v in result["grid_scores"].items():
        print(k,"wins",v["successes"],"trades",v["trades"],"mean",round(v["mean_return_pct"],4),"liqs",v["liquidation_events"])
if __name__=="__main__":main()


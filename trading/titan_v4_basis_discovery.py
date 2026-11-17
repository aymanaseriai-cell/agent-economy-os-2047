#!/usr/bin/env python3
"""V4 genuine mark/index/traded-price event discovery, not V1-3 TA repackaging.

Hypothesis-first 3-year 4H event test. Data: independent historical OKX
trade, mark and index candles from matching UTC timestamps. Funding-event
model deliberately UNAVAILABLE unless original point-in-time funding
records for 2023-2025 exist; no synthetic funding predictor.

Train 2023 only, develop 2024 only, use 2025 ONCE if and only if passed
development after-cost Holm monthly-block falsification. Previous
V1/V2/V3 2026 test calendar is NOT used to select V4.
"""
from __future__ import annotations
import math,random,statistics,calendar
from collections import defaultdict

SEED=2026111704
FAMILIES=(
    "mark_index_premium_reversion",
    "trade_mark_dislocation",
    "premium_impulse_exhaustion",
    "premium_duration_extreme",
    "mark_index_downside_tail",
)
SKIPPED={
    "historical_real_funding_shock":
        "Complete timestamp-aligned 2023-2025 realized funding NOT supplied by public recent-rate endpoint",
    "orderbook_flow_imbalance":
        "No historical point-in-time L2 bid/ask depth or trades tape archived",
    "news_response":
        "No timestamped independently sourced 2023-2025 news panel in this experiment",
}
LOG_COST_DEV=.004
ALPHA=.05
EARLIEST_YEAR=2023
DEV_YEAR=2024
FINAL_YEAR=2025
DAY_MS=86400000
BLOCK_MS=4*3600000

def quantile(values,p):
    if not values:raise ValueError("No training events for threshold")
    s=sorted(values)
    return s[min(len(s)-1,max(0,math.ceil(p*len(s))-1))]

def month_start(ts):
    from datetime import datetime,timezone
    d=datetime.fromtimestamp(ts/1000,timezone.utc)
    return d.year*100+d.month

def holm(p):
    order=sorted(p,key=lambda k:(p[k],k))
    running=0;out={}
    for i,k in enumerate(order):
        running=max(running,min(1,p[k]*(len(order)-i)))
        out[k]=running
    return out

def exact_month_signflip(weekly,base_seed=SEED):
    vals=list(weekly.values())
    if len(vals)<6:return 1.
    observed=sum(vals);n=len(vals)
    if n<=15:
        hits=0
        for mask in range(1<<n):
            total=sum(v*(1 if mask&(1<<j) else -1) for j,v in enumerate(vals))
            hits+=total>=observed-1e-14
        return hits/(1<<n)
    rng=random.Random(base_seed);hits=0;iters=8191
    for i in range(iters):
        if sum(v*(1 if rng.randrange(2) else -1) for v in vals)>=observed-1e-14:
            hits+=1
    return (hits+1)/(iters+1)

def features(trade,mark,index):
    """Each row open-time is public completed 4H bar, no future lookups."""
    if not trade or len(trade)!=len(mark) or len(mark)!=len(index):
        raise ValueError("Complete aligned triple-source history required")
    for t,m,k in zip(trade,mark,index):
        if t["ts"]!=m["ts"] or t["ts"]!=k["ts"]:
            raise ValueError("Cross-source mark-index-trade time mismatch")
    rows=[];dur=0;lastsign=0
    for i in range(49,len(trade)-1):
        T=trade[i];M=mark[i];I=index[i]
        tp=T["close"];mp=M["close"];ip=I["close"]
        if min(tp,mp,ip)<=0:continue
        prem=math.log(mp/ip)
        gap=math.log(tp/mp)
        old=math.log(mark[i-3]["close"]/index[i-3]["close"])
        sign=1 if prem>0 else -1 if prem<0 else 0
        dur=dur+1 if sign==lastsign else 1
        lastsign=sign
        # Separately observed extreme mark-price wick vs index wick,
        # normalized by contemporaneous index prices.
        downside=(M["low"]/I["low"]-M["high"]/I["high"])
        prev_turnover=statistics.mean(v["vol_quote"] for v in trade[i-24:i])
        q=math.log((T["vol_quote"]+1)/(prev_turnover+1))
        val={
          "mark_index_premium_reversion":-prem,
          "trade_mark_dislocation":-gap,
          "premium_impulse_exhaustion":-(prem-old),
          "premium_duration_extreme":-prem*math.log1p(min(40,dur)),
          "mark_index_downside_tail":-downside,
        }
        # OHLC directional label is future-bar OPEN to CLOSE, never used
        # as an input feature and never visible to the final selector.
        nxt=trade[i+1]
        y=math.log(nxt["close"]/nxt["open"])
        if not math.isfinite(y):raise ValueError("Bad future true OHLC")
        rows.append({"sym":T["symbol"],"ts":T["ts"],"i":i,
                     "next_ts":nxt["ts"],"open_next":nxt["open"],
                     "close_next":nxt["close"],
                     "mark_next_high":mark[i+1]["high"],
                     "mark_next_low":mark[i+1]["low"],
                     "mark_next_open":mark[i+1]["open"],
                     "mark_next_close":mark[i+1]["close"],
                     "trade_high_next":nxt["high"],
                     "trade_low_next":nxt["low"],
                     "quote_volume":T["vol_quote"],
                     "y":y,"prem":prem,"gap":gap,
                     "volume_z":q,"duration":dur,
                     "feature":{h:max(-3.,min(3.,v*100.))
                                for h,v in val.items()}})
    return rows

def fit_train_dev(rows):
    """Labels from 2025 cannot affect ANY fitted threshold or selection."""
    train=[x for x in rows if month_start(x["next_ts"])//100==EARLIEST_YEAR]
    dev=[x for x in rows if month_start(x["ts"])//100==DEV_YEAR
         and month_start(x["next_ts"])//100==DEV_YEAR]
    if len(train)<4000 or len(dev)<4000:
        raise ValueError("Insufficient 2023 training and 2024 development from original data")
    fitted={};p={};events={}
    for h in FAMILIES:
        usable=[x for x in train if abs(x["feature"][h])>1e-8]
        if len(usable)<50:
            fitted[h]={"beta":0.,"threshold":float("inf"),"n":len(usable)}
            p[h]=1.;events[h]=[]
            continue
        xs=[x["feature"][h] for x in usable]
        ys=[x["y"] for x in usable]
        # Freeze train-only shrinkage and activation threshold.
        beta=sum(a*b for a,b in zip(xs,ys))/(100+sum(x*x for x in xs))
        threshold=quantile([abs(x) for x in xs],.9)
        fitted[h]={"beta":beta,"threshold":threshold,"n":len(usable)}
        daily=set();chosen=[]
        for x in sorted(dev,key=lambda z:(z["ts"],z["sym"])):
            feat=x["feature"][h]
            if abs(feat)<max(1e-6,threshold) or beta==0:continue
            day=x["ts"]//DAY_MS;ident=(x["sym"],day)
            if ident in daily:continue
            daily.add(ident)
            direction=1 if beta*feat>0 else -1
            gross=direction*x["y"]
            pnl_proxy=gross-LOG_COST_DEV
            chosen.append({"sym":x["sym"],"ts":x["ts"],
                           "next_ts":x["next_ts"],"direction":direction,
                           "gross_log_return":gross,
                           "net_after_cost_proxy":pnl_proxy,
                           "year_month":month_start(x["ts"]),
                           "strength":abs(beta*feat)})
        events[h]=chosen
        months=defaultdict(float)
        for x in chosen:
            months[x["year_month"]]+=x["net_after_cost_proxy"]
        p[h]=exact_month_signflip(months)
    adjusted=holm(p)
    for h,vals in events.items():
        grouped=defaultdict(float)
        for x in vals:grouped[x["year_month"]]+=x["net_after_cost_proxy"]
        first=sum(z["net_after_cost_proxy"] for z in vals if z["year_month"]<=202406)
        second=sum(z["net_after_cost_proxy"] for z in vals if z["year_month"]>202406)
        fitted[h].update({
            "dev_events":len(vals),"dev_months":len(grouped),
            "unadjusted_p":p[h],"holm_p":adjusted[h],
            "dev_net_log_proxy":sum(x["net_after_cost_proxy"] for x in vals),
            "dev_direction_hit_pct":(
                100*sum(x["gross_log_return"]>0 for x in vals)/len(vals)
                if vals else None),
            "dev_first_six_months_net":first,
            "dev_second_six_months_net":second,
            "eligible":(
                len(vals)>=30 and len(grouped)>=8 and
                adjusted[h]<=ALPHA and first>0 and second>0 and
                sum(x["net_after_cost_proxy"] for x in vals)>0
            ),
        })
    qualified=[h for h in FAMILIES if fitted[h]["eligible"]]
    # One model can be chosen only on development, not 2025.
    candidate=(max(qualified,key=lambda h:fitted[h]["dev_net_log_proxy"])
               if qualified else None)
    return {"fitted":fitted,"selected_before_2025":candidate,
            "eligible":qualified,"train_year":2023,"dev_year":2024,
            "final_year":2025,"train_observations":len(train),
            "dev_observations":len(dev),
            "dev_event_ledger":events,
            "research_hypotheses_total":len(FAMILIES)+len(SKIPPED),
            "actually_tested":len(FAMILIES),
            "skipped_due_to_missing_data":SKIPPED,
            "multiple_test_method":"exact month sign-flip and Holm across five event families",
            "limits":[
                "Month sign-flip may not model cross-asset/serial dependence correctly",
                "The 2023/24 older test period predates prior 2026 studies, but is not new future time",
                "Matched causal experiments or real L2 are absent",
                "Historical funding was not manufactured from price premium",
            ]}

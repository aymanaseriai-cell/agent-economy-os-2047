#!/usr/bin/env python3
"""TITAN 2037: ten auditable, OFFLINE research and safety systems.

Never reads OKX credentials, uses private APIs, submits orders, or changes the
disabled live-trading workflow. This module is not a production trade executor.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import statistics

BAR_MS = 900000
FEATURE_NAMES = ("counterfactual","order_flow","shadow_exchange","regime_brain",
                 "alpha_discovery","liquidation_defense","smart_execution",
                 "thirty_second_router","self_healing","truth_engine")


def d(value, label="number"):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid "+label) from exc
    if not n.is_finite():
        raise ValueError("Nonfinite "+label)
    return n


def pos(value,label="number"):
    n=d(value,label)
    if n<=0: raise ValueError("Nonpositive "+label)
    return n


def confirmed_bars(bars, minimum=3):
    if not isinstance(bars,list) or len(bars)<minimum:
        raise ValueError("Insufficient confirmed candles")
    previous=None
    for row in bars:
        if not isinstance(row,dict) or type(row.get("ts")) is not int or row.get("confirmed") is not True:
            raise ValueError("Candle timestamp/confirmation missing")
        if previous is not None and row["ts"]-previous!=BAR_MS:
            raise ValueError("Missing or out-of-order 15m candle")
        previous=row["ts"]
        op,hi,lo,cl=(pos(row[k],k) for k in ("open","high","low","close"))
        if not lo<=min(op,cl)<=max(op,cl)<=hi:
            raise ValueError("Invalid OHLC candle geometry")
    return bars


# 1 — counterfactual / gap-through-stop adversarial simulator.
def counterfactual(side,entry,stop,target,gaps_bp=(25,100,300,800),fee_bp=10):
    if side not in ("LONG","SHORT"): raise ValueError("Invalid direction")
    e,s,t=(pos(x) for x in (entry,stop,target))
    if not (s<e<t if side=="LONG" else t<e<s):
        raise ValueError("Invalid stop/target")
    fee=d(fee_bp)/10000
    if fee<0: raise ValueError("Negative fee")
    direction=1 if side=="LONG" else -1
    results=[]
    for size in gaps_bp:
        gap=d(size)
        if not 0<gap<=10000: raise ValueError("Invalid gap")
        slipped=e*(1-direction*gap/10000)
        fill=min(s,slipped) if direction==1 else max(s,slipped)
        net=direction*(fill/e-1)-fee
        results.append({"adverse_gap_bp":int(gap),"modeled_net":float(net),
                        "exit":"WORSE_OF_STOP_OR_GAP"})
    if not results: raise ValueError("No counterfactual cases")
    return {"scenarios":results,"worst_net":min(x["modeled_net"] for x in results),
            "claim":"ADVERSARIAL_SCENARIOS_NOT_PROBABILITIES"}


# 2 — feed sequence integrity: no silent gaps or mutable partial state.
@dataclass
class SequencedBook:
    seq: int | None = None
    bids: dict = field(default_factory=dict)
    asks: dict = field(default_factory=dict)

    def apply(self,packet,now_ms=None):
        action=packet.get("action"); seq=packet.get("seqId");stamp=packet.get("ts")
        if action not in ("snapshot","update") or type(seq) is not int or seq<0 or type(stamp) is not int:
            raise ValueError("Unverifiable book packet")
        if now_ms is not None and not -1000<=now_ms-stamp<=10000:
            raise ValueError("Stale/future order book")
        if action=="update" and (self.seq is None or packet.get("prevSeqId")!=self.seq or seq<self.seq):
            raise ValueError("Sequence gap; resnapshot required")
        bids={} if action=="snapshot" else self.bids.copy()
        asks={} if action=="snapshot" else self.asks.copy()
        for key,book in (("bids",bids),("asks",asks)):
            updates=packet.get(key)
            if not isinstance(updates,list):raise ValueError("Missing side levels")
            for row in updates:
                if not isinstance(row,list) or len(row)<2:raise ValueError("Malformed level")
                price=pos(row[0]); qty=d(row[1])
                if qty<0:raise ValueError("Negative size")
                if qty==0:book.pop(price,None)
                else:book[price]=qty
        if not bids or not asks or max(bids)>=min(asks):
            raise ValueError("Crossed or empty book")
        self.seq,self.bids,self.asks=seq,bids,asks
        return self.snapshot()

    def snapshot(self):
        if self.seq is None:raise ValueError("No valid book")
        depth_bid=sum(self.bids.values(),Decimal(0))
        depth_ask=sum(self.asks.values(),Decimal(0))
        return {"sequence":self.seq,"bid":float(max(self.bids)),"ask":float(min(self.asks)),
                "depth_imbalance":float((depth_bid-depth_ask)/(depth_bid+depth_ask))}


def trade_flow(trades):
    if not isinstance(trades,list) or not trades:raise ValueError("No trades")
    buy=sell=Decimal(0)
    for row in trades:
        size=pos(row.get("sz"),"size")
        if row.get("side")=="buy":buy+=size
        elif row.get("side")=="sell":sell+=size
        else:raise ValueError("Unknown trade direction")
    return {"aggressor_imbalance":float((buy-sell)/(buy+sell)),"observations":len(trades)}


# 3 — next-closed-bar shadow exchange; never assumes favourable intrabar fill.
def shadow_exchange(signal,bars,fee_bp=10,slip_bp=3,funding_bp=1,max_bars=16):
    confirmed_bars(bars)
    when=signal.get("published_ms")
    side=signal.get("side")
    if type(when) is not int or side not in ("LONG","SHORT") or not 1<=max_bars<=96:
        raise ValueError("Invalid shadow parameters")
    start=((when+BAR_MS-1)//BAR_MS)*BAR_MS
    sample=[b for b in bars if b["ts"]>=start]
    if not sample or sample[0]["ts"]!=start:
        return {"status":"UNOBSERVED_NEXT_OPEN_NO_ORDER","orders":0}
    direction=1 if side=="LONG" else -1
    e=pos(sample[0]["open"]);s=pos(signal["stop"]);t=pos(signal["target"])
    fee=d(fee_bp)/10000; slip=d(slip_bp)/10000; fund=d(funding_bp)/10000
    if min(fee,slip,fund)<0:raise ValueError("Negative assumed cost")
    entry=e*(1+direction*slip)
    if not(s<entry<t if direction==1 else t<entry<s):
        return {"status":"GAP_INVALIDATED_ENTRY_NO_ORDER","orders":0}
    take=sample[:max_bars]
    if not take:raise ValueError("Empty horizon")
    exit_px=pos(take[-1]["close"]);outcome="horizon_close"
    for bar in take:
        low,high,opening=(d(bar[k]) for k in ("low","high","open"))
        if direction==1 and opening<=s or direction==-1 and opening>=s:
            exit_px=opening;outcome="stop_gap";break
        if (low<=s if direction==1 else high>=s):
            exit_px=s;outcome="stop_first";break
        if (high>=t if direction==1 else low<=t):
            exit_px=t;outcome="target";break
    net=direction*(exit_px*(1-direction*slip)/entry-1)-fee-fund
    return {"status":"SHADOW_ONLY","orders":0,"outcome":outcome,
            "modeled_net_fraction":float(net),"fee_slippage_funding_assumed":True}


# 4 — transparent market regime features, no future input.
def regime_brain(bars):
    confirmed_bars(bars,minimum=48)
    c=[float(pos(b["close"])) for b in bars[-48:]]
    steps=[math.log(v/u) for u,v in zip(c,c[1:])]
    vol=statistics.pstdev(steps)*math.sqrt(96)
    path=sum(abs(v-u) for u,v in zip(c,c[1:]))
    efficiency=abs(c[-1]-c[0])/max(path,1e-12)
    change=c[-1]/c[0]-1
    regime=("VOLATILE_UNCERTAIN" if vol>=.08 else
            "TREND_UP" if efficiency>=.35 and change>.008 else
            "TREND_DOWN" if efficiency>=.35 and change<-.008 else "RANGE")
    return {"regime":regime,"daily_realized_vol":vol,"path_efficiency":efficiency}


# 5 — purged chronological walk forward, not claimed independent CPCV.
def alpha_discovery(returns,train=40,test=10,embargo=4):
    if not isinstance(returns,dict) or len(returns)<2 or min(train,test)<5 or embargo<1:
        raise ValueError("Invalid strategy comparison")
    lengths={len(x) for x in returns.values()}
    if len(lengths)!=1:raise ValueError("Misaligned returns")
    n=lengths.pop()
    if n<train+embargo+test:raise ValueError("Insufficient OOS history")
    for k,x in returns.items():
        if not k or not isinstance(x,list) or any(not math.isfinite(float(y)) for y in x):
            raise ValueError("Nonfinite strategy returns")
    folds=[]
    for end in range(train,n-embargo-test+1,test):
        winner=max(sorted(returns),key=lambda k:statistics.mean(returns[k][end-train:end]))
        obs=returns[winner][end+embargo:end+embargo+test]
        folds.append({"selected_on_training":winner,"train_end":end,
                      "test_start":end+embargo,"mean_test_net_return":statistics.mean(obs)})
    return {"folds":folds,"mean_purged_oos_return":statistics.mean(f["mean_test_net_return"] for f in folds),
            "approved_for_live":False}


# 6 — aggregate shocks, NOT precise exchange liquidation modeling.
def liquidation_defense(positions,equity,shocks=(.01,.03,.05,.10),margin_cap=.50):
    eq=pos(equity)
    if not isinstance(positions,list) or not shocks:raise ValueError("No portfolio/shocks")
    notional=margin=Decimal(0)
    for p in positions:
        if p.get("side") not in ("LONG","SHORT"):raise ValueError("Bad side")
        n=pos(p["notional_usdt"]);leverage=pos(p["leverage"])
        if leverage>100:raise ValueError("Excessive leverage input")
        notional+=n;margin+=n/leverage
    outcome=[]
    for x in shocks:
        s=d(x)
        if not 0<s<=1:raise ValueError("Invalid shock")
        outcome.append(float(eq-notional*s))
    return {"margin_fraction":float(margin/eq),"gross_fraction":float(notional/eq),
            "stress_remaining_equity":outcome,
            "risk_gate":bool(margin/eq<=d(margin_cap) and all(v>0 for v in outcome)),
            "exact_liquidation":False}


# 7 — cost/depth aware PAPER plan, never an executable order payload.
def smart_execution(side,bid,ask,visible_depth_usdt,notional_usdt,gross_edge_bp,
                    fee_bp=10,slippage_bp=4):
    if side not in ("LONG","SHORT"):raise ValueError("Bad direction")
    b=pos(bid);a=pos(ask);depth=pos(visible_depth_usdt);n=pos(notional_usdt)
    if b>=a:raise ValueError("Crossed quote")
    spread=(a-b)/((a+b)/2)*10000
    cost=spread+d(fee_bp)+d(slippage_bp)
    if cost<0:raise ValueError("Negative cost")
    allow=spread<=15 and n<=depth/10 and d(gross_edge_bp)>cost
    return {"status":"PAPER_PLAN_ONLY" if allow else "COST_DEPTH_VETO",
            "orders":0,"estimated_cost_bp":float(cost),
            "paper_limit_reference":float(b if side=="LONG" else a) if allow else None}


# 8 — only verified exchange full-close history unlocks 30s re-entry.
def thirty_second_router(history,now_ms,history_verified=False,cooldown_ms=30000):
    if not history_verified or not isinstance(history,list) or not history:
        return {"eligible":False,"reason":"HISTORY_NOT_VERIFIED"}
    if type(now_ms) is not int or now_ms<=0 or cooldown_ms<30000:raise ValueError("Invalid timing")
    latest=None
    for row in history:
        ts=row.get("ts")
        if type(ts) is not int or ts<=0 or ts>now_ms:
            return {"eligible":False,"reason":"AMBIGUOUS_TIMESTAMP"}
        if str(row.get("type")) in ("2","3","6"):
            latest=max(latest or 0,ts)
    if latest is None:
        return {"eligible":True,"reason":"NO_CLOSE_IN_FULLY_VERIFIED_WINDOW"}
    remaining=max(0,latest+cooldown_ms-now_ms)
    return {"eligible":remaining==0,"remaining_ms":remaining,
            "reason":"COMPLETE" if remaining==0 else "COOLDOWN"}


# 9 — explicit circuit breaker, no private-POST retries.
def self_healing(operation,code,failures):
    if type(failures) is not int or failures<1:raise ValueError("Invalid failures")
    if operation!="PUBLIC_GET":
        return {"action":"HALT_RECONCILE_EXCHANGE","retry":False}
    if code not in ("50011","50013","50026","429","500","502","503","504","NETWORK"):
        return {"action":"HALT_UNKNOWN_ERROR","retry":False}
    if failures>3:
        return {"action":"OPEN_CIRCUIT","retry":False}
    return {"action":"RETRY_FRESH_PUBLIC_GET","retry":True,"delay_seconds":5*2**(failures-1)}


# 10 — signed realized PnL from imported records, NOT authenticated exchange truth.
def truth_engine(fills,funding):
    if not isinstance(fills,list) or not isinstance(funding,list):
        raise ValueError("Missing records")
    seen=set();pnl=fees=fin=Decimal(0)
    for row in fills:
        key=row.get("trade_id")
        if not isinstance(key,str) or not key or key in seen:
            raise ValueError("Duplicate or missing trade ID")
        seen.add(key)
        pnl+=d(row["realized_pnl_usdt"])
        fee=d(row["fee_usdt"])
        if fee>0:raise ValueError("Fee must be negative signed debit")
        fees+=fee
    seen.clear()
    for row in funding:
        key=row.get("event_id")
        if not isinstance(key,str) or not key or key in seen:
            raise ValueError("Duplicate or missing funding event ID")
        seen.add(key);fin+=d(row["amount_usdt"])
    return {"realized_before_fees":str(pnl),"signed_fees":str(fees),
            "signed_funding":str(fin),"net_realized_from_import":str(pnl+fees+fin),
            "record_count":len(fills)+len(funding),
            "verified_against_private_OKX":False}


def bundle(evidence):
    """Run supplied offline experiments; mark missing data rather than fabricate."""
    if not isinstance(evidence,dict):raise ValueError("Evidence must be an object")
    features={name:{"status":"NEEDS_DATA_NOT_CONNECTED"} for name in FEATURE_NAMES}
    calls={
      "counterfactual":(counterfactual,"counterfactual"),
      "regime_brain":(regime_brain,"bars"),
      "alpha_discovery":(alpha_discovery,"alpha_returns"),
    }
    for name,(fn,key) in calls.items():
        if key in evidence:
            args=evidence[key]
            value=fn(**args) if isinstance(args,dict) and name=="counterfactual" else fn(args)
            features[name]={"status":"EVALUATED","result":value}
    if "book_packets" in evidence:
        book=SequencedBook()
        for packet in evidence["book_packets"]:
            book.apply(packet,now_ms=evidence.get("book_now_ms"))
        info=book.snapshot()
        if "trades" in evidence:info.update(trade_flow(evidence["trades"]))
        features["order_flow"]={"status":"EVALUATED","result":info}
    pairs={
      "shadow_exchange":("shadow_signal","forward_bars"),
      "liquidation_defense":("positions","equity_usdt"),
      "truth_engine":("fills","funding")
    }
    funcs={"shadow_exchange":shadow_exchange,"liquidation_defense":liquidation_defense,
           "truth_engine":truth_engine}
    for name,keys in pairs.items():
        if all(k in evidence for k in keys):
            features[name]={"status":"EVALUATED","result":funcs[name](*(evidence[k] for k in keys))}
    for name,key,fn in (("smart_execution","route",smart_execution),
                        ("thirty_second_router","cooldown",thirty_second_router),
                        ("self_healing","recovery",self_healing)):
        if key in evidence:
            features[name]={"status":"EVALUATED","result":fn(**evidence[key])}
    return {"generated_utc":datetime.now(timezone.utc).isoformat(),
            "mode":"TITAN2037_OFFLINE_RESEARCH_NO_ORDERS",
            "live_trading_reenabled":False,"orders":0,
            "features":features,"caveat":"No forecast, no live broker control, no proof of profits"}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",required=True,help="JSON file of recorded offline evidence")
    p.add_argument("--out",default="reports/titan2037_offline.json")
    args=p.parse_args(argv)
    record=json.loads(Path(args.evidence).read_text(encoding="utf8"))
    outcome=bundle(record)
    target=Path(args.out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(outcome,indent=2,allow_nan=False)+"\n",encoding="utf8")
    print("TITAN 2037 OFFLINE SYSTEMS: evaluated=",
          sum(v["status"]=="EVALUATED" for v in outcome["features"].values()),
          "orders=0")
    return 0


if __name__=="__main__":
    raise SystemExit(main())

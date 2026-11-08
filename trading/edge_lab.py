#!/usr/bin/env python3
"""Read-only OKX 15m historical edge lab. NEVER access private API or place orders.

Tests two locked, candle-only signal hypotheses with next-bar execution and
conservative stops. It does NOT reconstruct the live 6-agent orderbook/AI strategy.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://www.okx.com"
BAR_MS = 900_000
DEFAULT_SYMBOLS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP",
                   "SOL-USDT-SWAP", "XRP-USDT-SWAP",
                   "DOGE-USDT-SWAP", "SUI-USDT-SWAP")
# Decimal percentages of traded notional (not leverage-multiplied percentages)
TAKER_FEE = .0005
BASE_SLIPPAGE = .0003
STRESS_SLIPPAGE = .001
STRESS_FEE = .0008
FUNDING_PER_8H = .0001  # Explicit conservative assumption, NOT exchange history.
START_EQUITY = 1000.0
MAX_NOTIONAL_EQUITY = .20  # Guarded size; 20% of equity notional max.
RISK_EQUITY = .0025       # Max 0.25% of equity planned stop risk.
TRAIN_FRACTION = .60
MAX_HOLD_BARS = 24


def candles_from_api(rows: list) -> list[dict]:
    result=[]
    for row in rows:
        if len(row)<9 or str(row[8])!="1":
            continue
        try:
            ts=int(row[0])
            op,hi,lo,cl=(float(v) for v in row[1:5])
            if not (0<lo<=op<=hi and lo<=cl<=hi):
                continue
            if not all(map(math.isfinite,(op,hi,lo,cl))):
                continue
            result.append({"ts":ts,"open":op,"high":hi,"low":lo,"close":cl})
        except (ValueError,TypeError,OverflowError):
            continue
    return result


def get_public(path: str, params: dict, retries: int = 3) -> list:
    if path != "/api/v5/market/history-candles":
        raise ValueError("Historical public-candle endpoint only")
    url=API+path+"?"+urlencode(params)
    for attempt in range(retries):
        try:
            request=Request(url,headers={"User-Agent":"Independent-OOS-Edge-Lab/1.0",
                                         "Accept":"application/json"})
            with urlopen(request,timeout=18) as response:
                obj=json.load(response)
            if obj.get("code")!="0" or not isinstance(obj.get("data"),list):
                raise RuntimeError("OKX history API rejected response")
            return obj["data"]
        except (TimeoutError,OSError,RuntimeError,ValueError) as exc:
            if attempt == retries-1:
                raise RuntimeError("Public candle history unavailable") from exc
            time.sleep(.5*(attempt+1))
    raise RuntimeError("History unavailable")


def fetch_history(symbol: str, days: int, *, now_ms: int | None = None,
                  get=get_public, pause=time.sleep, max_pages: int=450) -> list[dict]:
    if not symbol.endswith("-USDT-SWAP") or not 3<=days<=365:
        raise ValueError("Invalid symbol or days")
    now_ms=int(time.time()*1000) if now_ms is None else now_ms
    cutoff=now_ms-days*86_400_000
    by_time={}
    before_oldest=None
    for page_no in range(max_pages):
        query={"instId":symbol,"bar":"15m","limit":"100"}
        if before_oldest is not None:
            query["after"]=str(before_oldest)
        rows=get("/api/v5/market/history-candles",query)
        if not rows:
            break
        parsed=candles_from_api(rows)
        if not parsed:
            raise ValueError("History page missing completed valid candles")
        oldest=min(z["ts"] for z in parsed)
        if before_oldest is not None and oldest>=before_oldest:
            raise ValueError("Pagination cursor stalled")
        for row in parsed:
            if cutoff <= row["ts"] and row["ts"]+BAR_MS<=now_ms:
                by_time[row["ts"]]=row
        if oldest < cutoff or len(rows)<100:
            break
        before_oldest=oldest
        pause(.10)
    else:
        raise ValueError("History pagination exceeded safe page limit")
    candles=sorted(by_time.values(),key=lambda x:x["ts"])
    if len(candles)<300:
        raise ValueError("Insufficient history")
    # Reject an incomplete series rather than silently treating missing bars as
    # contiguous; this is critical for chronological event simulation.
    if any(b["ts"]-a["ts"]!=BAR_MS for a,b in zip(candles,candles[1:])):
        raise ValueError("Missing 15-minute bars: refuse misleading backtest")
    return candles


def ema_series(prices: list[float], span: int) -> list[float]:
    if not prices or span<1:
        raise ValueError("Invalid EMA")
    alpha=2/(span+1)
    out=[prices[0]]
    for x in prices[1:]:
        out.append(out[-1]+alpha*(x-out[-1]))
    return out


def rsi_simple(prices: list[float], i: int, span: int=14) -> float:
    if i<span:
        raise ValueError("Insufficient closes")
    diffs=(prices[k]-prices[k-1] for k in range(i-span+1,i+1))
    changes=list(diffs)
    up=sum(max(x,0) for x in changes)/span
    down=sum(max(-x,0) for x in changes)/span
    if not up and not down:return 50
    if down==0:return 100
    return 100-100/(1+up/down)


def atr_simple(bars: list[dict],i: int,span: int=14) -> float:
    if i<span:
        raise ValueError("Insufficient candles")
    tr=[]
    for k in range(i-span+1,i+1):
        cur=bars[k];prev=bars[k-1]["close"]
        tr.append(max(cur["high"]-cur["low"],abs(cur["high"]-prev),
                      abs(cur["low"]-prev)))
    return sum(tr)/span


def signals(bars: list[dict],strategy: str) -> list[tuple[int,int,float]]:
    closes=[b["close"] for b in bars]
    fast,slow=ema_series(closes,9),ema_series(closes,21)
    result=[]
    warmup=192 if strategy=="breakout" else 50
    if strategy not in ("ema_rsi","breakout"):
        raise ValueError("Unknown locked strategy")
    for i in range(warmup,len(bars)-1):
        direction=0
        if strategy=="ema_rsi":
            r=rsi_simple(closes,i)
            if fast[i]>slow[i] and closes[i]>fast[i] and 53<=r<=70:
                direction=1
            elif fast[i]<slow[i] and closes[i]<fast[i] and 30<=r<=47:
                direction=-1
        else:
            high=max(b["high"] for b in bars[i-48:i])
            low=min(b["low"] for b in bars[i-48:i])
            if closes[i]>high and fast[i]>slow[i]:direction=1
            elif closes[i]<low and fast[i]<slow[i]:direction=-1
        if direction:
            result.append((i,direction,atr_simple(bars,i)))
    return result


def trade_simulation(bars: list[dict],signal_rows: list[tuple[int,int,float]],
                     *, start_index: int, end_index: int,
                     fee: float=TAKER_FEE, slip: float=BASE_SLIPPAGE,
                     funding: float=FUNDING_PER_8H) -> dict:
    """Signal at completed bar i; enter OPEN(i+1), fees both sides.

    If both stop and target touch in one candle, fill at stop.
    A stop-gap fills at candle open, never at the original stop.
    """
    if not(0<=start_index<end_index<=len(bars)) or min(fee,slip,funding)<0:
        raise ValueError("Invalid simulation settings")
    equity=START_EQUITY
    equity_curve=[equity]
    results=[]
    next_available=start_index
    for i,side,atr in signal_rows:
        j=i+1
        if i<start_index or j<start_index or j>=end_index or j<next_available or atr<=0:
            continue
        entry_open=bars[j]["open"]
        entry=entry_open*(1+side*slip)
        dist=1.5*atr
        if dist<=0 or dist/entry>.10:
            continue
        stop=entry-side*dist
        target=entry+side*2.5*atr
        if min(stop,target)<=0:continue
        stop_frac=dist/entry
        notional=min(equity*MAX_NOTIONAL_EQUITY,
                     equity*RISK_EQUITY/stop_frac,
                     equity*10)
        if notional<=0:continue
        exit_index=min(j+MAX_HOLD_BARS-1,end_index-1)
        fill=bars[exit_index]["close"]
        outcome="timeout"
        for k in range(j,exit_index+1):
            bar=bars[k]
            if side==1:
                if bar["open"]<=stop:
                    fill=bar["open"];outcome="stop_gap";exit_index=k;break
                if bar["low"]<=stop:
                    fill=stop;outcome="stop";exit_index=k;break
                if bar["high"]>=target:
                    fill=target;outcome="target";exit_index=k;break
            else:
                if bar["open"]>=stop:
                    fill=bar["open"];outcome="stop_gap";exit_index=k;break
                if bar["high"]>=stop:
                    fill=stop;outcome="stop";exit_index=k;break
                if bar["low"]<=target:
                    fill=target;outcome="target";exit_index=k;break
        exit_fill=fill*(1-side*slip)
        gross=side*(exit_fill-entry)/entry*notional
        fees=(fee*notional)+(fee*notional*exit_fill/entry)
        # Explicit model assumption; not actual OKX funding timestamps.
        funding_cost=notional*funding*(exit_index-j+1)/32
        net=gross-fees-funding_cost
        equity=max(0,equity+net)
        next_available=exit_index+1
        equity_curve.append(equity)
        results.append({"signal_ts":bars[i]["ts"],"entry_ts":bars[j]["ts"],
                        "exit_ts":bars[exit_index]["ts"],"direction":side,
                        "entry":round(entry,8),"exit":round(exit_fill,8),
                        "notional":round(notional,6),"gross_usd":round(gross,6),
                        "fees_usd":round(fees,6),"funding_model_usd":round(funding_cost,6),
                        "net_usd":round(net,6),"outcome":outcome,"bars_held":exit_index-j+1})
        if equity<=0:break
    positives=[x["net_usd"] for x in results if x["net_usd"]>0]
    negatives=[x["net_usd"] for x in results if x["net_usd"]<0]
    peak=START_EQUITY;dd=0
    for amount in equity_curve:
        peak=max(peak,amount)
        dd=max(dd,(peak-amount)/peak)
    return {"trades":len(results),
            "win_rate_pct":round(100*len(positives)/len(results),2) if results else None,
            "return_pct":round(100*(equity/START_EQUITY-1),4),
            "max_drawdown_pct":round(100*dd,4),
            "profit_factor":round(sum(positives)/abs(sum(negatives)),4) if negatives else None,
            "gross_usd":round(sum(x["gross_usd"] for x in results),4),
            "fees_usd":round(sum(x["fees_usd"] for x in results),4),
            "funding_model_usd":round(sum(x["funding_model_usd"] for x in results),4),
            "net_usd":round(sum(x["net_usd"] for x in results),4),
            "ending_equity_usd":round(equity,4),
            "trade_log":results}


def evaluate(symbols: dict[str,list[dict]], *, days: int, timestamp: str) -> dict:
    report={"generated_utc":timestamp,"source":"OKX public /api/v5/market/history-candles",
            "mode":"OFFLINE_RESEARCH_NO_ORDERS","days_requested":days,
            "strategies":["ema_rsi","breakout"],"train_split":.6,
            "execution_assumptions":{
              "enter":"next_15m_candle_open","exit":"stop_then_target_if_ambiguous",
              "fees_taker_per_side":TAKER_FEE,"slippage_per_side":BASE_SLIPPAGE,
              "funding_model_per_8h":FUNDING_PER_8H,
              "initial_equity_per_symbol_usd":START_EQUITY,
              "notional_cap_fraction_of_equity":MAX_NOTIONAL_EQUITY,
              "planned_stop_risk_fraction":RISK_EQUITY,
              "max_holding_bars":MAX_HOLD_BARS},
            "limitations":["Not the 6-agent live bot: historical L2, flows and NVIDIA snapshots are absent",
                           "Fees are assumptions, not user account maker/taker tier",
                           "Funding is an explicit cost estimate, not OKX funding history",
                           "OHLC cannot tell true intrabar sequence; stop wins ambiguities",
                           "No true orderbook execution, liquidations, venue outage, or latency model",
                           "Do not choose strategy from holdout then claim unbiased out-of-sample",
                           "Multiple symbols are evaluated separately, not a runnable portfolio"],
            "symbols":{}}
    for symbol,bars in symbols.items():
        split=int(len(bars)*TRAIN_FRACTION)
        entry={"candles":len(bars),
               "first_utc":datetime.fromtimestamp(bars[0]["ts"]/1000,timezone.utc).isoformat(),
               "last_utc":datetime.fromtimestamp(bars[-1]["ts"]/1000,timezone.utc).isoformat(),
               "holdout_start_utc":datetime.fromtimestamp(bars[split]["ts"]/1000,timezone.utc).isoformat(),
               "holdout_price_change_pct":round((bars[-1]["close"]/bars[split]["close"]-1)*100,3),
               "strategies":{}}
        for name in report["strategies"]:
            choices=signals(bars,name)
            train=trade_simulation(bars,choices,start_index=192,end_index=split)
            holdout=trade_simulation(bars,choices,start_index=split,end_index=len(bars))
            stressed=trade_simulation(bars,choices,start_index=split,end_index=len(bars),
                                      fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
            frictionless=trade_simulation(bars,choices,start_index=split,end_index=len(bars),
                                          fee=0,slip=0,funding=0)
            # Keep report small; raw trade log is reproducible by script but
            # not part of the published artifact.
            for item in (train,holdout,stressed,frictionless):
                item.pop("trade_log",None)
            entry["strategies"][name]={"train":train,"holdout":holdout,
                                       "holdout_stress":stressed,
                                       "holdout_frictionless_diagnostic":frictionless}
        report["symbols"][symbol]=entry
    return report


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days",type=int,default=45)
    p.add_argument("--offline-dir",default=None,
                   help="Read frozen local .candles.json.gz snapshots; no network calls")
    p.add_argument("--symbols",nargs="+",default=list(DEFAULT_SYMBOLS))
    p.add_argument("--out",default="reports/okx_edge_lab.json")
    a=p.parse_args()
    if not 3<=a.days<=365 or len(a.symbols)>12 or not a.symbols:
        p.error("Invalid days or symbols")
    data={}
    for symbol in a.symbols:
        if a.offline_dir:
            source=Path(a.offline_dir)/(symbol+".candles.json.gz")
            with gzip.open(source,"rt",encoding="utf-8") as f:
                bars=json.load(f)
            if not isinstance(bars,list) or len(bars)<300:
                raise ValueError("Offline snapshot missing complete history")
            if any(b["ts"]-a0["ts"]!=BAR_MS for a0,b in zip(bars,bars[1:])):
                raise ValueError("Offline snapshot contains missing 15m bars")
        else:
            print("Fetching public history:",symbol,flush=True)
            bars=fetch_history(symbol,a.days)
        data[symbol]=bars
        print("  bars:",len(bars),flush=True)
    report=evaluate(data,days=a.days,
                    timestamp=datetime.now(timezone.utc).isoformat())
    report["data_mode"]="OFFLINE_FROZEN_SNAPSHOT" if a.offline_dir else "FRESH_PUBLIC_OKX_API"
    report["data_sha256"]={
        symbol:hashlib.sha256(json.dumps(bars,separators=(",",":")).encode()).hexdigest()
        for symbol,bars in data.items()}
    pth=Path(a.out);pth.parent.mkdir(parents=True,exist_ok=True)
    pth.write_text(json.dumps(report,indent=2)+"\n")
    for symbol,entry in report["symbols"].items():
        for strategy,out in entry["strategies"].items():
            hold=out["holdout"]
            print(symbol,strategy,"HOLDOUT",hold["return_pct"],"%",hold["trades"],"trades",
                  "STRESS",out["holdout_stress"]["return_pct"],"%",flush=True)
    print("Research saved:",pth)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

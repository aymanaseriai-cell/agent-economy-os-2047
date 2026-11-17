#!/usr/bin/env python3
"""OMEGA 25M public OKX original-data collection and causal 4h features.

History: /api/v5/market/history-candles, full 15m OHLCV with
volCcyQuote field, no incomplete bars. Per-instrument raw API arrays
are SHA256-archived for exact reproducibility. Funding is a separate
public actual realizedRate feed, limited to about 3 months.
"""
from __future__ import annotations
import hashlib,json,math,time
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from trading.edge_lab import BAR_MS
from trading import titan_omega_25m_families as fam

STUDY="OMEGA-SINGULARITY-25M-FROZEN-COHORT-20261117-A"
DAYS=180
MIN_BARS=17100
MARKETS=6
BLOCK=16
WARM=72
PRIOR=set(("BTC ETH SOL XRP DOGE HYPE ZEC BNB ATOM ONDO WLD LTC AVAX OP "
"CHZ WIF ZK MASK BLUR MINA ETHFI AR YGG LPT ZIL STX BONK PENGU IMX "
"DYDX JTO XTZ AXS CFX NMR COMP IOST UMA LDO CELO FIL SUSHI GALA "
"ZETA CRV ZEN ACH GRT RENDER ARB BCH ETC JUP NEAR").split())
POOL=set(("1INCH AEVO ALT ASTR BAL BAND BAT CKB COTI CTSI DASH DCR "
"DENT ENJ FET FLOW FXS GMX IOTA KAS KAVA KNC LSK QTUM RLC RUNE "
"SNX SSV STORJ THETA TWT VET XEC YFI AUDIO LRC GLM CVC NKN OGN "
"RSR TRB API3 ARKM AKT XAI MANTA ICX ONG HFT TLM BICO HIGH SXP "
"CHR SKL STG NTRN PHA NFP").split())-PRIOR

def public(path,params):
    url="https://www.okx.com"+path+"?"+urlencode(params)
    for attempt in range(4):
        try:
            with urlopen(Request(url,headers={"User-Agent":"OMEGA-SINGULARITY-PUBLIC-RESEARCH"}),
                         timeout=25) as h:payload=json.load(h)
            if payload.get("code")!="0" or not isinstance(payload.get("data"),list):
                raise ValueError("OKX public JSON response invalid")
            return payload["data"]
        except (ValueError,OSError,TimeoutError) as err:
            if attempt==3:raise RuntimeError("OKX real historical data unavailable") from err
            time.sleep(.55*(attempt+1))
    raise RuntimeError("Network source not available")

def catalogue(now_ms):
    raw=public("/api/v5/public/instruments",{"instType":"SWAP"})
    cutoff=now_ms-210*86400000
    valid=[]
    for s in raw:
        name=s.get("instId","")
        if not name.endswith("-USDT-SWAP"):continue
        coin=name[:-10]
        if (coin not in POOL or s.get("state")!="live" or
            s.get("ctType")!="linear" or s.get("ctValCcy")!=coin):continue
        try:
            if int(s["listTime"])>cutoff:continue
            vals=[float(s[k]) for k in ("ctVal","lotSz","minSz")]
            if any(not math.isfinite(x) or x<=0 for x in vals):continue
        except (KeyError,ValueError,TypeError):continue
        valid.append(s)
    valid.sort(key=lambda z:hashlib.sha256(
        (STUDY+"|"+z["instId"]).encode()).hexdigest())
    if len(valid)<MARKETS:raise ValueError("Fewer than six precommitted instruments")
    return valid[:MARKETS],len(valid)

def decode(row):
    if len(row)<9 or str(row[8])!="1":return None
    try:
        ts=int(row[0]);o,h,l,c=[float(x) for x in row[1:5]]
        vol=float(row[7])
        if (not all(math.isfinite(z) for z in (o,h,l,c,vol)) or
            not 0<l<=min(o,c)<=max(o,c)<=h or vol<0):
            raise ValueError("invalid real market OHLCV")
    except (TypeError,ValueError,OverflowError) as e:
        raise ValueError("Source historical candle malformed") from e
    return {"ts":ts,"open":o,"high":h,"low":l,"close":c,
            "vol_quote":vol}

def fetch_candles(sym,now_ms):
    cutoff=now_ms-DAYS*86400000
    raw_by_ts={};older=None
    for page in range(280):
        args={"instId":sym,"bar":"15m","limit":"100"}
        if older is not None:args["after"]=str(older)
        rows=public("/api/v5/market/history-candles",args)
        if not rows:break
        parsed=[(r,decode(r)) for r in rows]
        kept=[(r,x) for r,x in parsed if x is not None]
        if not kept:raise ValueError("No confirmed historical candles")
        earliest=min(x["ts"] for _,x in kept)
        if older is not None and earliest>=older:
            raise ValueError("Public OKX pagination stalled")
        for raw,bar in kept:
            if cutoff<=bar["ts"] and bar["ts"]+BAR_MS<=now_ms:
                raw_by_ts[bar["ts"]]=raw
        if earliest<cutoff or len(rows)<100:break
        older=earliest
        time.sleep(.08)
    else:raise ValueError("More than 280 historical pages needed")
    ordered=[raw_by_ts[t] for t in sorted(raw_by_ts)]
    bars=[decode(row) for row in ordered]
    if len(bars)<MIN_BARS:raise ValueError("Incomplete true 180d OHLCV history")
    if any(y["ts"]-x["ts"]!=BAR_MS for x,y in zip(bars,bars[1:])):
        raise ValueError("Missing completed 15m historical bars")
    # Returns byte-identical public candle fields (strings) in chronological order.
    return bars,ordered

def fetch_funding(sym,now_ms):
    cutoff=now_ms-95*86400000
    items={};older=None
    for page in range(14):
        args={"instId":sym,"limit":"400"}
        if older is not None:args["after"]=str(older)
        raw=public("/api/v5/public/funding-rate-history",args)
        if not raw:break
        first=min(int(x["fundingTime"]) for x in raw)
        if older is not None and first>=older:break
        for row in raw:
            try:
                t=int(row["fundingTime"]);v=float(row["realizedRate"])
                if t>=cutoff and math.isfinite(v):items[t]=[t,v,row]
            except (KeyError,TypeError,ValueError):continue
        if first<cutoff or len(raw)<400:break
        older=first
        time.sleep(.2)
    return [items[t] for t in sorted(items)]

def aggregate(bars):
    out=[];batch=[]
    for i,b in enumerate(bars):
        if b["ts"]%(BAR_MS*BLOCK)==0:batch=[]
        batch.append((i,b))
        if len(batch)==BLOCK and batch[0][1]["ts"]%(BAR_MS*BLOCK)==0:
            out.append({"idx":i,"ts":batch[0][1]["ts"],
                        "open":batch[0][1]["open"],
                        "high":max(z["high"] for _,z in batch),
                        "low":min(z["low"] for _,z in batch),
                        "close":batch[-1][1]["close"],
                        "quote":sum(z["vol_quote"] for _,z in batch)})
            batch=[]
    return out

def ema(seq,n):
    a=2/(n+1);out=[seq[0]]
    for v in seq[1:]:out.append(a*v+(1-a)*out[-1])
    return out

def atr(h,t,n):
    return sum(max(h[k]["high"]-h[k]["low"],
                   abs(h[k]["high"]-h[k-1]["close"]),
                   abs(h[k]["low"]-h[k-1]["close"]))
               for k in range(t-n+1,t+1))/n

def causal_feature(h,t,e8,e30,breadth):
    if t<WARM or t>=len(h):raise ValueError("Causal bar not fully known")
    p=h[t]["close"];a=atr(h,t,14);longa=atr(h,t,42)
    if min(p,a,longa)<=0:raise ValueError("Nonpositive price and volatility")
    norm=max(a/p,1e-8)
    mom=math.log(p/h[t-3]["close"])/(norm*math.sqrt(3))
    longmom=math.log(p/h[t-18]["close"])/(norm*math.sqrt(18))
    trend=(e8[t]-e30[t])/a
    comp=math.log(a/longa)*2
    q=math.log((h[t]["quote"]+1)/(1+sum(x["quote"] for x in h[t-24:t])/24))
    pressure=sum((h[k]["close"]-h[k]["open"])/max(
        h[k]["high"]-h[k]["low"],1e-8) for k in range(t-7,t+1))/8*3
    recent_hi=max(x["high"] for x in h[t-24:t])
    recent_lo=min(x["low"] for x in h[t-24:t])
    br=(p-recent_hi)/a if p>recent_hi else (p-recent_lo)/a if p<recent_lo else 0
    up=sum(1 if h[k]["close"]>h[k-1]["close"] else -1
           for k in range(t-13,t+1))/14
    dist=(p-e30[t])/a
    return tuple(max(-3.,min(3.,v)) for v in
                 (mom,longmom,trend,comp,q,pressure,br,breadth,up,dist)),a

def signal_panel(markets,fit_end):
    series={s:aggregate(v) for s,v in markets.items()}
    n=min(len(v) for v in series.values())
    axis=[x["ts"] for x in next(iter(series.values()))[:n]]
    if any([x["ts"] for x in b[:n]]!=axis for b in series.values()):
        raise ValueError("Incomplete aligned six-market breadth")
    fast={s:ema([x["close"] for x in b],8) for s,b in series.items()}
    slow={s:ema([x["close"] for x in b],30) for s,b in series.items()}
    observations=[];train=[]
    for t in range(WARM,n-1):
        breadth=sum(1 if h[t]["close"]>h[t-6]["close"] else -1
                    for h in series.values())/MARKETS
        for sym,h in series.items():
            f,a=causal_feature(h,t,fast[sym],slow[sym],breadth)
            if not .002<a/h[t]["close"]<.15:continue
            idx=h[t]["idx"]
            observations.append((sym,idx,f,a))
            # Purge two full 4h bars before end-of-fitting boundary.
            if h[t+1]["idx"]+BLOCK*2<fit_end:
                train.append((f,math.log(h[t+1]["close"]/h[t]["close"]),
                              sym,t))
    params=fam.fit(train)
    out={s:{p:[] for p in fam.ACTIVE} for s in markets}
    for sym,idx,f,a in observations:
        scores=fam.score(f,sym,params)
        for p,z in scores.items():
            if abs(z)>=.39:
                out[sym][p].append((idx,1 if z>0 else -1,a,
                                    round(min(1,abs(z)),7)))
    return out,params,{"train_samples":len(train),"hour_panels":n}

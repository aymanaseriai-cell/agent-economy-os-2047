#!/usr/bin/env python3
"""TITAN V4 ABSOLUTE FRONTIER - original OKX historical 2023-2025 basis events.

No funds, credentials, live orders, fabricated funding, orderbook or quote.
PUBLIC trade/mark/index 4H data are independently fetched from OKX and
SHA256 retained. Four-hour data do not prove actual order execution.

PREREGISTERED: BTC ETH SOL XRP DOGE ADA DOT LINK LTC ETC, from Jan 1
2023 to Jan 1 2026, 2023 fit, 2024 develop, blind 2025 final.
Not one 2025 event outcome influences fit or model selection. If no
credible positive economic effect, ALWAYS_FLAT, no strategy.
"""
from __future__ import annotations
import argparse,concurrent.futures,gzip,hashlib,json,math,threading,time
from datetime import datetime,timezone
from pathlib import Path
from trading import titan_omega_25m_market as oldmarket
from trading import titan_v4_basis_discovery as discovery

IDENTITY="TITAN-V4-3Y-TEN-SWAPS-FREEZE-20261117-PREDECLARE-01"
START_MS=1672531200000
END_MS=1767225600000
BAR_MS=14400000
EXPECTED=(END_MS-START_MS)//BAR_MS
ASSETS=("BTC","ETH","SOL","XRP","DOGE","ADA","DOT","LINK","LTC","ETC")
SWAPS=tuple(x+"-USDT-SWAP" for x in ASSETS)
MIN_ALIGNED_MARKETS=6
START_CAPITAL=4.15
TARGET=1037504.15
LEVERAGE=2.
MARGIN_FRAC=.15
EQUITY_RISK_FRAC=.025
VOLUME_SHARE_CAP=.001
# Historical funding 2023-25 is NOT accessible via public rolling REST.
# Charge two explicit UNKNOWN-funding proxies, never fake observed rates.
CASES={"base":{"taker_fee":.0005,"slip_including_spread":.0004,
               "assumed_funding_per_8h":.0001},
       "stress":{"taker_fee":.0015,"slip_including_spread":.003,
                 "assumed_funding_per_8h":.0005}}
AFTER_BAR_REJECT="OOS alpha not prequalified; do not inspect final strategy outcomes"
_gate=threading.Lock()
_next=[0.]

def api(path,params):
    with _gate:
        now=time.monotonic()
        if _next[0]>now:time.sleep(_next[0]-now)
        _next[0]=time.monotonic()+.145
    return oldmarket.public(path,params)

def sha(x):
    return hashlib.sha256(x).hexdigest()

def catalogue():
    public=api("/api/v5/public/instruments",{"instType":"SWAP"})
    byid={x.get("instId"):x for x in public}
    data={};status={}
    for sym in SWAPS:
        spec=byid.get(sym)
        if spec is None:
            status[sym]="public_instrument_missing"
            continue
        if (spec.get("state")!="live" or spec.get("ctType")!="linear"
            or spec.get("ctValCcy")!=sym.split("-")[0]):
            status[sym]="current_market_not_eligible"
            continue
        try:
            if int(spec["listTime"])>START_MS:status[sym]="listed_after_2023";continue
            if any(float(spec[k])<=0 for k in ("ctVal","lotSz","minSz")):
                status[sym]="invalid_current_contract_spec";continue
        except (KeyError,ValueError,TypeError):
            status[sym]="invalid_current_contract_spec"
            continue
        data[sym]=spec;status[sym]="predeclared_eligible"
    # A predeclared name is never replaced by a more profitable coin.
    return data,status

def parse_exchange_row(raw,kind,symbol):
    try:
        if kind=="trade":
            if len(raw)<9 or str(raw[8])!="1":return None
        elif len(raw)<6 or str(raw[-1])!="1":
            return None
        t=int(raw[0]);o,h,l,c=(float(x) for x in raw[1:5])
        if (not all(math.isfinite(x) for x in (o,h,l,c))
            or not 0<l<=min(o,c)<=max(o,c)<=h):
            raise ValueError("Malformed confirmed OHLC")
        turnover=float(raw[7]) if kind=="trade" else None
        if turnover is not None and (not math.isfinite(turnover) or turnover<0):
            raise ValueError("Invalid public actual volume")
        return {"ts":t,"symbol":symbol,"open":o,"high":h,"low":l,
                "close":c,"vol_quote":turnover}
    except (ValueError,TypeError,OverflowError) as e:
        raise ValueError("Malformed original exchange "+kind+" bar") from e

def endpoint(kind):
    return {"trade":"/api/v5/market/history-candles",
            "mark":"/api/v5/market/history-mark-price-candles",
            "index":"/api/v5/market/history-index-candles"}[kind]

def download_one(kind,sym):
    inst=sym if kind!="index" else sym.removesuffix("-SWAP")
    older=END_MS
    source={}
    for page in range(85):
        # after refers to bars strictly EARLIER than timestamp on OKX.
        kwargs={"instId":inst,"bar":"4H","limit":"100","after":str(older)}
        response=api(endpoint(kind),kwargs)
        if not response:break
        items=[(x,parse_exchange_row(x,kind,sym)) for x in response]
        parsed=[(raw,bar) for raw,bar in items if bar is not None]
        if not parsed:raise ValueError("No confirmed original candles")
        min_ts=min(z["ts"] for _,z in parsed)
        if min_ts>=older:raise ValueError("OKX historical cursor failed to advance")
        for original,bar in parsed:
            if START_MS<=bar["ts"]<END_MS:
                source[bar["ts"]]=original
        if min_ts<START_MS or len(response)<100:break
        older=min_ts
    else:raise ValueError("Exceeded 85-page budget; fail closed")
    original=[source[t] for t in sorted(source)]
    bars=[parse_exchange_row(x,kind,sym) for x in original]
    # Missing ANY bar means no invented interpolation and no usable event
    # analysis for that coin's incomplete triple-source chronology.
    if (len(bars)!=EXPECTED or
        bars[0]["ts"]!=START_MS or bars[-1]["ts"]!=END_MS-BAR_MS or
        any(b["ts"]-a["ts"]!=BAR_MS for a,b in zip(bars,bars[1:]))):
        raise ValueError(f"Incomplete true 2023-2025 {kind} history: {len(bars)}/{EXPECTED}")
    return original,bars

def fetch_sources(directory):
    specs,catalogue_status=catalogue()
    alljobs=[(sym,kind) for sym in SWAPS if sym in specs
             for kind in ("trade","mark","index")]
    outcomes={}
    # Endpoint-global rate limit is locked. 6 workers speed up latency.
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        submitted={executor.submit(download_one,kind,sym):(sym,kind)
                   for sym,kind in alljobs}
        for future in concurrent.futures.as_completed(submitted):
            sym,kind=submitted[future]
            try:
                original,bars=future.result()
                encoded=json.dumps(original,separators=(",",":")).encode()
                with gzip.open(directory/(sym+"-"+kind+".json.gz"),"wb") as file:
                    file.write(encoded)
                outcomes[(sym,kind)]={"status":"complete","rows":len(bars),
                                     "sha256":sha(encoded),"data":bars}
                print("V4 OKX ORIGINAL",sym,kind,len(bars),sha(encoded),
                      flush=True)
            except Exception as err:
                outcomes[(sym,kind)]={"status":"unavailable","error":str(err)[:240]}
                print("V4 SOURCE NOT AVAILABLE",sym,kind,str(err)[:200],
                      flush=True)
    manifest={
        "research_id":IDENTITY,"requested_utc_start":"2023-01-01T00:00:00Z",
        "requested_utc_end_exclusive":"2026-01-01T00:00:00Z",
        "download_timestamp_ms":int(time.time()*1000),
        "public_spec_status":catalogue_status,
        "source_manifest":{},"actual_verified_triples":[],
        "funding_2023_2025": "NOT OBTAINED, two explicit charges only",
        "spread_and_L2":"NOT OBTAINED; execution range assumption only",
        "point_in_time_contract_specs":"NOT OBTAINED; current public snapshot",
        "point_in_time_liquidation_tiers":"NOT OBTAINED",
    }
    bars={};active_specs={}
    for sym in SWAPS:
        record={}
        for kind in ("trade","mark","index"):
            v=outcomes.get((sym,kind),{"status":"not_eligible"})
            record[kind]={k:value for k,value in v.items() if k!="data"}
        record["current_spec"]=specs.get(sym)
        manifest["source_manifest"][sym]=record
        if all(outcomes.get((sym,k),{}).get("status")=="complete"
               for k in ("trade","mark","index")):
            bars[sym]={k:outcomes[(sym,k)]["data"]
                       for k in ("trade","mark","index")}
            active_specs[sym]=specs[sym]
            manifest["actual_verified_triples"].append(sym)
    (directory/"manifest.json").write_text(
        json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    return bars,active_specs,manifest

def load_sources(directory):
    manifest=json.loads((directory/"manifest.json").read_text())
    bars={};specs={}
    for sym in manifest["actual_verified_triples"]:
        triple={}
        for kind in ("trade","mark","index"):
            raw=gzip.decompress((directory/(sym+"-"+kind+".json.gz")).read_bytes())
            expected=manifest["source_manifest"][sym][kind]["sha256"]
            if sha(raw)!=expected:raise ValueError("SHA256 mismatch: "+sym+" "+kind)
            values=[parse_exchange_row(x,kind,sym) for x in json.loads(raw)]
            if len(values)!=EXPECTED or any(x is None for x in values):
                raise ValueError("Corrupted original market history")
            triple[kind]=values
        bars[sym]=triple
        specs[sym]=manifest["source_manifest"][sym]["current_spec"]
    return bars,specs,manifest

def quantity(spec,equity,price,range_pct):
    if equity<=.83 or price<=0:return 0.,0.
    try:
        cv=float(spec["ctVal"]);step=float(spec["lotSz"])
        minimum=float(spec["minSz"])
        if min(cv,step,minimum)<=0:return 0.,0.
        risk=max(.004,min(.30,range_pct*2.))
        notional=min(equity*MARGIN_FRAC*LEVERAGE,
                     equity*EQUITY_RISK_FRAC/risk)
        contracts=math.floor(notional/(price*cv)/step+1e-10)*step
        minimum=math.ceil(minimum/step-1e-10)*step
        if contracts+1e-10<minimum:return 0.,0.
        return round(contracts,10),contracts*cv*price
    except (KeyError,ValueError,TypeError,OverflowError,ZeroDivisionError):
        return 0.,0.

def simulate_event(book,bars,specs,case):
    equity=START_CAPITAL;peak=equity;dd=0.;last_exit=-1
    executed=[];curve=[{"ts":START_MS,"equity":equity}]
    refused={"minimum_contract":0,"volume_limit":0,"execution":0}
    for ev in sorted(book,key=lambda x:(x["next_ts"],-x["strength"],x["sym"])):
        t=ev["next_ts"]
        if t<=last_exit or equity<=.83 or equity>=TARGET:continue
        sym=ev["sym"]
        try:
            rows=bars[sym];i=ev["i"]+1
            trade=rows["trade"][i];mark=rows["mark"][i]
            prev=rows["trade"][i-1]
        except (KeyError,IndexError):
            refused["execution"]+=1;continue
        if trade["ts"]!=t or mark["ts"]!=t:raise ValueError("Future-mark clock leakage")
        openp=trade["open"];closep=trade["close"];direction=ev["direction"]
        rangep=max(.0001,(prev["high"]-prev["low"])/max(prev["close"],1e-8))  # ONLY COMPLETED PREVIOUS BAR
        qty,notional=quantity(specs[sym],equity,openp,rangep)
        if qty<=0:refused["minimum_contract"]+=1;continue
        if prev["vol_quote"]<=0 or notional>VOLUME_SHARE_CAP*prev["vol_quote"]:
            refused["volume_limit"]+=1;continue
        adverse_slip=case["slip_including_spread"]+min(.003,.15*notional/max(1.,prev["vol_quote"]))
        enter=openp*(1+direction*adverse_slip)
        exitp=closep*(1-direction*adverse_slip)
        notional=qty*float(specs[sym]["ctVal"])*enter
        fee=(notional+qty*float(specs[sym]["ctVal"])*exitp)*case["taker_fee"]
        funding=notional*case["assumed_funding_per_8h"]*.5
        initial=notional/LEVERAGE
        if initial+fee>equity:
            refused["execution"]+=1;continue
        # Actual Mark OHLC is observed, but maintenance tiers are
        # NOT historical; this only detects rough 2x liquidation proxy.
        liq=enter*(1-direction*(1/LEVERAGE-.015))
        mark_bad=mark["low"] if direction==1 else mark["high"]
        liquidation=(mark_bad<=liq if direction==1 else mark_bad>=liq)
        gross=direction*(exitp-enter)*qty*float(specs[sym]["ctVal"])
        pnl=max(-equity,gross-fee-funding)
        if liquidation:
            pnl=min(pnl,-initial-fee)
        newequity=max(0.,equity+pnl)
        executed.append({
            "sym":sym,"ts":t,"side":direction,"contracts":qty,
            "entry":round(enter,10),"exit":round(exitp,10),
            "equity_before":round(equity,9),
            "gross":round(gross,9),"taker_fees":round(fee,9),
            "assumed_funding":round(funding,9),
            "net":round(pnl,9),"equity_after":round(newequity,9),
            "margin":round(initial,9),
            "liquidation_mark_proxy":liquidation,
            "signal_strength":ev["strength"],
            "source_raw_ts":ev["signal_ts"],
            "note":"Public OHLC mark barrier, NOT exact historical maintenance-tier liquidation",
        })
        equity=newequity;peak=max(peak,equity)
        dd=max(dd,100*(peak-equity)/peak)
        last_exit=t+BAR_MS
        curve.append({"ts":last_exit,"equity":equity})
    wins=[x["net"] for x in executed if x["net"]>0]
    losses=[x["net"] for x in executed if x["net"]<0]
    pf=(sum(wins)/abs(sum(losses)) if losses else
        None if not wins else float("inf"))
    return {
        "equity_end":round(equity,9),
        "net_return_pct":round((equity/START_CAPITAL-1)*100,6),
        "closed_max_drawdown_pct":round(dd,5),
        "trades":len(executed),"winners":len(wins),"losers":len(losses),
        "avg_win_usdt":round(sum(wins)/len(wins),8) if wins else None,
        "avg_loss_usdt":round(sum(losses)/len(losses),8) if losses else None,
        "profit_factor":round(pf,6) if pf is not None and math.isfinite(pf) else None,
        "taker_fees_usdt":round(sum(x["taker_fees"] for x in executed),8),
        "funding_proxy_usdt":round(sum(x["assumed_funding"] for x in executed),8),
        "liquidation_proxy_events":sum(x["liquidation_mark_proxy"] for x in executed),
        "rejected":refused,
        "curve":curve,"ledger":executed,
    }

def selected_events(samples,model,policy,year):
    if model is None:return []
    fit=policy["fitted"][model]
    beta=fit["beta"];cut=fit["threshold"]
    if beta==0:return []
    daily=set();out=[]
    for ev in sorted(samples,key=lambda x:(x["ts"],x["sym"])):
        if ev["ts"]<START_MS or ev["next_ts"]>=END_MS:continue
        if discovery.month_start(ev["ts"])//100!=year or discovery.month_start(ev["next_ts"])//100!=year:
            continue
        x=ev["feature"][model]
        if abs(x)<max(1e-6,cut):continue
        key=(ev["sym"],ev["ts"]//discovery.DAY_MS)
        if key in daily:continue
        daily.add(key)
        out.append({"sym":ev["sym"],"i":ev["i"],
                    "signal_ts":ev["ts"],"next_ts":ev["next_ts"],
                    "direction":1 if beta*x>0 else -1,
                    "strength":round(abs(beta*x),10)})
    return out

def momentum_control(bars,year):
    """One predeclared simple baseline: 12-hour lagged momentum >=2.5%.

    All features derive from just-completed bar i. The next bar i+1 is
    used for EXECUTION, never for direction, strength, or position sizing.
    """
    events=[]
    for sym,triple in sorted(bars.items()):
        hist=triple["trade"]
        already=set()
        for i in range(3,len(hist)-1):
            finished=hist[i];nextbar=hist[i+1]
            if (discovery.month_start(finished["ts"])//100!=year or
                discovery.month_start(nextbar["ts"])//100!=year):
                continue
            past=math.log(finished["close"]/hist[i-3]["close"])
            if abs(past)<.025:continue
            day=finished["ts"]//discovery.DAY_MS
            if day in already:continue
            already.add(day)
            events.append({"sym":sym,"i":i,"signal_ts":finished["ts"],
                           "next_ts":nextbar["ts"],
                           "direction":1 if past>0 else -1,
                           "strength":round(abs(past),10)})
    return events

def analyze(bars,specs,manifest):
    valid=sorted(bars)
    sources={"requested":len(SWAPS),"complete_triples":len(valid),
             "original_4h_candles":sum(len(v["trade"]) for v in bars.values()),
             "triple_source_raw_candles":3*sum(len(v["trade"]) for v in bars.values()),
             "missing":{s:{k:v for k,v in rec.items() if k in ("trade","mark","index")}
                 for s,rec in manifest["source_manifest"].items()
                 if s not in valid}}
    if len(valid)<MIN_ALIGNED_MARKETS:
        return {"verdict":"UNTESTABLE_MARK_INDEX_NO_6_COMPLETE_MARKETS",
                "source_summary":sources,
                "real_orders":0,"alpha_selected":None,
                "final_not_opened":True}
    samples=[]
    for sym in valid:
        v=bars[sym]
        samples.extend(discovery.features(v["trade"],v["mark"],v["index"]))
    print("V4 SEALED 2023 TRAIN / 2024 DEV, FINAL 2025 NOT OPENED",
          "ROWS",len(samples),"CURRENCIES",len(valid),flush=True)
    fit=discovery.fit_train_dev(samples)
    print("V4 DEVELOPMENT HOLM",{
        h:{"p":fit["fitted"][h]["holm_p"],
           "events":fit["fitted"][h]["dev_events"],
           "net_proxy":fit["fitted"][h]["dev_net_log_proxy"]}
        for h in discovery.FAMILIES},flush=True)
    selected=fit["selected_before_2025"]
    print("V4 LOCKED STRATEGY BEFORE OPENING 2025",selected,flush=True)
    # Even for an eligible event model, development execution must pass
    # after both cost scenarios before 2025 is opened for that strategy.
    execution_dev={}
    accepted=None
    if selected:
        book=selected_events(samples,selected,fit,2024)
        execution_dev={c:simulate_event(book,bars,specs,v)
                       for c,v in CASES.items()}
        if (all(execution_dev[c]["net_return_pct"]>0 and
                execution_dev[c]["trades"]>=8 and
                execution_dev[c]["closed_max_drawdown_pct"]<=30
                for c in CASES)):
            accepted=selected
        print("V4 DEV EXECUTION GATE",accepted,flush=True)
    # Final data only consulted for a PRESELECTED approved event model.
    # If none, final "always-flat" has exactly zero paper trades.
    final={}
    if accepted:
        finalbook=selected_events(samples,accepted,fit,2025)
        final={c:simulate_event(finalbook,bars,specs,v) for c,v in CASES.items()}
    else:
        final={c:simulate_event([],bars,specs,v) for c,v in CASES.items()}
    # Precommitted simple classical control, always run ONE final comparison
    # without using its outcome to change any alpha selection or threshold.
    fixed_baseline=momentum_control(bars,2025)
    baseline={c:simulate_event(fixed_baseline,bars,specs,v)
              for c,v in CASES.items()}
    results={
        "study":IDENTITY,"target_pct":25_000_000.,
        "start_usdt":START_CAPITAL,"target_usdt":TARGET,
        "train_year":2023,"development_year":2024,"final_year":2025,
        "data_source":"Public ORIGINAL OKX history-candles, history-mark-price-candles and history-index-candles",
        "sources":sources,
        "catalogue_current_specs":{s:manifest["source_manifest"][s]["current_spec"]
                                   for s in valid},
        "raw_sha256":{s:{kind:manifest["source_manifest"][s][kind]["sha256"]
                         for kind in ("trade","mark","index")} for s in valid},
        "frozen_discovery":fit,
        "qualified_before_execution":selected,
        "accepted_before_final":accepted,
        "development_execution":execution_dev,
        "final_locked":final,
        "predeclared_classical_2025_baseline":baseline,
        "tested_event_families":len(discovery.FAMILIES),
        "data_gated_families":discovery.SKIPPED,
        "test_attempts":len(discovery.FAMILIES),
        "target_reached_closed":bool(accepted and
            all(final[c]["equity_end"]>=TARGET for c in CASES)),
        "verdict":("HISTORICAL_CANDIDATE_NOT_LIVE_PROOF"
            if accepted and all(final[c]["equity_end"]>=TARGET for c in CASES)
            else "NO_VALIDATED_25M_PERCENT_EDGE"),
        "real_orders":0,
        "limitations":[
            "No synchronized 2023-2025 book/spread/tick tape; taker fills modeled",
            "Historical funding 2023-2025 was not obtained: explicitly proxied and stressed",
            "Mark candle barriers approximate liquidation, no point-in-time tier archive",
            "Live-market survivor selection and current contract-spec survivorship bias",
            "Historical 2025 holdout not already V1-V3 2026, but still retrospective calendar",
            "Five Holm tests do not adjust for hundreds of previous OMEGA variants",
            "A small $4.15 portfolio can be blocked by actual contract minima",
            "Approximate paper execution not proof of real account fill prices",
        ]}
    return results

def save_report(report,path):
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")

def emit_svg(result,path):
    final=result.get("final_locked",{}).get("stress",{})
    curve=final.get("curve") or [{"ts":START_MS,"equity":START_CAPITAL}]
    y=[q["equity"] for q in curve];highest=max(y);lowest=min(0.,min(y))
    coords=" ".join("%.1f,%.1f"%(90+850*i/max(1,len(y)-1),
              385-300*(v-lowest)/max(1e-8,highest-lowest)) for i,v in enumerate(y))
    Path(path).write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="465">'
        '<rect width="1000" height="465" fill="white"/>'
        '<text x="90" y="35" font-size="20">V4 ORIGINAL OKX 2025 BLIND PAPER CLOSED EQUITY</text>'
        '<polyline fill="none" stroke="#3161b5" stroke-width="2" points="'
        +coords+'"/><text x="90" y="446" font-size="14">'
        'No actual exchange orders; true public 4H prices, approximate execution'
        '</text></svg>')

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--raw-dir",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--curve",required=True)
    p.add_argument("--offline",action="store_true")
    p.add_argument("--compare")
    a=p.parse_args(argv)
    root=Path(a.raw_dir);root.mkdir(parents=True,exist_ok=True)
    if a.offline:
        bars,specs,manifest=load_sources(root)
        print("V4 OFFLINE ORIGINAL THREE-SOURCE SHA VERIFIED",len(bars),flush=True)
    else:
        bars,specs,manifest=fetch_sources(root)
    result=analyze(bars,specs,manifest)
    if a.compare:
        expected=json.loads(Path(a.compare).read_text())
        if result!=expected:
            raise ValueError("FROZEN V4 REPLAY DOES NOT MATCH ORIGINAL REPORT")
        print("V4 OFFLINE FULL REPORT BITWISE VALUE MATCH",flush=True)
    save_report(result,a.out)
    emit_svg(result,a.curve)
    print("V4 OUTCOME",result["verdict"],
          "EVENT_HYPOTHESES_TESTED",result.get("tested_event_families"),
          "ECONOMIC_ALPHA",result.get("accepted_before_final"),
          "FINAL_PAPER",{
             k:{"return":v.get("net_return_pct"),"trades":v.get("trades")}
             for k,v in result.get("final_locked",{}).items()},
          "NO_REAL_TRADES",flush=True)

if __name__=="__main__":main()

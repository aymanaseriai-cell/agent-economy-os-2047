#!/usr/bin/env python3
"""Independent ledger and source audit: does NOT import strategy/engine."""
import argparse,collections,gzip,hashlib,json,math,statistics,zipfile
from pathlib import Path
from decimal import Decimal
BAR=300000
CAPITAL=4.15
GOAL=8.30
BARS=72
LEV=[3,5,10,20,30,50,75,100]
FAMILIES=("shock_continuation","shock_reversal","trade_mark_reversion")
CASES={"base":{"fee":.0005,"slip":.0004,"extra":.0002},
       "stress":{"fee":.0015,"slip":.0025,"extra":.001}}
def audit(source,results):
    faults=[];counts=collections.Counter()
    def fail(s):faults.append(s)
    with zipfile.ZipFile(source) as z:
        man=json.loads(z.read("manifest.json"));mkt={}
        for key,v in man["records"].items():
            decompressed=gzip.decompress(z.read(v["file"]))
            counts["files"]+=1
            if hashlib.sha256(decompressed).hexdigest()!=v["sha256"]:fail("SHA:"+key)
            rows=json.loads(decompressed)
            if len(rows)!=v["rows"]:fail("COUNT:"+key)
            if any(b-a!=BAR for a,b in zip([int(x[0]) for x in rows][:-1],[int(x[0]) for x in rows][1:])):fail("GAP:"+key)
            if any(str(x[-1])!="1" for x in rows):fail("UNCONFIRMED:"+key)
            sym,kind=key.rsplit("-",1);mkt.setdefault(sym,{})[kind]=rows
    out=json.loads(gzip.decompress(Path(results).read_bytes()) if str(results).endswith(".gz") else Path(results).read_text())
    clocks={s:tuple(int(x[0]) for x in d["trade"]) for s,d in mkt.items()}
    sample=next(iter(clocks.values()))
    if any(v!=sample for v in clocks.values()):fail("ALIGNMENT")
    if out["capital"]!=CAPITAL or out["goal"]!=GOAL or out["six_hour_bars"]!=72:fail("TARGET")
    if out["forward_oos_validated"] is not False or out["real_orders"]!=0:fail("FALSE_INDEPENDENT_OR_LIVE")
    starts=[i for i,t in enumerate(sample) if i>=50 and i+72<=len(sample) and t%(72*BAR)==0]
    if out["starts_utc_ms"]!=[sample[i] for i in starts]:fail("SAMPLED_ONLY_WINNERS")
    expected=set(f"{f}|{c}|{l}x" for f in FAMILIES for c in CASES for l in LEV)
    if set(out["grid_ledgers"])!=expected:fail("INCOMPLETE_GRID")
    for key,windows in out["grid_ledgers"].items():
        f,case,lx=key.split("|");lev=int(lx[:-1]);cost=CASES[case]
        if len(windows)!=len(starts):fail("INCOMPLETE_WINDOWS:"+key)
        for pos,window in enumerate(windows):
            counts["windows"]+=1
            if window["start_ts"]!=sample[starts[pos]] or window["end_ts"]!=sample[starts[pos]+71]+BAR:
                fail("TIME_WINDOW:"+key+":"+str(pos))
            if window["end_ts"]-window["start_ts"]!=21600000:fail("NOT_EXACT_SIX_HOURS")
            eq=CAPITAL;prior_exit=window["start_ts"];liq=0
            for trade in window["ledger"]:
                counts["trades"]+=1
                sym=trade["sym"];idx=clocks[sym].index(trade["entry_ts"])
                spec=man["specs"][sym]
                ct=float(spec["ctVal"]);lot=Decimal(spec["lotSz"]);sz=Decimal(str(trade["q"]))
                if trade["family"]!=f or trade["leverage"]!=lev:fail("BAD_FAMILY_OR_LEVERAGE")
                if not (trade["signal_ts"]==trade["entry_ts"]-BAR and
                        trade["entry_ts"]>=window["start_ts"] and
                        trade["exit_ts"]<=window["end_ts"] and
                        trade["entry_ts"]>=prior_exit):fail("LOOKAHEAD_OR_OVERLAP")
                if sz<Decimal(spec["minSz"]) or sz%lot!=0:fail("ILLEGAL_LOT:"+sym)
                tier=next(x for x in man["tiers"][sym] if x["tier"]=="1")
                if lev>min(float(tier["maxLever"]),float(spec["lever"]))+1e-8:fail("ILLEGAL_LEVERAGE:"+sym)
                if sz>Decimal(tier["maxSz"]):fail("TIER_EXCEEDED")
                b=mkt[sym]["trade"][idx]
                basepx=float(b[1])
                buy=trade["side"];fill=basepx*(1+buy*(cost["slip"]+cost["extra"]))
                if abs(fill-trade["entry_fill"])>max(1e-8,fill*1e-9):fail("ENTRY_PRICE_MISMATCH")
                notion=trade["q"]*ct*trade["entry_fill"]
                if abs(notion-trade["notional"])>1e-6:fail("NOTIONAL")
                if notion/lev+notion*cost["fee"]>eq+1e-6:fail("INSUFFICIENT_MARGIN")
                if notion>float(mkt[sym]["trade"][idx-1][7])*.001*1.01:fail("LIQUIDITY")
                # Recheck signal and direction using only prior rows, independently.
                r=math.log(float(mkt[sym]["trade"][idx-1][4])/float(mkt[sym]["trade"][idx-2][4]))
                hist=[math.log(float(mkt[sym]["trade"][j][4])/float(mkt[sym]["trade"][j-1][4]))
                      for j in range(idx-48,idx-1)]
                sigma=max(.00025,statistics.pstdev(hist))
                volume=float(mkt[sym]["trade"][idx-1][7])
                med=max(1.,statistics.median(float(mkt[sym]["trade"][j][7]) for j in range(idx-13,idx-1)))
                if f=="shock_continuation":
                    valid=abs(r)>=1.7*sigma and volume>=1.6*med
                    side=1 if r>0 else -1
                elif f=="shock_reversal":
                    valid=abs(r)>=2.2*sigma and volume>=med
                    side=-1 if r>0 else 1
                else:
                    b0=(float(mkt[sym]["trade"][idx-1][4])-float(mkt[sym]["mark"][idx-1][4]))/float(mkt[sym]["mark"][idx-1][4])
                    valid=abs(b0)>=.0008;side=-1 if b0>0 else 1
                if not valid or side!=buy:fail("FUTURE_SIGNAL_OR_WRONG_SIDE")
                # Independent mark-price path and conservative first-touch
                # liquidation proxy recheck. Five-minute OHLC order remains unknown.
                entry_mark=float(mkt[sym]["mark"][idx][1])
                mmr=float(tier["mmr"])
                liq_px=entry_mark*(1-buy*(1/lev-mmr-cost["fee"]-cost["extra"]-.001))
                end_bar=clocks[sym].index(trade["exit_ts"]-BAR)
                if end_bar<idx or end_bar>=idx+BARS:fail("BAD_TRADE_DURATION")
                mark_rows=mkt[sym]["mark"][idx:end_bar+1]
                hit=any((float(row[3])<=liq_px if buy>0 else float(row[2])>=liq_px) for row in mark_rows)
                if hit!=bool(trade["liquidation_proxy"]):
                    fail("LIQUIDATION_PATH_DISAGREEMENT")
                if trade["liquidation_proxy"] and trade["reason"]!="liquidated_proxy":fail("LIQUIDATION_REASON")
                funding=sum(float(x["realizedRate"])*buy*notion
                            for x in man["funding"][sym] if trade["entry_ts"]<int(x["fundingTime"])<=trade["exit_ts"])
                expected_gross=buy*trade["q"]*ct*(trade["exit_fill"]-trade["entry_fill"])
                expected_fee=notion*cost["fee"]+trade["q"]*ct*trade["exit_fill"]*cost["fee"]
                if trade["liquidation_proxy"]:
                    expected_net=-trade["margin"]-notion*(cost["fee"]+cost["slip"])
                    liq+=1
                else:expected_net=expected_gross-expected_fee-funding
                if abs(expected_net-trade["net"])>1e-6:fail("BAD_NET:"+key)
                if abs(expected_gross-trade["gross"])>1e-6:fail("BAD_GROSS")
                if abs(expected_fee-trade["fee"])>1e-6:fail("BAD_FEES")
                if abs(funding-trade["funding_net_cost"])>1e-6:fail("BAD_FUNDING")
                if abs(eq-trade["equity_before"])>1e-7:fail("BAD_COMPOUND_BEFORE")
                eq=max(0.,eq+expected_net)
                if abs(eq-trade["equity_after"])>1e-7:fail("BAD_COMPOUND_AFTER")
                prior_exit=trade["exit_ts"]
            if abs(eq-window["final_usdt"])>1e-7:fail("FALSE_FINAL_BALANCE")
            if bool(eq>=GOAL-1e-8)!=window["success"]:fail("FALSE_SUCCESS")
            if liq!=window["liquidations"]:fail("LIQUIDATION_COUNT")
            if window["trades"]!=len(window["ledger"]):fail("TRADE_COUNT")
            if abs((eq/CAPITAL-1)*100-window["return_pct"])>1e-7:fail("BAD_RETURN")
        given=out["grid_scores"][key]
        if given["n"]!=len(windows) or given["successes"]!=sum(v["success"] for v in windows):
            fail("SCORE_DRIFT:"+key)
    return {"passed":not bool(faults),"faults":faults[:100],"counts":dict(counts),
            "source":str(source),"results":str(results),
            "limitations":"Liquidity L2, historical tiers, actual liquidation path and queue fills cannot be proved by 5m OHLC."}
def main():
    p=argparse.ArgumentParser();p.add_argument("--data",required=True);p.add_argument("--results",required=True);p.add_argument("--out",required=True)
    a=p.parse_args();x=audit(a.data,a.results)
    Path(a.out).write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"passed":x["passed"],"counts":x["counts"],"faults":x["faults"][:10]}))
    if not x["passed"]:raise SystemExit(2)
if __name__=="__main__":main()


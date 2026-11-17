#!/usr/bin/env python3
"""TITAN Quantum Survival Interferometer (QSI) — immutable research, NO ORDERS.

A pure 3-qubit unitary amplitude-interference model is evaluated against an
identical-input classical probabilistic model and a zero-phase quantum ablation.
The object being optimized is a 4.15->8.30 USDT MICRO-BALANCE pathway before
0.83 USDT ruin, NOT an irrelevant hypothetical $1000 fixed-notional gain.
All exposures are quantized using verified PUBLIC OKX ctVal / lotSz / minSz,
with next-candle fills, fees, slippage, stop-first and adverse-liquidation
approximations. QUANTUM HARDWARE NOT USED. Results cannot guarantee profit.
"""
from __future__ import annotations
import argparse, cmath, gzip, hashlib, json, math, random, statistics, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from trading.edge_lab import (
    BAR_MS, TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE, STRESS_SLIPPAGE,
    FUNDING_PER_8H, atr_simple, fetch_history
)
from trading.titan_regime_research import validate_frozen

API="https://www.okx.com"
RESEARCH_ID="TITAN-QSI-20261117-LOCK-V1"
DAYS=60
WARMUP=224
SCAN_STRIDE=4
START=4.15
TARGET=8.30
RUIN=0.83
MAX_MARKETS=6
TRAIN_SHARE=.60
MIN_HISTORY=5600
LEVERAGES=(3.,10.)
MAX_MARGIN_PART=.40
MAX_PLANNED_STOP_RISK=.10
MAINTENANCE_PROXY=.015
MAX_HOLD=24
STOP_MULT=1.5
TAKE_MULT=2.5
PHASE=1.0
DECISION_CUTOFF=.66
MIN_TRAIN_FILLS=24
MIN_TEST_FILLS=20
MAX_PERMUTATIONS=999
RESEARCH_SEED=8302047
# Explicitly exclude all prior selected research baskets, including
# study branches 61-69, so this new test cannot recycle that market choice.
EXCLUDED=set(("BTC ETH SOL XRP DOGE SUI LTC ADA AVAX LINK DOT APT BCH "
    "ETC XLM NEAR ATOM UNI TRX FIL AAVE OP ARB INJ HBAR ICP WLD GALA "
    "SAND CRV PEPE SHIB TON PENDLE TIA SEI JUP ALGO APE ENA ENS LDO ONDO").split())
POLICIES=("quantum_interference","quantum_phase_robust",
          "quantum_zero_phase","classical_same_features")


def public_instruments():
    url=API+"/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-QSI-Research/1.0"}),
                 timeout=30) as h:
        data=json.load(h)
    if data.get("code")!="0":raise RuntimeError("OKX public catalogue refused")
    cutoff_ms=1700000000000
    eligible=[]
    for z in data.get("data",[]):
        sym=z.get("instId","")
        name=sym.removesuffix("-USDT-SWAP")
        if (not sym.endswith("-USDT-SWAP") or name in EXCLUDED
            or z.get("state")!="live" or z.get("ctType")!="linear"
            or z.get("ctValCcy")!=name
            or not str(z.get("listTime","")).isdigit()):
            continue
        # A listing must predate the test by >=90d for complete 60d history.
        if int(z["listTime"])>int(time.time()*1000)-90*86_400_000:continue
        try:
            ctval=float(z["ctVal"]);lot=float(z["lotSz"]);minimum=float(z["minSz"])
            if min(ctval,lot,minimum)<=0 or not all(
                math.isfinite(x) for x in (ctval,lot,minimum)):continue
        except (ValueError,TypeError,KeyError):continue
        eligible.append(z)
    # Deterministic data-independent ordering; NO post-hoc profit selection.
    eligible.sort(key=lambda z:hashlib.sha256(
        (RESEARCH_ID+":"+z["instId"]).encode()).hexdigest())
    if len(eligible)<MAX_MARKETS:raise RuntimeError("Few eligible public instruments")
    return eligible[:MAX_MARKETS],len(eligible)


def _h(psi, bit):
    out=[0j]*8
    k=1<<bit
    for i in range(8):
        if i&k:continue
        a,b=psi[i],psi[i|k]
        out[i]=(a+b)/math.sqrt(2)
        out[i|k]=(a-b)/math.sqrt(2)
    return out


def _ry(psi,bit,theta):
    out=[0j]*8;k=1<<bit
    c,s=math.cos(theta/2),math.sin(theta/2)
    for i in range(8):
        if i&k:continue
        a,b=psi[i],psi[i|k]
        out[i]=c*a-s*b
        out[i|k]=s*a+c*b
    return out


def interferometer(features, *, phase=PHASE):
    """Exact 3-qubit 8-state unitary circuit; returned observable is Born prob.

    Layers: local RY encodings, nonseparable diagonal pair ZZ phases,
    global H diffusion, another local feature phase, final H on bit 1.
    Identical OHLC features feed all classical / phase-0 ablation policies.
    """
    if len(features)!=3 or not all(math.isfinite(x) for x in features):
        raise ValueError("Invalid causal input vector")
    if not math.isfinite(phase) or phase<0 or phase>2:
        raise ValueError("Invalid phase scaling")
    p=[0j]*8
    p[0]=1+0j
    for j,v in enumerate(features):
        p=_ry(p,j,1.4*math.tanh(v))
    for i in range(8):
        z=[1 if (i>>b)&1 else -1 for b in range(3)]
        coupling=z[0]*z[1]+z[1]*z[2]-z[0]*z[2]
        phi=phase*(.54*coupling + .21*sum(z[b]*math.tanh(
            features[b]) for b in range(3)))
        p[i]*=cmath.exp(1j*phi)
    p=_h(p,0)
    p=_h(p,1)
    p=_h(p,2)
    for j,v in enumerate(features):
        p=_ry(p,j,.65*math.tanh(v))
    p=_h(p,1)
    norm=sum(abs(z)**2 for z in p)
    if abs(norm-1)>1e-8:raise ArithmeticError("Nonunitary wavefunction")
    bullish=sum(abs(z)**2 for i,z in enumerate(p) if i.bit_count()>=2)
    return bullish,norm


def classical_probability(features):
    # Same completed price inputs, no quantum circuit.
    values=[.5+.43*math.tanh(x) for x in features]
    return (values[0]*values[1]*(1-values[2])+
            values[0]*(1-values[1])*values[2]+
            (1-values[0])*values[1]*values[2]+
            values[0]*values[1]*values[2])


def candidate_stream(bars):
    validate_frozen(bars)
    cl=[b["close"] for b in bars]
    rows={name:[] for name in POLICIES}
    for i in range(WARMUP,len(bars)-1,SCAN_STRIDE):
        atr=atr_simple(bars,i,14)
        if not math.isfinite(atr) or atr<=0:continue
        af=atr/cl[i]
        if not .0012<=af<=.050:continue
        f=tuple(max(-3,min(3,math.log(cl[i]/cl[i-lag])/
                            max(af*math.sqrt(lag),1e-8)))
                for lag in (8,32,96))
        qp,_=interferometer(f)
        p0,_=interferometer(f,phase=0)
        ql,_=interferometer(f,phase=.7)
        qh,_=interferometer(f,phase=1.3)
        cp=classical_probability(f)
        choices={
            "quantum_interference":qp,
            "quantum_zero_phase":p0,
            "classical_same_features":cp}
        # Robust: all phase settings must agree in the same direction.
        strength=lambda p:abs(p-.5)
        if min(qp,ql,qh)>=DECISION_CUTOFF:
            rows["quantum_phase_robust"].append(
                (i,1,atr,round(min(qp,ql,qh)-.5,8)))
        elif max(qp,ql,qh)<=1-DECISION_CUTOFF:
            rows["quantum_phase_robust"].append(
                (i,-1,atr,round(.5-max(qp,ql,qh),8)))
        for name,p in choices.items():
            if p>=DECISION_CUTOFF:
                rows[name].append((i,1,atr,round(strength(p),8)))
            elif p<=1-DECISION_CUTOFF:
                rows[name].append((i,-1,atr,round(strength(p),8)))
    return rows


def affordable_contracts(spec,price,atr,equity,leverage):
    """Return exact public-lot-quantized quantity within small-account limits."""
    if equity<=RUIN or not 1<=leverage<=10 or min(price,atr)<=0:
        return 0.,0.
    try:
        if (spec.get("state")!="live" or spec.get("ctType")!="linear" or
            spec.get("ctValCcy")!=spec["instId"].split("-")[0]):
            return 0.,0.
        ctval=float(spec["ctVal"]);minimum=float(spec["minSz"])
        step=float(spec["lotSz"])
        if min(ctval,minimum,step)<=0:return 0.,0.
        stop_frac=STOP_MULT*atr/price
        if stop_frac<=0 or stop_frac>=.1:return 0.,0.
        exposure=min(equity*MAX_MARGIN_PART*leverage,
                     equity*MAX_PLANNED_STOP_RISK/stop_frac)
        qty_max=math.floor((exposure/(ctval*price))/step+1e-10)*step
        min_qty=math.ceil(minimum/step-1e-10)*step
        if qty_max+1e-10<min_qty:return 0.,0.
        notional=qty_max*ctval*price
        return round(qty_max,10),notional
    except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError):
        return 0.,0.


def sim_one(bars,signal,spec,*,equity,leverage,fee,slip,end):
    """Single quantized position; stop-first within OHLC, liquidation FIRST.

    Mark-price liquidation cannot be reconstructed from trade candles, so
    a conservative approximate adverse 1/lev-maintenance barrier is treated
    as liquidation whenever touched. This is a proxy, NOT an OKX replica.
    """
    i,side,atr,_=signal
    j=i+1
    if j>=end:return None
    entry=bars[j]["open"]*(1+side*slip)
    qty,notional=affordable_contracts(spec,entry,atr,equity,leverage)
    if qty<=0:return None
    stop=entry-side*STOP_MULT*atr
    target=entry+side*TAKE_MULT*atr
    liq_distance=max(0.001,1/leverage-MAINTENANCE_PROXY)
    liq=entry*(1-side*liq_distance)
    if min(stop,target,liq)<=0:return None
    ctval=float(spec["ctVal"])
    margin=notional/leverage
    enter_fee=notional*fee
    if enter_fee>=equity-margin:return None
    close_index=min(end-1,j+MAX_HOLD-1)
    fill=bars[close_index]["close"]
    status="timeout"
    for k in range(j,close_index+1):
        b=bars[k]
        # Conservative ambiguous OHLC: liquidation touch always before stop.
        bad=(b["low"] if side==1 else b["high"])
        gap=(b["open"]<=liq if side==1 else b["open"]>=liq)
        if gap or (bad<=liq if side==1 else bad>=liq):
            fill=b["open"] if gap else liq
            status="liquidation_proxy";close_index=k;break
        if (b["open"]<=stop if side==1 else b["open"]>=stop):
            fill=b["open"];status="stop_gap";close_index=k;break
        if (bad<=stop if side==1 else bad>=stop):
            fill=stop;status="stop";close_index=k;break
        good=(b["high"] if side==1 else b["low"])
        if (good>=target if side==1 else good<=target):
            fill=target;status="target";close_index=k;break
    exit_fill=fill*(1-side*slip)
    gross=side*(exit_fill-entry)*qty*ctval
    end_fee=abs(qty*ctval*exit_fill)*fee
    funding=notional*FUNDING_PER_8H*(close_index-j+1)/32
    net=gross-enter_fee-end_fee-funding
    if status=="liquidation_proxy":
        net=min(net,-margin-enter_fee-end_fee)
    net=max(-equity,net)
    return {"start_i":i,"exit_i":close_index,"day":bars[close_index]["ts"]//86_400_000,
            "net_usdt":round(net,9),"gross_usdt":round(gross,9),
            "entry_fee_usdt":round(enter_fee,9),"exit_fee_usdt":round(end_fee,9),
            "funding_estimate_usdt":round(funding,9),"status":status,
            "min_contract_quantity":qty,"equity_before":round(equity,9),
            "equity_after":round(max(0,equity+net),9)}


def paper_portfolio(markets,specs,signals,*,start,end,policy,leverage,
                    fee=TAKER_FEE,slip=BASE_SLIPPAGE):
    """Single-market-at-time chronological paper portfolio from REAL 4.15 USDT."""
    equity=START
    positions={}
    for symbol in markets:
        for signal in signals[symbol][policy]:
            i=signal[0]
            if start<=i and i+1<end:
                # Rank by quantum/classical confidence; tie by symbol name.
                positions.setdefault(i,[]).append((signal[3],symbol,signal))
    rows=[]
    available=start
    for i in sorted(positions):
        if i<available or equity<=RUIN:continue
        for _,symbol,signal in sorted(
            positions[i],key=lambda x:(-x[0],x[1])):
            t=sim_one(markets[symbol],signal,specs[symbol],
                      equity=equity,leverage=leverage,fee=fee,slip=slip,end=end)
            if t is None:continue
            equity=t["equity_after"]
            available=t["exit_i"]+1
            t["symbol"]=symbol
            rows.append(t)
            break
        if equity>=TARGET:break
    days={}
    for t in rows:
        days[t["day"]]=days.get(t["day"],0)+t["net_usdt"]
    peak=START
    max_dd=0.
    for t in rows:
        peak=max(peak,t["equity_before"],t["equity_after"])
        max_dd=max(max_dd,(peak-t["equity_after"])/peak)
    return {
        "trades":len(rows),"ending_usdt":round(equity,8),
        "return_pct":round(100*(equity/START-1),4),
        "reached_8_30":equity>=TARGET,
        "hit_0_83_ruin":equity<=RUIN,
        "positive_days":sum(v>0 for v in days.values()),
        "negative_days":sum(v<0 for v in days.values()),
        "max_drawdown_pct":round(max_dd*100,4),
        "liquidation_proxy_events":sum(t["status"]=="liquidation_proxy" for t in rows),
        "fees_usdt":round(sum(t["entry_fee_usdt"]+t["exit_fee_usdt"]
                              for t in rows),7),
        "trade_log":rows,
    }


def _brief(x):
    return {k:v for k,v in x.items() if k!="trade_log"}


def signflip_pvalue(trades,seed=RESEARCH_SEED):
    """Exploratory day-block symmetric-null test; NOT a calibrated alpha proof."""
    buckets={}
    for t in trades:
        d=t["day"];buckets[d]=buckets.get(d,0)+t["net_usdt"]
    values=list(buckets.values())
    if len(values)<15:return None
    actual=sum(values)
    rng=random.Random(seed)
    big=0
    for _ in range(MAX_PERMUTATIONS):
        candidate=sum(x*(1 if rng.randrange(2) else -1) for x in values)
        big+=candidate>=actual
    return round(min(1.,(big+1)/(MAX_PERMUTATIONS+1)*len(POLICIES)*len(LEVERAGES)),5)


def evaluate(markets,specs,*,raw_hashes=None,stamp_ms=None,catalogue_count=None):
    if len(markets)!=MAX_MARKETS or set(markets)!=set(specs):
        raise ValueError("Unverified fixed universe: fail closed")
    if any(len(b)<MIN_HISTORY for b in markets.values()):
        raise ValueError("Incomplete historical bar sample")
    n=min(len(v) for v in markets.values())
    common=[b["ts"] for b in next(iter(markets.values()))[:n]]
    if any([x["ts"] for x in b[:n]]!=common for b in markets.values()):
        raise ValueError("Unaligned chronological data; no accidental lookahead")
    selected={s:candidate_stream(b[:n]) for s,b in markets.items()}
    a=int(n*TRAIN_SHARE)
    b=a+(n-a)//2
    periods={"train":(WARMUP,a),"holdout_1":(a,b),
             "holdout_2":(b,n)}
    results={}
    for leverage in LEVERAGES:
        for policy in POLICIES:
            name=f"{policy}_{int(leverage)}x"
            out={}
            for part,(lo,hi) in periods.items():
                nominal=paper_portfolio(markets,specs,selected,start=lo,end=hi,
                                        policy=policy,leverage=leverage)
                stressed=paper_portfolio(markets,specs,selected,start=lo,end=hi,
                                         policy=policy,leverage=leverage,
                                         fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
                out[part]={"normal":_brief(nominal),
                           "stress":_brief(stressed)}
                if part!="train":
                    out[part]["exploratory_bonferroni_p"] = signflip_pvalue(
                        nominal["trade_log"],seed=RESEARCH_SEED+hi)
            results[name]=out
    # Selection from TRAIN ONLY. Same-family 3x/10x are separate hypotheses.
    eligible=[key for key,row in results.items() if
              row["train"]["normal"]["trades"]>=MIN_TRAIN_FILLS and
              row["train"]["normal"]["return_pct"]>0 and
              row["train"]["stress"]["return_pct"]>0 and
              row["train"]["normal"]["positive_days"]>=8 and
              row["train"]["normal"]["max_drawdown_pct"]<=25]
    chosen=(max(eligible,key=lambda k:results[k]["train"]["stress"][
        "return_pct"]) if eligible else None)
    reasons=[]
    if chosen is None:
        reasons.append("NO_TRAINING_AFTER_STRESS_PROFIT_WITH_MICRO_CONTRACTS")
    else:
        for part in ("holdout_1","holdout_2"):
            x=results[chosen][part]
            if (x["normal"]["trades"]<MIN_TEST_FILLS//2 or
                x["normal"]["return_pct"]<=0 or
                x["stress"]["return_pct"]<=0 or
                x["normal"]["positive_days"]<4):
                reasons.append(part+"_NO_REPEATED_PROFIT")
            if (x["exploratory_bonferroni_p"] is None or
                x["exploratory_bonferroni_p"]>.05):
                reasons.append(part+"_NO_MULTIPLICITY_ADJUSTED_EVIDENCE")
    return {
        "mode":"3_QUBIT_UNITARY_MICRO_4_15_ACCOUNT_LIVE_DISABLED_RESEARCH",
        "data_source":"OKX public instruments and 15m history candles only",
        "catalogue_selection":"min listing age 90d, live linear USDT perpetual, exclude 42 earlier symbols, SHA256 sorted exact 6; no return-based choice",
        "eligible_public_market_count":catalogue_count,
        "chosen_public_markets":sorted(markets),
        "raw_market_hashes":raw_hashes or {},
        "snapshot_utc":datetime.fromtimestamp(
            stamp_ms/1000,timezone.utc).isoformat() if stamp_ms else None,
        "bars_per_market":n,
        "user_start_balance_not_read":START,
        "goal_usdt":TARGET,"ruin_boundary_usdt":RUIN,
        "maximum_margin_fraction":MAX_MARGIN_PART,
        "max_planned_stop_risk_fraction":MAX_PLANNED_STOP_RISK,
        "unitary_three_qubit_computation_classical_emulation":True,
        "quantum_processor_used":False,
        "candidate_count_including_classical_and_ablation":len(results),
        "train_evidence_qualified_candidates":eligible,
        "train_only_selection":chosen,
        "multiplicity_test_note":"Exploratory day-block sign-flip with Bonferroni across eight predefined hypotheses, not formal guarantee; prior assistant experiments further inflate selection risk",
        "zero_trade_reference":{"ending_usdt":START,"return_pct":0.,"trades":0},
        "result":"HISTORICAL_CANDIDATE_ONLY_FORWARD_AUDIT_REQUIRED" if not reasons
                 else "NO_TRADE_NO_RELIABLE_DOUBLE_BEFORE_RUIN_EDGE",
        "failed_checks":reasons,
        "all_results":results,
        "no_real_orders":True,
        "no_private_account_read":True,
        "limitations":[
            "100% target is highly speculative and not guaranteed; default is no trade",
            "Historical trade-price OHLC cannot reconstruct mark-price liquidation, actual funding, exchange maintenance, bid/ask orderbook, latency or partial fills",
            "Proxy liquidation pessimistically assumes adverse extreme precedes the protective stop within a 15m candle",
            "The micro-account exchange public minimum can differ from current user-specific restrictions",
            "Three-qubit unitary matrices are simulated classically, never quantum hardware",
            "Only post costs and repeated untouched prospective real fill receipts can qualify a live strategy",
            "Repeated previous TITAN hypotheses mean even nominal p values are not proof",
        ]
    }


def main(argv=None):
    arg=argparse.ArgumentParser(description=__doc__)
    arg.add_argument("--out",default="reports/titan_qsi_4_15_usdt.json")
    arg.add_argument("--raw-dir",default="reports/titan_qsi_raw_candles")
    opts=arg.parse_args(argv)
    timestamp=int(time.time()*1000)
    obj,eligible=public_instruments()
    print("QSI UNSEEN DETERMINISTIC UNIVERSE",eligible,
          [x["instId"] for x in obj],flush=True)
    out=Path(opts.out);raw=Path(opts.raw_dir)
    out.parent.mkdir(parents=True,exist_ok=True)
    raw.mkdir(parents=True,exist_ok=True)
    markets={};specs={};hashes={}
    for spec in obj:
        sym=spec["instId"]
        print("QSI FETCH OKX COMPLETED HISTORICAL",sym,flush=True)
        bars=fetch_history(sym,DAYS,now_ms=timestamp)
        if len(bars)<MIN_HISTORY:
            raise ValueError("Frozen instrument lacks 60d full candles: "+sym)
        source=json.dumps(bars,separators=(",",":")).encode()
        hashes[sym]=hashlib.sha256(source).hexdigest()
        with gzip.open(raw/(sym+".json.gz"),"wb",compresslevel=6) as z:
            z.write(source)
        markets[sym]=bars
        specs[sym]=spec
        print("QSI RAW",sym,len(bars),"sha256",hashes[sym],
              "minSz",spec["minSz"],flush=True)
    report=evaluate(markets,specs,raw_hashes=hashes,stamp_ms=timestamp,
                    catalogue_count=eligible)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                   encoding="utf-8")
    for name,result in report["all_results"].items():
        print("QSI EXPERIMENT",name,"TRAIN",result["train"]["normal"],
              "H1",result["holdout_1"]["normal"],
              "H2",result["holdout_2"]["normal"],flush=True)
    print("QSI FINAL",report["result"],"TRAIN_SELECTION",
          report["train_only_selection"],"REASONS",report["failed_checks"],
          "NO ORDERS",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())

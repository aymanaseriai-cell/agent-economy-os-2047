#!/usr/bin/env python3
"""TITAN Omega — Quantum Geometry Failure Witness (QGFW), NO ORDERS.

An original, falsifiable project-specific quantum-inspired market hypothesis:
current OHLC context is embedded in a CLASSICALLY EMULATED physically unitary
two-qubit entangled feature map. Its Born-state fidelity to three PRECEDING
states yields quantum-geometric surprise; a phase-coupling stability check
decides whether the surprise indicates a trade-worthy regime transition.
We compare classical same-information distance, phase-free circuit and a
training-frequency-matched classical control. We never assert quantum hardware,
speedup, world-first priority, expected profitability or future certainty.

Portfolio is genuinely simulated at USD 4.15 initial equity with public OKX
integer lot/min contract constraints, 3x/10x research leverage, adverse fees,
funding approximation, next-bar entry, pessimistic liquidation proxy. Goal 8.30,
ruin <=0.83. Training-only winner selection; separate untouched 20% holdouts.
"""
from __future__ import annotations

import argparse,cmath,gzip,hashlib,json,math,random,statistics,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

from trading.edge_lab import atr_simple, ema_series, fetch_history, STRESS_FEE, STRESS_SLIPPAGE
from trading.titan_regime_research import validate_frozen
from trading.titan_quantum_survival_interferometer import (
    API, START, TARGET, RUIN, EXCLUDED, CRYPTO_ONLY_UNIVERSE,
    paper_portfolio, _brief
)
from trading.titan_quantum_time_reversal import PREVIOUS_QSI

RESEARCH_ID="TITAN-QGFW-20261117-V1-LOCKED"
EARLIER_QTRW={"CHZ","GRT","BONK","MASK","STX","WIF"}
SYMBOLS_COUNT=6
DAYS=60
MIN_BARS=5600
TRAIN_FRAC=.60
WARMUP=224
STEP=4
LEVERAGES=(3.,10.)
COUPLING=(0.,.75,1.,1.25)
Q_SURPRISE_THRESHOLD=.13
Q_STABLE_THRESHOLD=.10
CLASSIC_DISTANCE_THRESHOLD=.17
REVERSAL_SURPRISE_THRESHOLD=.22
TRAIN_MIN_FILLS=24
TRAIN_MIN_POSITIVE_DAYS=8
HOLDOUT_MIN_FILLS=10
DAY_BLOCK_MIN=15
RANDOM_SEED=8302047
BONFERRONI_TESTS=12
POLICIES=("q_geometric_breakout","q_robust_geometric_breakout",
          "q_geometric_reversion","q_no_entanglement_control",
          "classical_geometric_control","classical_frequency_matched")


def catalog():
    """Exclude every research market used earlier; deterministic hash sort."""
    url=API+"/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-QGFW-Research/1.0"}),timeout=30) as h:
        obj=json.load(h)
    if obj.get("code")!="0":
        raise ValueError("Unverified public OKX instruments catalogue")
    used=EXCLUDED|PREVIOUS_QSI|EARLIER_QTRW
    eligible=[]
    for spec in obj.get("data",[]):
        sym=spec.get("instId","")
        if not sym.endswith("-USDT-SWAP"):continue
        coin=sym[:-10]
        if (coin not in CRYPTO_ONLY_UNIVERSE or coin in used or
            spec.get("state")!="live" or spec.get("ctType")!="linear" or
            spec.get("ctValCcy")!=coin):continue
        try:
            if int(spec["listTime"])>int(time.time()*1000)-90*86_400_000:continue
            vals=[float(spec[z]) for z in ("ctVal","minSz","lotSz")]
            if not all(math.isfinite(v) and v>0 for v in vals):continue
        except (KeyError,TypeError,ValueError,OverflowError):continue
        eligible.append(spec)
    eligible.sort(key=lambda x:hashlib.sha256(
        (RESEARCH_ID+":"+x["instId"]).encode()).hexdigest())
    if len(eligible)<SYMBOLS_COUNT:
        raise RuntimeError("Too few genuinely unused crypto swap symbols")
    return eligible[:SYMBOLS_COUNT],len(eligible)


def _ry(psi,bit,theta):
    mask=1<<bit
    c,s=math.cos(theta/2),math.sin(theta/2)
    out=list(psi)
    for i in range(4):
        if i&mask:continue
        a,b=psi[i],psi[i|mask]
        out[i]=c*a-s*b
        out[i|mask]=s*a+c*b
    return out


def _rx(psi,bit,theta):
    mask=1<<bit
    c,s=math.cos(theta/2),-1j*math.sin(theta/2)
    out=list(psi)
    for i in range(4):
        if i&mask:continue
        a,b=psi[i],psi[i|mask]
        out[i]=c*a+s*b
        out[i|mask]=s*a+c*b
    return out


def _h(psi,bit):
    mask=1<<bit
    out=list(psi)
    for i in range(4):
        if i&mask:continue
        a,b=psi[i],psi[i|mask]
        out[i]=(a+b)/math.sqrt(2)
        out[i|mask]=(a-b)/math.sqrt(2)
    return out


def quantum_market_state(features,*,coupling=1.):
    """Physical 2-qubit unitary encoding of four causal normalised OHLC features.

    RY0,RX1, diagonal ZZ entangling phase, H0,RX1, RY0, then RZ1.
    Two qubits are a mathematical model, NOT real quantum market particles.
    """
    if len(features)!=4 or not all(math.isfinite(v) for v in features):
        raise ValueError("Invalid observed market feature vector")
    if not math.isfinite(coupling) or not 0<=coupling<=1.5:
        raise ValueError("Invalid entanglement coupling strength")
    a,b,c,d=(math.tanh(v) for v in features)
    p=[1+0j,0j,0j,0j]
    p=_ry(p,0,1.40*a)
    p=_rx(p,1,1.20*b)
    # The phase depends on the latest candle-body pressure and volatility.
    for i in range(4):
        parity=1 if i in (0,3) else -1
        p[i]*=cmath.exp(1j*coupling*parity*(.56*c+.34*d))
    p=_h(p,0)
    p=_rx(p,1,.58*(a+c))
    p=_ry(p,0,.47*(b-d))
    p=[v*cmath.exp(1j*(.34*d if i&2 else -.34*d)) for i,v in enumerate(p)]
    if abs(sum(abs(v)**2 for v in p)-1)>1e-8:
        raise ArithmeticError("Non-unitary two-qubit market map")
    return tuple(p)


def fidelity(a,b):
    if len(a)!=4 or len(b)!=4:raise ValueError("Expected 2-qubit statevectors")
    return max(0.,min(1.,abs(sum(x.conjugate()*y for x,y in zip(a,b)))**2))


def quantum_surprise(points,*,coupling=1.):
    """One minus averaged squared Born fidelity to STRICTLY PAST states."""
    if len(points)!=4:raise ValueError("Current and three prior causal observations needed")
    current=quantum_market_state(points[0],coupling=coupling)
    past=[quantum_market_state(x,coupling=coupling) for x in points[1:]]
    return 1-statistics.mean(fidelity(current,z) for z in past)


def classical_surprise(points):
    current=points[0]
    return statistics.mean(1-math.exp(-sum((x-y)**2 for x,y
        in zip(current,prior))/5) for prior in points[1:])


def _features_at(bars,cl,i):
    atr=atr_simple(bars,i,14)
    af=atr/cl[i]
    if not (math.isfinite(af) and 0<af<.5):raise ValueError("Invalid volatility")
    fast=max(-4.,min(4.,math.log(cl[i]/cl[i-8])/max(af*math.sqrt(8),1e-8)))
    slow=max(-4.,min(4.,math.log(cl[i]/cl[i-32])/max(af*math.sqrt(32),1e-8)))
    pressure=statistics.mean((z["close"]-z["open"])/max(
        z["high"]-z["low"],1e-8) for z in bars[i-7:i+1])
    volatility=max(-4.,min(4.,af*80-1))
    return (fast,slow,2*pressure,volatility)


def _train_match(classic,quantum,split,symbol):
    c=sum(x[0]<split for x in classic)
    q=sum(x[0]<split for x in quantum)
    frac=min(1.,q/c) if c else 0.
    out=[]
    for sig in classic:
        digest=hashlib.sha256((RESEARCH_ID+"|"+symbol+"|"+
                               str(sig[0])).encode()).digest()
        if int.from_bytes(digest[:8],"big")/2**64<frac:
            out.append(sig)
    return out,round(frac,6)


def signals(bars,symbol,split):
    validate_frozen(bars)
    n=len(bars);close=[float(x["close"]) for x in bars]
    fast=ema_series(close,24)
    slow=ema_series(close,96)
    votes={name:[] for name in POLICIES}
    for i in range(WARMUP,n-1,STEP):
        atr=atr_simple(bars,i,14)
        af=atr/close[i]
        if not (math.isfinite(af) and .0012<=af<=.05):continue
        prior_indices=(i,i-24,i-48,i-72)
        pts=[_features_at(bars,close,j) for j in prior_indices]
        q=quantum_surprise(pts,coupling=1)
        variants=[quantum_surprise(pts,coupling=z) for z in (.75,1.25)]
        nozz=quantum_surprise(pts,coupling=0)
        classical=classical_surprise(pts)
        trend=(1 if fast[i]>slow[i]+.4*atr and close[i]>close[i-24]
               else -1 if fast[i]<slow[i]-.4*atr and close[i]<close[i-24]
               else 0)
        if trend:
            if q>Q_SURPRISE_THRESHOLD:
                votes["q_geometric_breakout"].append((i,trend,atr,round(q,8)))
            if min((q,*variants))>Q_STABLE_THRESHOLD:
                votes["q_robust_geometric_breakout"].append(
                    (i,trend,atr,round(min((q,*variants)),8)))
            if nozz>Q_SURPRISE_THRESHOLD:
                votes["q_no_entanglement_control"].append(
                    (i,trend,atr,round(nozz,8)))
            if classical>CLASSIC_DISTANCE_THRESHOLD:
                votes["classical_geometric_control"].append(
                    (i,trend,atr,round(classical,8)))
        # A distinct, fixed competing hypothesis: quantum surprise at a 24-bar
        # extreme indicates reversion toward short-term mean.
        ret=(close[i]-close[i-24])/max(atr,1e-8)
        if q>REVERSAL_SURPRISE_THRESHOLD and abs(ret)>=1.75:
            votes["q_geometric_reversion"].append((i,-1 if ret>0 else 1,atr,round(q,8)))
    matched,ratio=_train_match(
        votes["classical_geometric_control"],
        votes["q_robust_geometric_breakout"],split,symbol)
    votes["classical_frequency_matched"]=matched
    return votes,ratio


def _dayblock_signflip(trades,multiplicity=BONFERRONI_TESTS):
    grouped={}
    for t in trades:
        grouped[t["day"]]=grouped.get(t["day"],0.)+t["net_usdt"]
    sample=list(grouped.values())
    if len(sample)<DAY_BLOCK_MIN:return None
    observed=sum(sample)
    rnd=random.Random(RANDOM_SEED)
    count=0
    for _ in range(999):
        draw=sum(v*(1 if rnd.getrandbits(1) else -1) for v in sample)
        count+=draw>=observed
    return min(1.,round((count+1)/1000*multiplicity,5))


def evaluate(markets,specs,*,hashes=None,stamp_ms=None,catalogue_n=None):
    if len(markets)!=SYMBOLS_COUNT or set(markets)!=set(specs):
        raise ValueError("Incomplete fixed pre-registered market panel")
    if any(len(v)<MIN_BARS for v in markets.values()):
        raise ValueError("Insufficient completed 60day public OKX history")
    n=min(map(len,markets.values()))
    first=[x["ts"] for x in next(iter(markets.values()))[:n]]
    if any([x["ts"] for x in v[:n]]!=first for v in markets.values()):
        raise ValueError("OHLC series have different time alignment")
    cut=int(n*TRAIN_FRAC);middle=cut+(n-cut)//2
    signals_by_market={}
    match_ratio={}
    for name,market in markets.items():
        candidates,ratio=signals(market[:n],name,cut)
        signals_by_market[name]=candidates;match_ratio[name]=ratio
    boundaries={"train":(WARMUP,cut),"holdout_1":(cut,middle),
                "holdout_2":(middle,n)}
    scored={}
    for policy in POLICIES:
        for lev in LEVERAGES:
            key=policy+"_"+str(int(lev))+"x"
            runs={}
            for period,(start,end) in boundaries.items():
                standard=paper_portfolio(markets,specs,signals_by_market,
                                         start=start,end=end,policy=policy,leverage=lev)
                stress=paper_portfolio(markets,specs,signals_by_market,
                                       start=start,end=end,policy=policy,leverage=lev,
                                       fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
                runs[period]={"normal":_brief(standard),"stress":_brief(stress)}
                if period!="train":
                    runs[period]["multiplicity_p_exploratory"]=_dayblock_signflip(
                        standard["trade_log"])
            scored[key]=runs
    valid=[name for name,d in scored.items()
           if d["train"]["normal"]["trades"]>=TRAIN_MIN_FILLS
           and d["train"]["normal"]["return_pct"]>0
           and d["train"]["stress"]["return_pct"]>0
           and d["train"]["normal"]["positive_days"]>=TRAIN_MIN_POSITIVE_DAYS
           and d["train"]["normal"]["max_drawdown_pct"]<=25]
    chosen=max(valid,key=lambda k:scored[k]["train"]["stress"][
        "return_pct"]) if valid else None
    failures=[]
    if not chosen:
        failures.append("NO_TRAIN_PROVEN_RECURRING_AFTER_STRESS_EDGE")
    else:
        for period in ("holdout_1","holdout_2"):
            a=scored[chosen][period]
            if (a["normal"]["trades"]<HOLDOUT_MIN_FILLS or
                a["normal"]["return_pct"]<=0 or
                a["stress"]["return_pct"]<=0 or
                a["normal"]["positive_days"]<4):
                failures.append(period+"_UNPROFITABLE_AFTER_ASSUMED_COSTS")
            if (a["multiplicity_p_exploratory"] is None or
                a["multiplicity_p_exploratory"]>.05):
                failures.append(period+"_NO_EXPLORATORY_SIGNIFICANCE")
    return {
        "study":"TITAN_QGFW_QUANTUM_GEOMETRIC_STATE_SURPRISE_4_15_USDT_NO_ORDERS",
        "physical_quantum_hardware_used":False,
        "quantum_state_math":"Classical emulation of normalized two-qubit unitary entangled feature map; Born fidelity relative to three earlier states",
        "actual_quantum_computational_advantage_shown":False,
        "precommitted_data_independent_cryptocurrency_selector":"Unseen live crypto USDT swaps only, SHA256 fixed study ID sorting from fixed allowlist",
        "crypto_markets":sorted(markets),
        "available_eligible_crypto_count":catalogue_n,
        "completed_15min_candles_per_market":n,
        "raw_market_data_sha256":hashes or {},
        "collected_utc":datetime.fromtimestamp(stamp_ms/1000,timezone.utc).isoformat() if stamp_ms else None,
        "micro_account_start":START,"micro_target":TARGET,"ruin_threshold":RUIN,
        "quantized_contracts_from_public_instrument_catalogue":True,
        "training_share":TRAIN_FRAC,"holdout_halves":2,
        "candidate_models_including_classical_control":len(scored),
        "classical_turnover_ratio_train_only_by_market":match_ratio,
        "training_qualified":valid,"selected_using_training_only":chosen,
        "null_trade_baseline":{"end_usdt":START,"return_pct":0,"trades":0},
        "verdict":"HISTORICALLY_POSITIVE_ONLY_NEEDS_INDEPENDENT_PROSPECTIVE_FILLS"
                  if not failures else "NO_TRADE_NO_PROVEN_QUANTUM_MICRO_EDGE",
        "failed_checks":failures,
        "all_models":scored,
        "real_orders_submitted":False,"private_account_read":False,
        "important_limitations":[
            "Quantum market-state analogy is a research tool; it does not assert quantum particles in prices",
            "Geometric fidelity is not a guaranteed predictive distribution or evidence of quantum advantage",
            "The experiment follows many previous TITAN hypotheses; apparent historical significance is insufficient",
            "15m candle OHLC cannot reproduce orderbook fills, actual funding, mark-price liquidation or 4.15 USDT exchange permissions",
            "Stress fee/slippage, leverage and liquidation proxy are model assumptions, not true OKX private account rules",
            "Any result requires independently reviewed untouched future execution evidence before real orders"
        ]
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",default="reports/titan_qgfw_micro_real_history.json")
    p.add_argument("--raw-dir",default="reports/titan_qgfw_public_raw")
    args=p.parse_args(argv)
    stamp=int(time.time()*1000)
    instruments,eligible=catalog()
    print("QGFW NEW CRYPTO BASKET",eligible,
          [i["instId"] for i in instruments],flush=True)
    out=Path(args.out);raw=Path(args.raw_dir)
    out.parent.mkdir(parents=True,exist_ok=True)
    raw.mkdir(parents=True,exist_ok=True)
    markets={};specs={};hashes={}
    for spec in instruments:
        sym=spec["instId"]
        print("QGFW FETCH REAL HISTORICAL",sym,flush=True)
        bars=fetch_history(sym,DAYS,now_ms=stamp)
        if len(bars)<MIN_BARS:raise RuntimeError("Real price series missing: "+sym)
        binary=json.dumps(bars,separators=(",",":")).encode()
        hashes[sym]=hashlib.sha256(binary).hexdigest()
        with gzip.open(raw/(sym+".json.gz"),"wb",compresslevel=6) as fd:
            fd.write(binary)
        markets[sym]=bars;specs[sym]=spec
        print("QGFW PRICE SOURCE",sym,len(bars),hashes[sym],flush=True)
    res=evaluate(markets,specs,hashes=hashes,stamp_ms=stamp,catalogue_n=eligible)
    out.write_text(json.dumps(res,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for name,periods in res["all_models"].items():
        print("QGFW MODEL",name,
              "TRAIN",periods["train"]["normal"],
              "TRAIN_STRESS",periods["train"]["stress"]["return_pct"],
              "H1",periods["holdout_1"]["normal"],
              "H1_STRESS",periods["holdout_1"]["stress"]["return_pct"],
              "H2",periods["holdout_2"]["normal"],
              "H2_STRESS",periods["holdout_2"]["stress"]["return_pct"],flush=True)
    print("QGFW FINAL",res["verdict"],"SELECTED",res["selected_using_training_only"],
          "REASONS",res["failed_checks"],"NO ORDERS",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())

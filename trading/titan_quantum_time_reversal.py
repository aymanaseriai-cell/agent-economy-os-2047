#!/usr/bin/env python3
"""TITAN Omega Quantum Time-Reversal Witness (QTRW), research-only.

Original project-specific hypothesis: the Born probability of a TWO-QUBIT
unitary circuit changes when the eight causal market shock increments are
processed in chronological order versus time-reversed order. This time-arrow
witness, and its resistance to dephasing/coupling-scale perturbations, may
reject bad trend trades. The same observations are supplied to a classical
asymmetry control and a no-entanglement quantum ablation.

ALL quantum amplitudes are classically simulated; the market is not a
physical quantum system. Models have NO promise of profitability. Run
micro-account OKX historical falsification: USDT 4.15 initially, goal 8.30,
public exact contract lots, 3x/10x adverse cost stress, untouched holdouts.
No private API endpoints, credentials, or exchange orders.
"""
from __future__ import annotations
import argparse, cmath, gzip, hashlib, json, math, statistics, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading.edge_lab import BAR_MS, STRESS_FEE, STRESS_SLIPPAGE, ema_series, atr_simple, fetch_history
from trading.titan_regime_research import validate_frozen
from trading.titan_quantum_survival_interferometer import (
    API, START, TARGET, RUIN, EXCLUDED, CRYPTO_ONLY_UNIVERSE, 
    paper_portfolio, signflip_pvalue, _brief,
)

RESEARCH_ID="TITAN-QTRW-20261117-LOCK-1"
MAX_MARKETS=6
DAYS=60
WARMUP=224
SCAN_STRIDE=4
MIN_HISTORY=5600
TRAIN_SHARE=.60
LEVERAGES=(3.,10.)
MIN_TRAIN_FILLS=24
MIN_TEST_FILLS=20
SIGNAL_THRESHOLD=.055
ROBUST_THRESHOLD=.04
CLASSIC_THRESHOLD=.40
TIME_SHOCK_COUNT=8
# QSI's last crypto panel and equity-linked first-cohort crypto must be excluded.
PREVIOUS_QSI={"1INCH","CFX","XTZ","BLUR","ZK","LPT","AZTEC"}
POLICIES=("q_time_reverse","q_time_reverse_robust",
          "q_no_entanglement","classical_same_observations")


def catalog():
    url=API+"/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-QTRW-Public-Only/1.0"}),timeout=30) as handle:
        raw=json.load(handle)
    if raw.get("code")!="0":raise RuntimeError("Failed public instrument listing")
    result=[]
    for z in raw.get("data",[]):
        sym=z.get("instId","")
        if not sym.endswith("-USDT-SWAP"):continue
        coin=sym[:-10]
        if (coin not in CRYPTO_ONLY_UNIVERSE or coin in EXCLUDED or
            coin in PREVIOUS_QSI or z.get("state")!="live" or
            z.get("ctType")!="linear" or z.get("ctValCcy")!=coin):
            continue
        try:
            age=int(z["listTime"])
            val=float(z["ctVal"]);lot=float(z["lotSz"]);minimum=float(z["minSz"])
            if min(val,lot,minimum)<=0 or not all(map(math.isfinite,(val,lot,minimum))):
                continue
            if age>int(time.time()*1000)-90*86_400_000:continue
        except (ValueError,KeyError,TypeError):
            continue
        result.append(z)
    result.sort(key=lambda x:hashlib.sha256(
        (RESEARCH_ID+":"+x["instId"]).encode()).hexdigest())
    if len(result)<MAX_MARKETS:raise RuntimeError("Insufficient fresh crypto instruments")
    return result[:MAX_MARKETS],len(result)


def _h(state,bit):
    out=[0j]*4;k=1<<bit
    for j in range(4):
        if j&k:continue
        a,b=state[j],state[j|k]
        out[j]=(a+b)/math.sqrt(2)
        out[j|k]=(a-b)/math.sqrt(2)
    return out


def _ry(state,bit,theta):
    out=[0j]*4;k=1<<bit
    c,s=math.cos(theta/2),math.sin(theta/2)
    for j in range(4):
        if j&k:continue
        a,b=state[j],state[j|k]
        out[j]=c*a-s*b;out[j|k]=s*a+c*b
    return out


def _rx(state,bit,theta):
    out=[0j]*4;k=1<<bit
    c=math.cos(theta/2);s=-1j*math.sin(theta/2)
    for j in range(4):
        if j&k:continue
        a,b=state[j],state[j|k]
        out[j]=c*a+s*b;out[j|k]=s*a+c*b
    return out


def _rz(state,bit,theta):
    return [z*cmath.exp(1j*(theta/2 if (j>>bit)&1 else -theta/2))
            for j,z in enumerate(state)]


def _zz(state,theta):
    return [z*cmath.exp(1j*theta/2*(1 if j in (0,3) else -1))
            for j,z in enumerate(state)]


def circuit(seq, *, coupling=1.):
    """Unitary two-qubit, return-order-sensitive noncommuting circuit.

    H -> chronological alternating RY0, RZ1, ZZ01, RX0 and H1.
    Reversal does not generally commute with this circuit. Output is
    the signed Born measurement of Pauli-Z on qubit 0.
    """
    if (len(seq)!=TIME_SHOCK_COUNT or not all(math.isfinite(v) for v in seq)
        or not math.isfinite(coupling) or not 0<=coupling<=1.5):
        raise ValueError("Invalid observed shock sequence or coupling")
    state=[1+0j,0j,0j,0j]
    state=_h(_h(state,0),1)
    for t,r in enumerate(seq):
        v=max(-2.,min(2.,r))
        state=_ry(state,0,.92*v)
        state=_rz(state,1,.73*v)
        state=_zz(state,coupling*(.37+.11*t)*v)
        state=_rx(state,0,.33*v)
        state=_h(state,1)
    norm=sum(abs(x)**2 for x in state)
    if abs(norm-1)>1e-8:raise ArithmeticError("Nonunitary circuit")
    z=sum(abs(x)**2*(1 if j&1 else -1) for j,x in enumerate(state))
    return z,norm


def arrow(seq,coupling=1.):
    a,_=circuit(seq,coupling=coupling)
    b,_=circuit(tuple(reversed(seq)),coupling=coupling)
    return (a-b)/2


def shocks(close,i,af):
    if i<32 or i>=len(close) or af<=0:raise ValueError("Insufficient causal history")
    # Eight non-overlapping 4x15m increments, strictly ending at bar i.
    return tuple(max(-2,min(2,math.log(close[k]/close[k-4])/
                   max(af*2,1e-8)))
                 for k in range(i-28,i+1,4))


def candidate_stream(bars):
    validate_frozen(bars)
    close=[float(b["close"]) for b in bars]
    fast=ema_series(close,24);slow=ema_series(close,96)
    rows={name:[] for name in POLICIES}
    for i in range(WARMUP,len(bars)-1,SCAN_STRIDE):
        atr=atr_simple(bars,i,14)
        if not math.isfinite(atr) or atr<=0:continue
        af=atr/close[i]
        if not .0012<=af<=.05:continue
        seq=shocks(close,i,af)
        longtrend=fast[i]>slow[i]+.4*atr and close[i]>close[i-32]
        shorttrend=fast[i]<slow[i]-.4*atr and close[i]<close[i-32]
        side=1 if longtrend else -1 if shorttrend else 0
        if not side:continue
        q=arrow(seq)
        quantum_no_zz=arrow(seq,coupling=0.)
        lo=arrow(seq,coupling=.75);hi=arrow(seq,coupling=1.25)
        # Identical information available to classical (last vs first half).
        classical=(sum(seq[4:])-sum(seq[:4]))/4
        if q*side>SIGNAL_THRESHOLD:
            rows["q_time_reverse"].append((i,side,atr,round(abs(q),8)))
        if min(q*side,lo*side,hi*side)>ROBUST_THRESHOLD:
            rows["q_time_reverse_robust"].append(
                (i,side,atr,round(min(abs(q),abs(lo),abs(hi)),8)))
        if quantum_no_zz*side>SIGNAL_THRESHOLD:
            rows["q_no_entanglement"].append(
                (i,side,atr,round(abs(quantum_no_zz),8)))
        if classical*side>CLASSIC_THRESHOLD:
            rows["classical_same_observations"].append(
                (i,side,atr,round(abs(classical)/4,8)))
    return rows


def evaluate(markets,specs,*,raw_hashes=None,stamp_ms=None,catalogue_count=None):
    if len(markets)!=MAX_MARKETS or set(markets)!=set(specs):
        raise ValueError("Missing precommitted public crypto market")
    if any(len(b)<MIN_HISTORY for b in markets.values()):
        raise ValueError("Incomplete public 60-day OHLC data")
    n=min(len(b) for b in markets.values())
    reference=[b["ts"] for b in next(iter(markets.values()))[:n]]
    if any([b["ts"] for b in rows[:n]]!=reference for rows in markets.values()):
        raise ValueError("Market timestamps mismatch")
    selections={name:candidate_stream(rows[:n]) for name,rows in markets.items()}
    split=int(n*TRAIN_SHARE)
    middle=split+(n-split)//2
    periods={"train":(WARMUP,split),"holdout_1":(split,middle),
             "holdout_2":(middle,n)}
    combinations={}
    for lev in LEVERAGES:
        for name in POLICIES:
            key=name+"_"+str(int(lev))+"x"
            r={}
            for phase,(start,end) in periods.items():
                base=paper_portfolio(markets,specs,selections,start=start,end=end,
                                     policy=name,leverage=lev)
                stressed=paper_portfolio(markets,specs,selections,start=start,end=end,
                                         policy=name,leverage=lev,
                                         fee=STRESS_FEE,slip=STRESS_SLIPPAGE)
                r[phase]={"nominal":_brief(base),"stress":_brief(stressed)}
                if phase!="train":
                    r[phase]["exploratory_bonferroni_p"]=signflip_pvalue(
                        base["trade_log"],seed=8302148+end)
            combinations[key]=r
    # The holdouts are NEVER examined for selecting the candidate.
    approved=[k for k,row in combinations.items()
              if row["train"]["nominal"]["trades"]>=MIN_TRAIN_FILLS
              and row["train"]["nominal"]["return_pct"]>0
              and row["train"]["stress"]["return_pct"]>0
              and row["train"]["nominal"]["positive_days"]>=8
              and row["train"]["nominal"]["max_drawdown_pct"]<=25]
    selected=max(approved,key=lambda k:combinations[k]["train"]["stress"][
        "return_pct"]) if approved else None
    failure=[]
    if selected is None:failure.append("NO_POSITIVE_STRESSED_TRAIN_EDGE")
    else:
        for phase in ("holdout_1","holdout_2"):
            row=combinations[selected][phase]
            a=row["nominal"];b=row["stress"]
            if (a["trades"]<MIN_TEST_FILLS//2 or a["return_pct"]<=0 or
                b["return_pct"]<=0 or a["positive_days"]<4):
                failure.append(phase+"_NOT_REPEATEDLY_PROFITABLE")
            if (row["exploratory_bonferroni_p"] is None or
                row["exploratory_bonferroni_p"]>.05):
                failure.append(phase+"_NOT_SIGNIFICANT_AFTER_MULTIPLICITY")
    return {
        "study":"TITAN_QTRW_TWO_QUBIT_TIME_ARROW_UNSEEN_CRYPTO_MICRO_RESEARCH",
        "public_crypto_universe":"named prior locked crypto allowlist minus all prior tested instruments; deterministic SHA256 selection; requires >=90d listed",
        "eligible_public_cryptos":catalogue_count,
        "markets":sorted(markets),
        "completed_15m_bars_per_market":n,
        "data_sha256":raw_hashes or {},
        "generated_utc":datetime.fromtimestamp(stamp_ms/1000,timezone.utc).isoformat() if stamp_ms else None,
        "market_source":"OKX public live instrument metadata and completed history candles",
        "quantum_hardware_used":False,
        "quantum_circuit_classically_simulated":True,
        "statistical_advantage_demonstrated":False,
        "strategy_precommitted":list(POLICIES),
        "micro_start_usdt":START,"micro_target_usdt":TARGET,"ruin_boundary_usdt":RUIN,
        "train_fraction":TRAIN_SHARE,"chronological_holdout_halves":2,
        "only_training_eligible":approved,"chosen_only_on_training":selected,
        "models_compared":len(combinations),
        "no_trade_baseline":{"ending_usdt":START,"net_return_pct":0,"trades":0},
        "verdict":"NO_TRADE_NO_PROVEN_MICRO_QUANTUM_EDGE" if failure
                  else "HISTORICAL_CANDIDATE_REQUIRES_INDEPENDENT_FORWARD_FILLS",
        "rejection_reasons":failure,"results":combinations,
        "real_orders_submitted":False,"real_user_balance_checked":False,
        "limitations":[
            "Quantum circuit is classically emulated physics math; markets are not physical qubits",
            "Sequential model family searches across PRs 61-70 inflate false discoveries; formal FDR not established",
            "15m OHLC stop-first and approximate liquidation cannot reconstruct mark-price exchange fills",
            "Funding and fees are assumed; user account rights and fee tier were not accessed",
            "Historic success would still require new prospective, independently verified fill-level evidence",
            "Small account target 4.15->8.30 is speculative and may be impossible under actual exchange friction"
        ]
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",default="reports/titan_qtrw_real_crypto_micro.json")
    parser.add_argument("--raw-dir",default="reports/titan_qtrw_raw")
    opt=parser.parse_args(argv)
    stamp=int(time.time()*1000)
    instruments,eligible=catalog()
    print("QTRW PRECOMMITTED CRYPTO PANEL",eligible,
          [x["instId"] for x in instruments],flush=True)
    markets={};specs={};hashes={}
    report=Path(opt.out);source=Path(opt.raw_dir)
    report.parent.mkdir(parents=True,exist_ok=True)
    source.mkdir(parents=True,exist_ok=True)
    for spec in instruments:
        name=spec["instId"]
        candles=fetch_history(name,DAYS,now_ms=stamp)
        if len(candles)<MIN_HISTORY:raise RuntimeError("Missing real data: "+name)
        raw=json.dumps(candles,separators=(",",":")).encode()
        hashes[name]=hashlib.sha256(raw).hexdigest()
        with gzip.open(source/(name+".json.gz"),"wb",compresslevel=6) as fd:
            fd.write(raw)
        markets[name]=candles;specs[name]=spec
        print("QTRW RAW OKX",name,len(candles),hashes[name],flush=True)
    result=evaluate(markets,specs,raw_hashes=hashes,stamp_ms=stamp,catalogue_count=eligible)
    report.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for key,rows in result["results"].items():
        print("QTRW MODEL",key,"TRAIN",rows["train"]["nominal"],
              "H1",rows["holdout_1"]["nominal"],
              "H2",rows["holdout_2"]["nominal"],
              "STRESS",rows["train"]["stress"]["return_pct"],
              rows["holdout_1"]["stress"]["return_pct"],
              rows["holdout_2"]["stress"]["return_pct"],flush=True)
    print("QTRW FINAL",result["verdict"],"SELECTED",result["chosen_only_on_training"],
          "FAIL",result["rejection_reasons"],"NO_ORDERS",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())

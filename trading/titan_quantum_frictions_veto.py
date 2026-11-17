#!/usr/bin/env python3
"""TITAN Omega — Quantum Friction/Regime Veto (QFRV) 128% challenge, NO ORDERS.

Falsifiable new combination, built before seeing the NEW market panel returns:
pre-frozen QSI mathematical THREE-qubit circuit's phase-robust Born signal
plus causal 8/32-bar momentum agreement, 24/96 EMA trend, 16-bar convexity
and an after-STRESS-fee theoretical exit edge gate. Equal-input classical
ablation and ungated controls. Only original 3x / 10x PAPER scenarios;
after-close 9.462 USDT (+128%) stop or 0.83 USDT ruin.

Six DIFFERENT public OKX crypto USDT swap markets hashed from a
predeclared never-used-by-QSI/QTRW/QGFW crypto list. Chronological
60% train, 20% H1, 20% H2; no holdout-based parameter selection.
Exact public contract minSz/lotSz/ctVal; next-bar open, adverse
stop-first and liquidation proxy; normal and stress fee/slippage.

Classical quantum-state math, NOT quantum hardware. No guarantee
of profit, no external/private API, no orders, no automated tasks.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,statistics,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

from trading import titan_quantum_survival_interferometer as qsi
from trading.edge_lab import (
    BAR_MS, TAKER_FEE, BASE_SLIPPAGE, STRESS_FEE, STRESS_SLIPPAGE,
    FUNDING_PER_8H, ema_series, fetch_history,
)
from trading.titan_regime_research import validate_frozen

STUDY="TITAN-OMEGA-QFRV-128-20261117-FROZEN1"
API="https://www.okx.com"
START=qsi.START
TARGET128=round(START*2.28,6)
RUIN=qsi.RUIN
DAYS=60
MIN_BARS=5600
MARKETS=6
PHASES=("train","holdout_1","holdout_2")
LEVERAGES=(3.,10.)
# This is a source and MARKET freeze; no result-based instrument choosing.
UNIVERSE=set(("AR DYDX ETHFI FET IMX KAS MINA PENGU PYTH RENDER RUNE "
              "TWT GMT CELO NEO ZRX CAKE IOTA DASH ASTR ROSE KAVA "
              "JASMY RSR").split())
PREVIOUS_QSI_QTRW_QGFW=set(("1INCH CFX XTZ BLUR ZK LPT CHZ GRT BONK "
                             "MASK STX WIF YGG FLOW ZEC ZIL JTO AXS").split())
POLICIES=("quantum_robust_ungated","quantum_interference_ungated",
          "quantum_cost_trend","quantum_cost_high_conf",
          "quantum_interference_cost_trend",
          "classical_ungated","classical_cost_trend",
          "classical_train_frequency_matched")
TRAIN_MIN_FILLS=20
TRAIN_MIN_POSITIVE_DAYS=6
TRAIN_DRAWDOWN_CEIL=25.
MIN_CONF=.20
MIN_EMA_GAP_ATR=.15
MIN_DECEL=-.25
STRESS_BREAK_EVEN_MULT=2.0


def market_catalogue():
    url=API+"/api/v5/public/instruments?"+urlencode({"instType":"SWAP"})
    with urlopen(Request(url,headers={"User-Agent":"TITAN-QFRV-PAPER-NO-ORDERS"}),
                 timeout=40) as h:
        data=json.load(h)
    if data.get("code")!="0":
        raise ValueError("Unverified OKX public market list")
    candidates=[]
    for spec in data.get("data",[]):
        sym=spec.get("instId","")
        if not sym.endswith("-USDT-SWAP"):continue
        coin=sym[:-10]
        if (coin not in UNIVERSE or coin in PREVIOUS_QSI_QTRW_QGFW
            or coin in qsi.EXCLUDED or spec.get("state")!="live"
            or spec.get("ctType")!="linear" or spec.get("ctValCcy")!=coin):
            continue
        try:
            if int(spec["listTime"])>int(time.time()*1000)-90*86400000:
                continue
            vals=(float(spec[k]) for k in ("ctVal","minSz","lotSz"))
            if not all(math.isfinite(v) and v>0 for v in vals):
                continue
        except (TypeError,KeyError,ValueError):
            continue
        candidates.append(spec)
    candidates.sort(key=lambda x:hashlib.sha256(
        (STUDY+"|"+x["instId"]).encode()).hexdigest())
    if len(candidates)<MARKETS*2:
        raise ValueError("Cannot find six preselected genuine new crypto instruments")
    return candidates[MARKETS:2*MARKETS],len(candidates)


def _is_causal_trend(bars,cl,ema_fast,ema_slow,i,side,atr):
    if i<qsi.WARMUP or atr<=0:return False
    # Completed prices at time i only; note i+1 is NEVER accessed.
    if side*(ema_fast[i]-ema_slow[i])<MIN_EMA_GAP_ATR*atr:
        return False
    if side*(cl[i]-cl[i-8])<=0 or side*(cl[i]-cl[i-32])<=0:
        return False
    decel=side*(cl[i]-2*cl[i-8]+cl[i-16])/atr
    return decel>=MIN_DECEL


def _stress_fee_veto(close,atr):
    if not close>0 or not atr>0:return False
    # Theoretical reward-to-fee veto; this is NOT actual orderbook fill alpha.
    theoretical_move=qsi.TAKE_MULT*atr/close
    full_cost=2*(STRESS_FEE+STRESS_SLIPPAGE)+FUNDING_PER_8H*(
        qsi.MAX_HOLD/32)
    return theoretical_move>=STRESS_BREAK_EVEN_MULT*full_cost


def signal_universe(bars):
    validate_frozen(bars)
    raw=qsi.candidate_stream(bars)
    cl=[float(x["close"]) for x in bars]
    ema_fast,ema_slow=ema_series(cl,24),ema_series(cl,96)
    out={k:[] for k in POLICIES}
    out["quantum_robust_ungated"]=list(raw["quantum_phase_robust"])
    out["quantum_interference_ungated"]=list(raw["quantum_interference"])
    out["classical_ungated"]=list(raw["classical_same_features"])
    for old,new in (
        ("quantum_phase_robust","quantum_cost_trend"),
        ("quantum_interference","quantum_interference_cost_trend"),
        ("classical_same_features","classical_cost_trend")):
        for i,side,atr,confidence in raw[old]:
            if (_stress_fee_veto(cl[i],atr) and
                _is_causal_trend(bars,cl,ema_fast,ema_slow,i,side,atr)):
                out[new].append((i,side,atr,confidence))
    out["quantum_cost_high_conf"]=[
        x for x in out["quantum_cost_trend"] if x[3]>=MIN_CONF]
    return out


def _match_frequency(all_signals,train_end):
    qcount=sum(sum(s[0]<train_end for s in t["quantum_cost_trend"])
               for t in all_signals.values())
    ccount=sum(sum(s[0]<train_end for s in t["classical_cost_trend"])
               for t in all_signals.values())
    # Locked on training event counts alone. Avoid any holdout return peeking.
    probability=min(1.,qcount/ccount) if ccount else 0.
    for sym,pols in all_signals.items():
        matched=[]
        for sig in pols["classical_cost_trend"]:
            fingerprint=hashlib.sha256(
                (STUDY+"|"+sym+"|"+str(sig[0])).encode()).digest()
            if int.from_bytes(fingerprint[:8],"big")/2**64<probability:
                matched.append(sig)
        pols["classical_train_frequency_matched"]=matched
    return {"quantum_train_signal_count":qcount,
            "classical_train_signal_count":ccount,
            "classical_train_retention_probability":round(probability,8)}


def paper(markets,specs,votes,*,policy,leverage,start,end,fee,slip):
    if (policy not in POLICIES or leverage not in LEVERAGES or
        set(markets)!=set(specs) or set(markets)!=set(votes)):
        raise ValueError("Malformed public market or locked paper policy")
    choices={}
    for sym in markets:
        for sig in votes[sym][policy]:
            i=sig[0]
            if start<=i and i+1<end:
                choices.setdefault(i,[]).append((sig[3],sym,sig))
    equity=START
    available=start
    trade_rows=[]
    peak=START
    dd=0.
    crossed=None
    for i in sorted(choices):
        if i<available or equity<=RUIN or equity>=TARGET128:continue
        for _,sym,sig in sorted(choices[i],key=lambda z:(-z[0],z[1])):
            trade=qsi.sim_one(markets[sym],sig,specs[sym],equity=equity,
                              leverage=leverage,fee=fee,slip=slip,end=end)
            if trade is None:continue
            equity=trade["equity_after"]
            available=trade["exit_i"]+1
            peak=max(peak,equity)
            dd=max(dd,100*(peak-equity)/peak)
            trade_rows.append(trade)
            if equity>=TARGET128:
                crossed=trade["exit_i"]
            break
        if crossed is not None:break
    days={}
    for trade in trade_rows:
        days[trade["day"]]=days.get(trade["day"],0)+trade["net_usdt"]
    return {
        "trades":len(trade_rows),
        "end_usdt":round(equity,8),
        "return_pct":round(100*(equity/START-1),5),
        "peak_realized_usdt":round(peak,8),
        "hit_128_after_closed_trade":equity>=TARGET128,
        "first_target_exit_i":crossed,
        "hit_ruin_at_any_closed_trade":any(t["equity_after"]<=RUIN
                                           for t in trade_rows),
        "liquidation_proxy_events":sum(
            t["status"]=="liquidation_proxy" for t in trade_rows),
        "max_drawdown_pct":round(dd,4),
        "positive_days":sum(v>0 for v in days.values()),
        "negative_days":sum(v<0 for v in days.values()),
        "fee_total_usdt":round(sum(
            t["entry_fee_usdt"]+t["exit_fee_usdt"] for t in trade_rows),7),
    }


def experiment(markets,specs,*,raw_hashes=None,panel_n=None,stamp_ms=None):
    if len(markets)!=MARKETS or len(specs)!=MARKETS or set(markets)!=set(specs):
        raise ValueError("Precommitted six-market portfolio required")
    if len(set(markets))!=MARKETS or any(
        s[:-10] not in UNIVERSE or s[:-10] in PREVIOUS_QSI_QTRW_QGFW
        for s in markets):
        raise ValueError("Prior-market contamination or wrong crypto panel")
    n=min(len(b) for b in markets.values())
    if n<MIN_BARS:raise ValueError("Incomplete 60-day market")
    aligned=[z["ts"] for z in next(iter(markets.values()))[:n]]
    for sym,bars in markets.items():
        validate_frozen(bars)
        if [z["ts"] for z in bars[:n]]!=aligned:
            raise ValueError("Incompatible UTC candle starts")
    cut=int(n*.6);middle=cut+(n-cut)//2
    bounds={"train":(qsi.WARMUP,cut),"holdout_1":(cut,middle),
            "holdout_2":(middle,n)}
    signals={sym:signal_universe(bars[:n]) for sym,bars in markets.items()}
    frequency=_match_frequency(signals,cut)
    results={}
    for policy in POLICIES:
        for lev in LEVERAGES:
            key=policy+"_"+str(int(lev))+"x"
            period_results={}
            for name,(start,end) in bounds.items():
                period_results[name]={
                    "ordinary":paper(markets,specs,signals,policy=policy,
                                     leverage=lev,start=start,end=end,
                                     fee=TAKER_FEE,slip=BASE_SLIPPAGE),
                    "stress":paper(markets,specs,signals,policy=policy,
                                   leverage=lev,start=start,end=end,
                                   fee=STRESS_FEE,slip=STRESS_SLIPPAGE)}
            results[key]=period_results
    # Training-only selection. No holdout tuning or after-the-fact winner.
    candidates=[key for key,r in results.items() if (
        r["train"]["ordinary"]["trades"]>=TRAIN_MIN_FILLS
        and r["train"]["stress"]["trades"]>=TRAIN_MIN_FILLS
        and r["train"]["ordinary"]["return_pct"]>0
        and r["train"]["stress"]["return_pct"]>0
        and r["train"]["ordinary"]["positive_days"]>=TRAIN_MIN_POSITIVE_DAYS
        and r["train"]["stress"]["max_drawdown_pct"]<=TRAIN_DRAWDOWN_CEIL
        and not r["train"]["stress"]["hit_ruin_at_any_closed_trade"])]
    chosen=(max(candidates,key=lambda k:results[k]["train"]["stress"][
        "return_pct"]) if candidates else None)
    validated=bool(chosen) and all(
        results[chosen][period][mode]["return_pct"]>0 and
        not results[chosen][period][mode]["hit_ruin_at_any_closed_trade"]
        for period in ("holdout_1","holdout_2") for mode in ("ordinary","stress"))
    repeated128=validated and all(
        results[chosen][p][cost]["hit_128_after_closed_trade"]
        for p in ("holdout_1","holdout_2") for cost in ("ordinary","stress"))
    return {
        "study":STUDY,\n        "validation_cohort":"second six of SAME frozen eligible SHA256 rank; no model or threshold tuning",
        "live_quantum_hardware":False,"real_trading":False,
        "source":"60 completed days of PUBLIC OKX 15m crypto USDT swap bars",
        "start_usdt":START,"goal_plus128_usdt":TARGET128,"ruin_usdt":RUIN,
        "new_crypto_markets_data_independent_hash_choice":sorted(markets),
        "eligible_public_markets":panel_n,
        "original_market_sha256":raw_hashes or {},
        "collected_at_utc":datetime.fromtimestamp(stamp_ms/1000,timezone.utc).isoformat() if stamp_ms else None,
        "completed_15m_bars_per_market":n,
        "completed_15m_market_bars_total":n*len(markets),
        "training_only_classical_frequency_control":frequency,
        "candidate_models":len(results),
        "train_eligible":candidates,
        "selected_on_training_only":chosen,
        "selected_holdouts_both_costs_positive":validated,
        "selected_holdouts_both_costs_reached128":repeated128,
        "verdict":("RETROSPECTIVE_STILL_REQUIRES_PROSPECTIVE_REPLICATION"
                   if repeated128 else "NO_TRADE_NO_VERIFIED_REPEATED_128_PERCENT"),
        "no_trade_baseline":{"ending_usdt":START,"return_pct":0.},
        "real_orders_submitted":0,
        "private_user_account_read":False,
        "risk_limitations":[
            "Even a new market panel is a retrospective historical test, not actual unseen future orders",
            "Several earlier TITAN hypotheses were tested; multiple-testing false positives accumulate",
            "10x leveraged SWAP may ruin a 4.15 USDT account and is not a safe recommendation",
            "Current public contract lot/min specifications may differ from historical settings",
            "Ordinary and stress fee/slippage and funding are assumptions, NOT verified OKX fills",
            "Trade OHLC cannot reconstruct mark-price liquidation or intrabar stop order arrival",
            "A 128% goal must never be mistaken for a statistically repeatable expected return"
        ],
        "all_models":results,
    }


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="reports/titan_qfrv_128_original.json")
    p.add_argument("--raw-dir",default="reports/titan_qfrv_128_raw")
    args=p.parse_args(argv)
    stamp=int(time.time()*1000)
    panel,panel_n=market_catalogue()
    print("QFRV LOCKED SECOND REPLICATION COHORT",panel_n,[s["instId"] for s in panel],flush=True)
    markets={};specs={};sha={}
    raw=Path(args.raw_dir);raw.mkdir(parents=True,exist_ok=True)
    for s in panel:
        sym=s["instId"]
        candles=fetch_history(sym,DAYS,now_ms=stamp)
        if len(candles)<MIN_BARS:
            raise ValueError("Required new real price history absent: "+sym)
        payload=json.dumps(candles,separators=(",",":")).encode()
        checksum=hashlib.sha256(payload).hexdigest()
        with gzip.open(raw/(sym+".json.gz"),"wb",compresslevel=6) as h:
            h.write(payload)
        markets[sym]=candles;specs[sym]=s;sha[sym]=checksum
        print("QFRV PUBLIC SHA",sym,len(candles),checksum,flush=True)
    audit=experiment(markets,specs,raw_hashes=sha,panel_n=panel_n,stamp_ms=stamp)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for name,phases in audit["all_models"].items():
        print("QFRV BACKTEST",name,
            "TRAIN",phases["train"]["ordinary"],
            "TRAIN_STRESS",phases["train"]["stress"]["return_pct"],
            "H1",phases["holdout_1"]["ordinary"],
            "H1_STRESS",phases["holdout_1"]["stress"]["return_pct"],
            "H2",phases["holdout_2"]["ordinary"],
            "H2_STRESS",phases["holdout_2"]["stress"]["return_pct"],flush=True)
    print("QFRV FINAL",audit["verdict"],"TRAIN_SELECTED",
          audit["selected_on_training_only"],"NO ORDERS",flush=True)


if __name__=="__main__":
    main()

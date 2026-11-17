#!/usr/bin/env python3
"""Forensic audit: original Q6 131.13655% historical PAPER window, no orders."""
import argparse, gzip, hashlib, json, math
from pathlib import Path
from trading.titan_regime_research import validate_frozen
from trading import titan_q6_convex_tail as q

ORIGINAL_RUN=44057013113
MARKETS={
"1INCH-USDT-SWAP":"bdf1a79ff6c0e00e837e2b3800ae2f4439731965327852cc54de1fda145b6626",
"TIA-USDT-SWAP":"80abd575108c0bb5dc42bacbdbd1facfc35534ba109019ff7fcebabaa74bb389",
"CRV-USDT-SWAP":"3ea6f3b902faa4e27d78afc5a063de1421ef38007bd97e2bdcf881f36dc6a4ad",
"ZIL-USDT-SWAP":"c2152ef7d6d57a1e5ec67612110508213dbf69cb56dfc469960ac4420b174a0d",
"DYDX-USDT-SWAP":"0795238b810e0b8ae5eb53d98f345dbaff205c0f7aea542dfff217f245d7eb4e",
"XTZ-USDT-SWAP":"ae7dbe1752d7814b400d27c79d5ec41b965af8ba1a1908e2aea31f7b01f64c01"}
MODEL="q6_trend_coherent_10x"

def closed_check(row):
    equity=row["closed_equity_usdt"];percent=row["return_pct"]
    trades=row["closed_trades"];hit=row["hit_128_closed"]
    if (type(equity) not in (int,float) or type(percent) not in (int,float)
        or type(trades) is not int or type(hit) is not bool
        or not math.isfinite(equity) or not math.isfinite(percent)
        or equity<0 or trades<0):
        raise ValueError("Invalid closed-paper record")
    if abs((equity/q.START-1)*100-percent)>0.00002:
        raise ValueError("Closed profit arithmetic disagrees with equity")
    if hit != (equity>=q.TARGET):
        raise ValueError("Target flag not supported by closed equity")
    if trades==0 and abs(equity-q.START)>1e-8:
        raise ValueError("Cannot earn from zero closed trades")
    return True

def audit(base):
    base=Path(base)
    report=json.loads((base/"titan_q6_128_results.json").read_text())
    if (report.get("study")!=q.STUDY
        or report.get("sha256")!=MARKETS
        or sorted(report.get("markets",[]))!=sorted(MARKETS)
        or report.get("bars_each")!=8639
        or report.get("total_completed_bars")!=51834
        or report.get("start")!=4.15
        or report.get("target")!=9.462
        or report.get("orders")!=0
        or report.get("quantum_hardware_used") is not False):
        raise ValueError("Report provenance mismatch")
    verified={}
    for market,hash_expected in MARKETS.items():
        with gzip.open(base/"titan_q6_real_market_bars"/(market+".json.gz"),"rb") as handle:
            blob=handle.read()
        if hashlib.sha256(blob).hexdigest()!=hash_expected:
            raise ValueError("Public historical OHLC checksum mismatch "+market)
        bars=json.loads(blob)
        validate_frozen(bars)
        if len(bars)!=8639:raise ValueError("Incomplete actual price history")
        verified[market]=hash_expected
    results=report["results"]
    for model,periods in results.items():
        for period in ("train","holdout_1","holdout_2","holdout_3","combined_untouched"):
            for cost in ("ordinary","stress"):
                closed_check(periods[period][cost])
    ordinary=results[MODEL]["holdout_3"]["ordinary"]
    stress=results[MODEL]["holdout_3"]["stress"]
    if (ordinary["return_pct"]!=131.13655 or stress["return_pct"]!=94.16113
        or ordinary["hit_128_closed"] is not True
        or stress["hit_128_closed"] is not False
        or report.get("selected_train_only") is not None
        or report.get("success_both_costs_three_holdouts") is not False):
        raise ValueError("The initial exploratory finding was misstated")
    return {"original_run":ORIGINAL_RUN,
            "source_data_sha256_verified":verified,
            "real_completed_15m_candles":51834,
            "model":MODEL,"isolated_holdout_3_ordinary":ordinary,
            "isolated_holdout_3_stress":stress,
            "training_stress":results[MODEL]["train"]["stress"],
            "first_holdout_stress":results[MODEL]["holdout_1"]["stress"],
            "combined_holdout_stress":results[MODEL]["combined_untouched"]["stress"],
            "replicated_128":False,"real_orders":0,
            "verdict":"ONE_CHERRY_PICKED_HISTORICAL_131_PERCENT_PAPER_NOT_REPLICATED",
            "limitations":["Archived aggregate results do not include full per-trade fill ledger",
                "Paper fill, liquidation and funding assumptions cannot be fully independently reconstructed",
                "Result is not a real OKX account gain, nor future profit guarantee"]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    report=audit(a.archive)
    target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("Q6 FORENSIC VERIFIED",report["model"],
          "ORDINARY",report["isolated_holdout_3_ordinary"]["return_pct"],
          "CLOSED_PAPER_USDT",report["isolated_holdout_3_ordinary"]["closed_equity_usdt"],
          "STRESS",report["isolated_holdout_3_stress"]["return_pct"],
          "REPLICATED",report["replicated_128"],"NO ORDERS",flush=True)
if __name__=="__main__":main()

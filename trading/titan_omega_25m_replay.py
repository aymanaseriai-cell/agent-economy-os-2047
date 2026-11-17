#!/usr/bin/env python3
"""Offline replay of 432 OMEGA 25M historical paper trials, NO NETWORK."""
import argparse,gzip,hashlib,json
from pathlib import Path
from zipfile import ZipFile
from trading import titan_omega_25m_market as market
from trading import titan_omega_25m_engine as engine

def replay(read):
    original=json.loads(read("omega_25m_report.json"))
    raw=original["source_manifest"]
    if len(raw)!=6:raise ValueError("Incomplete original source manifest")
    bars={};specs={};funding={};hashes={}
    for sym,meta in sorted(raw.items()):
        candle=gzip.decompress(read("omega_25m_original_okx/"+sym+"-original-15m.json.gz"))
        digest=hashlib.sha256(candle).hexdigest()
        if digest!=meta["original_price_ohlcv_sha256"]:
            raise ValueError("Tampered original OKX candle archive: "+sym)
        loaded=[market.decode(row) for row in json.loads(candle)]
        if len(loaded)<market.MIN_BARS or any(x is None for x in loaded):
            raise ValueError("Incomplete true OHLCV "+sym)
        fr=gzip.decompress(read("omega_25m_original_okx/"+sym+"-observed-funding.json.gz"))
        if hashlib.sha256(fr).hexdigest()!=meta["funding_observed_sha256"]:
            raise ValueError("Tampered observed funding "+sym)
        funding_raw=json.loads(fr)
        if len(funding_raw)!=meta["funding_observed_count"]:
            raise ValueError("Missing source funding settlements")
        funding[sym]=[(int(x["fundingTime"]),float(x["realizedRate"]))
                      for x in funding_raw]
        bars[sym]=loaded
        specs[sym]=meta["current_instrument_snapshot"]
        hashes[sym]=digest
    result=engine.study(bars,specs,funding,hashes)
    keys=("all_hypothesis_summaries","development_selected_before_final",
          "focus_score_by_period","focus_curve_closed","focus_final_trade_ledger",
          "week_block_signflip_bonferroni_exploratory",
          "week_bootstrap_95pct_exploratory",
          "highest_retrospective_holdout_NOT_validated","verdict")
    bad=[key for key in keys if result.get(key)!=original.get(key)]
    if bad:raise ValueError("Exact offline replay differs: "+",".join(bad))
    if len(result["all_trial_trades"])!=original["all_candidate_trade_rows_in_gzip"]:
        raise ValueError("Replayed paper trade rows do not match original")
    return {"offline_sha256_verified":True,"all_432_evaluations_replayed":True,
            "matched_fields":list(keys),"verified_markets":hashes,
            "replayed_trade_rows":len(result["all_trial_trades"]),
            "selected_policy":result["development_selected_before_final"],
            "final_return_pct":result["focus_score_by_period"][
                "final_combined"]["net_return_pct"],
            "verdict":result["verdict"],"real_orders":0,
            "future_or_live_profit_proven":False}

def main():
    p=argparse.ArgumentParser()
    x=p.add_mutually_exclusive_group(required=True)
    x.add_argument("--zip",type=Path)
    x.add_argument("--dir",type=Path)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if a.zip:
        with ZipFile(a.zip) as z:result=replay(z.read)
    else:
        result=replay(lambda name:(a.dir/name).read_bytes())
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("OMEGA 25M OFFLINE REPLAY",result["offline_sha256_verified"],
          "432 MATCH",result["all_432_evaluations_replayed"],
          "TRADE ROWS",result["replayed_trade_rows"],
          "FINAL RETURN",result["final_return_pct"],
          "VERDICT",result["verdict"],flush=True)
if __name__=="__main__":main()

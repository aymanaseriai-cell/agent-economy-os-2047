#!/usr/bin/env python3
"""FIRST EDGE 2024 historic SPOT+SWAP CASH CARRY.

NEW info: official monthly OKX historical funding archive + trade/mark/index
verified original 2024 V4 candles + newly fetched true SPOT 2024 4H candles.
This is a CONSUMED-CALENDAR development forensic test, not new blind OOS.

Read-only public exchange. NO account API, leverage changes or real orders.
Cash-and-carry ONLY if long spot is fully PAID and short perp contracts
represent exactly the same base units; funding sign flips, basis exposure,
four taker transactions, spread/slippage and contract minimums counted.
"""
from __future__ import annotations
import argparse,csv,datetime,decimal,gzip,hashlib,io,json,math,statistics,time,zipfile
from collections import defaultdict
from pathlib import Path
from trading import titan_first_edge_sources as sources
from trading import titan_first_edge_cash_carry as carry

D=decimal.Decimal
BASES=("BTC","ETH","SOL")
FOUR_H=14_400_000
START=1704067200000  # 2024-01-01 UTC
END=1735689600000    # 2025-01-01 UTC
EXPECTED=(END-START)//FOUR_H # 2196
START_EQUITY=4.15
COSTS={"base":(.0005,.0002),"stress":(.0015,.0015)} # taker / assumed per-leg slip
HOLDS={"one_funding_interval":1,"seven_days":21}
FAMILY_TEST_BUDGET=2
LEVER=2.
LIQ_PARTICIPATION=.001
NOT_A_BLIND_TEST=True

def sha(raw):return hashlib.sha256(raw).hexdigest()
def year_month(timestamp):
    return datetime.datetime.fromtimestamp(timestamp/1000,datetime.timezone.utc).strftime("%Y-%m")

def get_months(root):
    """Monthly archived actual funding 2024 Jan-Dec, never inferred from mark/index."""
    folder=Path(root)/"funding";folder.mkdir(parents=True,exist_ok=True)
    allrates={};manifest={};requests=[]
    for coin in BASES:
        fam=coin+"-USDT";wanted={f"2024-{m:02d}" for m in range(1,13)}
        files={}
        for begin,end in ((1704067200000,1719791999000),(1719792000000,1735689599000)):
            obj,raw,url=sources.listing("3",fam,"monthly",begin,end)
            name=f"{coin}-funding-query-{begin}.json"
            (folder/name).write_bytes(raw)
            requests.append({"coin":coin,"url":url,"filename":name,"sha256":sha(raw)})
            for block in obj["data"]:
                for detail in block.get("details",[]):
                    for item in detail.get("groupDetails",[]):
                        fname=item.get("filename","")
                        for month in wanted:
                            if fname==f"{coin}-USDT-SWAP-fundingrates-{month}.zip":
                                files[month]=item
        if set(files)!=wanted:
            missing=sorted(wanted-set(files))
            raise ValueError("Fail closed missing 2024 archived funding "+coin+": "+repr(missing))
        events={};monthinfo={}
        for month in sorted(files):
            item=files[month]
            original=sources.safe_archive_zip(item["url"])
            fname=coin+"-"+month+"-official-funding.zip"
            (folder/fname).write_bytes(original)
            with zipfile.ZipFile(io.BytesIO(original)) as z:
                name=z.namelist()[0]
                rawcsv=z.read(name)
                rows=list(csv.DictReader(io.TextIOWrapper(io.BytesIO(rawcsv),encoding="utf-8-sig")))
            if not {"instrument_name","funding_rate","funding_time"}.issubset(rows[0]):
                raise ValueError("Unrecognized true original settlement CSV fields")
            accepted=0
            for row in rows:
                t=int(row["funding_time"]);rate=float(row["funding_rate"])
                if row["instrument_name"]!=coin+"-USDT-SWAP" or not math.isfinite(rate):
                    raise ValueError("Wrong original exchange contract or nonfinite funding")
                if START<=t<END:
                    if t in events and abs(events[t]-rate)>1e-14:
                        raise ValueError("Same historical settlement conflicting")
                    events[t]=rate
                    if year_month(t)==month:accepted+=1
            monthinfo[month]={"zip_file":fname,"zip_sha256":sha(original),
                              "csv_sha256":sha(rawcsv),"source_url":item["url"],
                              "funding_records_claimed_in_month":accepted,
                              "zip_bytes":len(original)}
            print("ORIGINAL_2024_FUNDING",coin,month,accepted,flush=True)
        allrates[coin]=events
        manifest[coin]={"months":monthinfo,"actual_settlement_events":len(events)}
    return allrates,{"coins":manifest,"original_listing_requests":requests,
                     "raw_UTC_source":"funding_time milliseconds from OKX original CSV",
                     "year":"2024"}

def spot_prices(coin,folder):
    """OKX historical candles cursor jumps directly to Jan 2025, NOT 2026."""
    raw={}
    older=END;folder=Path(folder)
    for page in range(32):
        obj,original,url=sources.public("/api/v5/market/history-candles",
            {"instId":coin+"-USDT","bar":"4H","after":str(older),"limit":"100"})
        values=obj["data"]
        if not values:break
        confirmed=[x for x in values if len(x)>=9 and str(x[8])=="1"]
        if not confirmed:break
        earliest=min(int(x[0]) for x in confirmed)
        if earliest>=older:raise ValueError("OKX spot cursor stalled "+coin)
        for row in confirmed:
            stamp=int(row[0])
            if START<=stamp<END:raw[stamp]=row
        if earliest<START:break
        older=earliest
        time.sleep(.04)
    ordered=[raw[t] for t in sorted(raw)]
    if (len(ordered)!=EXPECTED or int(ordered[0][0])!=START or
        int(ordered[-1][0])!=END-FOUR_H or
        any(int(b[0])-int(a[0])!=FOUR_H for a,b in zip(ordered,ordered[1:]))):
        raise ValueError("2024 4H real SPOT candle series incomplete "+coin+" "+str(len(ordered)))
    payload=json.dumps(ordered,separators=(",",":")).encode()
    target=coin+"-SPOT-original-4H-2024.json.gz"
    with gzip.open(folder/target,"wb") as fp:fp.write(payload)
    return {int(x[0]):x for x in ordered},{"file":target,"sha256":sha(payload),
        "rows":len(ordered),"source_endpoint":"/api/v5/market/history-candles",
        "start":START,"end_exclusive":END}

def load_old_v4(file):
    """Consume source-verified historical 2024 perps; zero posthoc selection."""
    price={};specs={}
    with zipfile.ZipFile(file) as z:
        m=json.loads(z.read("v4_original_2023_2025/manifest.json"))
        for coin in BASES:
            sym=coin+"-USDT-SWAP"
            triple={};specs[coin]=m["source_manifest"][sym]["current_spec"]
            for typ in ("trade","mark"):
                raw=gzip.decompress(z.read("v4_original_2023_2025/"+sym+"-"+typ+".json.gz"))
                if sha(raw)!=m["source_manifest"][sym][typ]["sha256"]:
                    raise ValueError("Tampered 2024 original perpetual "+coin)
                arr=json.loads(raw)
                cut={int(row[0]):row for row in arr if START<=int(row[0])<END}
                if len(cut)!=EXPECTED:raise ValueError("Missing 2024 swap/mark original")
                triple[typ]=cut
            price[coin]=triple
    return price,specs

def source_spot_spec_from_first_zip(zfile):
    """Read time-stamped current contract snapshots, NOT 2024 point-in-time spec."""
    with zipfile.ZipFile(zfile) as z:
        manifest=json.loads(z.read("first_edge_original_okx/manifest.json"))
        out={}
        for coin in BASES:
            out[coin]={
                "spot":manifest["instrument_source"]["SPOT"]["symbols"][coin+"-USDT"],
                "swap":manifest["instrument_source"]["SWAP"]["symbols"][coin+"-USDT-SWAP"]}
        return out,manifest["captured_utc_ms"]

def affordable_exact(specs,eq,p_spot,p_swap,fee):
    spot=specs["spot"];sw=specs["swap"]
    try:
        sp_min=D(spot["minSz"]);sp_lot=D(spot["lotSz"])
        sw_min=D(sw["minSz"]);sw_lot=D(sw["lotSz"]);cv=D(sw["ctVal"])
        if sw["ctType"]!="linear" or sw["ctValCcy"]!=spot["baseCcy"]:
            return None
        for j in range(500):
            contracts=carry.ceil_lot(sw_min,sw_lot)+j*sw_lot
            qty=contracts*cv
            if qty<sp_min or not carry.is_quantized(qty,sp_lot):continue
            spot_cash=qty*D(str(p_spot))
            swap_notional=qty*D(str(p_swap))
            # Four taker transactions, conservatively reserve exit fees
            fees=2*D(str(fee))*(spot_cash+swap_notional)
            margin=swap_notional/D(str(LEVER))
            minimum=spot_cash+margin+fees
            if minimum<=D(str(eq)):
                return float(qty),float(contracts),float(minimum)
            # costs only rise with larger quantity, so abort search
            if qty>=sp_min and spot_cash+margin>D(str(eq)):break
    except (KeyError,decimal.InvalidOperation,OverflowError,ValueError):return None
    return None

def locate_events(rates,hold):
    """Signal only past known positive funding; ACTUAL next rates are labels."""
    result=[]
    keys=sorted(rates)
    for t in keys:
        if not rates[t]>0:continue
        entry=t+FOUR_H
        target=t+8*FOUR_H*hold//2 # hold 1: t+16h? intentional correction below
        # One funding interval = next 8h settlement; seven days = 21x8h.
        target=t+8*60*60*1000*hold
        exit_at=target+FOUR_H
        if not START<=entry<exit_at<END:continue
        if target not in rates:continue
        # Historical rates may temporarily go to 4h; don't assume next
        # is necessarily 8h, but all actual settlement events inside
        # exposure are included via real timestamp lookup.
        result.append({"signal_ts":t,"entry_ts":entry,"exit_ts":exit_at,
                       "source_sign_rate":rates[t]})
    return result

def simulate(spot,swap,mark,rates,specs,hold,cost_name,start,end):
    fee,slip=COSTS[cost_name];eq=START_EQUITY;peak=eq;dd=0.;last_exit=0
    results=[];blocked=defaultdict(int)
    candidates=locate_events(rates,hold)
    for record in candidates:
        ts=record["entry_ts"];out=record["exit_ts"]
        if not (start<=ts and out<=end):continue
        if ts<last_exit or eq<=.83:continue
        a=spot.get(ts);b=swap.get(ts);x=spot.get(out);y=swap.get(out)
        previous=spot.get(ts-FOUR_H);prevswap=swap.get(ts-FOUR_H)
        if None in (a,b,x,y,previous,prevswap):
            blocked["missing_original_spot_or_perp_quote"]+=1;continue
        minimum=affordable_exact(specs,eq,float(a[1]),float(b[1]),fee)
        if minimum is None:
            blocked["current_min_spot_swap_lot_or_cash"]+=1;continue
        q,contracts,min_cash=minimum
        # Can't assume tiny orders will fill over available prior candle
        # volume. Both sides separately bounded to 0.1% observed turnover.
        spotquote=float(previous[7]);swapquote=float(prevswap[7])
        if min(spotquote,swapquote)<=0 or max(
             q*float(a[1])/spotquote,q*float(b[1])/swapquote)>.001:
            blocked["historical_quote_volume_cap"]+=1;continue
        # Reject any candidate with a mark-priced short risk proxy barrier
        markseries=[mark[k] for k in range(ts,out,FOUR_H) if k in mark]
        if len(markseries)!=(out-ts)//FOUR_H:
            blocked["missing_intrabar_mark_ohlc"]+=1;continue
        perp_sell=float(b[1])*(1-slip);spot_buy=float(a[1])*(1+slip)
        spot_sell=float(x[1])*(1-slip);perp_buy=float(y[1])*(1+slip)
        liq_barrier=perp_sell*(1+(1/LEVER-.015))
        if any(float(z[2])>=liq_barrier for z in markseries):
            blocked["unverifiable_mark_liquidation_proxy_rejected"]+=1;continue
        # Short swap profits when perp falls, plus long spot PnL.
        basis_no_slip=q*((float(x[1])-float(a[1]))-(float(y[1])-float(b[1])))
        basis_after_slip=q*((spot_sell-spot_buy)-(perp_buy-perp_sell))
        paid_funding=0.;realized_events=[]
        for fundts,rate in rates.items():
            if ts<fundts<out:
                if fundts-FOUR_H not in mark:
                    blocked["missing_true_funding_mark_price"]+=1
                    paid_funding=float("nan");break
                mpx=float(mark[fundts-FOUR_H][4])
                paid_funding+=q*mpx*rate
                realized_events.append((fundts,rate))
        if not math.isfinite(paid_funding):continue
        taker_fee=fee*q*(spot_buy+spot_sell+perp_sell+perp_buy)
        net=basis_after_slip+paid_funding-taker_fee
        neweq=max(0.,eq+net)
        results.append({
            "coin":specs["spot"]["baseCcy"],"entry_ts":ts,"exit_ts":out,
            "previous_funding_rate_known_at_signal":record["source_sign_rate"],
            "position_base_quantity_exact":q,"swap_contracts_exact":contracts,
            "starting_cash_this_trade":eq,"min_cash_reserved_including_fees":min_cash,
            "spot_entry":spot_buy,"spot_exit":spot_sell,"perp_entry":perp_sell,"perp_exit":perp_buy,
            "basis_pnl_before_slippage_USDT":basis_no_slip,
            "basis_pnl_after_slippage_USDT":basis_after_slip,
            "real_observed_settlements_during_hold":len(realized_events),
            "funding_pnl_observed_rate_mark_proxy_USDT":paid_funding,
            "taker_fees_usdt":taker_fee,
            "net_closed_usdt":net,"equity_after":neweq,
            "source_label":"OKX original SPOT + SWAP trade and Mark 4h OHLC and original funding CSV; hypothetical fills"
        })
        eq=neweq;peak=max(peak,eq)
        dd=max(dd,100*(peak-eq)/peak);last_exit=out
    winners=[r["net_closed_usdt"] for r in results if r["net_closed_usdt"]>0]
    losses=[r["net_closed_usdt"] for r in results if r["net_closed_usdt"]<0]
    return {"net_return_pct":100*(eq/START_EQUITY-1),
            "equity_end_usdt":eq,
            "closed_max_dd_pct":dd,"trades":len(results),
            "winners":len(winners),"losers":len(losses),
            "profit_factor":(sum(winners)/abs(sum(losses)) if losses else None),
            "fee_paid_usdt":sum(r["taker_fees_usdt"] for r in results),
            "observed_settled_funding_usdt":sum(r["funding_pnl_observed_rate_mark_proxy_USDT"] for r in results),
            "basis_pnl_before_slip_usdt":sum(r["basis_pnl_before_slippage_USDT"] for r in results),
            "blocked_reasons":dict(blocked),"ledger":results}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--v4-zip",required=True)
    p.add_argument("--first-zip",required=True)
    p.add_argument("--data-dir",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--offline",action="store_true")
    p.add_argument("--compare")
    a=p.parse_args(argv)
    root=Path(a.data_dir);root.mkdir(parents=True,exist_ok=True)
    prev,specs_v4=load_old_v4(a.v4_zip)
    real_specs,asof=source_spot_spec_from_first_zip(a.first_zip)
    if a.offline:
        manifest=json.loads((root/"full_original_manifest.json").read_text())
        rates={}
        for coin in BASES:
            rates[coin]={}
            for month,meta in manifest["funding"]["coins"][coin]["months"].items():
                blob=(root/"funding"/meta["zip_file"]).read_bytes()
                if sha(blob)!=meta["zip_sha256"]:raise ValueError("Tampered 2024 original funding ZIP")
                with zipfile.ZipFile(io.BytesIO(blob)) as z:
                    original=z.read(z.namelist()[0])
                if sha(original)!=meta["csv_sha256"]:raise ValueError("Original CSV tampered")
                for row in csv.DictReader(io.TextIOWrapper(io.BytesIO(original),encoding="utf-8-sig")):
                    t=int(row["funding_time"])
                    if START<=t<END:rates[coin][t]=float(row["funding_rate"])
        spot={}
        for coin in BASES:
            meta=manifest["spot"][coin]
            raw=gzip.decompress((root/"spot"/meta["file"]).read_bytes())
            if sha(raw)!=meta["sha256"]:raise ValueError("Tampered original SPOT OHLC")
            spot[coin]={int(x[0]):x for x in json.loads(raw)}
    else:
        rates,funding_manifest=get_months(root)
        spot={};spotmeta={}
        (root/"spot").mkdir(exist_ok=True)
        for coin in BASES:
            spot[coin],spotmeta[coin]=spot_prices(coin,root/"spot")
            print("ORIGINAL_2024_SPOT",coin,len(spot[coin]),spotmeta[coin]["sha256"],flush=True)
        manifest={"funding":funding_manifest,"spot":spotmeta,
                  "snapshot_spot_swap_asof_ms":asof,
                  "source":"OKX ORIGINAL archived funding + 2024 SPOT/Perp/Mark OHLC",
                  "historical_execution_not_guaranteed":True}
        (root/"full_original_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True))
    report={"protocol":"FIRST_EDGE-CARRY-2-PRECOMMITTED-HORIZONS-2024-DEV-ONLY",
            "original_exchange_year":"2024 (historically CONSUMED V4 calendar)",
            "original_funding_records":{coin:len(rates[coin]) for coin in BASES},
            "original_spot_4h_rows":{coin:len(spot[coin]) for coin in BASES},
            "used_historical_swap_mark_from_V4_sha_verified":True,
            "current_contract_spec_snapshot_ms":asof,
            "horizons":{},"new_unseen_final_return":None,
            "alpha_proven":False,"no_exchange_orders":True}
    split=1719792000000 # 2024-07-01 00:00 UTC, H1 and H2 only DEVELOPMENT
    for horizon,hold in HOLDS.items():
        report["horizons"][horizon]={}
        for case in COSTS:
            report["horizons"][horizon][case]={}
            for coin in BASES:
                for block,(lo,hi) in (("h1",(START,split)),("h2",(split,END))):
                    result=simulate(spot[coin],prev[coin]["trade"],prev[coin]["mark"],
                                    rates[coin],real_specs[coin],hold,case,lo,hi)
                    report["horizons"][horizon][case].setdefault(coin,{})[block]=result
                    print("CARRY DEVELOPMENT",horizon,case,coin,block,
                          "TRADES",result["trades"],
                          "NET",round(result["net_return_pct"],4),
                          "FUND",round(result["observed_settled_funding_usdt"],6),flush=True)
    if a.compare:
        saved=json.loads(Path(a.compare).read_text())
        if report!=saved:raise ValueError("2024 archived original OFFLINE replay mismatch")
        print("FIRST EDGE CARRY ALL-RESULTS OFFLINE EXACT MATCH",flush=True)
    dst=Path(a.out);dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("FIRST EDGE VALIDATED PROSPECTIVE ALPHA",report["alpha_proven"],
          "REAL MONEY ORDERS",not report["no_exchange_orders"],flush=True)

if __name__=="__main__":main()

#!/usr/bin/env python3
"""ZERO ILLUSION: verify exchange ARCHIVED funding/L2 and genuine spot+swap BBO.

No account endpoints, API credentials or order endpoints. Does NOT turn an
old archive into unseen validation. Current BBO/minSz values are only
a current, time-stamped feasibility snapshot, NOT historic executable fills.
"""
from __future__ import annotations
import argparse,datetime,gzip,hashlib,json,time,urllib.parse,urllib.request,zipfile,io,csv
from pathlib import Path
from decimal import Decimal,ROUND_CEILING

COINS=("BTC","ETH","SOL")
ENDPOINT="https://www.okx.com"
ARCHIVE_MODULE_FUNDING="3"
ARCHIVE_MODULE_L2="4"
FROZEN_BUDGET_FUNDING_FILES=3
MAX_ZIP_BYTES=2_500_000
RESEARCH_ID="FIRST-EDGE-ZERO-ILLUSION-ARCHIVE-SPOT-PERP-20261117"

def sha(b):return hashlib.sha256(b).hexdigest()
def utc_ms():return int(time.time()*1000)
def public(path,params):
    url=ENDPOINT+path+"?"+urllib.parse.urlencode(params)
    for i in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"TITAN-RESEARCH-READ-ONLY"})
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read(5_000_000)
            obj=json.loads(raw)
            if obj.get("code")!="0" or not isinstance(obj.get("data"),list):
                raise ValueError("Exchange API returned nonzero code "+str(obj.get("code"))+" "+str(obj.get("msg")))
            return obj,raw,url
        except (ValueError,TimeoutError,OSError) as ex:
            if i==2:raise RuntimeError("Public source unavailable: "+str(ex)) from ex
            time.sleep((i+1)*.6)

def listing(module,family,aggregation,begin,end):
    params={"module":module,"instType":"SWAP","instFamilyList":family,
            "dateAggrType":aggregation,"begin":str(begin),"end":str(end)}
    return public("/api/v5/public/market-data-history",params)

def safe_archive_zip(url):
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!="https" or parsed.hostname!="static.okx.com":
        raise ValueError("Untrusted exchange-archive download destination")
    req=urllib.request.Request(url,headers={"User-Agent":"TITAN-RESEARCH-READ-ONLY"})
    with urllib.request.urlopen(req,timeout=35) as r:
        blob=r.read(MAX_ZIP_BYTES+1)
    if len(blob)>MAX_ZIP_BYTES:raise ValueError("Archive exceeds 2.5 MB budget")
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        raise ValueError("Archive endpoint returned non-ZIP")
    return blob

def run(directory):
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    events={"research_id":RESEARCH_ID,"captured_utc_ms":utc_ms(),
            "historical_archive":"2024 funding and historical L2 metadata are DEVELOPMENT only",
            "archives":[],"instrument_source":{},"bbo_snapshots":{},
            "hypothesis_budget":"ONE proposed new economic mechanism: fully delta-hedged spot-long and perp-short funding carry",
            "not_validated":"2023–2026 dates already consumed; no new prospective OOS data"}
    # 2024 archive funding is NOT the same as the rolling past-90d REST.
    selected=0
    for coin in COINS:
        family=coin+"-USDT"
        for mod,period,lo,hi in (
            (ARCHIVE_MODULE_FUNDING,"monthly",1704067200000,1706745599000),
            (ARCHIVE_MODULE_L2,"daily",1704931200000,1704931200000)):
            record={"coin":coin,"family":family,"module":mod,
                    "dateAggrType":period,"begin":lo,"end":hi}
            try:
                obj,raw,url=listing(mod,family,period,lo,hi)
                key=f"{coin}-module-{mod}-archive-listing.json"
                (root/key).write_bytes(raw)
                record.update({"ok":True,"listing_sha256":sha(raw),
                               "listing_file":key,"source_url":url,
                               "list_return_count":len(obj["data"])})
                groups=[]
                for block in obj["data"]:
                    for det in block.get("details",[]):
                        groups.extend(det.get("groupDetails",[]))
                record["candidate_links"]=[{"file":g.get("filename"),
                                             "MB":g.get("sizeMB"),
                                             "date":g.get("dateTs",g.get("dataTs"))}
                                            for g in groups[:20]]
                record["candidate_count"]=len(groups)
                if mod==ARCHIVE_MODULE_FUNDING and groups and selected<FROZEN_BUDGET_FUNDING_FILES:
                    for entry in groups[:1]:
                        if selected>=FROZEN_BUDGET_FUNDING_FILES:break
                        try:
                            blob=safe_archive_zip(entry["url"])
                            file=f"{coin}-archived-2024-funding.zip"
                            (root/file).write_bytes(blob)
                            files=[]
                            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                                for item in z.infolist()[:10]:
                                    if item.is_dir():continue
                                    if item.file_size>3_000_000:raise ValueError("ZIP expanded file over budget")
                                    raw_csv=z.read(item)
                                    first=raw_csv[:1400].decode("utf-8-sig",errors="replace")
                                    files.append({"name":item.filename,"sha256":sha(raw_csv),
                                                  "bytes":len(raw_csv),
                                                  "first_lines":first.splitlines()[:3]})
                            record["download"]={"file":file,"zip_sha256":sha(blob),
                                                "zip_size":len(blob),"members":files}
                            selected+=1
                        except Exception as err:
                            record["download_error"]=str(err)[:400]
            except Exception as err:
                record.update({"ok":False,"error":str(err)[:400]})
            events["archives"].append(record)
            print("ARCHIVE",coin,"module",mod,"files",record.get("candidate_count"),
                  "downloaded",bool(record.get("download")),"error",record.get("error"),flush=True)
    for typ in ("SPOT","SWAP"):
        try:
            obj,raw,url=public("/api/v5/public/instruments",{"instType":typ})
            file=f"current-{typ}-instruments-original.json"
            (root/file).write_bytes(raw)
            data={e["instId"]:e for e in obj["data"]}
            relevant={coin+(("-USDT") if typ=="SPOT" else "-USDT-SWAP"):
                      data.get(coin+(("-USDT") if typ=="SPOT" else "-USDT-SWAP"))
                      for coin in COINS}
            events["instrument_source"][typ]={"status":"complete","file":file,
                "sha256":sha(raw),"requested_source_url":url,
                "observed_utc_ms":utc_ms(),"symbols":relevant}
        except Exception as err:
            events["instrument_source"][typ]={"status":"error","error":str(err)[:400]}
    for coin in COINS:
        for pair in (coin+"-USDT",coin+"-USDT-SWAP"):
            try:
                obj,raw,url=public("/api/v5/market/books",{"instId":pair,"sz":"5"})
                file=pair+"-book5-original.json"
                (root/file).write_bytes(raw)
                book=obj["data"][0]
                events["bbo_snapshots"][pair]={"file":file,"sha256":sha(raw),
                    "source_url":url,"observed_utc_ms":utc_ms(),
                    "exchange_ts":book.get("ts"),
                    "best_bid":book["bids"][0][:2] if book.get("bids") else None,
                    "best_ask":book["asks"][0][:2] if book.get("asks") else None}
            except Exception as err:
                events["bbo_snapshots"][pair]={"error":str(err)[:400]}
    (root/"manifest.json").write_text(json.dumps(events,indent=2,sort_keys=True)+"\n")
    print("FIRST_EDGE_ARCHIVE_PROBE",json.dumps({
        "historical_funding_downloaded":sum("download" in x for x in events["archives"]),
        "historical_L2_catalogued":sum(x["module"]=="4" and x.get("candidate_count",0)>0 for x in events["archives"]),
        "spot_instruments_ok":events["instrument_source"].get("SPOT",{}).get("status"),
        "swap_instruments_ok":events["instrument_source"].get("SWAP",{}).get("status"),
        "books_ok":sum("best_bid" in s for s in events["bbo_snapshots"].values())
    }),flush=True)
    return events

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out-dir",required=True)
    args=p.parse_args()
    run(args.out_dir)

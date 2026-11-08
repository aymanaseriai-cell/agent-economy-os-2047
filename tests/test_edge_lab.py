import unittest
import gzip
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from trading.edge_lab import (
    BAR_MS, candles_from_api, ema_series, rsi_simple, fetch_history,
    signals, trade_simulation, evaluate, START_EQUITY
)

def make_bars(n=320, *,move=0.01):
    bars=[]
    for i in range(n):
        base=100+i*move
        bars.append({"ts":i*BAR_MS,"open":base,"high":base+1,
                     "low":base-1,"close":base+.25})
    return bars

class TestEdgeLab(unittest.TestCase):
    def test_reject_unfinished_and_malformed(self):
        rows=[["100","1","2",".5","1.2","0","0","0","0"],
              ["200","1","2",".5","1.2","0","0","0","1"],
              ["300","9","2","1","1.2","0","0","0","1"]]
        self.assertEqual([x["ts"] for x in candles_from_api(rows)],[200])

    def test_ema_is_causal(self):
        a=ema_series([1,2,3],9)
        b=ema_series([1,2,3,300],9)
        self.assertEqual(a,b[:3])

    def test_signal_not_using_future_prices(self):
        bars=make_bars(400)
        a=signals(bars,"ema_rsi")
        bars[-1]["close"]=200
        b=signals(bars,"ema_rsi")
        self.assertEqual([x for x in a if x[0]<398],[x for x in b if x[0]<398])

    def test_no_same_bar_entry(self):
        bars=make_bars(110)
        bars[60]={"ts":60*BAR_MS,"open":100,"high":110,"low":90,"close":100}
        bars[61]={"ts":61*BAR_MS,"open":100,"high":100,"low":100,"close":100}
        out=trade_simulation(bars,[(60,1,1.0)],start_index=50,end_index=62)
        self.assertEqual(out["trades"],1)
        self.assertEqual(out["trade_log"][0]["entry_ts"],bars[61]["ts"])

    def test_both_stop_and_target_touch_stop_wins(self):
        bars=make_bars(100,move=0)
        bars[51]={"ts":51*BAR_MS,"open":100,"high":110,"low":90,"close":100}
        out=trade_simulation(bars,[(50,1,1)],start_index=50,end_index=90,fee=0,slip=0,funding=0)
        self.assertEqual(out["trade_log"][0]["outcome"],"stop")
        self.assertLess(out["return_pct"],0)

    def test_stop_gap_fills_worse_than_stop(self):
        bars=make_bars(100,move=0)
        bars[51]={"ts":51*BAR_MS,"open":100,"high":100.5,"low":99.5,"close":100}
        bars[52]={"ts":52*BAR_MS,"open":90,"high":91,"low":89,"close":90}
        out=trade_simulation(bars,[(50,1,1)],start_index=50,end_index=80,fee=0,slip=0,funding=0)
        self.assertEqual(out["trade_log"][0]["outcome"],"stop_gap")
        self.assertEqual(out["trade_log"][0]["exit"],90)

    def test_shorts_also_pay_fees(self):
        bars=make_bars(80,move=0)
        out=trade_simulation(bars,[(50,-1,1)],start_index=50,end_index=80,
                             fee=.0005,slip=0,funding=0)
        self.assertGreater(out["fees_usd"],0)
        self.assertLess(out["net_usd"],out["gross_usd"])

    def test_stress_fees_reduce_return(self):
        bars=make_bars(100,move=0)
        signal=[(50,1,1)]
        base=trade_simulation(bars,signal,start_index=50,end_index=90,fee=0,slip=0,funding=0)
        stress=trade_simulation(bars,signal,start_index=50,end_index=90,fee=.001,slip=.001,funding=.001)
        self.assertLess(stress["return_pct"],base["return_pct"])

    def test_pagination_is_monotone_deduplicated(self):
        now=600*BAR_MS
        def line(i):
            return [str(i*BAR_MS),"100","101","99","100","0","0","0","1"]
        def get(_,q):
            marker=int(q.get("after",now))
            return [line(i) for i in range(marker//BAR_MS-1,marker//BAR_MS-101,-1)]
        # 3-day cutoff and 400 bars available
        out=fetch_history("BTC-USDT-SWAP",4,now_ms=now,get=get,pause=lambda _:None)
        self.assertGreater(len(out),300)
        self.assertEqual(len(set(x["ts"] for x in out)),len(out))

    def test_missing_bars_fail_closed(self):
        now=600*BAR_MS
        def line(i):
            return [str(i*BAR_MS),"100","101","99","100","0","0","0","1"]
        def get(_,q):
            marker=int(q.get("after",now))
            return [line(i) for i in range(marker//BAR_MS-1,marker//BAR_MS-103,-1) if i != 300][:100]
        with self.assertRaisesRegex(ValueError,"Missing 15-minute bars"):
            fetch_history("BTC-USDT-SWAP",4,now_ms=now,get=get,pause=lambda _:None)

    def test_no_private_endpoints(self):
        from trading.edge_lab import get_public
        with self.assertRaises(ValueError):
            get_public("/api/v5/trade/order",{})

    def test_frozen_snapshot_replays_without_market_access(self):
        from trading.edge_lab import main
        with TemporaryDirectory() as folder:
            folder=Path(folder)
            data=make_bars(400)
            with gzip.open(folder/"BTC-USDT-SWAP.candles.json.gz","wt",
                           encoding="utf-8") as out:
                json.dump(data,out,separators=(",",":"))
            output=folder/"result.json"
            with patch.object(sys,"argv",["edge_lab","--days","4",
                                         "--symbols","BTC-USDT-SWAP",
                                         "--offline-dir",str(folder),
                                         "--out",str(output)]):
                with patch("trading.edge_lab.fetch_history",
                           side_effect=AssertionError("Network fetch forbidden")):
                    self.assertEqual(main(),0)
            report=json.loads(output.read_text())
            self.assertEqual(report["data_mode"],"OFFLINE_FROZEN_SNAPSHOT")
            self.assertEqual(report["symbols"]["BTC-USDT-SWAP"]["candles"],400)
            self.assertEqual(len(report["data_sha256"]["BTC-USDT-SWAP"]),64)

    def test_out_of_sample_metrics_present(self):
        data={"BTC-USDT-SWAP":make_bars(400)}
        r=evaluate(data,days=4,timestamp="test")
        self.assertEqual(r["mode"],"OFFLINE_RESEARCH_NO_ORDERS")
        self.assertIn("holdout",r["symbols"]["BTC-USDT-SWAP"]["strategies"]["ema_rsi"])
        self.assertNotIn("trade_log",r["symbols"]["BTC-USDT-SWAP"]["strategies"]["ema_rsi"]["holdout"])
        self.assertIn("holdout_frictionless_diagnostic",
                      r["symbols"]["BTC-USDT-SWAP"]["strategies"]["ema_rsi"])

if __name__=="__main__":
    unittest.main()

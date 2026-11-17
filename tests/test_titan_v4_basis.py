"""V4 regression tests. These fixtures are synthetic and NEVER return evidence."""
import copy,hashlib,math,unittest
from datetime import datetime,timezone
from trading import titan_v4_basis_discovery as alpha
from trading import titan_v4_research as v4

def ms(y):
    return int(datetime(y,1,1,tzinfo=timezone.utc).timestamp()*1000)

def rows(sym,n=75,kind="trade",start=None):
    t=ms(2025) if start is None else start
    out=[]
    for i in range(n):
        p=100+i*.1
        out.append({"symbol":sym,"ts":t+i*v4.BAR_MS,
                    "open":p,"close":p+.1,"high":p+1.,"low":p-1.,
                    "vol_quote":30000. if kind=="trade" else None})
    return out

class V4(unittest.TestCase):
    def test_precommitted_cohort_2023_to_2025_and_goal(self):
        self.assertEqual(v4.EXPECTED,6576)
        self.assertEqual(v4.START_MS,ms(2023))
        self.assertEqual(v4.END_MS,ms(2026))
        self.assertEqual(len(v4.SWAPS),10)
        self.assertEqual(len(alpha.FAMILIES),5)
        self.assertEqual(v4.TARGET,1037504.15)
    def test_original_quote_volume_and_confirm(self):
        t=str(v4.START_MS);s="ADA-USDT-SWAP"
        r=[t,"100","102","99","101","1","1","5000","1"]
        self.assertEqual(v4.parse_exchange_row(r,"trade",s)["vol_quote"],5000.)
        self.assertIsNone(v4.parse_exchange_row(r[:-1]+["0"],"trade",s))
        self.assertEqual(v4.parse_exchange_row([t,"100","102","99","101","1"],"mark",s)["close"],101.)
        self.assertIsNone(v4.parse_exchange_row([t,"100","102","99","101","0"],"mark",s))
    def test_trade_mark_index_alignment_fails_closed(self):
        sym="ADA-USDT-SWAP"
        t=rows(sym);m=rows(sym,kind="mark");i=rows(sym,kind="index")
        self.assertTrue(alpha.features(t,m,i))
        m2=copy.deepcopy(m);m2[0]["ts"]+=v4.BAR_MS
        with self.assertRaises(ValueError):alpha.features(t,m2,i)
    def test_holm_and_exact_month_signflip(self):
        self.assertEqual(alpha.holm({"a":.01,"b":.04,"c":.9})["a"],.03)
        self.assertEqual(alpha.exact_month_signflip({i:1. for i in range(8)}),1/256)
    def test_future_2025_labels_do_not_affect_fitting_or_selection(self):
        samples=[]
        for year in (2023,2024,2025):
            for i in range(2190):
                t=ms(year)+i*v4.BAR_MS
                for sym in ("BTC","ADA","SOL"):
                    samples.append({"sym":sym,"ts":t,"next_ts":t+v4.BAR_MS,
                        "i":i,"y":.002*math.sin(i/5),
                        "feature":{h:.6+.05*math.sin(i/7)
                                   for h in alpha.FAMILIES}})
        original=alpha.fit_train_dev(samples)
        modified=copy.deepcopy(samples)
        for row in modified:
            if alpha.month_start(row["ts"])//100==2025:
                row["y"]=1000.
        self.assertEqual(original,alpha.fit_train_dev(modified))
    def test_min_lot_for_small_account(self):
        self.assertEqual(v4.quantity({"ctVal":"100","lotSz":"1",
                                     "minSz":"1"},4.15,100.,.01),(0.,0.))
    def test_next_bar_high_low_cannot_change_order_size(self):
        name="ADA-USDT-SWAP";origin=ms(2025)
        t=rows(name,75,start=origin);m=rows(name,75,"mark",origin)
        idx=rows(name,75,"index",origin)
        data={name:{"trade":t,"mark":m,"index":idx}}
        spec={name:{"ctVal":"1","lotSz":".001","minSz":".001"}}
        ev={"sym":name,"i":20,"next_ts":t[21]["ts"],
            "signal_ts":t[20]["ts"],"direction":1,"strength":1.}
        a=v4.simulate_event([ev],data,spec,v4.CASES["base"])
        tampered=copy.deepcopy(data)
        tampered[name]["trade"][21]["high"]*=2
        tampered[name]["trade"][21]["low"]*=.5
        b=v4.simulate_event([ev],tampered,spec,v4.CASES["base"])
        self.assertEqual([x["contracts"] for x in a["ledger"]],
                         [x["contracts"] for x in b["ledger"]])
    def test_fixed_momentum_baseline_ignores_last_future_close(self):
        name="ADA-USDT-SWAP";t=rows(name,45,start=ms(2025))
        for i,x in enumerate(t):
            x["close"]=x["open"]*(1+.05*math.sin(i/3))
        triple={name:{"trade":t,"mark":rows(name,45,"mark",ms(2025)),
                       "index":rows(name,45,"index",ms(2025))}}
        a=v4.momentum_control(triple,2025)
        b=copy.deepcopy(triple)
        b[name]["trade"][-1]["close"]*=99
        self.assertEqual(a,v4.momentum_control(b,2025))
    def test_no_mark_index_sources_no_fictitious_alpha(self):
        source={name:{"trade":{"status":"missing"},"mark":{"status":"missing"},
                      "index":{"status":"missing"},"current_spec":None}
                for name in v4.SWAPS}
        report=v4.analyze({}, {}, {"source_manifest":source})
        self.assertTrue(report["final_not_opened"])
        self.assertIsNone(report["alpha_selected"])
    def test_original_sha_and_zero_live_orders(self):
        from pathlib import Path
        self.assertNotEqual(v4.sha(b"some"),v4.sha(b"more"))
        for name in ("titan_v4_basis_discovery.py","titan_v4_research.py"):
            text=(Path(__file__).parents[1]/"trading"/name).read_text()
            self.assertNotIn("/api/v5/trade/order",text)
            self.assertNotIn("OKX_API_KEY",text)

if __name__=="__main__":unittest.main()

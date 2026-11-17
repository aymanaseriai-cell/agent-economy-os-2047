"""TITAN QF128: fail-closed tests for strictly future paper evidence."""
import copy
import math
import unittest
from trading import titan_quantum_forward_128 as f
from trading import titan_quantum_gate as q

def make_history(n=120):
    last=(1800000000000//f.BAR_MS)*f.BAR_MS
    start=last-(n-1)*f.BAR_MS
    rows=[];p=100.
    for i in range(n):
        close=100+i*.015+.2*math.sin(i/13)
        rows.append({"ts":start+i*f.BAR_MS,"open":p,
                     "high":max(p,close)+.4,"low":min(p,close)-.4,
                     "close":close})
        p=close
    return rows,last+f.BAR_MS+5*60_000

class FutureQuantumTests(unittest.TestCase):
    def test_fixed_target_and_models(self):
        self.assertEqual((f.START,f.TARGET),(4.15,9.462))
        self.assertEqual(f.HORIZONS,(4,16))
        self.assertEqual(len(f.SYMBOLS),6)
        self.assertEqual(f.MODELS,("quantum","quantum_zero_phase","classical"))

    def test_same_97_past_candles_for_all_models(self):
        rows,now=make_history()
        result=f.predict(f.complete_window(rows,now))
        self.assertEqual(set(result["signals"]),set(f.MODELS))
        self.assertFalse(result["quantum_hardware_used"])
        self.assertTrue(all(0<=x<=1 for x in result["probabilities"].values()))

    def test_changed_uncompleted_future_cannot_change_prediction(self):
        rows,now=make_history()
        original=f.predict(f.complete_window(rows,now))
        changed=copy.deepcopy(rows)
        changed.append({"ts":rows[-1]["ts"]+f.BAR_MS,"open":100.,
                        "high":200000.,"low":1.,"close":10000.})
        self.assertEqual(original,f.predict(f.complete_window(changed,now)))

    def test_seal_is_before_trade_and_hash_integrity(self):
        rows,now=make_history()
        seal=f.capture(get=lambda *_args,**_kwargs:rows,
                       now_ms=now,run_id="123",sha="abc")
        self.assertTrue(f.verify(seal))
        self.assertGreaterEqual(seal["entry_ms"]-now,f.BAR_MS)
        self.assertEqual([r["symbol"] for r in seal["records"]],list(f.SYMBOLS))

    def test_modified_past_signal_cannot_be_scored(self):
        rows,now=make_history()
        seal=f.capture(get=lambda *_a,**_kw:rows,now_ms=now)
        altered=copy.deepcopy(seal)
        altered["records"][0]["signals"]["quantum"]=-999
        with self.assertRaisesRegex(ValueError,"Seal hash mismatch"):
            f.verify(altered)

    def test_unregistered_cost_rejected_even_after_rehash(self):
        rows,now=make_history()
        seal=f.capture(get=lambda *_a,**_kw:rows,now_ms=now)
        altered=copy.deepcopy(seal)
        altered["costs"]["stress"]=[0.,0.]
        altered["seal_sha256"]=f.digest({k:v for k,v in altered.items()
                                         if k!="seal_sha256"})
        with self.assertRaisesRegex(ValueError,"contract changed"):
            f.verify(altered)

    def test_refuse_scoring_before_future_is_completed(self):
        rows,now=make_history()
        seal=f.capture(get=lambda *_a,**_kw:rows,now_ms=now)
        with self.assertRaisesRegex(ValueError,"not matured"):
            f.score(seal,get=lambda *_a,**_kw:rows,
                    now_ms=seal["mature_ms"]-1)

    def test_no_fake_future_prices(self):
        rows,now=make_history()
        seal=f.capture(get=lambda *_a,**_kw:rows,now_ms=now)
        with self.assertRaisesRegex(ValueError,"future bars incomplete"):
            f.score(seal,get=lambda *_a,**_kw:rows,
                    now_ms=seal["mature_ms"]+1)

    def test_valid_score_uses_frozen_signal_and_zero_live_orders(self):
        rows,now=make_history()
        seal=f.capture(get=lambda *_a,**_kw:rows,now_ms=now,run_id="888")
        expanded=list(rows);price=rows[-1]["close"]
        for t in range(rows[-1]["ts"]+f.BAR_MS,
                       seal["mature_ms"],f.BAR_MS):
            op=price;price=op+.04
            expanded.append({"ts":t,"open":op,"high":price+.2,
                             "low":op-.2,"close":price})
        result=f.score(seal,get=lambda *_a,**_kw:expanded,
                       now_ms=seal["mature_ms"]+1)
        self.assertEqual(result["original_run_id"],"888")
        self.assertFalse(result["verified_real_128"])
        self.assertEqual(result["real_orders"],0)
        self.assertEqual(set(result["results"]),{"4_bars","16_bars"})
        for model in f.MODELS:
            for horizon in ("4_bars","16_bars"):
                for cost in f.COSTS:
                    self.assertIn("paper_equity_usdt",
                                  result["results"][horizon][model][cost])

    def test_stress_cost_always_worse_per_same_trade(self):
        for side in (-1,1):
            normal=f.trade_return(side,100,101,*f.COSTS["ordinary"])
            stressed=f.trade_return(side,100,101,*f.COSTS["stress"])
            self.assertLess(stressed,normal)
            self.assertLess(f.trade_return(side,100,100,*f.COSTS["ordinary"]),0)

    def test_no_signal_no_gain(self):
        self.assertEqual(f.trade_return(0,100,130,*f.COSTS["stress"]),0.)

    def test_reject_gapped_recent_history(self):
        rows,now=make_history()
        removed=rows[:50]+rows[51:]
        with self.assertRaisesRegex(ValueError,"Discontinuous"):
            f.complete_window(removed,now)

    def test_real_order_endpoints_never_in_source(self):
        from pathlib import Path
        source=(Path(__file__).parents[1]/
                "trading/titan_quantum_forward_128.py").read_text()
        self.assertNotIn("OKX_API_KEY",source)
        self.assertNotIn("/api/v5/trade/order",source)

if __name__=="__main__":
    unittest.main()

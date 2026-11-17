"""TITAN Q6 quantum 4h signal with chronological 15m fills: guard tests."""
import copy, math, unittest
from trading import titan_q6_4h_swing_128 as q6
from trading.edge_lab import BAR_MS

def bars(n=16*65):
    out=[];last=100.
    for i in range(n):
        p=100+i*.008+.28*math.sin(i/19)
        out.append({"ts":i*BAR_MS,"open":last,
                    "high":max(last,p)+.12,"low":min(last,p)-.12,
                    "close":p})
        last=p
    return out

class Q6(unittest.TestCase):
    def test_exact_goal_and_never_order(self):
        self.assertEqual((q6.START,q6.TARGET),(4.15,9.462))
        self.assertEqual(q6.LEVERAGES,(3.,10.))
        self.assertEqual(q6.N_MARKETS,6)
        from pathlib import Path
        source=(Path(__file__).parents[1]/"trading/titan_q6_4h_swing_128.py").read_text()
        self.assertNotIn("/api/v5/trade/order",source)
        self.assertNotIn("OKX_API_KEY",source)
    def test_4h_aggregation_uses_exact_16_prior_completed_candles(self):
        series=bars()
        grouped=q6.four_hour_bars(series)
        self.assertEqual(len(grouped),len(series)//16)
        self.assertEqual(grouped[0]["signal_i"],15)
        self.assertEqual(grouped[0]["high"],max(x["high"] for x in series[:16]))
    def test_partial_4h_bar_excluded(self):
        full=bars()
        partial=copy.deepcopy(full)+[{"ts":full[-1]["ts"]+BAR_MS,
            "open":10,"high":10000,"low":1,"close":9999}]
        self.assertEqual(q6.four_hour_bars(full),q6.four_hour_bars(partial))
    def test_untouched_last_candle_cannot_affect_signal(self):
        full=bars();first=q6.causal_signals(full)
        tampered=copy.deepcopy(full)
        tampered[-1]["high"]*=100
        tampered[-1]["close"]=tampered[-1]["high"]
        self.assertEqual(first,q6.causal_signals(tampered))
    def test_models_have_phase_ablations_and_classical_baseline(self):
        r=q6.causal_signals(bars())
        self.assertEqual(set(r),set(q6.POLICIES))
        self.assertIn("q6_zero_phase",r)
        self.assertIn("classical_same_features",r)
    def test_lot_quantization_and_minimum_respected(self):
        spec={"instId":"AXS-USDT-SWAP","state":"live","ctValCcy":"AXS",
              "ctVal":"1","lotSz":".1","minSz":".1"}
        qty,notional=q6.contracts(spec,4.15,2,.05,3)
        self.assertTrue(qty==0 or abs(qty*10-round(qty*10))<1e-7)
        self.assertTrue(notional>=0)
    def test_minimum_exceeding_balance_does_not_fake_fill(self):
        spec={"instId":"AXS-USDT-SWAP","state":"live","ctValCcy":"AXS",
              "ctVal":"1000","lotSz":"1","minSz":"1"}
        qty,notional=q6.contracts(spec,4.15,100,.05,3)
        self.assertEqual((qty,notional),(0.,0.))
    def test_cannot_manufacture_missing_history(self):
        with self.assertRaisesRegex(ValueError,"Exactly six"):
            q6.evaluate({"AXS-USDT-SWAP":bars()},
                         {"AXS-USDT-SWAP":{}},{"AXS-USDT-SWAP":"x"})
    def test_regime_features_are_finite_on_synthetic_past(self):
        s=q6.four_hour_bars(bars())
        closes=[r["close"] for r in s]
        f,a,v=q6.hour_features(s,50,q6.ema_series(closes,9),
                               q6.ema_series(closes,27))
        self.assertEqual(len(f),5)
        self.assertTrue(all(math.isfinite(x) for x in f))
        self.assertGreater(a,0)
        self.assertGreater(v,0)

if __name__=="__main__":unittest.main()

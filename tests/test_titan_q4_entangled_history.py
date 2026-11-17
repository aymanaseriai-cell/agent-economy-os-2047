"""Falsification-first checks: four-qubit math, causal OHLC, no orders."""
import copy
import math
import unittest
from trading import titan_q4_entangled_history as q4
from trading.edge_lab import BAR_MS

def candles(n=480):
    data=[]
    p=100.
    for i in range(n):
        c=100 + .019*i + .23*math.sin(i/13)
        data.append({"ts":i*BAR_MS,"open":p,
                     "high":max(p,c)+.3,
                     "low":min(p,c)-.3,"close":c})
        p=c
    return data

class Q4BacktestTests(unittest.TestCase):
    def test_target_plus128_exact_and_real_lot_engine(self):
        self.assertEqual((q4.START,q4.TARGET,q4.RUIN),(4.15,9.462,.83))
        self.assertEqual(q4.LEVERAGES,(3.,10.))
        self.assertEqual(q4.MARKETS,6)
        self.assertEqual(q4.DAYS,90)
        self.assertTrue(q4.FORBIDDEN.isdisjoint(q4.UNIVERSE))

    def test_four_qubit_unitary_born_probabilities(self):
        for t in (-3,-1,0,1,3):
            for phase in (0.,.7,1.,1.3):
                p=q4.q4_born_probability((t,t/3,-t/2,t/4),phase)
                self.assertTrue(0<=p<=1)

    def test_phase_deletion_is_real_ablation(self):
        x=(1.2,-.9,.45,-.3)
        a=q4.q4_born_probability(x,0.)
        b=q4.q4_born_probability(x,1.)
        self.assertNotAlmostEqual(a,b,places=5)

    def test_classical_same_features_accepts_only_four_finite_inputs(self):
        p=q4.classical_same_inputs((1,2,-3,.2))
        self.assertTrue(0<p<1)
        with self.assertRaises(ValueError):
            q4.classical_same_inputs((math.nan,0,0,0))
        with self.assertRaises(ValueError):
            q4.q4_born_probability((1,2,3))

    def test_future_candle_mutation_cannot_rewrite_signals(self):
        bars=candles()
        original=q4.signal_stream(bars)
        mutated=copy.deepcopy(bars)
        mutated[-1]["close"]=mutated[-1]["high"]
        mutated[-1]["high"]*=1.6
        self.assertEqual(original,q4.signal_stream(mutated))

    def test_policies_and_causal_features(self):
        bars=candles()
        s=q4.signal_stream(bars)
        self.assertEqual(set(s),set(q4.POLICIES))
        self.assertTrue("classical_same_features" in s)
        fast,slow=q4.ema_series([x["close"] for x in bars],24),q4.ema_series(
            [x["close"] for x in bars],96)
        f,atr,ratio=q4.completed_features(bars,224,fast,slow)
        self.assertEqual(len(f),4)
        self.assertTrue(atr>0 and ratio>0)

    def test_invalid_history_fails_closed(self):
        with self.assertRaises(ValueError):
            q4.evaluate({"AR-USDT-SWAP":candles()},
                        {"AR-USDT-SWAP":{}},{"AR-USDT-SWAP":"hash"})

    def test_public_only_no_credentials_or_orders(self):
        from pathlib import Path
        s=(Path(__file__).parents[1]/"trading/titan_q4_entangled_history.py").read_text()
        self.assertNotIn("OKX_API_KEY",s)
        self.assertNotIn("/api/v5/trade/order",s)
        self.assertIn('"selected_on_train_only"',s)

if __name__=="__main__":
    unittest.main()

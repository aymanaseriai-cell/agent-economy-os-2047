"""Conservative OHLC trading and unitary 6-qubit Q6 controls."""
import copy,math,unittest
from trading import titan_q6_convex_tail as x
from trading.edge_lab import BAR_MS

def history(n=450):
    out=[];p=100.
    for i in range(n):
        close=100+i*.03+math.sin(i/9)*.2
        out.append({"ts":i*BAR_MS,"open":p,
                    "high":max(p,close)+.4,
                    "low":min(p,close)-.4,"close":close})
        p=close
    return out

class Q6(unittest.TestCase):
    def test_128_is_exact_goal(self):
        self.assertEqual((x.START,x.TARGET,x.RUIN),(4.15,9.462,.83))
        self.assertEqual(x.LEVERAGES,(3.,10.))
        self.assertEqual(len(x.POLICIES),8)
        self.assertTrue(x.UNIVERSE.isdisjoint(x.EXCLUDE))

    def test_all_phase_settings_unitary_and_finite(self):
        for scale in (-3.,-.6,0.,1.,3.):
            f=tuple(scale/(i+1) for i in range(6))
            for phase in (0.,.6,1.,1.4):
                p=x.q6_probability(f,phase)
                self.assertTrue(0<=p<=1)

    def test_ablation_cuts_entangling_phases(self):
        f=(1.,-.2,.3,.5,-1.2,.9)
        self.assertGreater(abs(x.q6_probability(f,1.) -
                               x.q6_probability(f,0)),1e-6)

    def test_matched_classical_features(self):
        self.assertTrue(0<x.classical_same_features((0,1,-1,.2,.5,-.2))<1)
        with self.assertRaises(ValueError):
            x.q6_probability((0,1,2))
        with self.assertRaises(ValueError):
            x.classical_same_features((math.inf,0,0,0,0,0))

    def test_no_future_last_bar_leakage(self):
        bars=history()
        orig=x.signals(bars)
        changed=copy.deepcopy(bars)
        changed[-1]["high"]*=100
        changed[-1]["close"]=changed[-1]["high"]
        self.assertEqual(orig,x.signals(changed))

    def test_stop_and_liquidation_first_on_ambiguous_candle(self):
        bars=history()
        # make entry candle touch both adverse liquidation and a hypothetical
        # favorable high; liquidations must be counted first for long.
        spec={"instId":"BONK-USDT-SWAP","state":"live",
              "ctType":"linear","ctValCcy":"BONK",
              "ctVal":"0.01","lotSz":"0.1","minSz":"0.1"}
        candles=copy.deepcopy(bars)
        j=225;initial=candles[j]["open"]
        candles[j]["low"]=initial*.5
        candles[j]["high"]=initial*1.5
        candles[j]["close"]=initial
        outcome=x.paper_one(candles,(224,1,1.,.4),spec,equity=4.15,
                            leverage=3.,fee=.0005,slip=.0003,end=270)
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome["status"],"liquidation_proxy")
        self.assertLess(outcome["equity_after"],4.15)

    def test_invalid_universe_fails_closed(self):
        with self.assertRaises(ValueError):
            x.evaluate({"BONK-USDT-SWAP":history()},
                       {"BONK-USDT-SWAP":{}},{"BONK-USDT-SWAP":"a"})

    def test_no_order_access(self):
        from pathlib import Path
        path=Path(__file__).parents[1]/"trading/titan_q6_convex_tail.py"
        text=path.read_text()
        self.assertNotIn("OKX_API_KEY",text)
        self.assertNotIn("/api/v5/trade/order",text)
        self.assertIn('"selected_train_only"',text)

if __name__=="__main__":
    unittest.main()
